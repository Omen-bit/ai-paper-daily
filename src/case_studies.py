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
A feed that is down is skipped; the posts already saved stay.
"""
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SRC_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from case_sources import (CUSTOMER_BLOGS, FOCUS_WORDS, SOURCES, TAG_NAMES, TAGS, TOPIC_RULES, TOPICS,
                          category_norm, match_category, split_agents, topic_of)

CASES_FILE = os.path.join(ROOT_DIR, "data", "cases.json")
MAX_POSTS = 800          # oldest posts drop off past this
MAX_AGE_DAYS = 400       # posts older than this are not added
MAX_GROQ_CALLS = int(os.environ.get("CASES_MAX_GROQ", "150"))  # per weekly run, to stay inside the free tier
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
    """One address per post: no tracking query, no trailing slash, https."""
    url = (url or "").strip()
    url = re.sub(r"[?#].*$", "", url)
    url = re.sub(r"^http://", "https://", url)
    return url.rstrip("/")


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
{{"kind": "<kind>", "topic": "<key>", "new_topic": "<short name or empty>", "issue": "<one sentence>", "summary": "<one or two sentences>", "result": "<short phrase or empty>", "tags": ["<tag>", ...], "customer": "<company name or empty>"}}

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
{tags}"""

# Titles that are never a write-up about how something was built, turned down without asking Groq
NOT_A_BUILD = re.compile(
    r"now (generally )?available|\brelease notes?\b|\brelease\s*$|security release|what we heard|"
    r"everything we talked|key takeaways|\brecap\b|\bwebinar\b|join us|we.re hiring|meet the team|"
    r"\bchangelog\b|\bnewsletter\b", re.I)
VERSION = 3  # posts sorted under an older prompt are sorted again, so they get a result and a kind
CAT_VERSION = 2  # sorted with the agent topics and new categories; older "agents" posts are split by keywords


def _topics_text() -> str:
    return "\n".join(f"- {k}: {name}. {about}" for k, (name, about) in TOPICS.items())


def parse_reply(raw: str) -> dict | None:
    """The classification from a Groq reply, or None when it is unusable."""
    match = re.search(r"\{.*\}", raw or "", re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
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
                messages=[{"role": "system", "content": GROQ_PROMPT.format(topics=_topics_text(), tags=", ".join(TAG_NAMES))},
                          {"role": "user", "content": user}],
                **gs.call_options(model, 400))
            result = parse_reply(response.choices[0].message.content)
            if result:
                return result
        except Exception as exc:
            if "429" in str(exc):
                time.sleep(4)
            print(f"  [cases] Groq error on {model}: {str(exc)[:100]}")
    return None


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
    return post


def update(existing: list[dict], fetched: list[dict], today: str, use_groq: bool = True,
           max_calls: int = MAX_GROQ_CALLS, reader=None, rejected: set | None = None,
           per_blog: int = MAX_PER_BLOG) -> tuple[list[dict], dict]:
    """Add the new AI posts in fetched to existing. Returns (posts, counts); counts["waiting"] is
    how many posts were left for the next run because the Groq calls ran out.
    reader(url) -> text opens a new post's page so Groq reads more than the feed's excerpt.
    rejected is the set of urls Groq already turned down; new rejections are added to it.
    counts["left"] lists the new posts that were left waiting, to save in the queue."""
    known = {p["url"] for p in existing} | {u for p in existing for u in p.get("aliases", [])}
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
            if result.get("category"):
                posts[i] = recategorize({**posts[i], "category": result["category"]}, known_cats)
        counts["resorted"] += 1
    posts = [p for p in posts if p]
    for post in interleave(fetched):
        if post["url"] in known or post["url"] in seen_skips:
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
            problem, summary, how = result["topic"], result["summary"], "groq"
            tags = result.get("tags") or rule_tags(post)
            extra = {"result": result.get("result", ""), "issue": result.get("issue", ""), "v": VERSION, "cat": CAT_VERSION}
            if result.get("category"):
                named = recategorize({"problem": problem, "category": result["category"]}, known_cats)
                problem = named["problem"]
                if named.get("category"):
                    extra["category"] = named["category"]
            if post["company"] in CUSTOMER_BLOGS and result.get("customer"):
                # A customer story on a cloud blog: the card is about the customer, written up by the cloud
                extra["via"] = post["company"]
                post = {**post, "company": result["customer"]}
        else:
            problem = rule_sort(post)
            if not problem:
                counts["skipped"] += 1
                continue
            if problem == "agents":
                problem = split_agents(post)
            summary, how = "", "rules"
            tags = rule_tags(post)
            extra = {}
            counts["rules"] += 1
        posts.append({"url": post["url"], "company": post["company"], "title": post["title"],
                      "published": post["published"] or today, "added": today, "problem": problem,
                      "summary": summary, "tags": tags, "sorted_by": how, **extra})
        known.add(post["url"])
        counts["new"] += 1
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
    for name, feed, *_ in SOURCES:
        try:
            got = parse_feed(fetch_feed(feed), name)
            fetched += got
            print(f"  [cases] {name}: {len(got)} posts in the feed")
        except Exception as exc:
            down.append(name)
            print(f"  [cases] {name}: feed failed ({str(exc)[:80]})")
    use_groq = bool(os.environ.get("GROQ_API_KEY", "").strip())
    rejected = set(saved.get("rejected", []))
    queue = saved.get("queue", [])
    posts, counts = update(existing, merge_queue(queue, fetched), today, use_groq=use_groq,
                           reader=read_article if use_groq else None, rejected=rejected)
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
          f"{counts['resorted']} older posts sorted again, {counts['skipped']} not about AI in production, {counts['waiting']} waiting for next week, "
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
    run(force="--now" in sys.argv)
