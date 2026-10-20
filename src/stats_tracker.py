"""
stats_tracker.py
Manages the cumulative stats.json file that tracks paper metadata over time.
"""

import json
import os
from datetime import datetime, timezone
from collections import Counter


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATS_FILE = os.path.join(ROOT_DIR, "stats", "stats.json")


def load_stats() -> dict:
    """Load existing stats or return a fresh skeleton."""
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    return {
        "total_papers": 0,
        "total_digests": 0,
        "first_digest": None,
        "last_updated": None,
        "papers_by_date": {},       # { "YYYY-MM-DD": count }
        "papers_by_category": {},   # { "slug": count }
        "top_authors": {},          # { "Author Name": count }
        "top_keywords": {},         # { "keyword": count }
        "digests": []               # [{ "date": ..., "paper_count": ..., "top_category": ... }]
    }


def save_stats(stats: dict) -> None:
    """Save stats to disk."""
    os.makedirs(os.path.dirname(STATS_FILE), exist_ok=True)
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    print(f"✅ Stats saved to {STATS_FILE}")


def extract_keywords(papers: list[dict], top_n: int = 20) -> list[str]:
    """Extract simple keyword tokens from paper titles."""
    stopwords = {
        "a", "an", "the", "of", "in", "for", "on", "with", "and", "or",
        "to", "is", "are", "via", "from", "by", "at", "as", "be", "its",
        "we", "our", "new", "using", "based", "large", "model", "models",
        "learning", "neural", "deep", "language", "approach", "method",
        "towards", "through", "toward", "can", "that", "this", "into"
    }
    counter = Counter()
    for paper in papers:
        words = paper.get("title", "").lower().split()
        for word in words:
            word = word.strip(".,():;'\"")
            if len(word) > 3 and word not in stopwords:
                counter[word] += 1

    return [kw for kw, _ in counter.most_common(top_n)]


def update_stats(papers: list[dict], date_str: str) -> dict:
    """
    Update stats.json with today's digest data.
    Returns the updated stats dict.
    """
    stats = load_stats()
    now = datetime.now(timezone.utc).isoformat()

    # Global counters
    stats["total_papers"] += len(papers)
    stats["total_digests"] += 1
    stats["last_updated"] = now

    if stats["first_digest"] is None:
        stats["first_digest"] = date_str

    # Papers by date
    stats["papers_by_date"][date_str] = (
        stats["papers_by_date"].get(date_str, 0) + len(papers)
    )

    # Papers by category
    category_counts = Counter()
    for paper in papers:
        for cat in paper.get("categories", []):
            slug = cat.get("slug", "unknown")
            category_counts[slug] += 1
            stats["papers_by_category"][slug] = (
                stats["papers_by_category"].get(slug, 0) + 1
            )

    # Top category for today
    top_cat_slug = category_counts.most_common(1)[0][0] if category_counts else "unknown"
    top_cat_name = next(
        (cat.get("name", top_cat_slug) for paper in papers for cat in paper.get("categories", []) if cat.get("slug") == top_cat_slug),
        top_cat_slug
    )

    # Authors
    for paper in papers:
        for author in paper.get("authors", []):
            stats["top_authors"][author] = stats["top_authors"].get(author, 0) + 1

    # Keywords from titles
    keywords = extract_keywords(papers)
    for kw in keywords:
        stats["top_keywords"][kw] = stats["top_keywords"].get(kw, 0) + 1

    # Digest log entry
    digest_entry = {
        "date": date_str,
        "paper_count": len(papers),
        "top_category": top_cat_name,
        "categories_covered": list(category_counts.keys()),
    }
    # Avoid duplicate entries for same date
    stats["digests"] = [d for d in stats["digests"] if d["date"] != date_str]
    stats["digests"].append(digest_entry)
    stats["digests"].sort(key=lambda x: x["date"], reverse=True)

    save_stats(stats)
    return stats


def get_top_authors(stats: dict, top_n: int = 5) -> list[tuple[str, int]]:
    """Return top N authors by paper count."""
    authors = stats.get("top_authors", {})
    return sorted(authors.items(), key=lambda x: x[1], reverse=True)[:top_n]


def get_top_categories(stats: dict, top_n: int = 5) -> list[tuple[str, int]]:
    """Return top N categories by paper count."""
    cats = stats.get("papers_by_category", {})
    return sorted(cats.items(), key=lambda x: x[1], reverse=True)[:top_n]


def get_recent_digests(stats: dict, n: int = 30) -> list[dict]:
    """Return N most recent digest entries."""
    return stats.get("digests", [])[:n]
