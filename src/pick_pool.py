"""
pick_pool.py
Which papers the day's picks are chosen from, set by PICK_FROM:

  today      (default) the papers fetched this morning, as before
  yesterday  the previous edition's candidates, with their upvotes refreshed.
             At 07:00 IST a new paper has only had a few hours on Hugging Face,
             so its upvotes say little. A day later they say much more.

Either way, this morning's papers are still saved as today's candidates, so
tomorrow's run can pick from them. If yesterday's candidates can't be read,
or all of them were featured already, the run falls back to today's papers.
scripts/backtest_picker.py --day-late compares the two on past days.
"""
import os
from typing import Callable, Optional

import paper_store

MODES = ("today", "yesterday")


def mode(value: Optional[str] = None) -> str:
    """PICK_FROM, checked. Anything unknown means 'today', with a warning."""
    raw = (value if value is not None else os.environ.get("PICK_FROM", "")).strip().lower()
    if not raw:
        return "today"
    if raw not in MODES:
        print(f"::warning::PICK_FROM={raw!r} is not one of {', '.join(MODES)}; picking from today's papers.")
        return "today"
    return raw


def refresh_upvotes(papers: list[dict], *fresh_lists: list[dict]) -> list[dict]:
    """
    Bring each paper up to date from fresh Hugging Face items: the newest upvote
    count, and its code repo and lab when Hugging Face has them and we didn't.
    A paper found on a list is marked as listed there, like the fetcher does.
    """
    newest: dict[str, dict] = {}
    for items in fresh_lists:
        for item in items or []:
            if not item.get("id") or "HuggingFace" not in (item.get("source") or ""):
                continue
            seen = newest.setdefault(item["id"], {"hf_upvotes": 0})
            seen["hf_upvotes"] = max(seen["hf_upvotes"], int(item.get("hf_upvotes") or 0))
            for key in ("github_repo", "hf_org"):
                if item.get(key) and not seen.get(key):
                    seen[key] = item[key]
    for p in papers:
        seen = newest.get(p["id"])
        if not seen:
            continue
        p["hf_upvotes"] = max(int(p.get("hf_upvotes") or 0), seen["hf_upvotes"])
        if seen.get("github_repo") and not p.get("code_url"):
            p["github_repo"] = seen["github_repo"]
        if seen.get("hf_org") and not p.get("org"):
            p["hf_org"] = seen["hf_org"]
        if "HuggingFace" not in (p.get("source") or ""):
            p["source"] = "arXiv + HuggingFace" if p.get("source") else "HuggingFace"
    return papers


def yesterdays_candidates(today: str, today_papers: list[dict], recent_ids: set,
                          data_dir: str = paper_store.DATA_DIR,
                          fetch_for_date: Optional[Callable[[str], list[dict]]] = None) -> tuple[list[dict], str]:
    """
    The previous saved day's candidates minus anything featured recently, with
    upvotes refreshed from this morning's papers and that day's Hugging Face list.
    Returns (papers, the date they come from); ([], "") when there are none.
    """
    day = paper_store.previous_day(today, data_dir)
    if not day:
        return [], ""
    skip = set(recent_ids) | set(day.get("featured") or [])
    papers = [paper_store.to_paper(r) for r in day["papers"]
              if isinstance(r, dict) and r.get("id") and r["id"] not in skip and r.get("abstract")]
    fresh = []
    if papers and fetch_for_date:
        try:
            fresh = fetch_for_date(day["date"])
        except Exception as exc:  # stale upvotes only make the pick a little less informed
            print(f"::warning::Could not refresh upvotes for {day['date']}, using the saved ones: {exc}")
    return refresh_upvotes(papers, today_papers, fresh), day["date"]


def candidates(today: str, today_papers: list[dict], recent_ids: set, pick_from: Optional[str] = None,
               data_dir: str = paper_store.DATA_DIR,
               fetch_for_date: Optional[Callable[[str], list[dict]]] = None) -> tuple[list[dict], str]:
    """
    The papers to pick from and where they come from ("today" or a past date).
    today_papers should already be filtered for recent picks and classified.
    """
    if mode(pick_from) == "yesterday":
        papers, source = yesterdays_candidates(today, today_papers, recent_ids, data_dir, fetch_for_date)
        if papers:
            print(f"  [pool] Picking from {len(papers)} candidates of {source}, with today's upvotes.")
            return papers, source
        print("::warning::No usable candidates from yesterday; picking from today's papers instead.")
    return today_papers, "today"
