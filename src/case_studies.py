"""
case_studies.py
Reads company engineering blogs and keeps the posts about AI running in real products,
for the Case studies pages.

For each new post, Groq decides whether it explains how the company built an AI system (not a launch, research or event post), which problem and
topic it is about (case_sources.TOPICS), picks 1-3 technique tags (case_sources.TAGS), and
writes a sentence or two in our own words on what was built and how, plus the result the post reports. Posts that look LLM-related are asked about first.
Without Groq, a keyword fallback sorts posts and the summary is left empty: the site never
shows the blog's own text as ours.

Writes data/cases.json. It reads the blogs once a week: the Case studies workflow
(.github/workflows/case-studies.yml) runs it early on Monday, and the daily edition only builds
the pages from the posts already saved. A second run in the same week (a rerun, a manual run)
does nothing, because cases.json remembers the day of the last read ("last_fetch").
Posts left over when the week's Groq calls run out are saved in "queue" and sorted first next week.
To read the blogs again now anyway:  python src/case_studies.py --now
To move the saved posts onto today's categories (keywords only, no Groq calls):
  python src/case_studies.py --recategorize
The same Groq call also tags each post for the case study finder (techniques, industry,
build_details, build_score; see FINDER_FIELDS; the category is the post's "problem" topic). Saved posts without those fields are tagged with
the week's spare calls. To tag every saved post that has none yet (one Groq call each, resumable):
  python src/case_studies.py --retag            (add --all to tag every post again)
To store a page address (slug) on every saved post that has none (no network, no Groq):
  python src/case_studies.py --slugs
To grow the Case studies page to a number of write-ups (one Groq call per candidate, resumable;
see backfill()):  python src/case_studies.py --backfill [--dry-run] [--target 520] [--max-calls 200]
A feed that is down is skipped; the posts already saved stay.
"""
import html
import unicodedata
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SRC_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from case_sources import (BUILD_DETAILS, CUSTOMER_BLOGS, EXTRA_FEEDS, FOCUS_WORDS, INDUSTRIES, MAX_TECHNIQUES, SOURCES,
                          TAG_NAMES, TAGS, TECHNIQUES, TOPIC_RULES, TOPICS,
                          category_norm, match_category, split_agents, topic_of)

CASES_FILE = os.path.join(ROOT_DIR, "data", "cases.json")
MAX_POSTS = 800          # oldest posts drop off past this
MAX_AGE_DAYS = 400       # posts older than this are not added
MAX_GROQ_CALLS = int(os.environ.get("CASES_MAX_GROQ", "").strip() or 150)  # per weekly run, to stay inside the free tier
GROQ_PAUSE = 8           # seconds to wait after a failed call, so a rate limit can clear
MAX_PER_BLOG = 6         # Groq calls per blog per run, so every blog gets a turn
MAX_REJECTED = 6000      # posts Groq said are not about AI in production, remembered so they are not asked again
MAX_QUEUE = 400          # posts waiting for next week's Groq calls, newest kept
IST = timezone(timedelta(hours=5, minutes=30))
USER_AGENT = "AIPapersDaily/1.0 (+https://omen-bit.github.io/ai-paper-daily/)"

# A post has to mention one of these to be worth asking Groq about
_AI_WORDS = re.compile(
    r"\b(machine learning|ml|ai|llms?|large language models?|genai|generative|neural|deep learning|"
    r"models?|embeddings?|transformers?|recommend\w*|ranking|personali[sz]\w*|retrieval|rag|"
    r"agents?|agentic|inference|training|fine-?tun\w*|classif\w*|predict\w*|forecast\w*|"
    r"computer vision|vision|ocr|search relevance|semantic search|vector|gpu)\b", re.I)

_TAG = re.compile(r"<[^>]+>")


def clean_text(raw: str, limit: int = 900) -> str:
    """Plain text from a feed summary: no tags, no entities, single spaces."""
    text = html.unescape(_TAG.sub(" ", raw or ""))
    text = " ".join(text.split())
    return text[:limit]


def _date(entry) -> str:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            try:
                return datetime(*value[:6], tzinfo=timezone.utc).strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                pass
    return ""


def normalise_url(url: str) -> str:
    """One address per post: no tracking query, no trailing slash, https, a lowercase host."""
    url = (url or "").strip()
    url = re.sub(r"[?#].*$", "", url)
    url = re.sub(r"^http://", "https://", url, flags=re.I)
    url = re.sub(r"^https://[^/]+", lambda m: m.group(0).lower(), url)
    return url.rstrip("/")


def title_key(title: str, company: str = "") -> str:
    """A company's title reduced to its words, so the same post under two addresses (a Medium link
    and the blog's own domain, say) is caught as one. Two blogs may share a plain title, so the
    company is part of the key."""
    words = " ".join(re.sub(r"[^a-z0-9]+", " ", html.unescape(title or "").lower()).split())
    return f"{company.lower()}|{words}" if words else ""


def feeds_of(name: str, feed: str) -> list[str]:
    """Every feed read for a source: its own, plus any second blog in EXTRA_FEEDS."""
    return [feed] + EXTRA_FEEDS.get(name, [])


def parse_feed(content: bytes, company: str) -> list[dict]:
    """Posts from one feed's raw bytes: url, title, date and the blog's own summary (for sorting only)."""
    import feedparser
    feed = feedparser.parse(content)
    posts = []
    for entry in feed.entries:
        url = normalise_url(entry.get("link", ""))
        title = clean_text(entry.get("title", ""), 300)
        if not url.startswith("https://") or not title:
            continue
        body = entry.get("summary", "")
        if not body and entry.get("content"):
            body = entry["content"][0].get("value", "")
        posts.append({"url": url, "company": company, "title": title, "published": _date(entry),
                      "text": clean_text(body)})
    return posts


def fetch_feed(url: str, timeout: int = 20) -> bytes:
    import requests
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    return resp.content


_PARA = re.compile(r"<p[\s>].*?</p>", re.S | re.I)


def article_text(page_html: str, limit: int = 2500) -> str:
    """The opening paragraphs of a blog post page, as plain text, for Groq to read. Never shown."""
    page_html = re.sub(r"<(script|style|nav|header|footer|aside)\b.*?</\1>", " ", page_html or "", flags=re.S | re.I)
    main = re.search(r"<article\b.*?</article>", page_html, re.S | re.I) or re.search(r"<main\b.*?</main>", page_html, re.S | re.I)
    scope = main.group(0) if main else page_html
    paras = [clean_text(p, 2000) for p in _PARA.findall(scope)]
    text = " ".join(p for p in paras if len(p.split()) >= 6)
    return text[:limit]


