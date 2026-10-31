"""
tech_trends.py
Numbers and SVG charts for specific technologies (AI agents, RAG, ...) on the
Trends page: the leaderboard, the breakout spotlight, the momentum map and the
small multiples.

Growth compares a technology's share of all papers in the last 90 days with its
share in the 90 days before. Shares, not counts, so a busy week on Hugging Face
does not look like a trend. A technology needs MIN_RECENT papers in the last
90 days before it gets a status, and MIN_BEFORE papers in the 90 days before
that before it gets a growth figure, so tiny topics never show silly numbers.
"""
import math
from collections import Counter
from datetime import date, timedelta
from urllib.parse import quote

from technologies import TECH_NAMES
from trends import _month_label, _spark, esc, pct

RECENT_DAYS = 90
MIN_RECENT = 15
MIN_BEFORE = 6

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
    for s in rated:
        hi = max(max(s["line"]) * 1.15, 0.001)
        rows.append(f'''<tr class="st-{s["status"]}">
  <th scope="row"><a href="{_search(s["name"])}">{esc(s["name"])}</a></th>
  <td class="tb-spark">{_spark(s["line"], w=140, h=32, cls="spark tb-line", lo=0, hi=hi)}</td>
  <td class="num">{s["recent"]:,}<span>{pct(s["share"], 1)} of papers</span></td>
  <td class="num tb-change"><i class="tb-shape" aria-hidden="true">{STATUS[s["status"]][1]}</i>{change(s["growth"])}</td>
  <td>{_status_pill(s["status"])}</td>
</tr>''')
    few = [s["name"] for s in stats if s["status"] == "few"]
    note = (f'<p class="tb-note">Not enough papers yet to rate: {esc(", ".join(few))}.</p>' if few else "")
    return f'''<div class="card tech-board-wrap"><table class="tech-board">
<thead><tr><th scope="col">Technology</th><th scope="col">{_month_label(months[0])} to {_month_label(months[-1])}</th>
<th scope="col" class="num">Papers, last 90 days</th><th scope="col" class="num">Change in share</th><th scope="col">Status</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table>{note}</div>'''


# ---------------------------------------------------------------------------
# 2. Breakout spotlight: one technology in the accent colour, the rest in grey
# ---------------------------------------------------------------------------

