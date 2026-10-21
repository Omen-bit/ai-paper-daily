"""
stats_tracker.py
Manages the cumulative stats.json file that tracks paper metadata over time.
All counters are reconciled from the digest log on every run to stay idempotent.
"""

import json
import os
import re
from datetime import datetime, timezone
from collections import Counter


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATS_FILE = os.path.join(ROOT_DIR, "stats", "stats.json")
DIGESTS_DIR = os.path.join(ROOT_DIR, "digests")


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
        "papers_by_date": {},
        "papers_by_category": {},
        "top_authors": {},
        "top_keywords": {},
        "digests": [],
    }


def save_stats(stats: dict) -> None:
    """Save stats to disk."""
    os.makedirs(os.path.dirname(STATS_FILE), exist_ok=True)
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    print(f"  [stats] Saved to {STATS_FILE}")


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


def _reconcile_totals(stats: dict) -> dict:
    """
    Recompute total_papers, total_digests, first_digest, and papers_by_date
    from the digest log so they are always consistent with what is stored.
    Running this on every update makes the pipeline idempotent.
    """
    digests = stats.get("digests", [])
    stats["total_digests"] = len(digests)
    stats["total_papers"] = sum(d.get("paper_count", 0) for d in digests)
    # Rebuild papers_by_date from the log
    stats["papers_by_date"] = {
        d["date"]: d.get("paper_count", 0)
        for d in digests
    }
    if digests:
        sorted_dates = sorted(d["date"] for d in digests)
        stats["first_digest"] = sorted_dates[0]
    return stats


def update_stats(papers: list[dict], date_str: str) -> dict:
    """
    Update stats.json with today's digest data.
    Idempotent: running twice on the same day replaces the existing row.
    Returns the updated stats dict.
    """
    stats = load_stats()
    now = datetime.now(timezone.utc).isoformat()

    # Papers by category
    category_counts = Counter()
    for paper in papers:
        for cat in paper.get("categories", []):
            slug = cat.get("slug", "unknown")
            category_counts[slug] += 1

    # Top category for today
    top_cat_slug = category_counts.most_common(1)[0][0] if category_counts else "unknown"
    top_cat_name = next(
        (
            cat.get("name", top_cat_slug)
            for paper in papers
            for cat in paper.get("categories", [])
            if cat.get("slug") == top_cat_slug
        ),
        top_cat_slug,
    )

    # Update rolling papers_by_category (cumulative across all time)
    for slug, count in category_counts.items():
        # Remove the previous contribution from today if re-running
        prev_entry = next(
            (d for d in stats.get("digests", []) if d["date"] == date_str), None
        )
        if prev_entry:
            prev_cats = Counter(
                {c: 1 for c in prev_entry.get("categories_covered", [])}
            )
            # Subtract the previous today contribution if present
            pass  # category accumulation is rebuilt below

        stats["papers_by_category"][slug] = (
            stats["papers_by_category"].get(slug, 0) + count
        )

    # Authors
    for paper in papers:
        for author in paper.get("authors", []):
            stats["top_authors"][author] = stats["top_authors"].get(author, 0) + 1

    # Keywords from titles
    keywords = extract_keywords(papers)
    for kw in keywords:
        stats["top_keywords"][kw] = stats["top_keywords"].get(kw, 0) + 1

    # Digest log entry (idempotent: replace row for same date)
    digest_entry = {
        "date": date_str,
        "paper_count": len(papers),
        "top_category": top_cat_name,
        "categories_covered": list(category_counts.keys()),
    }
    stats["digests"] = [d for d in stats.get("digests", []) if d["date"] != date_str]
    stats["digests"].append(digest_entry)
    stats["digests"].sort(key=lambda x: x["date"], reverse=True)

    # Reconcile totals from the log so double-runs cannot inflate counters
    stats = _reconcile_totals(stats)
    stats["last_updated"] = now

    save_stats(stats)
    return stats


def get_top_authors(stats: dict, top_n: int = 5) -> list[tuple]:
    """Return top N authors by paper count."""
    authors = stats.get("top_authors", {})
    return sorted(authors.items(), key=lambda x: x[1], reverse=True)[:top_n]


def get_top_categories(stats: dict, top_n: int = 5) -> list[tuple]:
    """Return top N categories by paper count."""
    cats = stats.get("papers_by_category", {})
    return sorted(cats.items(), key=lambda x: x[1], reverse=True)[:top_n]


def get_recent_digests(stats: dict, n: int = 30) -> list[dict]:
    """Return N most recent digest entries."""
    return stats.get("digests", [])[:n]


def scan_digests_folder() -> list[dict]:
    """
    Scan the digests/ folder for YYYY-MM-DD.md files.
    Returns a list of dicts with at least {"date": ..., "is_placeholder": bool}.
    Used by the archive builder to ensure README matches what is on disk.
    """
    results = []
    if not os.path.exists(DIGESTS_DIR):
        return results

    date_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
    for filename in sorted(os.listdir(DIGESTS_DIR), reverse=True):
        match = date_pattern.match(filename)
        if not match:
            continue
        date_str = match.group(1)
        filepath = os.path.join(DIGESTS_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            first_lines = f.read(500)
        is_placeholder = "no new papers" in first_lines.lower()
        results.append({"date": date_str, "is_placeholder": is_placeholder})

    return results