def read_article(url: str) -> str:
    """Open a post once and return its opening text, or "" when the page cannot be read."""
    try:
        import requests
        resp = requests.get(url, timeout=15, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        return article_text(resp.text)
    except Exception as exc:
        print(f"  [cases] Could not read {url[:70]} ({str(exc)[:60]})")
        return ""


def looks_like_ai(post: dict) -> bool:
    return bool(_AI_WORDS.search(f"{post['title']} {post.get('text', '')}"))


def rule_sort(post: dict) -> str | None:
    """A topic from keywords, title first then the opening text, or None when nothing matches."""
    for text in (post["title"].lower(), post.get("text", "")[:400].lower()):
        for topic, pattern in TOPIC_RULES:
            if re.search(pattern, text):
                return topic
    return None


def is_focus(post: dict) -> bool:
    return bool(re.search(FOCUS_WORDS, f"{post['title']} {post.get('text', '')[:600]}", re.I))


MAX_TAGS = 3


def rule_tags(post: dict) -> list[str]:
    """Up to MAX_TAGS technique tags from keywords in the title first, then the text."""
    title, text = post["title"].lower(), f"{post.get('text', '')[:600]} {post.get('summary', '')}".lower()
    tags = [t for t, pattern in TAGS if re.search(pattern, title)]
    tags += [t for t, pattern in TAGS if t not in tags and re.search(pattern, text)]
    return tags[:MAX_TAGS]


GROQ_PROMPT = """You pick engineering blog posts for a site that shows how companies build AI into their
products: how they built a RAG system, an agent, a recommender, an evaluation setup, and so on.

Topics:
{topics}

Reply with JSON only:
{{"kind": "<kind>", "topic": "<key>", "new_topic": "<short name or empty>", "issue": "<one sentence>", "summary": "<one or two sentences>", "result": "<short phrase or empty>", "tags": ["<tag>", ...], "customer": "<company name or empty>", {finder_json}}}

kind is one of:
- build: the company explains how it built, trained, served, tested or improved an AI or machine
  learning system that it runs in its own product or its own work, with some detail of how it works.
- launch: a product or feature announcement, release notes, a new version or "now available".
- research: a research result, paper or model that the post does not say is running in a product.
- event: a talk, conference, meetup or webinar recap.
- other: culture, hiring, opinion, advice, an operating model or a security notice, with no concrete system.
On a cloud provider's blog (AWS, Google Cloud), a post in which a named customer company
explains how it built its own AI system on that cloud is build too, and customer is that
company's name (for example "Booking.com"). Otherwise customer is empty.
Only build posts are kept, so when unsure between build and another kind, pick the other kind.
topic is the one key the post is mainly about. Prefer the specific LLM topics (rag, evals, cost,
tuning, safety, and the agent topics) over llm when one fits: a post about making an LLM cheaper or
faster is cost, a post about testing answer quality is evals. For a post about agents, pick the
narrower agent topic (coding, data, ops, support, platforms) when one fits; use agents only when
none of them does.
new_topic is empty in most replies. Only when none of the topics fits the post well, give a new
category name of 2 or 3 words in sentence case, like the topic names above (for example "Voice
agents" or "Document processing"); topic is then still the closest key.
Write issue and summary for someone new to AI: simple everyday words, short sentences, no
jargon (or explain it in a few words), in your own words (never copy the post's sentences),
and never start with the company name.
issue is the problem the company was trying to solve, in at most 20 words, as its users or
team felt it (for example "Hotel partners kept asking support the same setup questions,
which slowed down their sign-up").
summary is how they solved it, in at most 30 words: what they built and how it works.
result is the outcome the post reports, in at most 10 words, with its number when the post gives
one (for example "Support tickets resolved 30% faster"). Leave it empty when the post reports none;
never guess one.
tags are 1 to 3 techniques the system uses, the most specific first, chosen only from this list:
{tags}
{finder_rules}"""

# The case study finder's fields, asked for in the same call (GROQ_PROMPT) or alone (TAG_PROMPT)
FINDER_FIELDS = ("techniques", "industry", "build_details", "build_score")
FINDER_JSON = ('"techniques": ["<key>", ...], "industry": "<key>", '
               '"build": {' + ", ".join(f'"{k}": true|false' for k in BUILD_DETAILS) + "}")
FINDER_RULES = (f"techniques are 1 to {MAX_TECHNIQUES} keys from this list, the main one first:\n"
                + "\n".join(f"- {k}: {about}" for k, about in TECHNIQUES.items())
                + "\nindustry is the company's industry (for a customer story, the customer's), one of: "
                + ", ".join(INDUSTRIES)
                + "\nbuild says, for each item, whether the post itself describes it (true) or not (false);"
                + " when unsure, false:\n"
                + "\n".join(f"- {k}: {about}" for k, about in BUILD_DETAILS.items()))

TAG_PROMPT = """You tag engineering blog posts about AI systems that companies run in their products.
Reply with JSON only:
{{{finder_json}}}
{finder_rules}"""

# Titles that are never a write-up about how something was built, turned down without asking Groq
NOT_A_BUILD = re.compile(
    r"now (generally )?available|\brelease notes?\b|\brelease\s*$|security release|what we heard|"
    r"everything we talked|key takeaways|\brecap\b|\bwebinar\b|join us|we.re hiring|meet the team|"
    r"\bchangelog\b|\bnewsletter\b", re.I)
VERSION = 3  # posts sorted under an older prompt are sorted again, so they get a result and a kind
CAT_VERSION = 2  # sorted with the agent topics and new categories; older "agents" posts are split by keywords


def _topics_text() -> str:
    return "\n".join(f"- {k}: {name}. {about}" for k, (name, about) in TOPICS.items())


_TRUE = {"true", "yes", "y", "1"}


def _key_of(value, allowed) -> str:
    """value as one of the allowed keys (case, spaces and "&" forgiven), or "" when it is none of them."""
    text = re.sub(r"[\s_/&]+", "-", str(value or "").strip().lower()).strip("-")
    text = re.sub(r"-+", "-", text.replace("-and-", "-"))
    return text if text in allowed else ""


def parse_finder(data) -> dict | None:
    """The finder fields from a reply's JSON, checked against the fixed lists: unknown values are
    dropped, "other" fills an empty technique list or industry, and build_score is the
    number of build details the post describes (0-5). None when the reply has none of the fields,
    so the post is tagged again later."""
    if not isinstance(data, dict) or not any(k in data for k in ("techniques", "industry", "build")):
        return None
    raw = data.get("techniques")
    raw = raw if isinstance(raw, list) else [raw] if isinstance(raw, str) else []
    techniques = []
    for t in raw:
        key = _key_of(t, TECHNIQUES)
        if key and key not in techniques:
            techniques.append(key)
    if len(techniques) > 1 and "other" in techniques:
        techniques.remove("other")
    techniques = techniques[:MAX_TECHNIQUES] or ["other"]
    industry = _key_of(data.get("industry"), INDUSTRIES) or "other"
    build = data.get("build") if isinstance(data.get("build"), dict) else {}
    details = {}
    for k in BUILD_DETAILS:
        v = build.get(k)
        details[k] = (v is True or (isinstance(v, (int, float)) and not isinstance(v, bool) and v == 1)
                      or (isinstance(v, str) and v.strip().lower() in _TRUE))
    score = max(0, min(len(BUILD_DETAILS), sum(details.values())))
    return {"techniques": techniques, "industry": industry,
            "build_details": details, "build_score": score}


def _reply_json(raw: str):
    match = re.search(r"\{.*\}", raw or "", re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def parse_reply(raw: str) -> dict | None:
    """The classification from a Groq reply, or None when it is unusable."""
    data = _reply_json(raw)
    if data is None:
        return None
    if str(data.get("kind", "")).strip().lower() != "build":
        return {"keep": False}
    topic = str(data.get("topic", "")).strip().lower()
    if topic not in TOPICS:
        return None
    summary = " ".join(str(data.get("summary", "")).split())
    if len(summary.split()) > 45:
        summary = ""
    by_lower = {t.lower(): t for t in TAG_NAMES}
    raw_tags = data.get("tags") if isinstance(data.get("tags"), list) else []
    tags = []
    for t in raw_tags:
        name = by_lower.get(str(t).strip().lower())
        if name and name not in tags:
            tags.append(name)
    result = " ".join(str(data.get("result") or "").split()).rstrip(".")
    if len(result.split()) > 14 or result.lower() in ("none", "n/a", "not stated", "unknown"):
        result = ""
    issue = " ".join(str(data.get("issue") or "").split())
    if not issue or len(issue.split()) > 30:
        return None  # every card shows the problem, so a reply without one is asked again on the next run
    customer = " ".join(str(data.get("customer") or "").split())[:60]
    if customer.lower() in ("none", "n/a", "empty", "unknown"):
        customer = ""
    new_topic = str(data.get("new_topic") or "").strip()
    category = ""
    if new_topic:
        key, name = match_category(new_topic)
        if key:  # the "new" name is one of the topics (or a synonym of one): use that topic
            topic = key
        category = name
    out = {"keep": True, "topic": topic, "issue": issue, "summary": summary, "result": result, "tags": tags[:MAX_TAGS]}
    if customer:
        out["customer"] = customer
    if category:
        out["category"] = category
    finder = parse_finder(data)
    if finder:
        out["finder"] = finder
    return out


def groq_sort(post: dict) -> dict | None:
    """Ask Groq about one post. None when Groq is unavailable or the reply is unusable."""
    try:
        import groq_summarizer as gs
        client = gs._get_client()
        models = gs._active_models or gs._resolve_active_models()
        gs._active_models = models
    except Exception as exc:
        print(f"  [cases] Groq unavailable ({str(exc)[:80]})")
        return None
    user = f"Company: {post['company']}\nTitle: {post['title']}\nPost start: {post.get('text', '')[:2500]}"
    for model in models[:2]:
        try:
            response = client.chat.completions.create(
                model=model, temperature=0.2,
                messages=[{"role": "system", "content": GROQ_PROMPT.format(
                              topics=_topics_text(), tags=", ".join(TAG_NAMES),
                              finder_json=FINDER_JSON, finder_rules=FINDER_RULES)},
                          {"role": "user", "content": user}],
                **gs.call_options(model, 600))
            result = parse_reply(response.choices[0].message.content)
            if result:
                return result
        except Exception as exc:
            if "429" in str(exc):
                time.sleep(4)
            print(f"  [cases] Groq error on {model}: {str(exc)[:100]}")
    return None


TAG_PAUSE = float(os.environ.get("CASES_TAG_PAUSE", "").strip() or 6)  # seconds between tagging calls
MAX_TAG_CALLS = int(os.environ.get("CASES_MAX_TAG", "").strip() or 40)  # weekly run: saved posts tagged per run


class GroqOutOfCalls(Exception):
    """Every model has hit its daily limit (or Groq is not set up): stop tagging and save."""


def _retry_after(error: str) -> float:
    """Seconds Groq asks us to wait in a 429 message ("try again in 1m7.5s"), 20 when it does not say."""
    m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", error)
    if not m or not any(m.groups()):
        return 20.0
    h, mins, secs = (float(g) if g else 0.0 for g in m.groups())
    return h * 3600 + mins * 60 + secs


def needs_tags(post: dict) -> bool:
    return not all(k in post for k in FINDER_FIELDS)


_TIRED: set = set()  # models out of calls for today, in this run


def groq_tag(post: dict, sleep=time.sleep, tries: int = 4) -> dict | None:
    """The finder fields for one saved post, in one Groq call (TAG_PROMPT), with waits on rate limits.
    None when the reply is unusable. Raises GroqOutOfCalls when no model has calls left today."""
    system = TAG_PROMPT.format(finder_json=FINDER_JSON, finder_rules=FINDER_RULES)
    user = (f"Company: {post['company']}\nTitle: {post['title']}\n"
            f"Problem: {post.get('issue', '')}\nSolution: {post.get('summary', '')}\n"
            f"Post: {post.get('text', '')[:3500]}")
    return parse_finder(_reply_json(groq_call(system, user, 250, 0.1, sleep, tries)))


def groq_sort_paced(post: dict, sleep=time.sleep, tries: int = 4) -> dict | None:
    """groq_sort for the backfill: the same prompt and reply (sorting plus the finder tags), but it
    waits out rate limits and raises GroqOutOfCalls at the daily limit instead of giving up."""
    system = GROQ_PROMPT.format(topics=_topics_text(), tags=", ".join(TAG_NAMES),
                                finder_json=FINDER_JSON, finder_rules=FINDER_RULES)
    user = f"Company: {post['company']}\nTitle: {post['title']}\nPost start: {post.get('text', '')[:2500]}"
    return parse_reply(groq_call(system, user, 600, 0.2, sleep, tries))


def groq_call(system: str, user: str, max_tokens: int, temperature: float, sleep=time.sleep, tries: int = 4) -> str:
    """One Groq chat call on the first model with calls left, waiting as long as Groq asks on a rate
    limit and moving to the next model at a daily limit. The reply text, or "" when it failed.
    Raises GroqOutOfCalls when Groq is not set up or every model is out of calls for today."""
    import groq_summarizer as gs
    try:
        client = gs._get_client()
        models = gs._active_models or gs._resolve_active_models()
        gs._active_models = models
    except Exception as exc:
        raise GroqOutOfCalls(str(exc)[:120])
    for _ in range(tries):
        live = [m for m in models[:2] if m not in _TIRED]
        if not live:
            raise GroqOutOfCalls("every model is at its daily limit")
        model = live[0]
        try:
            response = client.chat.completions.create(
                model=model, temperature=temperature,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                **gs.call_options(model, max_tokens))
            return response.choices[0].message.content or ""
        except Exception as exc:
            error = str(exc)
            if gs._is_auth_error(error):
                raise GroqOutOfCalls(error[:120])
            if "429" in error or "rate limit" in error.lower():
                if re.search(r"per day|\(TPD\)|\(RPD\)", error, re.I):
                    print(f"  [cases] {model} is at its daily limit")
                    _TIRED.add(model)
                    continue
                wait = min(_retry_after(error) + 1, 120)
                print(f"  [cases] Rate limited on {model}; waiting {wait:.0f}s")
                sleep(wait)
                continue
            print(f"  [cases] Groq error on {model}: {error[:100]}")
            sleep(GROQ_PAUSE)
    return ""


def tag_posts(posts: list[dict], tagger=None, reader=None, max_calls: int | None = None,
              everything: bool = False, sleep=time.sleep, on_progress=None) -> dict:
    """Add the finder fields to saved posts that have none (every post when everything is True),
    one Groq call each, newest first. Changes posts in place; the Problem/Solution text is never
    touched. on_progress() is called every 10 tagged posts, so a long run can save as it goes.
    Returns {"tagged", "failed", "left"}."""
    tagger = tagger or (lambda p: groq_tag(p, sleep=sleep))
    todo = [p for p in posts if everything or needs_tags(p)]
    todo.sort(key=lambda p: p.get("published") or "", reverse=True)
    counts = {"tagged": 0, "failed": 0, "left": 0}
    for n, post in enumerate(todo):
        if max_calls is not None and n >= max_calls:
            counts["left"] = len(todo) - n
            break
        if n:
            sleep(TAG_PAUSE)
        text = (reader(post["url"]) if reader else "") or ""
        try:
            fields = tagger({**post, "text": text})
        except GroqOutOfCalls as exc:
            print(f"  [cases] Tagging stopped: {exc}")
            counts["left"] = len(todo) - n
            break
        if fields:
            post.update(fields)
            counts["tagged"] += 1
            if on_progress and counts["tagged"] % 10 == 0:
                on_progress()
        else:
            counts["failed"] += 1
    return counts


def load_all(path: str = CASES_FILE) -> dict:
    """The whole file: posts, the urls already rejected, and how many posts are waiting for Groq."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load(path: str = CASES_FILE) -> list[dict]:
    return load_all(path).get("posts", [])


def save(posts: list[dict], path: str = CASES_FILE, rejected=(), waiting: int = 0,
         last_fetch: str = "", queue=()) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    posts = sorted(posts, key=lambda p: (p.get("published") or "", p["url"]), reverse=True)[:MAX_POSTS]
    queue = sorted(queue, key=lambda p: p.get("published") or "", reverse=True)[:MAX_QUEUE]
    queue = [{k: p.get(k, "") for k in ("url", "company", "title", "published", "text")} for p in queue]
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"last_fetch": last_fetch, "posts": posts, "waiting": waiting, "queue": queue,
                   "rejected": sorted(rejected)[-MAX_REJECTED:]},
                  f, ensure_ascii=False, indent=1)
        f.write("\n")


def interleave(fetched: list[dict]) -> list[dict]:
    """Newest post of every blog first, then the second newest of each, and so on,
    so a busy blog cannot use up the run's Groq calls before the others get a turn.
    LLM-looking posts go before the rest, since those are the site's focus."""
    by_blog: dict[str, list[dict]] = {}
    for post in fetched:
        by_blog.setdefault(post["company"], []).append(post)
    queues = [sorted(v, key=lambda p: p.get("published") or "", reverse=True) for v in by_blog.values()]
    out = []
    for i in range(max((len(q) for q in queues), default=0)):
        out += [q[i] for q in queues if i < len(q)]
    return [p for p in out if is_focus(p)] + [p for p in out if not is_focus(p)]  # LLM posts first


def recategorize(post: dict, known: dict[str, str] | None = None) -> dict:
    """A saved post moved onto today's categories, by keywords only (no Groq, no network):
    a post filed under the old catch-all "agents" goes to the narrower agent topic its words point
    to, and a proposed category name is merged with the same name spelled another way (known maps
    normal form -> display name, and is filled in as names are seen)."""
    post = dict(post)
    if post.get("problem") == "agents" and post.get("cat") != CAT_VERSION:
        post["problem"] = split_agents(post)
        post["cat"] = CAT_VERSION
    if post.get("category"):
        key, name = match_category(post["category"], known)
        if key:
            post["problem"] = key
        if name and known is not None:
            known.setdefault(category_norm(name), name)
        if name:
            post["category"] = name
        else:
            post.pop("category", None)
    return post


def known_categories(posts: list[dict]) -> dict[str, str]:
    """The proposed category names already saved: normal form -> the name saved first."""
    known: dict[str, str] = {}
    for p in sorted(posts, key=lambda p: (p.get("added") or p.get("published") or "", p.get("url", ""))):
        if p.get("category"):
            known.setdefault(category_norm(p["category"]), p["category"])
    return known


def migrate(post: dict, known: dict[str, str] | None = None) -> dict:
    """A saved post in today's shape: today's topics, no step, and tags."""
    post = dict(post)
    topic = topic_of(post)
    if topic:
        post["problem"] = topic
    post = recategorize(post, known)
    post.pop("step", None)
    if post.get("v") != VERSION or not post.get("issue"):
        post["resort"] = True  # sorted under an older prompt, or no problem yet: Groq sorts it again when it has room
    tags = [t for t in post.get("tags") or [] if t in TAG_NAMES]  # tags from older lists are redone
    post["tags"] = tags or rule_tags(post)
    post.setdefault("added_at", added_on(post))
    return post


NEW_FOR_DAYS = 14  # a post published longer ago than this before it reached the site is old news, not new


def added_at_for(published: str, day: str) -> str:
    """When a post counts as new on the site: the day it was added, unless it was published more than
    NEW_FOR_DAYS before that (a blog's back catalogue, the first import, a backfill), when it counts
    from its own publish date instead, so "New this week" and the weekly email never fill up with
    old posts that merely reached the site late."""
    published, day = str(published or "")[:10], str(day or "")[:10]
    if not day:
        return published
    if not published:
        return day
    try:
        late = (datetime.strptime(day, "%Y-%m-%d") - datetime.strptime(published, "%Y-%m-%d")).days > NEW_FOR_DAYS
    except ValueError:
        return day
    return published if late else max(day, published)


def added_on(post: dict) -> str:
    """A saved post's added_at, worked out from "added" and "published" for posts saved before it existed."""
    return str(post.get("added_at") or "")[:10] or added_at_for(post.get("published"), post.get("added") or post.get("published"))


def groq_record(post: dict, result: dict, today: str, known_cats: dict[str, str]) -> dict:
    """The saved record for a new post Groq kept (result from parse_reply)."""
    problem, summary = result["topic"], result["summary"]
    tags = result.get("tags") or rule_tags(post)
    extra = {"result": result.get("result", ""), "issue": result.get("issue", ""), "v": VERSION, "cat": CAT_VERSION,
             **(result.get("finder") or {})}
    if result.get("category"):
        named = recategorize({"problem": problem, "category": result["category"]}, known_cats)
        problem = named["problem"]
        if named.get("category"):
            extra["category"] = named["category"]
    if post["company"] in CUSTOMER_BLOGS and result.get("customer"):
        # A customer story on a cloud blog: the card is about the customer, written up by the cloud
        extra["via"] = post["company"]
        post = {**post, "company": result["customer"]}
    return {"url": post["url"], "company": post["company"], "title": post["title"],
            "published": post["published"] or today, "added": today,
            "added_at": added_at_for(post["published"], today), "problem": problem,
            "summary": summary, "tags": tags, "sorted_by": "groq", **extra}


def update(existing: list[dict], fetched: list[dict], today: str, use_groq: bool = True,
           max_calls: int = MAX_GROQ_CALLS, reader=None, rejected: set | None = None,
           per_blog: int = MAX_PER_BLOG) -> tuple[list[dict], dict]:
    """Add the new AI posts in fetched to existing. Returns (posts, counts); counts["waiting"] is
    how many posts were left for the next run because the Groq calls ran out.
    reader(url) -> text opens a new post's page so Groq reads more than the feed's excerpt.
    rejected is the set of urls Groq already turned down; new rejections are added to it.
    counts["left"] lists the new posts that were left waiting, to save in the queue."""
    known = {p["url"] for p in existing} | {u for p in existing for u in p.get("aliases", [])}
    known_titles = {title_key(p.get("title", ""), p.get("company", "")) for p in existing} - {""}
    seen_skips = rejected if rejected is not None else set()
    blog_calls: dict[str, int] = {}
    cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=MAX_AGE_DAYS)).strftime("%Y-%m-%d")
    known_cats = known_categories(existing)
    posts = [migrate(p, known_cats) for p in existing]
    counts = {"new": 0, "skipped": 0, "groq": 0, "rules": 0, "waiting": 0, "resorted": 0, "left": []}
    calls = 0

    # Posts saved under the old problems, or with no problem line, are sorted again, with up to half of this run's calls
    # Posts with no problem line come first, newest first, since their cards look unfinished
    order = sorted(enumerate(posts), key=lambda ip: ip[1].get("published") or "", reverse=True)
    order.sort(key=lambda ip: bool(ip[1].get("issue")))
    for i, old in order:
        if not old.get("resort"):
            continue
        if not use_groq or calls >= max_calls // 2:
            counts["waiting"] += 1 if use_groq else 0
            continue
        calls += 1
        text = (reader(old["url"]) if reader else "") or old.get("summary", "")
        result = groq_sort({**old, "text": text})
        if result is None:
            counts["waiting"] += 1
            continue
        if not result["keep"]:
            posts[i] = None
            seen_skips.add(old["url"])
        else:
            posts[i] = {**old, "problem": result["topic"], "summary": result["summary"] or old.get("summary", ""),
                        "result": result.get("result", ""), "issue": result.get("issue", ""), "tags": result.get("tags") or old.get("tags", []),
                        "sorted_by": "groq", "v": VERSION, "cat": CAT_VERSION}
            posts[i].pop("resort", None)
            posts[i].pop("category", None)
            posts[i].update(result.get("finder") or {})
            if result.get("category"):
                posts[i] = recategorize({**posts[i], "category": result["category"]}, known_cats)
        counts["resorted"] += 1
    posts = [p for p in posts if p]
    for post in interleave(fetched):
        if post["url"] in known or post["url"] in seen_skips:
            continue
        if title_key(post["title"], post["company"]) in known_titles:
            seen_skips.add(post["url"])  # the same post under another address
            continue
        if post["published"] and post["published"] < cutoff:
            continue
        if not looks_like_ai(post) or NOT_A_BUILD.search(post["title"]):
            seen_skips.add(post["url"])
            continue
        result = None
        if use_groq and (calls >= max_calls or blog_calls.get(post["company"], 0) >= per_blog):
            counts["waiting"] += 1
            counts["left"].append(post)
            continue  # leave it for the next run, when Groq has room again
        if use_groq:
            calls += 1
            blog_calls[post["company"]] = blog_calls.get(post["company"], 0) + 1
            if reader:
                page = reader(post["url"])
                if len(page) > len(post.get("text", "")):
                    post = {**post, "text": page}
            result = groq_sort(post)
            if result is None and calls == 1:
                use_groq = False  # Groq is down or not set up: sort the rest by keywords
            elif result is None:
                counts["waiting"] += 1  # a passing failure such as a rate limit: try it on the next run
                counts["left"].append(post)
                time.sleep(GROQ_PAUSE)
                continue
        if result is not None:
            counts["groq"] += 1
            if not result["keep"]:
                counts["skipped"] += 1
                seen_skips.add(post["url"])
                continue
            posts.append(groq_record(post, result, today, known_cats))
        else:
            problem = rule_sort(post)
            if not problem:
                counts["skipped"] += 1
                continue
            if problem == "agents":
                problem = split_agents(post)
            counts["rules"] += 1
            posts.append({"url": post["url"], "company": post["company"], "title": post["title"],
                          "published": post["published"] or today, "added": today,
            "added_at": added_at_for(post["published"], today), "problem": problem,
                          "summary": "", "tags": rule_tags(post), "sorted_by": "rules"})
        known.add(post["url"])
        known_titles.add(title_key(post["title"], post["company"]))
        counts["new"] += 1
    counts["calls"] = calls
    assign_slugs(posts)
    return posts, counts