def spotlight(stats: list[dict], months: list[str], on_site: set[str] | None = None) -> str:
    spot = spotlight_pick(stats)
    if not spot:
        return ""
    on_site = on_site or set()
    # Grey lines: technologies of a similar size, so the scale stays readable
    top = max(max(spot["line"]) * 1.6, 0.01)
    others = [s for s in stats if s["status"] != "few" and s["id"] != spot["id"] and max(s["line"]) <= top]
    W, H, L, R, T, B = 1000, 320, 52, 170, 18, 32
    pw, ph = W - L - R, H - T - B
    step = 0.05 if top > 0.15 else 0.02 if top > 0.06 else 0.01
    x = lambda i: L + pw * i / max(1, len(months) - 1)
    y = lambda v: T + ph * (1 - v / top)
    line = lambda vals: " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
    ticks = [i * step for i in range(int(top / step) + 1)]
    grid = "".join(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                   f'<text x="{L - 8}" y="{y(v) + 4:.1f}" text-anchor="end">{round(v * 100)}%</text>' for v in ticks)
    last = len(months) - 1
    xl = "".join(f'<text x="{x(i):.1f}" y="{H - 8}" text-anchor="middle">{_month_label(m, i == 0 or m.endswith("-01"))}</text>'
                 for i, m in enumerate(months) if i % 2 == last % 2)
    greys = "".join(f'<polyline class="sl-other" points="{line(s["line"])}"><title>{esc(s["name"])}</title></polyline>' for s in others)
    main = f'<polyline class="sl-main" points="{line(spot["line"])}"/>'
    end = f'<circle class="sl-end" cx="{x(last):.1f}" cy="{y(spot["line"][-1]):.1f}" r="5"/>' \
          f'<text class="sl-label" x="{x(last) + 12:.1f}" y="{y(spot["line"][-1]) + 4:.1f}">{esc(spot["name"])}</text>' \
          f'<text class="sl-value" x="{x(last) + 12:.1f}" y="{y(spot["line"][-1]) + 22:.1f}">{pct(spot["line"][-1], 1)} in {_month_label(months[-1])}</text>'
    # The most-upvoted papers of the year, marked where they came out
    marks, items = [], []
    for n, p in enumerate(spot["top"], 1):
        m = p["day"][:7]
        if m not in months:
            continue
        i = months.index(m)
        cx, cy = x(i), y(spot["line"][i])
        marks.append(f'<g class="sl-mark"><circle cx="{cx:.1f}" cy="{cy - 20:.1f}" r="10"/>'
                     f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{cy - 10:.1f}" y2="{cy - 4:.1f}"/>'
                     f'<text x="{cx:.1f}" y="{cy - 16:.1f}" text-anchor="middle">{n}</text></g>')
        href = f'paper/{esc(p["id"])}.html' if p["id"] in on_site else f'https://huggingface.co/papers/{esc(p["id"])}'
        items.append(f'<li><span class="sl-n">{n}</span><div><a href="{href}">{esc(p["title"])}</a>'
                     f'<span>{_month_label(m, True)} · {p["up"]:,} upvotes on Hugging Face</span></div></li>')
    cols = []
    bw = pw / max(1, last)
    for i, m in enumerate(months):
        cx = x(i)
        text = f'{_month_label(m, True)}: {pct(spot["line"][i], 1)} of papers ({spot["counts"][i]:,})'
        tw_ = round(24 + 6.3 * len(text))
        tx = cx + 12 if cx + 12 + tw_ < W else cx - 12 - tw_
        cols.append(f'<g class="col" tabindex="0" aria-label="{esc(text)}"><rect class="hit" x="{cx - bw / 2:.1f}" y="{T}" width="{bw:.1f}" height="{ph}"/>'
                    f'<line class="cross" x1="{cx:.1f}" x2="{cx:.1f}" y1="{T}" y2="{T + ph}"/>'
                    f'<g class="tip"><rect x="{tx:.1f}" y="{T + 4}" width="{tw_}" height="30" rx="8"/>'
                    f'<text x="{tx + 12:.1f}" y="{T + 24}">{esc(text)}</text></g></g>')
    table = "".join(f"<tr><th scope=row>{_month_label(m, True)}</th><td>{spot['counts'][i]:,}</td><td>{pct(spot['line'][i], 1)}</td></tr>"
                    for i, m in enumerate(months))
    label = (f'{spot["name"]}: share of papers by month, from {pct(spot["line"][0], 1)} in {_month_label(months[0], True)} '
             f'to {pct(spot["line"][-1], 1)} in {_month_label(months[-1], True)}. Technologies of a similar size in grey.')
    return f'''<div class="spotlight">
  <div class="sl-head">
    <span class="status st-{spot["status"]}"><i aria-hidden="true">{STATUS[spot["status"]][1]}</i>{STATUS[spot["status"]][0]}</span>
    <p class="sl-title">{esc(spot["name"])} went from {pct(spot["share_before"], 1)} to {pct(spot["share"], 1)} of new papers in 90 days.</p>
    <p class="sl-sub">{spot["recent"]:,} papers in the last 90 days, {pct(spot["code"])} with code. The grey lines are technologies of a similar size.</p>
  </div>
  <svg class="chart sl-chart" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(label)}">
    <g class="grid">{grid}</g><g class="xlab">{xl}</g><g class="sl-others">{greys}</g>{main}{end}
    <g class="sl-marks">{"".join(marks)}</g><g class="cols">{"".join(cols)}</g></svg>
  {f'<ol class="sl-papers" aria-label="Most upvoted {esc(spot["name"])} papers">{"".join(items)}</ol>' if items else ""}
  <details class="table-view"><summary>Show as a table</summary><table class="data-table"><thead><tr><th scope=col>Month</th>
  <th scope=col>Papers</th><th scope=col>Share</th></tr></thead><tbody>{table}</tbody></table></details>
</div>'''


# ---------------------------------------------------------------------------
# 3. Momentum map: size against growth (a dumbbell list on phones)
# ---------------------------------------------------------------------------

GROWTH_LO, GROWTH_HI = 0.35, 4.0  # growth beyond these is drawn at the edge


