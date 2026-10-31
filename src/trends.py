"""
trends.py
Numbers and charts for the Trends page and the home page's topic pulse.

All charts are plain SVG built here, so the site needs no chart library.
They read the year of papers exported from Supabase (build/supabase/papers.json).
To keep the trend lines honest, they use the papers picked for Hugging Face
Daily Papers: one consistent source for the whole year. Our own daily arXiv
fetch only started recently and would make the latest weeks look bigger.
"""
import html
import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta

from technologies import tag as tag_technologies

esc = html.escape

# Five chart colours, checked for colour-blind separation in light and dark mode.
# They are only used where several topics share one chart; everything else is one colour.
SERIES = ["s1", "s2", "s3", "s4", "s5"]
OTHER = "other-ml"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

STOPWORDS = set("""
a an the and or of for in on to with via from by as at is are be its into over under than using use based
towards toward through without across beyond large language model models learning learn neural network networks
data dataset datasets benchmark benchmarks method methods approach approaches framework frameworks paper study
new efficient scalable improving improved improve better simple general generalization task tasks training
towards can do does how what when why we our your their more less via vs versus one two three all any
system systems analysis evaluating evaluation understanding towards enhancing enhanced unified via self
""".split())


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def _day(row: dict) -> str:
    return str(row.get("first_seen") or row.get("submitted") or "")[:10]


def trend_rows(archive: list[dict], site_papers: dict) -> tuple[list[dict], str]:
    """
    The papers the charts count, plus a sentence saying where they come from.
    Prefers the Hugging Face Daily Papers part of the database export.
    """
    rows = archive or []
    curated = [r for r in rows if "hug" in str(r.get("source") or "").lower() or (r.get("hf_upvotes") or 0) > 0]
    if len(curated) >= 200:
        rows, source = curated, "papers picked for Hugging Face Daily Papers"
    elif len(rows) >= 200:
        source = "papers in our database"
    else:
        rows, source = list(site_papers.values()), "papers on this site"
    clean = []
    for r in rows:
        d = _day(r)
        if len(d) != 10:
            continue
        tech = r.get("tech")
        if not isinstance(tech, list):  # older exports and site papers: tag them here
            tech = tag_technologies(r.get("title") or "", r.get("abstract"))
        clean.append({"id": r.get("id"), "day": d, "title": r.get("title") or "",
                      "cats": list(r.get("categories") or []) or [OTHER], "code": bool(r.get("code_url")),
                      "tech": tech, "up": int(r.get("hf_upvotes") or 0)})
    return clean, source


def _month(d: str) -> str:
    return d[:7]


def _month_label(m: str, with_year: bool = False) -> str:
    y, mo = m.split("-")
    return f"{MONTHS[int(mo) - 1]} {y}" if with_year else MONTHS[int(mo) - 1]


def last_months(rows: list[dict], n: int = 12) -> list[str]:
    """Up to n calendar months ending with the latest one, starting at the first with papers."""
    if not rows:
        return []
    end = max(r["day"] for r in rows)
    y, m = int(end[:4]), int(end[5:7])
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    out.reverse()
    # Start at the first month that has papers, so thin history isn't drawn as empty months
    have = {r["day"][:7] for r in rows}
    while out and out[0] not in have:
        out.pop(0)
    return out


def topic_counts(rows: list[dict], months: list[str]) -> dict[str, Counter]:
    """Per month, papers per topic. A paper in two topics counts half in each, so shares add up to 100%."""
    out = {m: Counter() for m in months}
    for r in rows:
        m = _month(r["day"])
        if m in out:
            for c in r["cats"]:
                out[m][c] += 1 / len(r["cats"])
    return out


def shares(counter: Counter) -> dict[str, float]:
    total = sum(counter.values())
    return {k: v / total for k, v in counter.items()} if total else {}


def top_topics(per_month: dict[str, Counter], k: int = 5) -> list[str]:
    total = Counter()
    for c in per_month.values():
        total.update(c)
    return [t for t, _ in total.most_common() if t != OTHER][:k]