def is_run_day(now: datetime, days: str = "mon") -> bool:
    """Kept for older tests and scripts; the weekly read now uses read_this_week()."""
    if days in ("daily", "all", "every day"):
        return True
    wanted = {d.strip()[:3] for d in days.split(",") if d.strip()}
    return now.strftime("%a").lower() in wanted


def read_this_week(last_fetch: str, now: datetime) -> bool:
    """True when the blogs were already read in the same Monday-to-Sunday week as now."""
    try:
        last = datetime.strptime(last_fetch, "%Y-%m-%d")
    except (TypeError, ValueError):
        return False
    return last.isocalendar()[:2] == now.isocalendar()[:2]


def merge_queue(queue: list[dict], fetched: list[dict]) -> list[dict]:
    """Last week's waiting posts plus this week's feeds, one entry per url (the feed's copy wins)."""
    urls = {p["url"] for p in fetched}
    return fetched + [p for p in queue if p.get("url") and p["url"] not in urls]


def run(path: str = CASES_FILE, force: bool = False) -> int:
    now = datetime.now(IST)
    today = now.strftime("%Y-%m-%d")
    saved = load_all(path)
    existing = saved.get("posts", [])
    last_fetch = saved.get("last_fetch", "")
    if existing and not force and read_this_week(last_fetch, now):
        print(f"  [cases] The blogs were already read this week (on {last_fetch}); keeping the saved posts. "
              "Use --now to read them again.")
        return 0
    fetched, down = [], []
    for name, main, *_ in SOURCES:
        got, failed = [], 0
        for feed in feeds_of(name, main):
            try:
                got += parse_feed(fetch_feed(feed), name)
            except Exception as exc:
                failed += 1
                print(f"  [cases] {name}: feed failed ({str(exc)[:80]})")
        if failed == len(feeds_of(name, main)):
            down.append(name)
        fetched += got
        print(f"  [cases] {name}: {len(got)} posts in the feed")
    use_groq = bool(os.environ.get("GROQ_API_KEY", "").strip())
    rejected = set(saved.get("rejected", []))
    queue = saved.get("queue", [])
    posts, counts = update(existing, merge_queue(queue, fetched), today, use_groq=use_groq,
                           reader=read_article if use_groq else None, rejected=rejected)
    # Saved posts with no finder fields yet (older posts, or a reply without them) use the spare calls
    tagged = {"tagged": 0}
    spare = min(MAX_TAG_CALLS, MAX_GROQ_CALLS - counts.get("calls", 0))
    if use_groq and spare > 0 and any(needs_tags(p) for p in posts):
        tagged = tag_posts(posts, reader=read_article, max_calls=spare)
    # Every feed down usually means no network: leave last_fetch alone so the next run tries again
    read_ok = len(down) < len(SOURCES)
    save(posts, path, rejected, counts["waiting"], today if read_ok else last_fetch, counts["left"])
    try:  # icons for the companies with no drawn logo, from their own websites
        import case_logos
        with open(os.path.join(SRC_DIR, "case_brands.json"), encoding="utf-8") as f:
            drawn = set(json.load(f))
        case_logos.fetch_missing([name for name, _, _, slug, _ in SOURCES if slug not in drawn])
    except Exception as exc:
        print(f"  [cases] Logos skipped ({str(exc)[:80]})")
    print(f"  [cases] {counts['new']} new posts ({counts['groq']} sorted by Groq, {counts['rules']} by keywords), "
          f"{counts['resorted']} older posts sorted again, {tagged['tagged']} tagged for the finder, {counts['skipped']} not about AI in production, {counts['waiting']} waiting for next week, "
          f"{len(down)} of {len(SOURCES)} feeds down. {len(posts)} saved.")
    return counts["new"]


