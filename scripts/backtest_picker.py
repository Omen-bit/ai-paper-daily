"""
backtest_picker.py
Replays every saved day in data/daily/ through one or more pickers and checks
how good their choice turned out to be, using Hugging Face upvotes collected
some days later as the measure of "best".

    python scripts/backtest_picker.py              # later upvotes from Hugging Face (needs internet)
    python scripts/backtest_picker.py --offline    # later upvotes from the saved files only (rough)
    python scripts/backtest_picker.py --day-late   # also try picking from yesterday's papers
    python scripts/backtest_picker.py --json out.json

For each day and each picker it records:
  hit       the pick is in the day's top 10 by later upvotes
  pctile    where the pick ranks in the day's pool, 1.0 = the most upvoted paper
  capture   the pick's later upvotes divided by the best paper's later upvotes

Limits worth knowing:
  - The saved pools are the best 200 papers by the scorer of that day, not every
    paper it read, so a new picker is only compared inside that shortlist.
  - Papers that never reach Hugging Face count as 0 upvotes. The target rewards
    what the HF community liked, which is a proxy for "best", not the truth.
  - Days younger than --min-age are skipped, since their upvotes are still growing.
"""
import argparse
import contextlib
import copy
import io
import json
import os
import sys
from datetime import date, timedelta
from typing import Callable, Optional

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
for _path in (SRC_DIR, SCRIPTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import paper_store  # noqa: E402
import scorer  # noqa: E402

DATA_DIR = os.path.join(ROOT_DIR, "data")
CACHE_PATH = os.path.join(ROOT_DIR, ".cache", "backtest", "hf_upvotes.json")
TOP_K = 10
MIN_AGE_DAYS = 3
# A pool holds arXiv papers from the last 2 to 4 days plus that day's HF list,
# so later upvotes are looked up on HF's lists from a few days before to a day after.
HF_DAYS_BEFORE = 4
HF_DAYS_AFTER = 1


# ---------------------------------------------------------------------------
# Loading the saved days
# ---------------------------------------------------------------------------

def to_paper(record: dict) -> dict:
    """A saved record back into the shape the scorer reads. Upvotes are as of that day."""
    return paper_store.to_paper(record)


def load_days(data_dir: str = DATA_DIR) -> list[dict]:
    """
    Every saved day that can be replayed, oldest first: {"date", "featured", "pool"}.
    Days from before full pools were saved (no abstracts) are left out.
    """
    daily_dir = os.path.join(data_dir, "daily")
    days = []
    for name in sorted(os.listdir(daily_dir)) if os.path.isdir(daily_dir) else []:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(daily_dir, name), encoding="utf-8") as f:
                day = json.load(f)
        except (OSError, ValueError) as exc:
            print(f"  [backtest] skipped {name}: {exc}")
            continue
        records = [r for r in day.get("papers", []) if isinstance(r, dict) and r.get("id")]
        if len(records) < 2 or not any(r.get("abstract") for r in records):
            continue
        days.append({
            "date": day.get("date") or name[:-5],
            "featured": list(day.get("featured") or []),
            "pool": [to_paper(r) for r in records],
        })
    return days


def late_days(days: list[dict], max_gap: int = 4) -> list[dict]:
    """
    The same days as PICK_FROM=yesterday would see them: each day's pool is the
    previous saved day's candidates minus the picks of the 7 days before. Their upvotes are the newest
    the saved files show (a paper often appears again the next day), which is a
    little below what a live run would see.
    """
    out = []
    for prev, day in zip(days, days[1:]):
        gap = (date.fromisoformat(day["date"]) - date.fromisoformat(prev["date"])).days
        if gap > max_gap:
            continue
        seen_today = {p["id"]: p for p in day["pool"]}
        d = date.fromisoformat(day["date"])
        recent = {pid for x in days if 0 < (d - date.fromisoformat(x["date"])).days <= 7 for pid in x["featured"]}
        pool = []
        for p in prev["pool"]:
            if p["id"] in recent:
                continue
            p = dict(p)
            again = seen_today.get(p["id"])
            if again:
                p["hf_upvotes"] = max(p.get("hf_upvotes") or 0, again.get("hf_upvotes") or 0)
                p["source"] = again.get("source") or p.get("source")
            pool.append(p)
        if len(pool) >= 2:
            out.append({"date": day["date"], "featured": [], "pool": pool, "from": prev["date"]})
    return out


# ---------------------------------------------------------------------------
# Later upvotes, the measure of "best"
# ---------------------------------------------------------------------------

def upvotes_from_saved(days: list[dict]) -> dict[str, int]:
    """Offline: the most upvotes each paper showed on any saved day. Rough, and low for recent papers."""
    best: dict[str, int] = {}
    for day in days:
        for p in day["pool"]:
            best[p["id"]] = max(best.get(p["id"], 0), int(p.get("hf_upvotes") or 0))
    return best