def movers(rows: list[dict], months: list[str], recent: int = 3) -> list[dict]:
    """Each topic's share in the last `recent` months against the months before, in points."""
    per = topic_counts(rows, months)
    now, before = Counter(), Counter()
    for i, m in enumerate(months):
        (now if i >= len(months) - recent else before).update(per[m])
    s_now, s_before = shares(now), shares(before)
    out = []
    for t in set(s_now) | set(s_before):
        if t == OTHER:
            continue
        line = [shares(per[m]).get(t, 0.0) for m in months]
        out.append({"topic": t, "now": s_now.get(t, 0.0), "before": s_before.get(t, 0.0),
                    "delta": s_now.get(t, 0.0) - s_before.get(t, 0.0), "line": line,
                    "enough": sum(before.values()) >= 50})
    return sorted(out, key=lambda x: -x["delta"])


def weekly_pulse(rows: list[dict], today: str | None = None) -> list[dict]:
    """Topic shares for the last 7 days against the 28 days before (a steadier baseline)."""
    if not rows:
        return []
    end = date.fromisoformat(today or max(r["day"] for r in rows))
    week_start, base_start = end - timedelta(days=6), end - timedelta(days=34)
    week, base = Counter(), Counter()
    for r in rows:
        d = date.fromisoformat(r["day"])
        target = week if week_start <= d <= end else base if base_start <= d < week_start else None
        if target is not None:
            for c in r["cats"]:
                target[c] += 1 / len(r["cats"])
    s_week, s_base = shares(week), shares(base)
    steady = sum(base.values()) >= 60 and sum(week.values()) >= 20
    out = [{"topic": t, "share": s, "base": s_base.get(t), "delta": (s - s_base[t]) if steady and t in s_base else None,
            "count": round(week[t])} for t, s in s_week.items()]
    return sorted(out, key=lambda x: -x["share"])


def code_share(rows: list[dict], months: list[str]) -> list[tuple[str, float, int]]:
    """Per month: the share of papers that link to code, and how many papers there were."""
    total, coded = Counter(), Counter()
    for r in rows:
        m = _month(r["day"])
        total[m] += 1
        coded[m] += r["code"]
    return [(m, coded[m] / total[m] if total[m] else 0.0, total[m]) for m in months]


def daily_counts(rows: list[dict]) -> Counter:
    return Counter(r["day"] for r in rows)


_WORD = re.compile(r"[a-z][a-z0-9\-]{2,}")


def rising_words(rows: list[dict], months: list[str], recent: int = 3, k: int = 8) -> list[dict]:
    """Title words used much more in the last few months than before (share of titles)."""
    per_month_titles = Counter()
    word_month = defaultdict(Counter)
    for r in rows:
        m = _month(r["day"])
        if m not in months:
            continue
        per_month_titles[m] += 1
        for w in set(_WORD.findall(r["title"].lower())):
            w = w.strip("-")
            if w not in STOPWORDS and len(w) > 2 and not w.isdigit():
                word_month[w][m] += 1
    recent_m, before_m = months[-recent:], months[:-recent]
    n_recent = sum(per_month_titles[m] for m in recent_m)
    n_before = sum(per_month_titles[m] for m in before_m)
    if n_recent < 50 or n_before < 50:
        return []
    out = []
    for w, by_m in word_month.items():
        a = sum(by_m[m] for m in recent_m)
        b = sum(by_m[m] for m in before_m)
        if a < 8:
            continue
        rate_now, rate_before = a / n_recent, b / n_before
        ratio = (rate_now + 0.002) / (rate_before + 0.002)
        if ratio < 1.3:
            continue
        line = [by_m[m] / per_month_titles[m] if per_month_titles[m] else 0 for m in months]
        out.append({"word": w, "now": rate_now, "ratio": ratio, "line": line, "count": a})
    out.sort(key=lambda x: -(x["ratio"] * min(1.0, x["count"] / 20)))
    return out[:k]


# ---------------------------------------------------------------------------
# Charts (SVG)
# ---------------------------------------------------------------------------

def pct(v: float, digits: int = 0) -> str:
    return f"{v * 100:.{digits}f}%"


