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
from datetime import datetime, timedelta, timezone

import labs

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SRC_DIR)
DATA_DIR = os.path.join(ROOT_DIR, "data")

SCHEMA_VERSION = 1

# The pipeline reads every new arXiv paper (often 1,000+ a day) but only the
# best of them are written to data/, so the repo stays small. The rest were
# still considered for the day's picks.
KEEP_PER_DAY = 200


def _category_slugs(categories: list) -> list[str]:
    """Categories arrive as classifier dicts or as bare slugs (from older records)."""
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
        "slot": paper.get("slot") if featured else None,
        "summary": summary,
        "curator": paper.get("curator"),
        "code_url": paper.get("code_url") or None,
        "org": paper.get("org") or labs.detect(paper) or None,
        "org_avatar": labs.hf_avatar(paper.get("hf_org")) or paper.get("org_avatar") or None,
        "first_seen": date_str,
    }


def to_paper(record: dict) -> dict:
    """
    A saved record back into a pipeline paper, so a past day's candidates can be
    scored again. Notes, summaries and badges are left behind: a new pick gets fresh ones.
    """
    return {
        "id": record["id"],
        "title": record.get("title") or "",
        "authors": list(record.get("authors") or []),
        "abstract": record.get("abstract") or "",
        "url": record.get("url") or f"https://arxiv.org/abs/{record['id']}",
        "pdf_url": record.get("pdf_url") or f"https://arxiv.org/pdf/{record['id']}",
        "submitted": record.get("submitted") or "",
        "arxiv_categories": list(record.get("arxiv_categories") or []),
        "categories": _category_slugs(record.get("categories")),
        "source": record.get("source") or "",
        "hf_upvotes": record.get("hf_upvotes") or 0,
        "code_url": record.get("code_url"),
        "org": record.get("org"),
        "org_avatar": record.get("org_avatar"),
    }


def load_day(date_str: str, data_dir: str = DATA_DIR) -> dict | None:
    """One saved day as written by save_day, or None when it is missing or damaged."""
    path = os.path.join(data_dir, "daily", f"{date_str}.json")
    try:
        with open(path, encoding="utf-8") as f:
            day = json.load(f)
        return day if isinstance(day, dict) and isinstance(day.get("papers"), list) else None
    except (OSError, ValueError):
        return None


def previous_day(before: str, data_dir: str = DATA_DIR, max_gap: int = 4) -> dict | None:
    """The newest saved day before `before` (YYYY-MM-DD), at most max_gap days earlier."""
    start = datetime.strptime(before, "%Y-%m-%d").date()
    for back in range(1, max_gap + 1):
        day = load_day((start - timedelta(days=back)).isoformat(), data_dir)
        if day:
            return day
    return None


def _write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def save_day(all_papers: list[dict], selected: list[dict], date_str: str,
             data_dir: str = DATA_DIR, keep: int = KEEP_PER_DAY) -> str:
    """
    Write data/daily/<date>.json with the day's featured papers first, then the
    best of the other candidates by score, up to `keep` records in all.
    "scanned" records how many papers the run considered.
    """
    featured_ids = [p["id"] for p in selected]
    # The selected list carries the summaries, so prefer it over all_papers
    by_id = {p["id"]: p for p in all_papers}
    by_id.update({p["id"]: p for p in selected})

    records = [to_record(p, date_str, p["id"] in featured_ids) for p in by_id.values()]
    records.sort(key=lambda r: (not r["featured"], -(r["score"] or 0)))
    scanned = len(records)
    records = records[:max(keep, len(featured_ids))]

    day = {
        "schema_version": SCHEMA_VERSION,
        "date": date_str,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "featured": featured_ids,
        "scanned": scanned,
        "papers": records,
    }
    path = os.path.join(data_dir, "daily", f"{date_str}.json")
    _write_json(path, day)
    rebuild_index(data_dir)
    print(f"  [store] Saved the best {len(records)} of {scanned} papers to {path}")
    return path


def recent_featured(days: int = 7, data_dir: str = DATA_DIR) -> set[str]:
    """Ids of the papers featured in the last few editions, so they aren't picked again."""
    path = os.path.join(data_dir, "index.json")
    if not os.path.exists(path):
        return set()
    try:
        with open(path, encoding="utf-8") as f:
            index = json.load(f)
        return {pid for day in index.get("days", [])[:days] for pid in day.get("featured", [])}
    except (OSError, ValueError, AttributeError, TypeError) as exc:
        print(f"  [store] WARNING: could not read {path} ({exc}); recent picks may repeat today")
        return set()


def rebuild_index(data_dir: str = DATA_DIR) -> dict:
    """Regenerate data/index.json and data/latest.json from the daily files."""
    daily_dir = os.path.join(data_dir, "daily")
    days = []
    unique_ids = set()
    if os.path.isdir(daily_dir):
        for name in sorted(os.listdir(daily_dir), reverse=True):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(daily_dir, name), encoding="utf-8") as f:
                    day = json.load(f)
                day["date"]
            except (OSError, ValueError, KeyError, TypeError) as exc:  # skip a damaged day, keep the rest
                print(f"  [store] WARNING: skipped {name}, it could not be read ({exc})")
                continue
            unique_ids.update(p["id"] for p in day.get("papers", []) if isinstance(p, dict) and "id" in p)
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