def momentum(stats: list[dict]) -> str:
    pts_ = [s for s in stats if s["status"] not in ("few", "new") and s["growth"]]
    if len(pts_) < 4:
        return ""
    W, H, L, R, T, B = 1000, 460, 64, 30, 30, 48
    pw, ph = W - L - R, H - T - B
    xmax = max(s["share"] for s in pts_) * 1.12
    lg = lambda g: math.log2(min(max(g, GROWTH_LO), GROWTH_HI))
    # The growth range follows the data, from at least -50% to +100%
    ylo = min(lg(0.5), lg(min(s["growth"] for s in pts_)) - 0.3)
    yhi = max(lg(2), lg(max(s["growth"] for s in pts_)) + 0.3)
    # Square-root scale on share: most technologies are small, a few are huge
    x = lambda v: L + pw * math.sqrt(max(v, 0) / xmax)
    y = lambda g: T + ph * (1 - (lg(g) - ylo) / (yhi - ylo))
    mid = sorted(s["share"] for s in pts_)[len(pts_) // 2]
    xticks = [v for v in (0, 0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5) if v <= xmax]
    xt = "".join(f'<line x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{T}" y2="{T + ph}"/>'
                 f'<text x="{x(v):.1f}" y="{T + ph + 20}" text-anchor="middle">{round(v * 100)}%</text>'
                 for v in xticks)
    yt = "".join(f'<line x1="{L}" x2="{W - R}" y1="{y(g):.1f}" y2="{y(g):.1f}"/>'
                 f'<text x="{L - 8}" y="{y(g) + 4:.1f}" text-anchor="end">{t}</text>'
                 for g, t in ((0.5, "−50%"), (1, "0%"), (2, "+100%"), (4, "+300%")) if ylo <= lg(g) <= yhi)
    quads = (f'<line class="q-line" x1="{x(mid):.1f}" x2="{x(mid):.1f}" y1="{T}" y2="{T + ph}"/>'
             f'<line class="q-line" x1="{L}" x2="{W - R}" y1="{y(1):.1f}" y2="{y(1):.1f}"/>'
             f'<text class="q-name" x="{L + 10}" y="{T + 16}">Emerging</text>'
             f'<text class="q-name" x="{W - R - 10}" y="{T + 16}" text-anchor="end">Hot and big</text>'
             f'<text class="q-name" x="{L + 10}" y="{T + ph - 10}">Niche or fading</text>'
             f'<text class="q-name" x="{W - R - 10}" y="{T + ph - 10}" text-anchor="end">Established</text>')
    # Direct labels where they fit: growing technologies first, then the biggest.
    # A dot whose label would collide keeps only its tooltip (and its row in the table above).
    centres = {s["id"]: (x(s["share"]), y(s["growth"])) for s in pts_}
    boxes = [(L + 4, T + 2, L + 90, T + 22), (W - R - 100, T + 2, W - R - 4, T + 22),
             (L + 4, T + ph - 26, L + 130, T + ph - 2), (W - R - 100, T + ph - 26, W - R - 4, T + ph - 2)]
    boxes += [(cx - 9, cy - 9, cx + 9, cy + 9) for cx, cy in centres.values()]
    labels: dict[str, tuple[float, float, str]] = {}
    for s in sorted(pts_, key=lambda s: (s["growth"] < 1.2, -s["share"])):
        cx, cy = centres[s["id"]]
        tw = 6.6 * len(s["name"])
        for lx, ly, anchor, bx in ((cx + 12, cy + 4, "start", cx + 12), (cx - 12, cy + 4, "end", cx - 12 - tw),
                                   (cx, cy - 13, "middle", cx - tw / 2), (cx, cy + 22, "middle", cx - tw / 2),
                                   (cx + 8, cy - 11, "start", cx + 8), (cx - 8, cy - 11, "end", cx - 8 - tw),
                                   (cx + 8, cy + 20, "start", cx + 8), (cx - 8, cy + 20, "end", cx - 8 - tw)):
            box = (bx, ly - 11, bx + tw, ly + 3)
            if box[0] < L or box[2] > W - R or box[1] < T or box[3] > T + ph:
                continue
            if all(box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3] for b in boxes):
                boxes.append(box)
                labels[s["id"]] = (lx, ly, anchor)
                break
    dots = []
    for s in sorted(pts_, key=lambda s: -s["share"]):
        cx, cy = centres[s["id"]]
        lab = labels.get(s["id"])
        label = (f'<text class="mm-label" x="{lab[0]:.1f}" y="{lab[1]:.1f}" text-anchor="{lab[2]}">{esc(s["name"])}</text>'
                 if lab else "")
        cls = "up" if s["growth"] >= 1.2 else "down" if s["growth"] <= 0.85 else "flat"
        tip = f'{s["name"]}: {pct(s["share"], 1)} of papers, {change(s["growth"])} vs the 90 days before'
        tw_ = round(24 + 6.3 * len(tip))
        tx = cx + 14 if cx + 14 + tw_ < W else cx - 14 - tw_
        dots.append(f'<g class="pt mm-pt {cls}" tabindex="0" aria-label="{esc(tip)}">'
                    f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="7"/>'
                    f'{label}'
                    f'<g class="tip"><rect x="{tx:.1f}" y="{cy - 40:.1f}" width="{tw_}" height="30" rx="8"/>'
                    f'<text x="{tx + 12:.1f}" y="{cy - 20:.1f}">{esc(tip)}</text></g></g>')
    axes = (f'<text class="ax-title" x="{L + pw / 2:.1f}" y="{H - 4}" text-anchor="middle">Share of papers in the last 90 days</text>'
            f'<text class="ax-title" x="{14}" y="{T + ph / 2:.1f}" text-anchor="middle" transform="rotate(-90 14 {T + ph / 2:.1f})">Change in share</text>')
    scatter = (f'<svg class="chart mm-chart" viewBox="0 0 {W} {H}" role="img" aria-label="Momentum map: share of papers against change in share, '
               f'for {len(pts_)} technologies. The table above lists every technology.">'
               f'<g class="grid">{xt}{yt}</g>{quads}{axes}<g class="mm-dots">{"".join(dots)}</g></svg>')
    # Phones: a dumbbell per technology, 90 days before (hollow) to now (filled)
    top = max(max(s["share"], s["share_before"]) for s in pts_) or 1
    bells = []
    for s in sorted(pts_, key=lambda s: -(s["growth"] or 0)):
        a, b = s["share_before"] / top * 100, s["share"] / top * 100
        lo, hi = min(a, b), max(a, b)
        cls = "up" if s["growth"] >= 1.2 else "down" if s["growth"] <= 0.85 else "flat"
        bells.append(f'<li class="{cls}"><span class="db-name">{esc(s["name"])}</span>'
                     f'<span class="db-track" aria-hidden="true"><i class="db-bar" style="left:{lo:.1f}%;width:{hi - lo:.1f}%"></i>'
                     f'<i class="db-from" style="left:{a:.1f}%"></i><i class="db-to" style="left:{b:.1f}%"></i></span>'
                     f'<span class="db-val">{pct(s["share_before"], 1)} → {pct(s["share"], 1)}</span></li>')
    dumbbell = (f'<div class="mm-narrow"><p class="db-key"><span><i class="db-from"></i>90 days before</span>'
                f'<span><i class="db-to"></i>Last 90 days</span></p><ol class="dumbbell">{"".join(bells)}</ol></div>')
    return f'<div class="mm-wide">{scatter}</div>{dumbbell}'


# ---------------------------------------------------------------------------
# 4. Small multiples: one mini chart per technology, all on the same scale
# ---------------------------------------------------------------------------

def multiples(stats: list[dict], months: list[str]) -> str:
    rated = [s for s in stats if s["status"] != "few"]
    if not rated:
        return ""
    cards = []
    for s in rated:
        hi = max(max(s["line"]) * 1.15, 0.001)
        cards.append(f'''<li class="sm st-{s["status"]}"><a href="{_search(s["name"])}">
  <span class="sm-head"><b>{esc(s["name"])}</b><span class="sm-now">{pct(s["line"][-1], 1)}</span></span>
  {_spark(s["line"], w=200, h=56, cls="spark sm-line", lo=0, hi=hi)}
  <span class="sm-axis"><span>{_month_label(months[0])}</span><span>peak {pct(max(s["line"]), 1)}</span><span>{_month_label(months[-1])}</span></span>
  <span class="sm-foot">{_status_pill(s["status"])}<span>{change(s["growth"])}</span></span></a></li>''')
    return (f'<ol class="smalls">{"".join(cards)}</ol>'
            f'<p class="tb-note">Each chart has its own scale, starting at 0, so small technologies show their shape too. '
            f'Compare sizes on the momentum map or the table.</p>')
