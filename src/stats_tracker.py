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
    """Load existing stats or return a fresh skeleton reconciled from digests folder."""
    stats = None
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                stats = json.load(f)
        except Exception as exc:
            print(f"  [stats] Warning: Could not parse {STATS_FILE} ({exc}); rebuilding from digests.")
            stats = None

    if not stats or not isinstance(stats, dict):
        stats = {
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

    stats = reconcile_from_disk(stats)
    save_stats(stats)
    return stats


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


def _parse_digest_file(filepath: str) -> list[dict]:
    """Parse paper records (id, title, authors, categories) from a digest markdown file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return []

    if "no new papers" in text.lower():
        return []

    try:
        from classifier import CATEGORIES
    except ImportError:
        try:
            from .classifier import CATEGORIES
        except ImportError:
            CATEGORIES = []

    blocks = re.split(r"\n#{3,4}\s+\d+\.\s+\[", text)[1:]
    papers = []
    for block in blocks:
        block = block.split("\n---\n")[0]
        first_line = block.split("\n")[0]
        title_part = first_line.split("](")[0]
        title = re.sub(
            r"^[\U0001F300-\U0001FFFF\u2600-\u26FF\u2700-\u27BF⭐🔥💡📖🔀\s]+", "", title_part
        ).strip()
        url = first_line.split("](")[1].rstrip(")") if "](" in first_line else ""

        arxiv_id = ""
        if "/abs/" in url:
            arxiv_id = url.split("/abs/")[-1]
        elif "/papers/" in url:
            arxiv_id = url.split("/papers/")[-1]

        # Extract categories from category chips in block
        paper_cats = []
        for cat in CATEGORIES:
            emoji, name, slug = cat[0], cat[1], cat[2]
            if name in block:
                paper_cats.append(slug)

        # Extract authors
        authors = []
        auth_match = re.search(r"Authors:\*\*\s*(.+)", block)
        if auth_match:
            raw = auth_match.group(1).split("*+")[0].replace("et al.", "").strip("., *")
            authors = [a.strip() for a in raw.split(",") if a.strip()]

        date_match = re.search(r"\*\*Date:\*\*\s*(\d{4}-\d{2}-\d{2})", block)

        papers.append({
            "id": arxiv_id,
            "title": title,
            "url": url,
            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else "",
            "submitted": date_match.group(1) if date_match else "",
            "authors": authors,
            "categories": paper_cats,
        })

    return papers


def _recompute_all(stats: dict) -> dict:
    """
    Recompute all totals and distributions from stored data across all digests.
    Deduplicates papers by date and paper ID so multiple runs on the same date
    cannot inflate counters or corrupt statistics.
    """
    digests = stats.get("digests", [])

    unique_papers = {}
    papers_by_date = Counter()

    for d in digests:
        date = d.get("date", "")
        for p in d.get("papers", []):
            pid = p.get("id") or p.get("title", "")
            key = (date, pid)
            if key not in unique_papers:
                unique_papers[key] = p
                papers_by_date[date] += 1

    # Fallback for digests where full paper records were not yet stored
    for d in digests:
        date = d.get("date", "")
        if date not in papers_by_date and d.get("paper_count", 0) > 0:
            papers_by_date[date] = d.get("paper_count", 0)

    # Recompute category counts and author counts strictly from unique papers
    if unique_papers:
        cat_counts = Counter()
        author_counts = Counter()
        stopwords = {
            "a", "an", "the", "of", "in", "for", "on", "with", "and", "or",
            "to", "is", "are", "via", "from", "by", "at", "as", "be", "its",
            "we", "our", "new", "using", "based", "large", "model", "models",
            "learning", "neural", "deep", "language", "approach", "method",
            "towards", "through", "toward", "can", "that", "this", "into"
        }
        keyword_counts = Counter()

        for p in unique_papers.values():
            for c in p.get("categories", []):
                slug = c if isinstance(c, str) else c.get("slug", "unknown")
                cat_counts[slug] += 1
            for author in p.get("authors", []):
                author_counts[author] += 1
            for word in p.get("title", "").lower().split():
                word = word.strip(".,():;'\"")
                if len(word) > 3 and word not in stopwords:
                    keyword_counts[word] += 1

        stats["papers_by_category"] = dict(cat_counts)
        stats["top_authors"] = dict(author_counts)
        stats["top_keywords"] = dict(keyword_counts)

    valid_editions = [d for d in digests if d.get("paper_count", 0) > 0]
    stats["total_digests"] = len(valid_editions)
    stats["total_papers"] = sum(papers_by_date.values())
    stats["papers_by_date"] = dict(papers_by_date)

    if digests:
        sorted_dates = sorted(d["date"] for d in digests)
        stats["first_digest"] = sorted_dates[0]
    else:
        stats["first_digest"] = None

    return stats


# Alias for backwards compatibility
_reconcile_totals = _recompute_all


def _merge_paper_records(stored: list[dict], parsed: list[dict]) -> list[dict]:
    """
    Combine the paper records stored in stats.json with those parsed from the digest file.
    Stored records are the source of truth: they hold the full author list, badges,
    submission date and PDF link, which the Markdown only partly shows. Parsed records
    only fill fields that are missing or empty, and add papers absent from stats.
    """
    if not stored:
        return parsed
    if not parsed:
        return stored

    def _key(p: dict) -> str:
        return p.get("id") or p.get("title", "")

    parsed_by_key = {_key(p): p for p in parsed}
    merged = []
    for record in stored:
        fill = parsed_by_key.pop(_key(record), {})
        for field, value in fill.items():
            if value and not record.get(field):
                record[field] = value
        merged.append(record)
    merged.extend(parsed_by_key.values())
    return merged


def reconcile_from_disk(stats: dict) -> dict:
    """
    Dynamically reconcile stats.json against the digests/ folder.
    Removes phantom digests, parses missing/corrupted entries from disk,
    and repairs all aggregate totals.
    """
    if not os.path.exists(DIGESTS_DIR):
        return _recompute_all(stats)

    disk_entries = scan_digests_folder()
    disk_dates = {e["date"] for e in disk_entries}

    # Filter out any digests from stats that do not actually exist on disk
    existing_digests = [d for d in stats.get("digests", []) if d.get("date") in disk_dates]
    digests_by_date = {d["date"]: d for d in existing_digests}

    for disk_entry in disk_entries:
        date_str = disk_entry["date"]
        is_placeholder = disk_entry["is_placeholder"]
        filepath = os.path.join(DIGESTS_DIR, f"{date_str}.md")

        if is_placeholder:
            actual_count = 0
            papers = []
        else:
            papers = _parse_digest_file(filepath)
            actual_count = len(papers)

        if date_str in digests_by_date:
            entry = digests_by_date[date_str]
            entry["paper_count"] = actual_count
            entry["papers"] = _merge_paper_records(entry.get("papers", []), papers)
        else:
            new_entry = {
                "date": date_str,
                "paper_count": actual_count,
                "top_category": "General",
                "categories_covered": [],
                "papers": papers,
            }
            existing_digests.append(new_entry)
            digests_by_date[date_str] = new_entry

    existing_digests.sort(key=lambda x: x["date"], reverse=True)
    stats["digests"] = existing_digests

    return _recompute_all(stats)


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

    paper_records = [
        {
            "id": p.get("id", ""),
            "title": p.get("title", ""),
            "authors": p.get("authors", []),
            "categories": [
                c.get("slug") if isinstance(c, dict) else c
                for c in p.get("categories", [])
            ],
            "badges": p.get("badges", []),
            "url": p.get("url", f"https://arxiv.org/abs/{p.get('id', '')}"),
            "pdf_url": p.get("pdf_url", f"https://arxiv.org/pdf/{p.get('id', '')}"),
            "submitted": p.get("submitted", date_str),
        }
        for p in papers
    ]

    # Digest log entry (idempotent: replace row for same date)
    digest_entry = {
        "date": date_str,
        "paper_count": len(papers),
        "top_category": top_cat_name,
        "categories_covered": list(category_counts.keys()),
        "papers": paper_records,
    }
    stats["digests"] = [d for d in stats.get("digests", []) if d["date"] != date_str]
    stats["digests"].append(digest_entry)
    stats["digests"].sort(key=lambda x: x["date"], reverse=True)

    # Recompute all totals, categories, authors, and keywords from stored data
    stats = _recompute_all(stats)
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
