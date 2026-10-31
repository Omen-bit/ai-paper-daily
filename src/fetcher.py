"""
fetcher.py
Fetches AI/ML papers from arXiv and HuggingFace Papers.
Retries on transient errors with exponential backoff.
Strips arXiv version suffixes (v1, v2) before deduplication.
"""

import re
import sys
import time
import requests
import feedparser
from datetime import datetime, timedelta, timezone
from dateutil import parser as dateparser


# All arXiv categories to track
ARXIV_CATEGORIES = [
    "cs.AI",    # Artificial Intelligence
    "cs.LG",    # Machine Learning
    "cs.CL",    # Computation and Language (NLP)
    "cs.CV",    # Computer Vision
    "cs.NE",    # Neural and Evolutionary Computing
    "cs.RO",    # Robotics
    "stat.ML",  # Statistical Machine Learning
]

ARXIV_API_BASE = "https://export.arxiv.org/api/query"
REQUEST_TIMEOUT = 15
USER_AGENT = "ai-paper-daily/1.0 (https://github.com/Omen-bit/ai-paper-daily)"
RETRY_DELAYS = [2, 4, 8]  # seconds between attempts 1, 2, 3

_TRANSIENT_ERRORS = ("timeout", "Timeout", "ConnectionError", "503", "502", "500", "429")


def get_default_lookback_hours() -> int:
    """
    arXiv does not publish new papers over the weekend (Friday night to Sunday night UTC).
    On Friday, Saturday, Sunday, and Monday, use a 96-hour lookback window so weekend
    and Monday runs always capture the latest research.
    """
    now = datetime.now(timezone.utc)
    # 4: Friday, 5: Saturday, 6: Sunday, 0: Monday
    if now.weekday() in (4, 5, 6, 0):
        return 96
    return 48


def _strip_version(arxiv_id: str) -> str:
    """Remove version suffix from arXiv ID: '2301.00234v2' -> '2301.00234'."""
    return re.sub(r"v\d+$", "", arxiv_id.strip())


def _is_transient(error_str: str) -> bool:
    return any(t in error_str for t in _TRANSIENT_ERRORS)


def _fetch_with_retry(fetch_fn, source_name: str):
    """
    Call fetch_fn() up to 3 times with exponential backoff on transient errors.
    Returns the result of fetch_fn() on success, or None on all-fail.
    """
    last_error = None
    for attempt, delay in enumerate(RETRY_DELAYS, 1):
        try:
            return fetch_fn()
        except Exception as exc:
            error_str = str(exc)
            last_error = error_str
            if _is_transient(error_str) and attempt < len(RETRY_DELAYS):
                print(f"  [{source_name}] Attempt {attempt} failed ({error_str[:60]}), retrying in {delay}s...")
                time.sleep(delay)
            else:
                print(f"  [{source_name}] Attempt {attempt} failed: {error_str[:100]}")
                break
    print(f"  [{source_name}] All retries exhausted. Last error: {last_error[:120]}")
    return None


def fetch_arxiv_papers(max_results: int = 150, lookback_hours: int = None) -> list[dict]:
    """
    Fetch recent papers from arXiv across all tracked categories.
    Uses dynamic lookback window (96h on weekends/Mondays, 48h on weekdays).
    Strips version suffixes from arXiv IDs before returning.
    """
    if lookback_hours is None:
        lookback_hours = get_default_lookback_hours()

    query = "+OR+".join([f"cat:{cat}" for cat in ARXIV_CATEGORIES])
    url = (
        f"{ARXIV_API_BASE}?search_query={query}"
        f"&sortBy=submittedDate&sortOrder=descending"
        f"&max_results={max_results}"
    )

    print(f"  [arxiv] Fetching from {len(ARXIV_CATEGORIES)} categories (last {lookback_hours}h window)...")

    def _do_fetch():
        # feedparser does its own HTTP; wrap in requests first to get retry on transport errors
        resp = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        if resp.status_code == 429:
            raise Exception(f"429 rate limited by arXiv")
        if resp.status_code >= 500:
            raise Exception(f"{resp.status_code} server error from arXiv")
        return feedparser.parse(resp.text)

    feed = _fetch_with_retry(_do_fetch, "arxiv")
    if feed is None:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    papers = []

    for entry in feed.entries:
        try:
            submitted_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            if submitted_dt < cutoff:
                continue

            raw_id = entry.id.split("/abs/")[-1]
            arxiv_id = _strip_version(raw_id)

            abstract = " ".join(entry.summary.replace("\n", " ").split())
            title = " ".join(entry.title.replace("\n", " ").split())

            paper = {
                "id": arxiv_id,
                "title": title,
                "authors": [a.name for a in entry.authors],
                "abstract": abstract,
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
                "submitted": submitted_dt.strftime("%Y-%m-%d"),
                "submitted_dt": submitted_dt,
                "arxiv_categories": [tag.term for tag in entry.tags if "." in tag.term],
                "source": "arXiv",
                "hf_upvotes": 0,
            }
            papers.append(paper)

        except Exception as exc:
            print(f"  [arxiv] Skipping entry due to parse error: {exc}")
            continue

    print(f"  [arxiv] {len(papers)} papers fetched from last {lookback_hours}h")
    return papers