def hf_dates(days: list[dict], today: Optional[date] = None) -> list[str]:
    """The Hugging Face daily lists to read so every pool's papers are covered."""
    today = today or date.today()
    wanted = set()
    for day in days:
        d = date.fromisoformat(day["date"])
        for offset in range(-HF_DAYS_BEFORE, HF_DAYS_AFTER + 1):
            x = d + timedelta(days=offset)
            if x <= today:
                wanted.add(x.isoformat())
    return sorted(wanted)


def upvotes_from_hf(days: list[dict], cache_path: str = CACHE_PATH, refresh: bool = False,
                    fetch: Optional[Callable[[str], list[dict]]] = None,
                    today: Optional[date] = None) -> dict[str, int]:
    """
    Current upvotes for every paper on HF's daily lists around the saved days.
    Lists are cached per date; lists for the last few days are always fetched
    again, since their upvotes are still moving. Saved upvotes fill any gap.
    """
    if fetch is None:
        from fetcher import fetch_hf_papers_for_date as fetch
    today = today or date.today()
    cache: dict = {}
    if os.path.exists(cache_path) and not refresh:
        try:
            with open(cache_path, encoding="utf-8") as f:
                cache = json.load(f)
        except (OSError, ValueError):
            cache = {}
    settled = (today - timedelta(days=7)).isoformat()
    for d in hf_dates(days, today):
        if d in cache and d < settled:
            continue
        items = fetch(d)
        if items or d not in cache:  # keep an old list rather than an empty failed fetch
            cache[d] = {p["id"]: int(p.get("hf_upvotes") or 0) for p in items}
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=1, sort_keys=True)

    best = upvotes_from_saved(days)
    for votes in cache.values():
        for pid, n in votes.items():
            best[pid] = max(best.get(pid, 0), n)
    return best


# ---------------------------------------------------------------------------
# Pickers: each takes a day's pool and returns paper ids, today's pick first
# ---------------------------------------------------------------------------

def pick_current(pool: list[dict]) -> list[str]:
    """The live picker, scorer.select_daily."""
    return [p["id"] for p in scorer.select_daily(copy.deepcopy(pool))]


def pick_v1(pool: list[dict]) -> list[str]:
    """The picker before the Phase 2 rewrite (scripts/scorer_v1.py), kept for comparison."""
    import scorer_v1
    return [p["id"] for p in scorer_v1.select_daily(copy.deepcopy(pool))]


def pick_upvotes_now(pool: list[dict]) -> list[str]:
    """A simple reference: the most upvoted papers at pick time."""
    ranked = sorted(pool, key=lambda p: -(p.get("hf_upvotes") or 0))
    return [p["id"] for p in ranked[:2]]


# Phase 2 and the LLM judge add their pickers here
PICKERS: dict[str, Callable[[list[dict]], list[str]]] = {
    "current": pick_current,
    "v1": pick_v1,
    "upvotes-now": pick_upvotes_now,
}


# ---------------------------------------------------------------------------
# Scoring the picks
# ---------------------------------------------------------------------------

def is_hit(mine: int, all_votes, top_k: int = TOP_K) -> bool:
    """In the top k by later upvotes. Ties share a place, and 0 upvotes is never a hit."""
    return mine > 0 and sum(1 for v in all_votes if v > mine) < top_k


def random_hit_rate(pool: list[dict], later: dict[str, int], top_k: int = TOP_K) -> float:
    """The chance that a paper picked at random from the pool is a hit."""
    votes = [later.get(p["id"], 0) for p in pool]
    return sum(1 for v in votes if is_hit(v, votes, top_k)) / len(votes) if votes else 0.0


def judge(pick_id: str, pool: list[dict], later: dict[str, int], top_k: int = TOP_K) -> dict:
    """How good one pick turned out to be inside its day's pool."""
    votes = {p["id"]: later.get(p["id"], 0) for p in pool}
    ranked = sorted(votes, key=lambda i: -votes[i])
    best = votes[ranked[0]] if ranked else 0
    mine = votes.get(pick_id, 0)
    # Rank = how many papers did strictly better, so ties share a rank
    better = sum(1 for v in votes.values() if v > mine)
    n = len(pool)
    return {
        "id": pick_id,
        "later_upvotes": mine,
        "best_upvotes": best,
        "hit": is_hit(mine, votes.values(), top_k),
        "pctile": round(1 - better / (n - 1), 3) if n > 1 else 1.0,
        "capture": round(mine / best, 3) if best else 0.0,
    }