def recategorize_saved(path: str = CASES_FILE) -> dict[str, int]:
    """Move the saved posts onto today's categories by keywords, offline and free (no Groq calls),
    and save them. Returns how many posts each topic has afterwards, most first."""
    saved = load_all(path)
    posts = saved.get("posts", [])
    known = known_categories(posts)
    posts = [recategorize(p, known) for p in posts]
    save(posts, path, saved.get("rejected", []), saved.get("waiting", 0), saved.get("last_fetch", ""),
         saved.get("queue", []))
    counts: dict[str, int] = {}
    for p in posts:
        counts[p.get("problem", "")] = counts.get(p.get("problem", ""), 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


# ---------- backfill: growing the page to a number of write-ups

BACKFILL_TARGET = 520     # write-ups shown on the Case studies page
BACKFILL_MAX_CALLS = 200  # Groq calls per backfill run; run it again to go on
BACKFILL_KEEP_RATE = 0.4  # share of keyword-picked candidates Groq keeps, for the dry run's estimate
DEEP_PAGES = 6            # older feed pages read per blog
MEDIUM_TAGS = ("machine-learning", "artificial-intelligence", "llm", "generative-ai", "data-science")


def older_pages(feed: str, pages: int = DEEP_PAGES) -> list[str]:
    """Addresses that list a blog's older posts, for blogs whose feed only holds the newest few:
    WordPress feeds page with ?paged=N, Ghost feeds with /rss/N/, and Medium publications (and
    Medium blogs on their own domain) have a feed per tag, which reaches further back for AI tags."""
    out = []
    if "medium.com/feed/" in feed or re.search(r"\.[a-z]+/feed$", feed):
        out += [f"{feed}/tagged/{tag}" for tag in MEDIUM_TAGS]
    if re.search(r"/feed/?$", feed) and "medium.com" not in feed:
        out += [f"{feed.rstrip('/')}/?paged={n}" for n in range(2, pages + 1)]
    if re.search(r"/rss/?$", feed):
        out += [f"{feed.rstrip('/')}/{n}/" for n in range(2, pages + 1)]
    return out


def read_deep(name: str, feed: str, cutoff: str, fetch=None) -> list[dict]:
    """A blog's posts from its feed and its older pages, back to cutoff. Paging stops at the first
    page that fails, adds nothing new, or reaches past cutoff."""
    fetch = fetch or fetch_feed
    seen: dict[str, dict] = {}
    paging_over = False
    for i, url in enumerate([feed] + older_pages(feed)):
        paged = "paged=" in url or bool(re.search(r"/rss/\d+/$", url))
        if paged and paging_over:
            continue
        try:
            got = parse_feed(fetch(url), name)
        except Exception:
            if i == 0:
                return []  # the blog's own feed is down: skip the blog this run
            paging_over = paging_over or paged
            continue
        new = [p for p in got if p["url"] not in seen]
        for p in new:
            seen[p["url"]] = p
        if paged and (not new or all(p["published"] and p["published"] < cutoff for p in new)):
            paging_over = True
    return [p for p in seen.values() if not p["published"] or p["published"] >= cutoff]


def shown_count(posts: list[dict]) -> int:
    """How many write-ups the Case studies page shows: the valid ones within its one-year window."""
    import case_pages
    return len(case_pages.recent(case_pages._clean(posts)))


def backfill_candidates(saved: dict, today: str, fetch=None, deep: bool = True,
                        sources=None) -> tuple[list[dict], dict[str, int]]:
    """The posts worth asking Groq about: from every blog (older pages too when deep) and the saved
    queue, within the page's one-year window, not saved or turned down already (by address or by
    title), and passing the free keyword checks. Returns (candidates in asking order, count per blog)."""
    from concurrent.futures import ThreadPoolExecutor
    cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=365)).strftime("%Y-%m-%d")
    posts = saved.get("posts", [])
    known = {p["url"] for p in posts} | {u for p in posts for u in p.get("aliases", [])} | set(saved.get("rejected", []))
    titles = {title_key(p.get("title", ""), p.get("company", "")) for p in posts} - {""}
    jobs = [(name, feed) for name, main, *_ in (sources or SOURCES) for feed in feeds_of(name, main)]
    if deep:
        with ThreadPoolExecutor(12) as pool:
            batches = list(pool.map(lambda job: read_deep(job[0], job[1], cutoff, fetch), jobs))
    else:
        def one(job):
            try:
                return parse_feed((fetch or fetch_feed)(job[1]), job[0])
            except Exception:
                return []
        with ThreadPoolExecutor(12) as pool:
            batches = list(pool.map(one, jobs))
    found = [p for batch in batches for p in batch] + [dict(p) for p in saved.get("queue", []) if p.get("url")]
    out, per_source = [], {}
    for post in found:
        key = title_key(post.get("title", ""), post.get("company", ""))
        if post["url"] in known or not key or key in titles:
            continue
        if not post.get("published") or post["published"] < cutoff:
            continue
        if not looks_like_ai(post) or NOT_A_BUILD.search(post["title"]):
            continue
        known.add(post["url"])
        titles.add(key)
        out.append(post)
        per_source[post["company"]] = per_source.get(post["company"], 0) + 1
    return interleave(out), dict(sorted(per_source.items(), key=lambda kv: -kv[1]))