def pts(v: float) -> str:
    sign = "▲" if v > 0.0005 else "▼" if v < -0.0005 else "■"
    return f"{sign} {abs(v) * 100:.1f} pts"


def _spark(values: list[float], w: int = 120, h: int = 32, cls: str = "spark", lo: float | None = None,
           hi: float | None = None) -> str:
    if not values:
        return ""
    lo = min(values) if lo is None else lo
    hi = max(values) if hi is None else hi
    span = (hi - lo) or 1
    step = w / max(1, len(values) - 1)
    pts_ = [(i * step, h - 3 - (v - lo) / span * (h - 6)) for i, v in enumerate(values)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts_)
    area = f"0,{h} " + line + f" {w},{h}"
    lx, ly = pts_[-1]
    return (f'<svg class="{cls}" viewBox="-2 0 {w + 6} {h}" aria-hidden="true" preserveAspectRatio="none">'
            f'<polygon class="spark-area" points="{area}"/><polyline class="spark-line" points="{line}"/>'
            f'<circle class="spark-end" cx="{lx:.1f}" cy="{ly:.1f}" r="3"/></svg>')


def pulse_rows(pulse: list[dict], names: dict, limit: int = 6, root: str = "") -> str:
    """Home page: this week's share per topic, with a tick at the 4-week baseline."""
    rows = pulse[:limit]
    if not rows:
        return '<p class="empty-note">Topic shares appear after a few days of papers.</p>'
    top = max(max(r["share"], r["base"] or 0) for r in rows) or 1
    out = []
    for r in rows:
        w = r["share"] / top * 100
        tick = f'<i class="pulse-base" style="left:{(r["base"] or 0) / top * 100:.1f}%"></i>' if r["base"] is not None else ""
        if r["delta"] is None:
            change = '<span class="pulse-ch">—</span>'
        else:
            cls = "up" if r["delta"] > 0.0005 else "down" if r["delta"] < -0.0005 else "flat"
            change = f'<span class="pulse-ch {cls}">{pts(r["delta"])}</span>'
        label = (f'{esc(names.get(r["topic"], r["topic"]))}: {pct(r["share"])} of papers this week'
                 + (f', {pct(r["base"])} in the 4 weeks before' if r["base"] is not None else ""))
        out.append(f'''<li><a href="{root}papers.html?cat={esc(r["topic"])}" aria-label="{esc(label)}">
  <span class="pulse-name"><span class="topic t-{esc(r["topic"])}"><span class="dot"></span>{esc(names.get(r["topic"], r["topic"]))}</span></span>
  <span class="pulse-track"><span class="pulse-fill" style="width:{w:.1f}%"></span>{tick}</span>
  <span class="pulse-pct">{pct(r["share"])}</span>{change}</a></li>''')
    return f'<ol class="pulse2">{"".join(out)}</ol>'


def spread_labels(want: list[float], gap: float, top: float, bottom: float) -> list[float]:
    """Moves label positions apart so no two are closer than gap, staying near
    where they want to be and inside top..bottom. Keeps their order."""
    order = sorted(range(len(want)), key=lambda i: want[i])
    pos = [want[i] for i in order]
    for j in range(len(pos)):  # push down
        pos[j] = max(pos[j], top if j == 0 else pos[j - 1] + gap)
    if pos and pos[-1] > bottom:  # then back up from the bottom
        pos[-1] = bottom
        for j in range(len(pos) - 2, -1, -1):
            pos[j] = min(pos[j], pos[j + 1] - gap)
    out = [0.0] * len(want)
    for j, i in enumerate(order):
        out[i] = pos[j]
    return out


