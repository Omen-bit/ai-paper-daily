"""
case_suggestions.py
Write-ups readers suggest on the Case studies page ("Suggest a write-up"). Run by the daily
workflow after the edition is made:

  1. Every suggestion still "new" (at most MAX_PER_RUN a run) is checked, the free checks first:
     the link works (one fetch with a timeout and a size cap, never a blocked site), the page is
     about an AI system (case_studies.looks_like_ai), and it is not on the site yet (same address or
     same company and title as a saved post). Only a suggestion that passes all three costs one Groq
     call: the weekly sort-and-tag prompt, which fills in the topic, techniques, industry, build
     details and the Problem/Solution lines. The results go back on the row, now "checked" (or
     "duplicate" when the post is already on the site). A failure on one row never stops the rest.
  2. Every suggestion the owner approved on the review page (case-studies/review.html) that is not
     on the site yet is added to data/cases.json, with "suggested_by" when the reader gave a name.
     Rejected and duplicate rows are never published.

Needs SUPABASE_URL and SUPABASE_SECRET_KEY (service key); without them it does nothing.
  python src/case_suggestions.py
"""
import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from urllib.parse import urlparse

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import case_studies as cs
from case_sources import BY_NAME

MAX_PER_RUN = 20
FETCH_TIMEOUT = 15
MAX_BYTES = 2_000_000
CREDIT_MAX = 40
TIMEOUT = 30
# Never fetched: link shorteners, social sites and file hosts are not engineering write-ups
BLOCKED = ("bit.ly", "t.co", "tinyurl.com", "goo.gl", "ow.ly", "buff.ly", "lnkd.in", "x.com", "twitter.com",
           "facebook.com", "instagram.com", "tiktok.com", "youtube.com", "youtu.be", "drive.google.com",
           "docs.google.com", "dropbox.com", "wetransfer.com", "pastebin.com")
PRIVATE = re.compile(r"^(localhost|.*\.local|.*\.internal|127\.|10\.|192\.168\.|169\.254\.|0\.|"
                     r"172\.(1[6-9]|2\d|3[01])\.|\[|\d+$)", re.I)


def clean_credit(raw) -> str:
    """The reader's credit as plain text: letters, digits, spaces and @ . _ - only, at most 40
    characters. The same rule as cleanCredit() in supabase/functions/_shared/suggest.ts."""
    text = unicodedata.normalize("NFKC", str(raw or ""))
    text = "".join(ch for ch in text if ch.isalnum() or ch in " @._-")
    return " ".join(text.split())[:CREDIT_MAX].strip()


def blocked(url: str) -> bool:
    """True for addresses the job never opens: not https, a private host, or a blocked site."""
    try:
        parts = urlparse(url)
    except ValueError:
        return True
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme != "https" or not host or parts.username or parts.password or PRIVATE.match(host):
        return True
    return any(host == b or host.endswith("." + b) for b in BLOCKED)


def fetch_page(url: str, timeout: int = FETCH_TIMEOUT, max_bytes: int = MAX_BYTES) -> tuple[bool, str]:
    """(link works, the page's HTML up to max_bytes). Redirects to a blocked or private host fail."""
    import requests
    try:
        with requests.get(url, timeout=timeout, stream=True, allow_redirects=True,
                          headers={"User-Agent": cs.USER_AGENT}) as resp:
            if resp.status_code >= 400 or blocked(resp.url):
                return False, ""
            if "html" not in resp.headers.get("content-type", "html").lower():
                return False, ""
            body = b""
            for chunk in resp.iter_content(65536):
                body += chunk
                if len(body) >= max_bytes:
                    break
            return True, body[:max_bytes].decode(resp.encoding or "utf-8", errors="replace")
    except Exception as exc:
        print(f"  [suggest] Could not open {url[:70]} ({str(exc)[:60]})")
        return False, ""