def backfill(path: str = CASES_FILE, target: int = BACKFILL_TARGET, max_calls: int = BACKFILL_MAX_CALLS,
             dry_run: bool = False, fetch=None, sorter=None, reader=read_article, sleep=time.sleep,
             today: str | None = None, deep: bool = True) -> dict:
    """Ask Groq about older posts until the page shows target write-ups or max_calls are used.
    One Groq call per candidate (the weekly prompt, which also tags it for the finder); the
    keyword checks drop the rest for free. Saves every 10 calls and at the end; posts not reached
    go in the queue, so the next run (or the weekly run) carries on. A dry run makes no Groq call:
    it counts the candidates and estimates the calls needed."""
    today = today or datetime.now(IST).strftime("%Y-%m-%d")
    saved = load_all(path)
    posts = list(saved.get("posts", []))
    rejected = set(saved.get("rejected", []))
    shown = shown_count(posts)
    candidates, per_source = backfill_candidates(saved, today, fetch, deep)
    need = max(0, target - shown)
    report = {"shown_before": shown, "target": target, "candidates": len(candidates), "per_source": per_source,
              "need": need, "estimated_calls": min(len(candidates), math.ceil(need / BACKFILL_KEEP_RATE)) if need else 0,
              "calls": 0, "kept": 0, "turned_down": 0, "failed": 0, "stopped": ""}
    if dry_run or not need:
        report["shown_after"] = shown
        report["stopped"] = "dry run" if dry_run else "already at target"
        return report
    sorter = sorter or (lambda p: groq_sort_paced(p, sleep=sleep))
    known_cats = known_categories(posts)
    done: set[str] = set()

    def keep():
        left = [p for p in candidates if p["url"] not in done]
        save(posts, path, rejected, saved.get("waiting", 0), saved.get("last_fetch", ""), left)

    for post in candidates:
        if shown >= target:
            report["stopped"] = "target reached"
            break
        if report["calls"] >= max_calls:
            report["stopped"] = "call cap reached"
            break
        if report["calls"]:
            sleep(TAG_PAUSE)
        page = reader(post["url"]) if reader else ""
        if len(page) > len(post.get("text", "")):
            post = {**post, "text": page}
        try:
            result = sorter(post)
        except GroqOutOfCalls as exc:
            report["stopped"] = f"Groq out of calls ({exc})"
            break
        report["calls"] += 1
        if result is None:
            report["failed"] += 1  # stays a candidate for the next run
        elif not result["keep"]:
            report["turned_down"] += 1
            rejected.add(post["url"])
            done.add(post["url"])
        else:
            posts.append(groq_record(post, result, today, known_cats))
            done.add(post["url"])
            report["kept"] += 1
            assign_slugs(posts)
            shown = shown_count(posts)
        if report["calls"] % 10 == 0:
            keep()
    else:
        report["stopped"] = report["stopped"] or "no candidates left"
    keep()
    report["shown_after"] = shown
    return report