def share_area(per_month: dict[str, Counter], months: list[str], topics: list[str], names: dict) -> str:
    """100% stacked area of topic shares by month: the top topics plus everything else."""
    W, H, L, R, T, B = 1000, 340, 44, 236, 16, 30
    pw, ph = W - L - R, H - T - B
    x = lambda i: L + pw * i / max(1, len(months) - 1)
    y = lambda v: T + ph * (1 - v)
    layers = topics + ["__rest"]
    stacks = []
    for m in months:
        s = shares(per_month[m])
        vals = [s.get(t, 0.0) for t in topics]
        vals.append(max(0.0, 1 - sum(vals)) if s else 0.0)
        stacks.append(vals)
    bottoms = [[sum(v[:k]) for k in range(len(layers))] for v in stacks]
    paths = []
    for k, t in enumerate(layers):
        upper = [(x(i), y(bottoms[i][k] + stacks[i][k])) for i in range(len(months))]
        lower = [(x(i), y(bottoms[i][k])) for i in reversed(range(len(months)))]
        d = "M" + " L".join(f"{a:.1f},{b:.1f}" for a, b in upper + lower) + "Z"
        cls = "area-rest" if t == "__rest" else f"area-{SERIES[k]}"
        paths.append(f'<path class="{cls}" d="{d}"/>')
    # Direct labels at the right edge, in ink, next to a swatch of the series colour
    labels = []
    last = len(months) - 1
    spots = spread_labels([y(bottoms[last][k] + stacks[last][k] / 2) for k in range(len(layers))], 18, T + 6, T + ph)
    for k, t in enumerate(layers):
        ly = spots[k]
        name = "Everything else" if t == "__rest" else names.get(t, t)
        sw = "sw-rest" if t == "__rest" else f"sw-{SERIES[k]}"
        labels.append(f'<rect class="{sw}" x="{W - R + 12}" y="{ly - 5:.1f}" width="10" height="10" rx="2"/>'
                      f'<text x="{W - R + 28}" y="{ly + 4:.1f}">{esc(name)} {pct(stacks[last][k])}</text>')
    grid = "".join(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                   f'<text x="{L - 8}" y="{y(v) + 4:.1f}" text-anchor="end">{int(v * 100)}%</text>'
                   for v in (0, .25, .5, .75, 1))
    xl = "".join(f'<text x="{x(i):.1f}" y="{H - 8}" text-anchor="middle">{_month_label(m, i == 0 or m.endswith("-01"))}</text>'
                 for i, m in enumerate(months) if i % 2 == 0 or i == last)
    # Hover columns: one per month, with every share listed
    cols = []
    for i, m in enumerate(months):
        cx = x(i)
        bw = pw / max(1, len(months) - 1)
        lines = [f"{_month_label(m, True)}"] + [
            f'{"Everything else" if t == "__rest" else names.get(t, t)}: {pct(stacks[i][k])}' for k, t in reversed(list(enumerate(layers)))]
        tw, th = 210, 18 * len(lines) + 12
        tx = cx + 12 if cx + 12 + tw < W - R else cx - 12 - tw
        tip = "".join(f'<text x="{tx + 12:.1f}" y="{T + 22 + 18 * j}"{" class=tip-h" if j == 0 else ""}>{esc(s)}</text>'
                      for j, s in enumerate(lines))
        cols.append(f'<g class="col" tabindex="0" aria-label="{esc("; ".join(lines))}">'
                    f'<rect class="hit" x="{cx - bw / 2:.1f}" y="{T}" width="{bw:.1f}" height="{ph}"/>'
                    f'<line class="cross" x1="{cx:.1f}" x2="{cx:.1f}" y1="{T}" y2="{T + ph}"/>'
                    f'<g class="tip"><rect x="{tx:.1f}" y="{T + 4}" width="{tw}" height="{th}" rx="8"/>{tip}</g></g>')
    return (f'<svg class="chart share-area" viewBox="0 0 {W} {H}" role="img" '
            f'aria-label="Share of papers by topic, month by month, for the last {len(months)} months">'
            f'<g class="grid">{grid}</g><g class="areas">{"".join(paths)}</g><g class="xlab">{xl}</g>'
            f'<g class="direct">{"".join(labels)}</g><g class="cols">{"".join(cols)}</g></svg>')