def fetch_hf_papers() -> list[dict]:
    """
    Fetch trending papers from HuggingFace Papers daily endpoint.
    HF papers are community-curated and represent the most talked-about research.
    Strips version suffixes from arXiv IDs before returning.
    """
    print("  [hf] Fetching HuggingFace trending feed...")

    def _do_fetch():
        resp = requests.get(
            "https://huggingface.co/api/daily_papers",
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        if resp.status_code == 429:
            raise Exception("429 rate limited by HuggingFace")
        if resp.status_code >= 500:
            raise Exception(f"{resp.status_code} server error from HuggingFace")
        resp.raise_for_status()
        return resp.json()

    data = _fetch_with_retry(_do_fetch, "hf")
    if data is None:
        return []

    papers = []
    for item in data:
        try:
            paper_info = item.get("paper", {})
            raw_id = paper_info.get("id", "").strip()
            if not raw_id:
                continue
            arxiv_id = _strip_version(raw_id)

            title = paper_info.get("title", "").strip()
            abstract = " ".join(paper_info.get("summary", "").replace("\n", " ").split())
            authors = [a.get("name", "") for a in paper_info.get("authors", []) if a.get("name")]

            published_raw = item.get("publishedAt", "") or paper_info.get("publishedAt", "")
            try:
                submitted_dt = (
                    dateparser.parse(published_raw).replace(tzinfo=timezone.utc)
                    if published_raw
                    else datetime.now(timezone.utc)
                )
            except Exception:
                submitted_dt = datetime.now(timezone.utc)

            # Robust upvote extraction from item or paper_info
            raw_upvotes = item.get("upvotes")
            if raw_upvotes is None:
                raw_upvotes = paper_info.get("upvotes", 0)
            upvotes = int(raw_upvotes) if raw_upvotes is not None else 0

            paper = {
                "id": arxiv_id,
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
                "submitted": submitted_dt.strftime("%Y-%m-%d"),
                "submitted_dt": submitted_dt,
                "arxiv_categories": paper_info.get("arxivCategories", []),
                "source": "HuggingFace",
                "hf_upvotes": upvotes,
                "github_repo": paper_info.get("githubRepo") or "",
            }

            if paper["title"] and paper["abstract"]:
                papers.append(paper)

        except Exception as exc:
            print(f"  [hf] Skipping item due to parse error: {exc}")
            continue

    print(f"  [hf] {len(papers)} trending papers fetched")
    return papers


def fetch_all_papers(max_arxiv: int = 150) -> list[dict]:
    """
    Fetch from both sources, deduplicate by arXiv ID (version-stripped), return unified list.
    """
    arxiv_papers = fetch_arxiv_papers(max_results=max_arxiv)
    hf_papers = fetch_hf_papers()

    if not arxiv_papers and not hf_papers:
        print("  [fetch] WARNING: Both arXiv and HuggingFace returned no papers.")
        return []

    if not arxiv_papers:
        print("  [fetch] INFO: arXiv returned 0 papers (e.g. weekend/holiday); continuing with HuggingFace only.")
    if not hf_papers:
        print("  [fetch] INFO: HuggingFace returned 0 papers; continuing with arXiv only.")

    # Deduplicate by version-stripped arXiv ID
    paper_map: dict[str, dict] = {}

    for p in arxiv_papers:
        paper_map[p["id"]] = p

    for p in hf_papers:
        pid = p["id"]
        if pid in paper_map:
            paper_map[pid]["hf_upvotes"] = max(paper_map[pid].get("hf_upvotes", 0), p["hf_upvotes"])
            paper_map[pid]["source"] = "arXiv + HuggingFace"
            if p.get("github_repo"):
                paper_map[pid]["github_repo"] = p["github_repo"]
        else:
            paper_map[pid] = p

    result = list(paper_map.values())
    print(f"  [fetch] {len(result)} unique papers after deduplication")
    _fill_missing_arxiv_categories(result)
    return result


def _fill_missing_arxiv_categories(papers: list[dict]) -> None:
    """
    HuggingFace items usually carry no arXiv categories, which leaves the classifier
    without its category signal. Look them up in one batched arXiv id_list query.
    Leaves papers unchanged if the lookup fails.
    """
    missing = [p for p in papers if not p.get("arxiv_categories") and p.get("id")]
    if not missing:
        return

    ids = ",".join(p["id"] for p in missing)
    url = f"{ARXIV_API_BASE}?id_list={ids}&max_results={len(missing)}"

    def _do_fetch():
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
        if resp.status_code == 429:
            raise Exception("429 rate limited by arXiv")
        if resp.status_code >= 500:
            raise Exception(f"{resp.status_code} server error from arXiv")
        return feedparser.parse(resp.text)

    feed = _fetch_with_retry(_do_fetch, "arxiv-categories")
    if feed is None:
        return

    cats_by_id = {}
    for entry in feed.entries:
        try:
            arxiv_id = _strip_version(entry.id.split("/abs/")[-1])
            cats_by_id[arxiv_id] = [tag.term for tag in entry.tags if "." in tag.term]
        except Exception:
            continue

    filled = 0
    for p in missing:
        if cats_by_id.get(p["id"]):
            p["arxiv_categories"] = cats_by_id[p["id"]]
            filled += 1
    print(f"  [fetch] arXiv categories filled for {filled}/{len(missing)} HuggingFace papers")
