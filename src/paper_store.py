"""
paper_store.py
Saves every paper the pipeline sees as a structured JSON record, so the
website and later features read from data/ instead of parsing Markdown.

Layout:
  data/daily/YYYY-MM-DD.json   all candidate papers for that day, best first
  data/latest.json             copy of the newest daily file
  data/index.json              one entry per day: date, paper count, featured IDs
"""
import json
import os
from datetime import datetime, timezone

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SRC_DIR)
DATA_DIR = os.path.join(ROOT_DIR, "data")

SCHEMA_VERSION = 1


def _category_slugs(categories: list) -> list[str]:
    """Categories arrive as classifier dicts or as bare slugs (from stats.json)."""
    return [c["slug"] if isinstance(c, dict) else c for c in categories or []]


def _badge_labels(badges: list) -> list[str]:
    """Badges arrive as (emoji, label) pairs; keep just the label."""
    labels = []
    for b in badges or []:
        if isinstance(b, (list, tuple)) and len(b) == 2:
            labels.append(b[1])
        elif isinstance(b, str):
            labels.append(b)
    return labels


def to_record(paper: dict, date_str: str, featured: bool) -> dict:
    """Convert an in-memory pipeline paper into a JSON-safe record."""
    summary = None
    if paper.get("why_it_matters"):
        summary = {
            "text": paper["why_it_matters"],
            "source": paper.get("summary_source", "unknown"),
        }
    return {
        "id": paper["id"],
        "title": paper.get("title", ""),
        "authors": list(paper.get("authors", [])),
        "abstract": paper.get("abstract", ""),
        "url": paper.get("url") or f"https://arxiv.org/abs/{paper['id']}",
        "pdf_url": paper.get("pdf_url") or f"https://arxiv.org/pdf/{paper['id']}",
        "submitted": paper.get("submitted", ""),
        "arxiv_categories": list(paper.get("arxiv_categories", [])),
        "categories": _category_slugs(paper.get("categories")),
        "source": paper.get("source", ""),
        "hf_upvotes": paper.get("hf_upvotes", 0),
        "score": paper.get("score"),
        "badges": _badge_labels(paper.get("badges")),
        "featured": featured,
        "summary": summary,
        "first_seen": date_str,
    }


def _write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def save_day(all_papers: list[dict], selected: list[dict], date_str: str,
             data_dir: str = DATA_DIR) -> str:
    """
    Write data/daily/<date>.json with every candidate paper of the run.
    Featured papers come first, then the rest by score.
    """
    featured_ids = [p["id"] for p in selected]
    # The selected list carries the summaries, so prefer it over all_papers
    by_id = {p["id"]: p for p in all_papers}
    by_id.update({p["id"]: p for p in selected})

    records = [to_record(p, date_str, p["id"] in featured_ids) for p in by_id.values()]
    records.sort(key=lambda r: (not r["featured"], -(r["score"] or 0)))

    day = {
        "schema_version": SCHEMA_VERSION,
        "date": date_str,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "featured": featured_ids,
        "papers": records,
    }
    path = os.path.join(data_dir, "daily", f"{date_str}.json")
    _write_json(path, day)
    rebuild_index(data_dir)
    print(f"  [store] Saved {len(records)} paper records to {path}")
    return path


def backfill_from_stats(stats: dict, data_dir: str = DATA_DIR) -> int:
    """
    Create daily files for past digests that predate the paper store.
    Only the featured papers are known for those days. Existing files are kept.
    """
    created = 0
    for digest in stats.get("digests", []):
        date_str = digest.get("date")
        papers = digest.get("papers", [])
        if not date_str or not papers:
            continue
        path = os.path.join(data_dir, "daily", f"{date_str}.json")
        if os.path.exists(path):
            continue
        records = [to_record(p, date_str, True) for p in papers if p.get("id")]
        _write_json(path, {
            "schema_version": SCHEMA_VERSION,
            "date": date_str,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "featured": [r["id"] for r in records],
            "papers": records,
            "backfilled": True,
        })
        created += 1
    if created:
        rebuild_index(data_dir)
        print(f"  [store] Backfilled {created} past days from stats.json")
    return created


def rebuild_index(data_dir: str = DATA_DIR) -> dict:
    """Regenerate data/index.json and data/latest.json from the daily files."""
    daily_dir = os.path.join(data_dir, "daily")
    days = []
    unique_ids = set()
    if os.path.isdir(daily_dir):
        for name in sorted(os.listdir(daily_dir), reverse=True):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(daily_dir, name), encoding="utf-8") as f:
                day = json.load(f)
            unique_ids.update(p["id"] for p in day.get("papers", []))
            days.append({
                "date": day["date"],
                "paper_count": len(day.get("papers", [])),
                "featured": day.get("featured", []),
            })

    index = {
        "schema_version": SCHEMA_VERSION,
        "total_days": len(days),
        "total_papers": len(unique_ids),
        "days": days,
    }
    _write_json(os.path.join(data_dir, "index.json"), index)

    if days:
        latest_src = os.path.join(daily_dir, f"{days[0]['date']}.json")
        with open(latest_src, encoding="utf-8") as f:
            _write_json(os.path.join(data_dir, "latest.json"), json.load(f))
    return index