def share_table(per_month: dict[str, Counter], months: list[str], topics: list[str], names: dict) -> str:
    head = "".join(f"<th scope=col>{esc(names.get(t, t))}</th>" for t in topics) + "<th scope=col>Everything else</th>"
    body = []
    for m in months:
        s = shares(per_month[m])
        vals = [s.get(t, 0.0) for t in topics]
        rest = max(0.0, 1 - sum(vals)) if s else 0.0
        body.append(f"<tr><th scope=row>{_month_label(m, True)}</th>" + "".join(f"<td>{pct(v, 1)}</td>" for v in vals + [rest]) + "</tr>")
    return f'<table class="data-table"><thead><tr><th scope=col>Month</th>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def mover_cards(items: list[dict], names: dict, months: list[str]) -> str:
    cards = []
    for it in items:
        cls = "up" if it["delta"] > 0.0005 else "down" if it["delta"] < -0.0005 else "flat"
        change = pts(it["delta"]) if it["enough"] else "—"
        cards.append(f'''<li class="mover {cls}">
  <a href="papers.html?cat={esc(it["topic"])}"><span class="topic t-{esc(it["topic"])}"><span class="dot"></span>{esc(names.get(it["topic"], it["topic"]))}</span></a>
  <div class="mover-nums"><strong>{pct(it["now"], 1)}</strong><span class="pulse-ch {cls}">{change}</span></div>
  {_spark(it["line"], cls="spark mover-spark", lo=0, hi=max(max(it["line"]) * 1.15, 0.01))}
  <span class="mover-axis"><span>{_month_label(months[0])}</span><span>{_month_label(months[-1])}</span></span>
</li>''')
    return f'<ol class="movers">{"".join(cards)}</ol>'


def calendar(counts: Counter, end: str, weeks: int = 53) -> str:
    """A year of days as squares, darker when more papers came out. Weeks run Monday to Sunday."""
    last = date.fromisoformat(end)
    start = last - timedelta(days=last.weekday()) - timedelta(weeks=weeks - 1)
    days = [start + timedelta(days=i) for i in range((last - start).days + 1)]
    values = [counts.get(d.isoformat(), 0) for d in days]
    nonzero = sorted(v for v in values if v)
    # Five steps by quantile, so one huge day doesn't wash out the rest
    cuts = [nonzero[int(len(nonzero) * q)] for q in (.2, .4, .6, .8)] if nonzero else [1, 2, 3, 4]
    level = lambda v: 0 if v == 0 else 1 + sum(v > c for c in cuts)
    C, G, L, T = 14, 3, 30, 20
    cells, mlabels = [], []
    seen_month = None
    for i, d in enumerate(days):
        col, row = (d - start).days // 7, d.weekday()
        x, y = L + col * (C + G), T + row * (C + G)
        v = counts.get(d.isoformat(), 0)
        cells.append(f'<rect class="cal-{level(v)}" x="{x}" y="{y}" width="{C}" height="{C}" rx="3">'
                     f'<title>{v} papers on {d.day} {MONTHS[d.month - 1]} {d.year}</title></rect>')
        if row == 0 and d.month != seen_month and d.day <= 7:
            seen_month = d.month
            mlabels.append(f'<text x="{x}" y="{T - 7}">{MONTHS[d.month - 1]}</text>')
    W = L + weeks * (C + G)
    H = T + 7 * (C + G)
    dl = "".join(f'<text x="{L - 8}" y="{T + r * (C + G) + 11}" text-anchor="end">{n}</text>'
                 for r, n in ((0, "Mon"), (2, "Wed"), (4, "Fri")))
    legend = "".join(f'<i class="cal-{k}"></i>' for k in range(6))
    total = sum(values)
    busiest = max(zip(values, days)) if total else (0, last)
    svg = (f'<svg class="chart calendar" viewBox="0 0 {W} {H}" role="img" '
           f'aria-label="Papers per day for the last year: {total} in total, busiest day {busiest[1].isoformat()} with {busiest[0]}">'
           f'<g class="xlab">{"".join(mlabels)}{dl}</g>{"".join(cells)}</svg>')
    return (f'<div class="cal-wrap">{svg}</div><div class="cal-legend"><span>Fewer</span>{legend}<span>More</span>'
            f'<span class="cal-note">Busiest day: {busiest[1].day} {MONTHS[busiest[1].month - 1]} {busiest[1].year}, {busiest[0]} papers</span></div>')


