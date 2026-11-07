"""
case_studies.py
Reads company engineering blogs and keeps the posts about AI running in real products,
for the Case studies pages.

For each new post, Groq decides whether it is about AI in production, which problem and
step it explains (case_sources.PROBLEMS), picks 1-3 technique tags (case_sources.TAGS), and
writes one line about it in our own words.
Without Groq, a keyword fallback sorts posts and the summary is left empty: the site never
shows the blog's own text as ours.

Writes data/cases.json. The daily workflow runs it before the site build; it reads the blogs on
RUN_DAYS only (Monday and Thursday by default). To run it now:  python src/case_studies.py --now
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

from case_sources import SOURCES, PROBLEMS, TAGS, TAG_NAMES

CASES_FILE = os.path.join(ROOT_DIR, "data", "cases.json")
MAX_POSTS = 800          # oldest posts drop off past this
MAX_AGE_DAYS = 400       # posts older than this are not added
MAX_GROQ_CALLS = int(os.environ.get("CASES_MAX_GROQ", "60"))  # per run, to stay inside the free tier
# Company blogs post about once a week, so the blogs are read on these days only.
# CASES_RUN_DAYS="mon" reads them weekly, "daily" every day. "--now" runs today regardless.
RUN_DAYS = os.environ.get("CASES_RUN_DAYS", "").strip().lower() or "mon,thu"
USER_AGENT = "AIPapersDaily/1.0 (+https://omen-bit.github.io/ai-paper-daily/)"

# A post has to mention one of these to be worth asking Groq about
_AI_WORDS = re.compile(
    r"\b(machine learning|ml|ai|llms?|large language models?|genai|generative|neural|deep learning|"
    r"models?|embeddings?|transformers?|recommend\w*|ranking|personali[sz]\w*|retrieval|rag|"
    r"agents?|agentic|inference|training|fine-?tun\w*|classif\w*|predict\w*|forecast\w*|"
    r"computer vision|vision|ocr|search relevance|semantic search|vector|gpu)\b", re.I)

# Fallback sorting when Groq is not available: (problem, step, pattern), first match wins
_RULES = [
    ("llm", 3, r"guardrail|safety|hallucinat|jailbreak|red.?team"),
    ("llm", 2, r"\bagents?\b|agentic|tool.?(use|call)|copilot|assistant"),
    ("llm", 1, r"\brag\b|retrieval.augmented|knowledge base|grounding"),
    ("llm", 0, r"prompt|context window|\bllms?\b|large language|genai|generative ai|chatbot|gpt"),
    ("ads", 3, r"\bbid(ding)?\b|auction"),
    ("ads", 2, r"\bads?\b.{0,20}retrieval|ad candidates"),
    ("ads", 0, r"\bads?\b|advertis|targeting|lookalike"),
    ("search", 0, r"query understanding|query rewriting|spell|autocomplete|typeahead"),
    ("search", 1, r"\bindex(ing)?\b|vector (store|database)"),
    ("search", 3, r"re-?rank"),
    ("search", 2, r"\bsearch\b|semantic retrieval|relevance"),
    ("vision", 3, r"video (editing|resiz|crop|enhanc)|reframe|upscal"),
    ("vision", 2, r"tracking|tracker"),
    ("vision", 1, r"detection|detector|\bocr\b|segmentation"),
    ("vision", 0, r"label(l)?ing|annotat"),
    ("vision", 1, r"computer vision|image|video|visual"),
    ("predict", 3, r"fraud|risk|pricing|dispatch"),
    ("predict", 2, r"forecast|demand|eta\b|arrival time|time series|churn"),
    ("recs", 0, r"user (intent|interest|journey)|personali[sz]"),
    ("recs", 2, r"candidate|two.tower|retrieval"),
    ("recs", 3, r"recommend|ranking|feed\b|home ?feed"),
]
_SHARED_RULES = [
    (1, r"feature (store|platform|pipeline)|features? (to|in) production"),
    (5, r"\bevaluat|a/b test|experiment|offline metric|benchmark"),
    (4, r"\bserving\b|inference|latency|\bgpus?\b|throughput|kernel|quantiz"),
]

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


def rule_sort(post: dict) -> tuple[str, int] | None:
    """(problem, step) from keywords, or None when nothing matches."""
    text = f"{post['title']} {post.get('text', '')[:400]}".lower()
    problem = step = None
    for p, s, pattern in _RULES:
        if re.search(pattern, text):
            problem, step = p, s
            break
    if problem is None:
        return None
    for s, pattern in _SHARED_RULES:  # a post about serving or evaluation sits on that shared stop
        if re.search(pattern, post["title"].lower()):
            if s != 1 or problem in ("recs", "ads", "predict"):
                step = s
                break
    return problem, step


MAX_TAGS = 3


def rule_tags(post: dict) -> list[str]:
    """Up to MAX_TAGS technique tags from keywords in the title first, then the text."""
    title, text = post["title"].lower(), f"{post.get('text', '')[:600]} {post.get('summary', '')}".lower()
    tags = [t for t, pattern in TAGS if re.search(pattern, title)]
    tags += [t for t, pattern in TAGS if t not in tags and re.search(pattern, text)]
    return tags[:MAX_TAGS]


GROQ_PROMPT = """You sort engineering blog posts for a site about how companies use AI in real products.

Problems and their steps (0-5):
{problems}

Reply with JSON only:
{{"ai_in_production": true or false, "problem": "<key or none>", "step": <0-5>, "summary": "<one sentence>", "tags": ["<tag>", ...]}}

