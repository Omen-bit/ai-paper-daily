"""
scoreboard.py
Checks the ranking against what happened to each paper 30 days later, and
writes the result to data/scoreboard.json for the Methodology page.

The target is NOT Hugging Face upvotes, which the old backtest used and which
the ranking itself reads (so it could only show we copy HF well). Instead, for
every paper in a saved day's pool:

  citations  Semantic Scholar citation count today
  stars      GitHub stars on the paper's code today (0 when it has no code)
  impact     the average of the two as percentiles within that day's pool

Rankers compared on the same pools:

  live         the score each paper had on the day it was published (whatever scorer ran then)
  hf-upvotes   Hugging Face upvotes at pick time, the baseline the ranking must beat
  v1, v2       the two earlier scorers, replayed on the saved papers
  v3 on saved fields   the current scorer replayed on what was saved (upvotes, code, lab),
                       without the looked-up signals older days don't have
  random       the expected result of picking at random
  live minus <group>   the live score with one signal group taken out (ablation),
                       only for days saved with a per-signal breakdown

Metrics, averaged over days:

  hit       the ranker's top paper is in the day's top 10 by impact
  p10       how many of the ranker's top 10 are in the day's top 10 by impact (0..1)
  spearman  rank correlation between the ranker's order and impact, over the whole pool

    python scripts/scoreboard.py                 # days at least 30 days old
    python scripts/scoreboard.py --min-age 7     # an early look (citations barely exist yet)
    python scripts/scoreboard.py --offline       # outcomes from the cache and data/links.json only
"""
import argparse
import json
import os
import random
import sys
from datetime import date, datetime, timezone
from typing import Callable, Optional

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
for _path in (SRC_DIR, SCRIPTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT_DIR, ".env"))
except ImportError:
    pass

import paper_store  # noqa: E402
import scorer  # noqa: E402
import signals  # noqa: E402

DATA_DIR = os.path.join(ROOT_DIR, "data")
OUT_PATH = os.path.join(DATA_DIR, "scoreboard.json")
CACHE_PATH = os.path.join(DATA_DIR, "scoreboard", "outcomes.json")
MIN_AGE_DAYS = 30
TOP_K = 10
# GitHub calls per run for repos that data/links.json has no stars for
MAX_GITHUB = int(os.environ.get("SCOREBOARD_MAX_GITHUB") or 400)


# ---------------------------------------------------------------- days and outcomes

def load_days(data_dir: str = DATA_DIR, min_age: int = MIN_AGE_DAYS, today: Optional[date] = None) -> list[dict]:
    """Saved days old enough to judge: {"date", "records"} with full records (score_parts included)."""
    today = today or date.today()
    daily = os.path.join(data_dir, "daily")
    out = []
    for name in sorted(os.listdir(daily)) if os.path.isdir(daily) else []:
        if not name.endswith(".json"):
            continue
        d = name[:-5]
        try:
            if (today - date.fromisoformat(d)).days < min_age:
                continue
        except ValueError:
            continue
        day = paper_store.load_day(d, data_dir)
        records = [r for r in (day or {}).get("papers", []) if isinstance(r, dict) and r.get("id") and r.get("abstract")]
        if len(records) >= 2 * TOP_K:
            out.append({"date": d, "records": records})
    return out


def load_cache(path: str = CACHE_PATH) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)


def s2_citations(ids: list[str]) -> dict[str, int]:
    """Citation counts from Semantic Scholar's batch API (500 per call). Unindexed papers are left out."""
    headers = {"x-api-key": os.environ["S2_API_KEY"]} if os.environ.get("S2_API_KEY") else {}
    out = {}
    for start in range(0, len(ids), signals.S2_BATCH):
        chunk = ids[start:start + signals.S2_BATCH]
        rows = signals._post_json("https://api.semanticscholar.org/graph/v1/paper/batch",
                                  {"ids": [f"ARXIV:{i}" for i in chunk]}, headers,
                                  params={"fields": "citationCount"})
        for pid, row in zip(chunk, rows or []):
            if row and row.get("citationCount") is not None:
                out[pid] = int(row["citationCount"])
    return out