# ---------- a page per case study: case-studies/<slug>.html (case_detail.py)

SLUG_TITLE_MAX = 60
RESERVED_SLUGS = {"index", "review", "logos", "how-i-built-ai-papers-daily"}


def slugify(text: str, limit: int = 0) -> str:
    """Lowercase ASCII words joined by hyphens; cut at a word boundary when longer than limit."""
    text = unicodedata.normalize("NFKD", html.unescape(str(text or ""))).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if limit and len(slug) > limit:
        cut = slug[:limit + 1].rsplit("-", 1)[0]
        slug = (cut or slug[:limit]).strip("-")
    return slug


def base_slug(post: dict) -> str:
    """<company>-<short title>, for a case page's address."""
    company = slugify(post.get("company", ""), 30) or "case"
    title = slugify(post.get("title", ""), SLUG_TITLE_MAX)
    if title.startswith(company + "-"):  # "Netflix: ..." titles would say the company twice
        title = title[len(company) + 1:]
    return f"{company}-{title}".strip("-") if title else company


def assign_slugs(posts: list[dict], reserved=()) -> int:
    """Give every post without one a slug, unique among the posts and the reserved page names.
    A slug is never changed once given, even when the title changes later; collisions get -2,
    -3 ... in the order posts reached the site, so the same data always gives the same slugs.
    Returns how many posts got a new slug."""
    taken = set(RESERVED_SLUGS) | set(reserved) | {p["slug"] for p in posts if p.get("slug")}
    fresh = sorted((p for p in posts if not p.get("slug")),
                   key=lambda p: (str(p.get("added") or p.get("published") or ""), p.get("url", "")))
    for post in fresh:
        base = base_slug(post)
        slug, n = base, 2
        while slug in taken:
            slug, n = f"{base}-{n}", n + 1
        post["slug"] = slug
        taken.add(slug)
    return len(fresh)


