"""
fetcher.py
Fetches AI/ML papers from arXiv and HuggingFace Papers.
"""

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

ARXIV_API_BASE = "http://export.arxiv.org/api/query"


def fetch_arxiv_papers(max_results: int = 150, lookback_hours: int = 48) -> list[dict]:
    """
    Fetch recent papers from arXiv across all tracked categories.
    Uses a 48-hour lookback window to handle timezone differences and weekends.
    """
    query = "+OR+".join([f"cat:{cat}" for cat in ARXIV_CATEGORIES])
    url = (
        f"{ARXIV_API_BASE}?search_query={query}"
        f"&sortBy=submittedDate&sortOrder=descending"
        f"&max_results={max_results}"
    )

    print(f"📡 Fetching arXiv papers from {len(ARXIV_CATEGORIES)} categories...")

    try:
        feed = feedparser.parse(url)
    except Exception as e:
        print(f"❌ arXiv fetch error: {e}")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    papers = []

    for entry in feed.entries:
        try:
            # Parse submission date
            submitted_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            if submitted_dt < cutoff:
                continue

            arxiv_id = entry.id.split("/abs/")[-1]

            # Clean up abstract (remove extra whitespace/newlines)
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

        except Exception as e:
            print(f"⚠️ Skipping entry due to parse error: {e}")
            continue

    print(f"✅ arXiv: fetched {len(papers)} papers from last {lookback_hours}h")
    return papers


def fetch_hf_papers() -> list[dict]:
    """
    Fetch trending papers from HuggingFace Papers daily endpoint.
    HF papers are community-curated and represent the most talked-about research.
    """
    print("📡 Fetching HuggingFace Papers trending feed...")

    try:
        url = "https://huggingface.co/api/daily_papers"
        resp = requests.get(url, timeout=20, headers={"User-Agent": "ai-paper-daily/1.0"})
        resp.raise_for_status()
        data = resp.json()

        papers = []
        for item in data:
            paper_info = item.get("paper", {})
            arxiv_id = paper_info.get("id", "").strip()
            if not arxiv_id:
                continue

            title = paper_info.get("title", "").strip()
            abstract = " ".join(paper_info.get("summary", "").replace("\n", " ").split())
            authors = [a.get("name", "") for a in paper_info.get("authors", []) if a.get("name")]

            # Parse submitted date
            published_raw = item.get("publishedAt", "") or paper_info.get("publishedAt", "")
            try:
                submitted_dt = dateparser.parse(published_raw).replace(tzinfo=timezone.utc) if published_raw else datetime.now(timezone.utc)
            except Exception:
                submitted_dt = datetime.now(timezone.utc)

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
                "hf_upvotes": item.get("upvotes", 0),
            }

            if paper["title"] and paper["abstract"]:
                papers.append(paper)

        print(f"✅ HuggingFace: fetched {len(papers)} trending papers")
        return papers

    except Exception as e:
        print(f"⚠️ HuggingFace fetch failed: {e}")
        return []


def fetch_all_papers(max_arxiv: int = 150) -> list[dict]:
    """
    Fetch from both sources, deduplicate by arXiv ID, and return unified list.
    HuggingFace papers are boosted (higher hf_upvotes signal).
    """
    arxiv_papers = fetch_arxiv_papers(max_results=max_arxiv)
    hf_papers = fetch_hf_papers()

    # Build a dict keyed by arxiv ID for deduplication
    paper_map: dict[str, dict] = {}

    # Add arXiv papers first
    for p in arxiv_papers:
        paper_map[p["id"]] = p

    # Merge HF papers — if already present, update with HF upvotes + source tag
    for p in hf_papers:
        pid = p["id"]
        if pid in paper_map:
            paper_map[pid]["hf_upvotes"] = p["hf_upvotes"]
            paper_map[pid]["source"] = "arXiv + HuggingFace"
        else:
            paper_map[pid] = p

    result = list(paper_map.values())
    print(f"\n📚 Total unique papers after deduplication: {len(result)}")
    return result
