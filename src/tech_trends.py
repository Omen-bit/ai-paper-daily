"""
tech_trends.py
Numbers and SVG charts for specific technologies (AI agents, RAG, ...) on the
Trends page: the numbers behind the momentum chart, and the leaderboard that is its table.

Growth compares a technology's share of all papers in the last 90 days with its
share in the 90 days before. Shares, not counts, so a busy week on Hugging Face
does not look like a trend. A technology needs MIN_RECENT papers in the last
90 days before it gets a status, and MIN_BEFORE papers in the 90 days before
that before it gets a growth figure, so tiny topics never show silly numbers.
"""
from collections import Counter
from datetime import date, timedelta
from urllib.parse import quote

from technologies import TECH_NAMES
from trends import _month_label, _spark, esc, pct

RECENT_DAYS = 90
MIN_RECENT = 15
MIN_BEFORE = 6
BOARD_ROWS = 8  # rows the leaderboard shows before "Show all"

# Status: label, a shape so it is never colour alone, and the cut-off on growth
STATUS = {
    "breakout": ("Breakout", "▲▲"),
    "rising": ("Rising", "▲"),
    "new": ("New", "✦"),
    "steady": ("Steady", "■"),
    "cooling": ("Cooling", "▼"),
    "few": ("Too few papers", "·"),
}
ORDER = list(STATUS)


def status_for(recent: int, growth: float | None) -> str:
    if recent < MIN_RECENT:
        return "few"
    if growth is None:
        return "new"
    if growth >= 1.8:
        return "breakout"
    if growth >= 1.2:
        return "rising"
    if growth > 0.85:
        return "steady"
    return "cooling"


def change(growth: float | None) -> str:
    """Growth in share as a plain percentage change: +92%, -35%."""
    if growth is None:
        return "—"
    v = round((growth - 1) * 100)
    return f"+{v}%" if v > 0 else f"−{abs(v)}%" if v < 0 else "0%"


def tech_stats(rows: list[dict], months: list[str]) -> list[dict]:
    """One entry per technology, most interesting first."""
    if not rows or not months:
        return []
    end = date.fromisoformat(max(r["day"] for r in rows))
    rec_from = (end - timedelta(days=RECENT_DAYS - 1)).isoformat()
    bef_from = (end - timedelta(days=2 * RECENT_DAYS - 1)).isoformat()
    first_day = months[0] + "-01"
    tot_rec = tot_bef = 0
    month_tot = Counter()
    per = {t: {"rec": 0, "bef": 0, "code": 0, "month": Counter(), "papers": []} for t in TECH_NAMES}
    for r in rows:
        day = r["day"]
        in_rec, in_bef = day >= rec_from, bef_from <= day < rec_from
        month_tot[day[:7]] += 1
        tot_rec += in_rec
        tot_bef += in_bef
        for t in r.get("tech") or []:
            p = per.get(t)
            if p is None:
                continue
            p["month"][day[:7]] += 1
            if in_rec:
                p["rec"] += 1
                p["code"] += bool(r.get("code"))
            if in_bef:
                p["bef"] += 1
            if day >= first_day:
                p["papers"].append(r)
    out = []
    for t, p in per.items():
        share = p["rec"] / tot_rec if tot_rec else 0.0
        share_before = p["bef"] / tot_bef if tot_bef else 0.0
        growth = share / share_before if p["bef"] >= MIN_BEFORE and share_before > 0 else None
        top = sorted(p["papers"], key=lambda r: (-(r.get("up") or 0), r["day"]))[:3]
        out.append({
            "id": t, "name": TECH_NAMES[t], "recent": p["rec"], "before": p["bef"],
            "share": share, "share_before": share_before, "growth": growth,
            "status": status_for(p["rec"], growth),
            "counts": [p["month"][m] for m in months],
            "line": [p["month"][m] / month_tot[m] if month_tot[m] else 0.0 for m in months],
            "code": p["code"] / p["rec"] if p["rec"] else 0.0,
            "top": [{"id": r["id"], "title": r["title"], "day": r["day"], "up": r.get("up") or 0} for r in top
                    if (r.get("up") or 0) > 0],
        })
    out.sort(key=lambda s: (ORDER.index(s["status"]), -(s["growth"] or 0), -s["recent"]))
    return out


def spotlight_pick(stats: list[dict]) -> dict | None:
    """The fastest grower with enough papers."""
    growing = [s for s in stats if s["status"] in ("breakout", "rising") and s["growth"]]
    return max(growing, key=lambda s: s["growth"]) if growing else None


def _search(name: str) -> str:
    return f"papers.html?q={quote(name)}&amp;m=1"


def _status_pill(st: str) -> str:
    label, shape = STATUS[st]
    return f'<span class="status st-{st}"><i aria-hidden="true">{shape}</i>{label}</span>'


# ---------------------------------------------------------------------------
# 1. Leaderboard
# ---------------------------------------------------------------------------

def leaderboard(stats: list[dict], months: list[str]) -> str:
    rated = [s for s in stats if s["status"] != "few"]
    if not rated:
        return '<p class="empty-note">Technologies appear once the database has a few months of papers.</p>'
    rows = []
    for n, s in enumerate(rated):
        hi = max(max(s["line"]) * 1.15, 0.001)
        rows.append(f'''<tr class="st-{s["status"]}{" tb-more" if n >= BOARD_ROWS else ""}">
  <th scope="row"><a href="{_search(s["name"])}">{esc(s["name"])}</a></th>
  <td class="tb-spark">{_spark(s["line"], w=140, h=32, cls="spark tb-line", lo=0, hi=hi)}</td>
  <td class="num">{s["recent"]:,}<span>{pct(s["share"], 1)} of papers</span></td>
  <td class="num tb-change"><i class="tb-shape" aria-hidden="true">{STATUS[s["status"]][1]}</i>{change(s["growth"])}</td>
  <td>{_status_pill(s["status"])}</td>
</tr>''')
    more = (f'<button class="btn tb-all" type="button" data-board-all aria-expanded="false">'
            f'Show all {len(rated)} technologies</button>' if len(rated) > BOARD_ROWS else "")
    few = [s["name"] for s in stats if s["status"] == "few"]
    note = (f'<p class="tb-note">Not enough papers yet to rate: {esc(", ".join(few))}.</p>' if few else "")
    return f'''<div class="card tech-board-wrap"><table class="tech-board">
<thead><tr><th scope="col">Technology</th><th scope="col">{_month_label(months[0])} to {_month_label(months[-1])}</th>
<th scope="col" class="num">Papers, last 90 days</th><th scope="col" class="num">Change in share</th><th scope="col">Status</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table>{more}{note}</div>'''