ai_in_production is true only when the post explains how the company builds, trains, serves or
evaluates a machine learning or AI system it runs. Hiring posts, events, culture, security
incidents and general infrastructure without a model are false.
The summary is at most 25 words, in plain words, in your own words (never copy the post's
sentences), says what the team did and why, and does not start with the company name.
tags are 1 to 3 techniques the post is mainly about, chosen only from this list:
{tags}"""


def _problems_text() -> str:
    return "\n".join(f'- {k}: {name}. Steps: ' + "; ".join(f"{i} {s}" for i, s in enumerate(steps))
                     for k, (name, _, steps) in PROBLEMS.items())


def parse_reply(raw: str) -> dict | None:
    """The classification from a Groq reply, or None when it is unusable."""
    match = re.search(r"\{.*\}", raw or "", re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not data.get("ai_in_production"):
        return {"keep": False}
    problem = str(data.get("problem", "")).strip()
    try:
        step = int(data.get("step"))
    except (TypeError, ValueError):
        return None
    if problem not in PROBLEMS or not 0 <= step <= 5:
        return None
    summary = " ".join(str(data.get("summary", "")).split())
    if len(summary.split()) > 40:
        summary = ""
    by_lower = {t.lower(): t for t in TAG_NAMES}
    raw_tags = data.get("tags") if isinstance(data.get("tags"), list) else []
    tags = []
    for t in raw_tags:
        name = by_lower.get(str(t).strip().lower())
        if name and name not in tags:
            tags.append(name)
    return {"keep": True, "problem": problem, "step": step, "summary": summary, "tags": tags[:MAX_TAGS]}


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
                messages=[{"role": "system", "content": GROQ_PROMPT.format(problems=_problems_text(), tags=", ".join(TAG_NAMES))},
                          {"role": "user", "content": user}],
                **gs.call_options(model, 200))
            result = parse_reply(response.choices[0].message.content)
            if result:
                return result
        except Exception as exc:
            if "429" in str(exc):
                time.sleep(4)
            print(f"  [cases] Groq error on {model}: {str(exc)[:100]}")
    return None


def load(path: str = CASES_FILE) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("posts", [])
    except (OSError, ValueError):
        return []


def save(posts: list[dict], path: str = CASES_FILE) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    posts = sorted(posts, key=lambda p: (p.get("published") or "", p["url"]), reverse=True)[:MAX_POSTS]
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"posts": posts}, f, ensure_ascii=False, indent=1)
        f.write("\n")


def update(existing: list[dict], fetched: list[dict], today: str, use_groq: bool = True,
           max_calls: int = MAX_GROQ_CALLS, reader=None) -> tuple[list[dict], dict]:
    """Add the new AI posts in fetched to existing. Returns (posts, counts).
    reader(url) -> text opens a new post's page so Groq reads more than the feed's excerpt."""
    known = {p["url"] for p in existing} | {u for p in existing for u in p.get("aliases", [])}
    seen_skips = set()
    cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=MAX_AGE_DAYS)).strftime("%Y-%m-%d")
    posts = [p if "tags" in p else {**p, "tags": rule_tags(p)} for p in existing]  # older posts get tags too
    counts = {"new": 0, "skipped": 0, "groq": 0, "rules": 0}
    calls = 0
    for post in fetched:
        if post["url"] in known or post["url"] in seen_skips:
            continue
        if post["published"] and post["published"] < cutoff:
            continue
        if not looks_like_ai(post):
            seen_skips.add(post["url"])
            continue
        result = None
        if use_groq and calls < max_calls:
            calls += 1
            if reader:
                page = reader(post["url"])
                if len(page) > len(post.get("text", "")):
                    post = {**post, "text": page}
            result = groq_sort(post)
            if result is None and calls == 1:
                use_groq = False  # Groq is down or not set up: sort the rest by keywords
        if result is not None:
            counts["groq"] += 1
            if not result["keep"]:
                counts["skipped"] += 1
                seen_skips.add(post["url"])
                continue
            problem, step, summary, how = result["problem"], result["step"], result["summary"], "groq"
            tags = result.get("tags") or rule_tags(post)
        else:
            if use_groq and calls >= max_calls:
                continue  # leave it for tomorrow's run, when Groq has room again
            sorted_ = rule_sort(post)
            if not sorted_:
                counts["skipped"] += 1
                continue
            problem, step = sorted_
            summary, how = "", "rules"
            tags = rule_tags(post)
            counts["rules"] += 1
        posts.append({"url": post["url"], "company": post["company"], "title": post["title"],
                      "published": post["published"] or today, "added": today, "problem": problem,
                      "step": step, "summary": summary, "tags": tags, "sorted_by": how})
        known.add(post["url"])
        counts["new"] += 1
    return posts, counts


def is_run_day(now: datetime, days: str = RUN_DAYS) -> bool:
    if days in ("daily", "all", "every day"):
        return True
    wanted = {d.strip()[:3] for d in days.split(",") if d.strip()}
    return now.strftime("%a").lower() in wanted


def run(path: str = CASES_FILE, force: bool = False) -> int:
    now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    today = now.strftime("%Y-%m-%d")
    if not force and not is_run_day(now):
        print(f"  [cases] Blogs are read on {RUN_DAYS} only; nothing to do today. Use --now to run anyway.")
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
    existing = load(path)
    use_groq = bool(os.environ.get("GROQ_API_KEY", "").strip())
    posts, counts = update(existing, fetched, today, use_groq=use_groq, reader=read_article if use_groq else None)
    save(posts, path)
    print(f"  [cases] {counts['new']} new posts ({counts['groq']} sorted by Groq, {counts['rules']} by keywords), "
          f"{counts['skipped']} not about AI in production, {len(down)} feeds down. {len(posts)} saved.")
    return counts["new"]


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    run(force="--now" in sys.argv)
