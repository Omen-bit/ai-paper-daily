"""
why_now.py
The "why it's here now" line on a top pick that came out on arXiv a while ago.

A reader who sees a 9 Nov paper as the 18 Nov pick should not have to guess why.
When the pick is more than OLD_AFTER_DAYS days older than the edition, its card
says when it came out and what changed since, from the measured signals only:

  From 9 Nov. Picked today because it gained 1,200 GitHub stars this week.

Every number comes from the evidence the scorer recorded (GitHub, Hugging Face,
Hacker News) or from the daily signal snapshots in data/signals/. A value the
scorer marked as estimated is never used, and no model writes any of it.
"""
import json
import os
from datetime import date, timedelta

OLD_AFTER_DAYS = 3      # a pick this many days old or newer needs no explanation
MIN_STARS = 20          # fewer new stars than this is not a reason worth naming
MIN_UPVOTES = 5
MIN_HN_POINTS = 20
MIN_MODELS = 2
WEEK = 7


def _day(iso) -> date | None:
    try:
        return date.fromisoformat(str(iso or "")[:10])
    except ValueError:
        return None


def short_date(d: date) -> str:
    return f"{d.day} {d:%b}"


def _n(x) -> str:
    return f"{int(x):,}"


def stars_this_week(paper_id: str, edition: str, data_dir: str) -> tuple[int | None, int]:
    """
    (stars gained, over how many days) from the signal snapshots of the last week,
    or (None, 0) when there is no earlier count to compare with.
    """
    end = _day(edition)
    folder = os.path.join(data_dir, "signals")
    if not end or not os.path.isdir(folder):
        return None, 0
    counts = {}
    for back in range(WEEK + 1):
        d = end - timedelta(days=back)
        path = os.path.join(folder, f"{d.isoformat()}.json")
        try:
            with open(path, encoding="utf-8") as f:
                sig = (json.load(f).get("papers") or {}).get(paper_id) or {}
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(sig.get("stars"), int):
            counts[d] = sig["stars"]
    if end not in counts:
        return None, 0
    earlier = [d for d in counts if d < end]
    if not earlier:
        return None, 0
    first = min(earlier)
    return max(0, counts[end] - counts[first]), (end - first).days


def reasons(rec: dict, stars_week: int | None = None, span: int = 0) -> list[str]:
    """What changed for the paper lately, strongest first, as clauses after "because"."""
    ev = rec.get("evidence") or {}
    estimated = set(ev.get("estimated") or [])
    out = []
    if stars_week is not None and stars_week >= MIN_STARS:
        out.append(f"it gained {_n(stars_week)} GitHub stars {'since yesterday' if span == 1 else 'this week'}")
    elif "stars_gain" not in estimated and (ev.get("stars_gain") or 0) >= MIN_STARS:
        gain, stars = ev["stars_gain"], ev.get("stars")
        if stars is not None and gain >= stars:
            out.append(f"its new code repo drew {_n(gain)} GitHub stars")
        else:
            out.append(f"it gained {_n(gain)} GitHub stars since yesterday")
    upvotes = ev.get("upvotes", rec.get("hf_upvotes")) or 0
    models = ev.get("hf_models") or 0
    on_hf = "HuggingFace" in str(rec.get("source") or "") or rec.get("slot") == "trending"
    if on_hf and upvotes >= MIN_UPVOTES:
        extra = f" and {_n(models)} models built on it" if models >= MIN_MODELS else ""
        out.append(f"it made Hugging Face’s daily papers with {_n(upvotes)} upvotes{extra}")
    elif models >= MIN_MODELS:
        out.append(f"{_n(models)} models built on it are now on Hugging Face")
    if "hn_points" not in estimated and (ev.get("hn_points") or 0) >= MIN_HN_POINTS:
        out.append(f"it reached {_n(ev['hn_points'])} points on Hacker News")
    return out


def why_now(rec: dict, edition: str, today: bool = True,
            stars_week: int | None = None, span: int = 0) -> str:
    """
    The plain-text line, or "" when the paper is recent enough to need none.
    today=False words it for a past edition's page ("Picked on 18 Nov").
    """
    out, ed = _day(rec.get("submitted")), _day(edition)
    if not out or not ed or (ed - out).days <= OLD_AFTER_DAYS:
        return ""
    picked = "Picked today" if today else f"Picked on {short_date(ed)}"
    why = reasons(rec, stars_week, span)[:2]
    if why:
        because = why[0] if len(why) == 1 else f"{why[0]}, and {why[1]}"
    elif rec.get("rank") and rec.get("of"):
        because = f"it scored highest of the {_n(rec['of'])} papers we ranked that morning"
    else:
        because = "it scored highest of the papers we ranked that morning"
    return f"From {short_date(out)}. {picked} because {because}."