def slug_saved(path: str = CASES_FILE) -> int:
    """One-off: store a slug on every saved post that has none. No network, no Groq."""
    saved = load_all(path)
    posts = saved.get("posts", [])
    n = assign_slugs(posts)
    save(posts, path, saved.get("rejected", []), saved.get("waiting", 0), saved.get("last_fetch", ""),
         saved.get("queue", []))
    return n


def retag_saved(path: str = CASES_FILE, everything: bool = False, tagger=None, reader=read_article,
                sleep=time.sleep) -> dict:
    """One-off: tag the saved posts for the finder (only those with no tags yet, unless everything),
    saving every 10 posts so a run stopped by Groq's daily limit keeps its work; run it again the
    next day to go on. Returns the counts plus the spread of topics ("problem") and build_score over the tagged posts."""
    saved = load_all(path)
    posts = saved.get("posts", [])

    def keep():
        save(posts, path, saved.get("rejected", []), saved.get("waiting", 0), saved.get("last_fetch", ""),
             saved.get("queue", []))

    counts = tag_posts(posts, tagger=tagger, reader=reader, everything=everything, sleep=sleep, on_progress=keep)
    keep()
    counts["problem"], counts["build_score"] = {}, {}
    for p in posts:
        if not needs_tags(p):
            counts["problem"][p.get("problem", "")] = counts["problem"].get(p.get("problem", ""), 0) + 1
            counts["build_score"][p["build_score"]] = counts["build_score"].get(p["build_score"], 0) + 1
    counts["untagged"] = sum(needs_tags(p) for p in posts)
    return counts