def fetch_outcomes(days: list[dict], cache: dict, links: dict, offline: bool = False,
                   cite_fn: Callable = s2_citations, star_fn: Callable = signals.github_repo,
                   today: Optional[str] = None) -> dict:
    """
    Fill cache[id] = {"citations", "stars", "as_of"} for every paper in the days.
    Stars come from data/links.json when it has them (refreshed weekly), else from GitHub.
    A paper is refreshed at most once a week.
    """
    today = today or date.today().isoformat()
    ids = sorted({r["id"] for d in days for r in d["records"]})

    def stale(pid):
        e = cache.get(pid) or {}
        try:
            return (date.fromisoformat(today) - date.fromisoformat(e.get("as_of", "1970-01-01"))).days >= 7
        except ValueError:
            return True

    todo = [pid for pid in ids if stale(pid)]
    cites = {}
    if todo and not offline:
        try:
            cites = cite_fn(todo)
        except Exception as exc:
            print(f"::warning::Semantic Scholar failed, using cached citations: {exc}")
    records = {r["id"]: r for d in days for r in d["records"]}
    github_left = MAX_GITHUB
    for pid in todo:
        e = dict(cache.get(pid) or {})
        if pid in cites:
            e["citations"] = cites[pid]
        stars = (links.get(pid) or {}).get("stars")
        repo = signals.repo_of(records[pid])
        if stars is None and repo and not offline and github_left > 0:
            github_left -= 1
            try:
                stars = (star_fn(repo) or {}).get("stars")
            except Exception as exc:
                print(f"  [scoreboard] GitHub {repo}: {str(exc)[:80]}")
        if stars is not None:
            e["stars"] = int(stars)
        elif not repo:
            e["stars"] = 0
        if "citations" in e or "stars" in e:
            e["as_of"] = today
        cache[pid] = e
    return cache


def percentiles(values: dict[str, float]) -> dict[str, float]:
    """Each id's share of the others it beats (ties share), 0..1."""
    ids = sorted(values, key=lambda k: values[k])
    n = len(ids)
    out, i = {}, 0
    while i < n:
        j = i
        while j + 1 < n and values[ids[j + 1]] == values[ids[i]]:
            j += 1
        pct = ((i + j) / 2) / (n - 1) if n > 1 else 0.5
        for k in ids[i:j + 1]:
            out[k] = pct
        i = j + 1
    return out


def impact(records: list[dict], outcomes: dict) -> dict[str, float]:
    """The day's impact per paper: mean of citation and star percentiles (unknown counts as 0)."""
    ids = [r["id"] for r in records]
    cit = percentiles({i: (outcomes.get(i) or {}).get("citations") or 0 for i in ids})
    sta = percentiles({i: (outcomes.get(i) or {}).get("stars") or 0 for i in ids})
    return {i: (cit[i] + sta[i]) / 2 for i in ids}


# ---------------------------------------------------------------- rankers

def _order(records: list[dict], key: Callable[[dict], float]) -> list[str]:
    return [r["id"] for r in sorted(records, key=lambda r: (-key(r), r["id"]))]


def rank_live(records):
    return _order(records, lambda r: r.get("score") or 0)


def rank_upvotes(records):
    return _order(records, lambda r: r.get("hf_upvotes") or 0)


def _replay(module_name: str):
    def ranker(records):
        mod = __import__(module_name)
        scored = {}
        for r in records:
            p = mod.score_paper(paper_store.to_paper(r))
            scored[r["id"]] = p["score"]
        return _order(records, lambda r: scored[r["id"]])
    return ranker


def ablation(group_key: str):
    sigs = [s for k, _, ss in scorer.GROUPS if k == group_key for s, _ in ss]

    def ranker(records):
        def key(r):
            parts = r.get("score_parts") or {}
            return sum(v for k, v in parts.items() if k not in sigs)
        return _order(records, key)
    return ranker


RANKERS: dict[str, Callable] = {
    "live": rank_live,
    "hf-upvotes": rank_upvotes,
    "v1": _replay("scorer_v1"),
    "v2": _replay("scorer_v2"),
    "v3 on saved fields": _replay("scorer"),
}
ABLATIONS = {f"live minus {label.lower()}": ablation(key) for key, label, _ in scorer.GROUPS}