def _meta(page: str, name: str) -> str:
    m = (re.search(rf'<meta[^>]+(?:property|name)=["\']{name}["\'][^>]+content=["\']([^"\']+)', page, re.I)
         or re.search(rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{name}["\']', page, re.I))
    return cs.clean_text(m.group(1), 300) if m else ""


def page_title(page: str) -> str:
    title = _meta(page, "og:title")
    if not title:
        m = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
        title = cs.clean_text(m.group(1), 300) if m else ""
    return re.sub(r"\s+[|–—-]\s+[^|–—-]{2,40}$", "", title).strip()  # drop " | Blog name"


def company_of(url: str, page: str) -> str:
    """The company behind a post: a known source whose blog lives on this host, else the site name."""
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    for name, (_, feed, home, *_rest) in BY_NAME.items():
        for addr in (home, feed):
            h = (urlparse(addr).hostname or "").lower().removeprefix("www.")
            if h and h == host and h != "medium.com":
                return name
    site = _meta(page, "og:site_name")
    if site and len(site) <= 40:
        return site
    parts = host.split(".")
    return (parts[-2] if len(parts) >= 2 else host).capitalize()


def sort_and_tag(post: dict, sleep=None) -> tuple[dict | None, str]:
    """The one Groq call (the weekly sort-and-tag prompt). Returns (parse_reply result or None, kind).
    A post Groq calls a launch or research is still tagged when the reply has the fields, so the
    owner can approve it anyway; kind says what Groq thought it was."""
    system = cs.GROQ_PROMPT.format(topics=cs._topics_text(), tags=", ".join(cs.TAG_NAMES),
                                   finder_json=cs.FINDER_JSON, finder_rules=cs.FINDER_RULES)
    user = f"Company: {post['company']}\nTitle: {post['title']}\nPost start: {post.get('text', '')[:2500]}"
    raw = cs.groq_call(system, user, 600, 0.2, sleep or cs.time.sleep)
    data = cs._reply_json(raw)
    if data is None:
        return None, ""
    kind = str(data.get("kind", "")).strip().lower()
    # A reply with no usable topic or problem line is still an answer: the row is checked, untagged
    return cs.parse_reply(json.dumps({**data, "kind": "build"})) or {"keep": False}, kind


def check(row: dict, posts: list[dict], fetch=fetch_page, sorter=sort_and_tag, today: str = "") -> dict:
    """The update for one "new" suggestion: its checks, the filled-in fields and the new status."""
    today = today or datetime.now(cs.IST).strftime("%Y-%m-%d")
    url = cs.normalise_url(row.get("url", ""))
    checks = {"link_works": False, "about_ai": False, "not_on_site": True, "has_build_details": False}
    out = {"status": "checked", "checks": checks}
    saved_urls = {p["url"] for p in posts} | {u for p in posts for u in p.get("aliases", [])}
    if url in saved_urls:
        checks["not_on_site"] = False
        return {**out, "status": "duplicate"}
    ok, page = (False, "") if blocked(url) else fetch(url)
    checks["link_works"] = ok
    if not ok:
        return out
    title = page_title(page) or url.rsplit("/", 1)[-1].replace("-", " ")
    company = company_of(url, page)
    text = cs.article_text(page, 4000)
    post = {"url": url, "company": company, "title": title, "published": "", "text": text}
    out.update(title=title, company=company)
    known_titles = {cs.title_key(p.get("title", ""), p.get("company", "")) for p in posts}
    if cs.title_key(title, company) in known_titles:
        checks["not_on_site"] = False
        return {**out, "status": "duplicate"}
    checks["about_ai"] = cs.looks_like_ai(post)
    if not checks["about_ai"]:
        return out
    result, kind = sorter(post)
    if result is None:
        checks["groq"] = "failed"
        return {**out, "status": "new"}  # asked again on the next run
    checks["announcement"] = kind in ("launch", "event")
    checks["kind"] = kind or "build"
    if result.get("keep"):
        card = cs.groq_record(post, result, today, cs.known_categories(posts))
        finder = result.get("finder") or {}
        out.update(topic=card["problem"], techniques=finder.get("techniques"), industry=finder.get("industry"),
                   build_details=finder.get("build_details"), build_score=finder.get("build_score"),
                   problem=card.get("issue", ""), solution=card.get("summary", ""), card=card)
        checks["has_build_details"] = (finder.get("build_score") or 0) >= 3
    return out


def publish(rows: list[dict], posts: list[dict], today: str) -> list[dict]:
    """The approved rows not on the site yet, as cases.json records (with suggested_by when credited)."""
    urls = {p["url"] for p in posts} | {u for p in posts for u in p.get("aliases", [])}
    titles = {cs.title_key(p.get("title", ""), p.get("company", "")) for p in posts}
    added = []
    for row in rows:
        card = row.get("card")
        if row.get("status") != "approved" or not isinstance(card, dict) or not card.get("url"):
            continue
        key = cs.title_key(card.get("title", ""), card.get("company", ""))
        if card["url"] in urls or key in titles:
            continue
        record = {k: v for k, v in card.items() if k != "suggested_by"}
        record["added"] = today
        record["published"] = record.get("published") or today
        record["suggested"] = True
        credit = clean_credit(row.get("credit"))
        if credit:
            record["suggested_by"] = credit
        added.append(record)
        urls.add(card["url"])
        titles.add(key)
    return added


# ---------- Supabase (service key, REST)

def _config() -> dict | None:
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    return {"url": url, "key": key} if url and key else None


def _headers(cfg: dict) -> dict:
    return {"apikey": cfg["key"], "Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json"}


def fetch_rows(cfg: dict, status: str, limit: int, session=None) -> list[dict]:
    import requests
    session = session or requests
    r = session.get(f"{cfg['url']}/rest/v1/case_suggestions", headers=_headers(cfg), timeout=TIMEOUT,
                    params={"status": f"eq.{status}", "order": "created_at.asc", "limit": str(limit), "select": "*"})
    if r.status_code >= 300:
        raise RuntimeError(f"({r.status_code}) {r.text[:200]}")
    return r.json()


def save_row(cfg: dict, row_id: int, patch: dict, session=None) -> None:
    import requests
    session = session or requests
    r = session.patch(f"{cfg['url']}/rest/v1/case_suggestions", headers={**_headers(cfg), "Prefer": "return=minimal"},
                      params={"id": f"eq.{row_id}"}, json=patch, timeout=TIMEOUT)
    if r.status_code >= 300:
        raise RuntimeError(f"({r.status_code}) {r.text[:200]}")


def run(path: str = cs.CASES_FILE, cfg: dict | None = None, session=None, fetch=fetch_page, sorter=sort_and_tag,
        max_per_run: int = MAX_PER_RUN, today: str = "") -> dict:
    """Check the new suggestions and publish the approved ones. Returns what happened."""
    cfg = cfg or _config()
    counts = {"checked": 0, "duplicate": 0, "waiting": 0, "failed": 0, "groq": 0, "published": 0}
    if not cfg:
        print("  [suggest] SUPABASE_URL or SUPABASE_SECRET_KEY not set; suggestions skipped.")
        return counts
    today = today or datetime.now(cs.IST).strftime("%Y-%m-%d")
    saved = cs.load_all(path)
    posts = saved.get("posts", [])
    try:
        new_rows = fetch_rows(cfg, "new", max_per_run, session)
    except Exception as exc:
        print(f"  [suggest] Could not read suggestions ({str(exc)[:120]}); run supabase/schema.sql to add the table.")
        return counts
    groq_ok = bool(os.environ.get("GROQ_API_KEY", "").strip()) or sorter is not sort_and_tag

    def counted_sorter(post):
        if not groq_ok:
            return None, ""
        counts["groq"] += 1
        try:
            return sorter(post)
        except cs.GroqOutOfCalls as exc:
            print(f"  [suggest] Groq unavailable ({exc})")
            return None, ""

    for row in new_rows[:max_per_run]:
        try:
            patch = check(row, posts, fetch, counted_sorter, today)
            save_row(cfg, row["id"], patch, session)
            key = "waiting" if patch["status"] == "new" else patch["status"]
            counts[key] = counts.get(key, 0) + 1
        except Exception as exc:  # one bad row never stops the others
            counts["failed"] += 1
            print(f"  [suggest] Suggestion {row.get('id')} skipped ({str(exc)[:100]})")
    try:
        added = publish(fetch_rows(cfg, "approved", 200, session), posts, today)
    except Exception as exc:
        print(f"  [suggest] Could not read approved suggestions ({str(exc)[:100]})")
        added = []
    if added:
        cs.save(posts + added, path, saved.get("rejected", []), saved.get("waiting", 0),
                saved.get("last_fetch", ""), saved.get("queue", []))
    counts["published"] = len(added)
    print(f"  [suggest] {counts['checked']} checked, {counts['duplicate']} already on the site, {counts['waiting']} "
          f"waiting for Groq, {counts['failed']} failed, {counts['groq']} Groq calls, {len(added)} published.")
    return counts


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    run()