def run_backtest(days: list[dict], later: dict[str, int], pickers: dict = PICKERS,
                 min_age: int = MIN_AGE_DAYS, today: Optional[date] = None,
                 top_k: int = TOP_K, quiet: bool = True) -> dict:
    """Every picker on every day old enough to judge. Returns per-day rows and averages."""
    today = today or date.today()
    mature = [d for d in days if (today - date.fromisoformat(d["date"])).days >= min_age]
    rows, summary = [], {}
    for name, picker in pickers.items():
        results = []
        for day in mature:
            with contextlib.redirect_stdout(io.StringIO()) if quiet else contextlib.nullcontext():
                ids = picker(day["pool"])
            if not ids:
                continue
            r = judge(ids[0], day["pool"], later, top_k)
            r.update(picker=name, date=day["date"], pool=len(day["pool"]))
            if len(ids) > 1:
                r["second"] = judge(ids[1], day["pool"], later, top_k)
            results.append(r)
            rows.append(r)
        n = len(results)
        summary[name] = {
            "days": n,
            "hit_rate": round(sum(r["hit"] for r in results) / n, 3) if n else None,
            "mean_pctile": round(sum(r["pctile"] for r in results) / n, 3) if n else None,
            "mean_capture": round(sum(r["capture"] for r in results) / n, 3) if n else None,
            "second_hit_rate": (round(sum(r["second"]["hit"] for r in results if "second" in r)
                                      / max(1, sum(1 for r in results if "second" in r)), 3)
                                if any("second" in r for r in results) else None),
        }
    # What picking at random would score, for scale
    if mature:
        summary["_random"] = {
            "days": len(mature),
            "hit_rate": round(sum(random_hit_rate(d["pool"], later, top_k) for d in mature) / len(mature), 3),
        }
    return {
        "top_k": top_k, "min_age": min_age, "today": today.isoformat(),
        "days_loaded": len(days), "days_judged": len(mature),
        "summary": summary, "rows": rows,
    }


def report(result: dict) -> str:
    """A plain-text table of the averages and each day's pick."""
    lines = [
        f"Backtest of {result['days_judged']} days (of {result['days_loaded']} saved; "
        f"days younger than {result['min_age']} are skipped). Hit = in the day's top {result['top_k']} by later upvotes.",
        "",
        f"{'picker':<14}{'days':>5}{'hit rate':>10}{'2nd hit':>9}{'pctile':>8}{'capture':>9}",
    ]
    for name, s in result["summary"].items():
        if name == "_random":
            continue
        fmt = lambda v: "-" if v is None else f"{v:.2f}"  # noqa: E731
        lines.append(f"{name:<14}{s['days']:>5}{fmt(s['hit_rate']):>10}{fmt(s['second_hit_rate']):>9}"
                     f"{fmt(s['mean_pctile']):>8}{fmt(s['mean_capture']):>9}")
    rnd = result["summary"].get("_random")
    if rnd:
        lines.append(f"{'random':<14}{rnd['days']:>5}{rnd['hit_rate']:>10.2f}")
    lines += ["", f"{'date':<12}{'picker':<14}{'pick':<12}{'upvotes':>8}{'best':>6}{'hit':>5}"]
    for r in sorted(result["rows"], key=lambda r: (r["date"], r["picker"])):
        lines.append(f"{r['date']:<12}{r['picker']:<14}{r['id']:<12}{r['later_upvotes']:>8}"
                     f"{r['best_upvotes']:>6}{'yes' if r['hit'] else 'no':>5}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Backtest the daily paper picker on saved days.")
    ap.add_argument("--offline", action="store_true", help="use only upvotes in the saved files (rough)")
    ap.add_argument("--refresh", action="store_true", help="fetch every Hugging Face list again")
    ap.add_argument("--min-age", type=int, default=MIN_AGE_DAYS, help="skip days younger than this (default 3)")
    ap.add_argument("--day-late", action="store_true",
                    help="also run the current picker on yesterday's papers (PICK_FROM=yesterday)")
    ap.add_argument("--json", metavar="PATH", help="also write the full result as JSON")
    ap.add_argument("--data", default=DATA_DIR, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    days = load_days(args.data)
    if not days:
        print("No saved days with full candidate pools were found in data/daily/.")
        return 1
    later = upvotes_from_saved(days) if args.offline else upvotes_from_hf(days, refresh=args.refresh)
    result = run_backtest(days, later, min_age=args.min_age)
    if args.day_late:
        late = run_backtest(late_days(days), later, pickers={"day-late": pick_current}, min_age=args.min_age)
        result["summary"].update({k: v for k, v in late["summary"].items() if k != "_random"})
        result["rows"] += late["rows"]
    result["upvote_source"] = "saved files" if args.offline else "Hugging Face"
    print(report(result))
    if args.offline:
        print("\nOffline mode: later upvotes come from the saved files only, so recent days read low.")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