# ---------------------------------------------------------------- metrics

def spearman(order: list[str], target: dict[str, float]) -> float:
    """Rank correlation between a ranker's order (best first) and the target (higher is better)."""
    n = len(order)
    if n < 3:
        return 0.0
    mine = {pid: 1 - i / (n - 1) for i, pid in enumerate(order)}
    theirs = percentiles({pid: target[pid] for pid in order})
    mx, my = sum(mine.values()) / n, sum(theirs.values()) / n
    cov = sum((mine[k] - mx) * (theirs[k] - my) for k in order)
    vx = sum((mine[k] - mx) ** 2 for k in order) ** 0.5
    vy = sum((theirs[k] - my) ** 2 for k in order) ** 0.5
    return round(cov / (vx * vy), 3) if vx and vy else 0.0


def day_metrics(order: list[str], target: dict[str, float], k: int = TOP_K) -> dict:
    best = set(sorted(target, key=lambda pid: (-target[pid], pid))[:k])
    return {"hit": order[0] in best, "p10": len(best & set(order[:k])) / k, "spearman": spearman(order, target)}


def evaluate(days: list[dict], outcomes: dict, rankers: dict, ablations: dict) -> dict:
    results = {}
    with_parts = [d for d in days if sum(1 for r in d["records"] if r.get("score_parts") and
                                         any(s in r["score_parts"] for s in ("stars", "h_index", "hn")))
                  >= TOP_K]
    plan = [(name, fn, days) for name, fn in rankers.items()] + \
           [(name, fn, with_parts) for name, fn in ablations.items()]
    if with_parts:
        plan.append(("live (same days as ablations)", rank_live, with_parts))
    for name, fn, use in plan:
        rows = []
        for d in use:
            target = impact(d["records"], outcomes)
            try:
                rows.append(day_metrics(fn(d["records"]), target))
            except Exception as exc:  # one broken replay shouldn't hide the rest
                print(f"  [scoreboard] {name} on {d['date']}: {exc}")
        if rows:
            results[name] = {"days": len(rows),
                             "hit": round(sum(r["hit"] for r in rows) / len(rows), 3),
                             "p10": round(sum(r["p10"] for r in rows) / len(rows), 3),
                             "spearman": round(sum(r["spearman"] for r in rows) / len(rows), 3)}
    if days:
        n = sum(len(d["records"]) for d in days) / len(days)
        results["random"] = {"days": len(days), "hit": round(TOP_K / n, 3), "p10": round(TOP_K / n, 3),
                             "spearman": 0.0}
    return results


def report(board: dict) -> str:
    lines = [f"Scoreboard: {board['days']} days at least {board['min_age']} days old "
             f"({board.get('first') or '-'} to {board.get('last') or '-'})",
             f"{'ranker':<38}{'days':>5}{'hit':>8}{'p@10':>8}{'spearman':>10}"]
    for name, r in board["rankers"].items():
        lines.append(f"{name:<38}{r['days']:>5}{r['hit']:>8.0%}{r['p10']:>8.0%}{r['spearman']:>10.2f}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--min-age", type=int, default=MIN_AGE_DAYS)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--out", default=OUT_PATH)
    args = ap.parse_args(argv)

    random.seed(0)
    days = load_days(DATA_DIR, args.min_age)
    cache = load_cache()
    try:
        with open(os.path.join(DATA_DIR, "links.json"), encoding="utf-8") as f:
            links = json.load(f)
    except (OSError, ValueError):
        links = {}
    if days:
        cache = fetch_outcomes(days, cache, links, offline=args.offline)
        save_json(CACHE_PATH, cache)
    board = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "min_age": args.min_age,
        "days": len(days),
        "first": days[0]["date"] if days else None,
        "last": days[-1]["date"] if days else None,
        "target": "mean percentile of Semantic Scholar citations and GitHub stars, measured now",
        "top_k": TOP_K,
        "rankers": evaluate(days, cache, RANKERS, ABLATIONS),
    }
    save_json(args.out, board)
    print(report(board))
    if not days:
        print(f"No saved day is {args.min_age} days old yet; the scoreboard will fill in as days age.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