def code_chart(series: list[tuple[str, float, int]]) -> str:
    """Share of papers with code, month by month, as one line with a value on hover."""
    if not series:
        return ""
    W, H, L, R, T, B = 1000, 240, 44, 24, 24, 30
    pw, ph = W - L - R, H - T - B
    top = max(0.2, max(v for _, v, _ in series))
    mx = min(1.0, (int(top * 10) + 1) / 10)
    tick = 0.1 if mx <= 0.6 else 0.2
    x = lambda i: L + pw * i / max(1, len(series) - 1)
    y = lambda v: T + ph * (1 - v / mx)
    grid = "".join(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                   f'<text x="{L - 8}" y="{y(v) + 4:.1f}" text-anchor="end">{int(round(v * 100))}%</text>'
                   for v in [round(tick * k, 2) for k in range(int(round(mx / tick)) + 1)])
    line = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, (_, v, _) in enumerate(series))
    area = f"{x(0):.1f},{y(0):.1f} {line} {x(len(series) - 1):.1f},{y(0):.1f}"
    pts_ = []
    for i, (m, v, n) in enumerate(series):
        label = f"{_month_label(m, True)}: {pct(v)} of {n} papers link to code"
        tw = 250
        tx = min(max(x(i) - tw / 2, L), W - R - tw)
        pts_.append(f'<g class="pt" tabindex="0" aria-label="{esc(label)}">'
                    f'<rect class="hit" x="{x(i) - pw / len(series) / 2:.1f}" y="{T}" width="{pw / len(series):.1f}" height="{ph}"/>'
                    f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="4"/>'
                    f'<g class="tip"><rect x="{tx:.1f}" y="{y(v) - 40:.1f}" width="{tw}" height="26" rx="6"/>'
                    f'<text x="{tx + tw / 2:.1f}" y="{y(v) - 23:.1f}" text-anchor="middle">{esc(label)}</text></g></g>')
    lm, lv, _ = series[-1]
    end_label = f'<text class="end-label" x="{x(len(series) - 1) - 8:.1f}" y="{y(lv) - 12:.1f}" text-anchor="end">{pct(lv)}</text>'
    xl = "".join(f'<text x="{x(i):.1f}" y="{H - 8}" text-anchor="middle">{_month_label(m, i == 0 or m.endswith("-01"))}</text>'
                 for i, (m, _, _) in enumerate(series) if i % 2 == 0 or i == len(series) - 1)
    return (f'<svg class="chart code-chart" viewBox="0 0 {W} {H}" role="img" aria-label="Share of papers that link to code, by month">'
            f'<g class="grid">{grid}</g><polygon class="code-area" points="{area}"/><polyline class="code-line" points="{line}"/>'
            f'{end_label}<g class="xlab">{xl}</g><g>{"".join(pts_)}</g></svg>')


def word_rows(words: list[dict], months: list[str]) -> str:
    if not words:
        return '<p class="empty-note">Not enough titles yet to spot rising words.</p>'
    out = []
    for i, w in enumerate(words, 1):
        out.append(f'''<li><span class="w-n">{i:02d}</span><a class="w-word" href="papers.html?q={esc(w["word"])}">{esc(w["word"])}</a>
  {_spark(w["line"], w=140, h=28, cls="spark word-spark", lo=0)}
  <span class="w-now">in {pct(w["now"], 1)} of titles</span><span class="w-x">{w["ratio"]:.1f}×</span></li>''')
    return f'<ol class="words">{"".join(out)}</ol>'


def field_shares_json(rows: list[dict], months: list[str], recent: int = 3) -> str:
    """Topic shares of the last few months, for the 'you vs the field' chart drawn in the browser."""
    per = topic_counts(rows, months[-recent:])
    total = Counter()
    for c in per.values():
        total.update(c)
    return json.dumps({k: round(v, 4) for k, v in shares(total).items()}, separators=(",", ":"))