if __name__ == "__main__":
    if "--recategorize" in sys.argv:  # keywords only, no API calls
        for key, n in recategorize_saved().items():
            print(f"  [cases] {TOPICS.get(key, (key,))[0]}: {n}")
        sys.exit(0)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    if "--backfill" in sys.argv:
        def flag(name, default):
            return int(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default
        dry = "--dry-run" in sys.argv
        if not dry and not os.environ.get("GROQ_API_KEY", "").strip():
            print("  [cases] GROQ_API_KEY is not set; showing the dry run instead.")
            dry = True
        result = backfill(target=flag("--target", BACKFILL_TARGET), max_calls=flag("--max-calls", BACKFILL_MAX_CALLS),
                          dry_run=dry)
        print(f"  [cases] Shown before: {result['shown_before']}, target {result['target']}, "
              f"{result['candidates']} candidates after the keyword checks.")
        for name, n in result["per_source"].items():
            print(f"  [cases]   {name}: {n}")
        print(f"  [cases] Estimated Groq calls to reach the target: {result['estimated_calls']} "
              f"(if {BACKFILL_KEEP_RATE:.0%} are kept). This run: {result['calls']} calls, {result['kept']} kept, "
              f"{result['turned_down']} turned down, {result['failed']} unusable; shown now {result['shown_after']} "
              f"({result['stopped']}).")
        sys.exit(0)
    if "--slugs" in sys.argv:  # no network, no Groq
        print(f"  [cases] {slug_saved()} posts got a slug.")
        sys.exit(0)
    if "--retag" in sys.argv:
        if not os.environ.get("GROQ_API_KEY", "").strip():
            print("  [cases] GROQ_API_KEY is not set; nothing tagged.")
            sys.exit(1)
        result = retag_saved(everything="--all" in sys.argv)
        print(f"  [cases] {result['tagged']} posts tagged, {result['failed']} unusable replies, "
              f"{result['left']} left for another run, {result['untagged']} saved posts still untagged.")
        print("  [cases] topics:", dict(sorted(result["problem"].items(), key=lambda kv: -kv[1])))
        print("  [cases] build_score:", dict(sorted(result["build_score"].items())))
        sys.exit(0)
    run(force="--now" in sys.argv)
