"""
supabase_sync.py
Uploads paper records from data/ to the Supabase papers table, then asks the
embed function to turn each new paper into a vector for search and For you.

Usage:
  python src/supabase_sync.py          sync the newest day (the daily run)
  python src/supabase_sync.py --all    sync every day in data/daily
  python src/supabase_sync.py --backfill-hf 365
                                       also load a year of Hugging Face daily
                                       papers (search only, no site pages)

Needs SUPABASE_URL, SUPABASE_SECRET_KEY and SYNC_SECRET. When they are not
set the script prints a note and exits 0, so the daily run never fails here.
"""
import os
import sys
import time
from datetime import date, timedelta

import requests

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from site_builder import load_days, merge_papers, DATA_DIR  # noqa: E402
from fetcher import fetch_hf_papers_for_date  # noqa: E402
from classifier import classify_papers  # noqa: E402
from curator import find_code_url  # noqa: E402

BATCH = 200          # rows per upsert request
EMBED_BATCH = 8      # most papers one embed call may take; the function stops early when its CPU time runs low
MAX_EMBED_CALLS = 6000
EMBED_RETRIES = 4    # attempts per call before giving up (CPU limit or cold start errors)
TIMEOUT = 60


def _config() -> dict | None:
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    secret = os.environ.get("SYNC_SECRET", "").strip()
    if not (url and key and secret):
        return None
    return {"url": url, "key": key, "secret": secret}


def _headers(key: str) -> dict:
    headers = {"apikey": key, "Content-Type": "application/json"}
    if key.startswith("eyJ"):  # legacy service_role keys are JWTs and also go in Authorization
        headers["Authorization"] = f"Bearer {key}"
    return headers


def to_row(rec: dict) -> dict:
    """A merged site record as a row of the papers table."""
    return {
        "id": rec["id"],
        "title": rec.get("title", ""),
        "abstract": rec.get("abstract") or "",
        "authors": list(rec.get("authors") or []),
        "categories": list(rec.get("categories") or []),
        "submitted": rec.get("submitted") or None,
        "first_seen": rec.get("first_seen") or None,
        "featured": bool(rec.get("featured")),
        "hf_upvotes": int(rec.get("hf_upvotes") or 0),
        "code_url": rec.get("code_url") or None,
        "source": rec.get("source") or None,
    }


def select_rows(days: list[dict], everything: bool) -> list[dict]:
    """Rows to upload: every paper, or only those in the newest day."""
    if not days:
        return []
    papers = merge_papers(days)
    ids = list(papers) if everything else [p["id"] for p in days[0].get("papers", [])]
    return [to_row(papers[i]) for i in ids if i in papers and papers[i].get("title")]


def upsert(cfg: dict, rows: list[dict], session=requests, keep_existing: bool = False) -> int:
    # The backfill must never overwrite a paper our pipeline already recorded
    mode = "ignore-duplicates" if keep_existing else "merge-duplicates"
    headers = dict(_headers(cfg["key"]), Prefer=f"resolution={mode},return=minimal")
    for start in range(0, len(rows), BATCH):
        chunk = rows[start:start + BATCH]
        r = session.post(f"{cfg['url']}/rest/v1/papers?on_conflict=id", json=chunk,
                         headers=headers, timeout=TIMEOUT)
        if r.status_code >= 300:
            raise RuntimeError(f"Upload failed ({r.status_code}): {r.text[:200]}")
    return len(rows)


def embed_pending(cfg: dict, session=requests, sleep=time.sleep) -> int:
    """Call the embed function until no paper is missing a vector."""
    total = 0
    batch = EMBED_BATCH
    for call in range(MAX_EMBED_CALLS):
        body = None
        for attempt in range(EMBED_RETRIES):
            r = session.post(f"{cfg['url']}/functions/v1/embed", json={"limit": batch},
                             headers={"x-sync-secret": cfg["secret"], "Content-Type": "application/json"},
                             timeout=TIMEOUT)
            if r.status_code < 300:
                body = r.json()
                break
            if r.status_code in (401, 403, 404):  # wrong secret or function missing: retrying won't help
                raise RuntimeError(f"Embedding failed ({r.status_code}): {r.text[:200]}")
            # Hit the CPU limit or a cold start: take fewer papers and try again
            batch = max(1, batch // 2)
            print(f"[supabase] Embed call failed ({r.status_code}), retrying with {batch} per call")
            sleep(2 * (attempt + 1))
        if body is None:
            raise RuntimeError(f"Embedding kept failing after {total} papers ({r.status_code}): {r.text[:200]}")
        total += body.get("embedded", 0)
        if call % 50 == 0:
            print(f"[supabase] Embedded {total} so far, {body.get('remaining', 0)} left")
        if not body.get("remaining") or not body.get("embedded"):
            break
        sleep(0.1)
    return total


def hf_rows(day: str, fetch=fetch_hf_papers_for_date) -> list[dict]:
    """One past day of Hugging Face papers as table rows, classified into our topics."""
    papers = classify_papers(fetch(day))
    rows = []
    for p in papers:
        rows.append(to_row({
            "id": p["id"], "title": p.get("title"), "abstract": p.get("abstract"),
            "authors": p.get("authors"), "categories": [c["slug"] for c in p.get("categories", [])],
            "submitted": p.get("submitted"), "first_seen": day, "featured": False,
            "hf_upvotes": p.get("hf_upvotes"), "code_url": find_code_url(p), "source": "HuggingFace",
        }))
    return rows


def backfill_hf(cfg: dict, days_back: int, session=requests, fetch=fetch_hf_papers_for_date,
                today: date | None = None, sleep=time.sleep) -> int:
    """Load days_back days of Hugging Face daily papers, oldest first."""
    today = today or date.today()
    total = 0
    pending: list[dict] = []
    for n in range(days_back, 0, -1):
        day = (today - timedelta(days=n)).isoformat()
        try:
            pending.extend(hf_rows(day, fetch))
        except Exception as exc:  # one bad day should not stop a year of backfill
            print(f"[supabase] Skipped {day}: {exc}")
        if len(pending) >= BATCH or n == 1:
            total += upsert(cfg, pending, session, keep_existing=True)
            print(f"[supabase] Backfill reached {day}, {total} papers so far")
            pending = []
        sleep(0.3)
    return total


def sync(everything: bool = False, data_dir: str = DATA_DIR, session=requests, backfill_days: int = 0) -> int:
    cfg = _config()
    if not cfg:
        print("[supabase] SUPABASE_URL, SUPABASE_SECRET_KEY or SYNC_SECRET not set; skipping sync.")
        return 0
    rows = select_rows(load_days(data_dir), everything)
    if rows:
        print(f"[supabase] Uploading {len(rows)} papers...")
        upsert(cfg, rows, session)
    if backfill_days:
        print(f"[supabase] Loading {backfill_days} days of Hugging Face papers...")
        backfill_hf(cfg, backfill_days, session)
    print(f"[supabase] Embedded {embed_pending(cfg, session)} papers.")
    return len(rows)


def main() -> int:
    try:
        days = 0
        if "--backfill-hf" in sys.argv:
            days = int(sys.argv[sys.argv.index("--backfill-hf") + 1])
        sync(everything="--all" in sys.argv or days > 0, backfill_days=days)
    except Exception as exc:  # never fail the daily run because of search
        print(f"[supabase] Sync failed: {exc}")
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::warning title=Supabase sync failed::{str(exc)[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
