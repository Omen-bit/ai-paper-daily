"""
trend_story.py
The story half of the Trends page: an opening sentence written from the numbers,
and five charts that each make one point.

  01 The topic shift      the fastest-growing topic against the biggest one
  02 Momentum             every technology's change in share, grouped by status
  03 Research vs practice technology share in papers against company case studies
  04 Off the peak         cooling technologies: their best month against now
  05 Words on the rise    title words, share before against share now

Every chart is plain HTML or SVG built here, styled by classes in style.css so
it follows the light and dark themes. Every chart also has a table.
Nothing here is hard-coded to this year's news: the sentences come from the data,
and a chart that has too little data returns "" so the page leaves it out.
"""
import math
from collections import Counter
from urllib.parse import quote

from technologies import tag as tag_technologies
from tech_trends import STATUS, change
from trends import _month_label, esc, pct, shares

OTHER = "other-ml"

# How the headline names a topic: "AI research is becoming agent research."
TOPIC_PHRASE = {
    "reasoning-agents": "agent research", "code-ai": "code research", "multimodal": "multimodal research",
    "ai-science": "science research", "safety-privacy": "safety research", "efficient-ai": "efficiency research",
    "alignment": "alignment research", "computer-vision": "vision research", "generative-ai": "generative research",
    "audio-speech": "speech research", "llms": "language-model research", "ml-theory": "theory research",
}
GROUPS = [("breakout", "Breakout"), ("rising", "Rising"), ("steady", "Steady"), ("cooling", "Cooling")]
MIN_CASES = 20  # case studies needed before comparing research with practice


def _search(name: str) -> str:
    return f"papers.html?q={quote(name)}&amp;m=1"


def _times(r: float) -> str:
    return f"{r:.0f}×" if r >= 2.95 else f"{r:.1f}×"


def full_months(months: list[str], per_month_total: Counter) -> list[str]:
    """Drops the latest month when it has only just started, so a few days don't read as a trend."""
    if len(months) >= 4 and per_month_total[months[-1]] < 0.3 * per_month_total[months[-2]]:
        return months[:-1]
    return months


def smooth(pts: list[tuple[float, float]]) -> str:
    """An SVG path through every point, with gentle curves between them (Catmull-Rom)."""
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i > 0 else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d


def card(num: str, label: str, title: str, sub: str, stat: str, stat_label: str, tone: str,
         body: str, note: str, table: str = "") -> str:
    """One chart in the story: what it shows, its headline number, the chart, and its table."""
    view = f'<details class="table-view"><summary>Show as a table</summary>{table}</details>' if table else ""
    return f'''<section class="story-card">
  <header class="sc-head">
    <div class="sc-text"><p class="sc-eyebrow"><b>{num}</b> / {esc(label)}</p><h2>{title}</h2><p class="sc-sub">{sub}</p></div>
    <p class="sc-stat tone-{tone}"><strong>{stat}</strong><span>{stat_label}</span></p>
  </header>
  <div class="sc-body">{body}</div>
  <footer class="sc-foot"><span>{note}</span>{view}</footer>
</section>'''


# ---------------------------------------------------------------------------
# 01 The topic shift
# ---------------------------------------------------------------------------

def topic_shift(per: dict[str, Counter], months: list[str], names: dict) -> dict | None:
    """The topic whose share grew most across the year, and the biggest topic beside it."""
    totals = Counter({m: sum(per[m].values()) for m in months})
    months = full_months(months, totals)
    if len(months) < 6:
        return None
    sh = [shares(per[m]) for m in months]
    topics = {t for s in sh for t in s if t != OTHER}
    k = 3 if len(months) >= 9 else 2
    avg = lambda t, part: sum(s.get(t, 0.0) for s in part) / len(part)
    grow = {t: avg(t, sh[-k:]) / avg(t, sh[:k]) for t in topics if avg(t, sh[:k]) >= 0.02}
    if not grow:
        return None
    rise = max(grow, key=grow.get)
    if grow[rise] < 1.3:
        return None
    rest = [t for t in topics if t != rise]
    if not rest:
        return None
    base = max(rest, key=lambda t: avg(t, sh))
    return {"rise": rise, "base": base, "months": months, "growth": grow[rise],
            "rise_line": [s.get(rise, 0.0) for s in sh], "base_line": [s.get(base, 0.0) for s in sh],
            "rise_name": names.get(rise, rise), "base_name": names.get(base, base)}


def topic_shift_chart(d: dict) -> str:
    months, ra, bl = d["months"], d["rise_line"], d["base_line"]
    W, H, L, R, T, B = 880, 380, 48, 236, 28, 330
    hi = max(max(ra), max(bl)) * 1.15
    step = 0.1 if hi > 0.45 else 0.05 if hi > 0.12 else 0.02
    top = step * math.ceil(hi / step - 1e-9)
    n = len(months) - 1
    x = lambda i: L + i * (W - L - R) / n
    y = lambda v: B - v / top * (B - T)
    o = []
    for g in range(int(round(top / step)) + 1):
        v = g * step
        o.append(f'<line class="{"base" if g == 0 else "dash"}" x1="{L}" x2="{W - R + 8}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                 f'<text x="{L - 12}" y="{y(v) + 4:.1f}" text-anchor="end">{round(v * 100)}%</text>')
    grid = "".join(o)
    xl = "".join(f'<text x="{x(i):.1f}" y="{B + 26}" text-anchor="middle">{_month_label(m).upper()}</text>'
                 for i, m in enumerate(months))
    pr = [(x(i), y(v)) for i, v in enumerate(ra)]
    pb = [(x(i), y(v)) for i, v in enumerate(bl)]
    d_rise = smooth(pr)
    area = f'<path class="ts-area" d="{d_rise} L{x(n):.1f},{B} L{x(0):.1f},{B} Z"/>'
    lines = (f'<path class="ts-base" d="{smooth(pb)}"/><path class="ts-rise" d="{d_rise}"/>'
             f'<circle class="ts-start" cx="{pr[0][0]:.1f}" cy="{pr[0][1]:.1f}" r="6"/>'
             f'<circle class="ts-halo" cx="{pr[-1][0]:.1f}" cy="{pr[-1][1]:.1f}" r="12"/>'
             f'<circle class="ts-end" cx="{pr[-1][0]:.1f}" cy="{pr[-1][1]:.1f}" r="6.5"/>'
             f'<circle class="ts-base-end" cx="{pb[-1][0]:.1f}" cy="{pb[-1][1]:.1f}" r="4.5"/>')
    # Labels at the right edge, moved apart when the two lines end close together
    ry, by = pr[-1][1], pb[-1][1]
    if abs(ry - by) < 62:
        mid = (ry + by) / 2
        ry, by = (mid - 31, mid + 31) if ry <= by else (mid + 31, mid - 31)
    lx = x(n) + 22
    start_txt = f"{pct(ra[0])} in {_month_label(months[0], True)}"
    sw = len(start_txt) * 6.9 + 22
    base_note = (f"{pct(bl[-1])}, flat all year" if abs(bl[-1] - bl[0]) < 0.15 * max(bl[0], 0.001)
                 else f"{pct(bl[-1])}, from {pct(bl[0])}")
    labels = (f'<g class="ts-pill"><rect x="{pr[0][0] + 12:.1f}" y="{pr[0][1] - 34:.1f}" width="{sw:.1f}" height="24" rx="12"/>'
              f'<text x="{pr[0][0] + 12 + sw / 2:.1f}" y="{pr[0][1] - 17.5:.1f}" text-anchor="middle">{esc(start_txt)}</text></g>'
              f'<text class="ts-name" x="{lx:.1f}" y="{ry - 14:.1f}">{esc(d["rise_name"])}</text>'
              f'<text class="ts-value" x="{lx:.1f}" y="{ry + 16:.1f}">{pct(ra[-1])}</text>'
              f'<g class="ts-x"><rect x="{lx + 62:.1f}" y="{ry - 2:.1f}" width="40" height="24" rx="12"/>'
              f'<text x="{lx + 82:.1f}" y="{ry + 14.5:.1f}" text-anchor="middle">{_times(ra[-1] / max(ra[0], 0.001))}</text></g>'
              f'<text class="ts-base-name" x="{lx:.1f}" y="{by - 6:.1f}">{esc(d["base_name"])}</text>'
              f'<text class="ts-base-note" x="{lx:.1f}" y="{by + 12:.1f}">{esc(base_note)}</text>')
    cols = []
    bw = (W - L - R) / n
    for i, m in enumerate(months):
        cx = x(i)
        text = f'{_month_label(m, True)}: {d["rise_name"]} {pct(ra[i], 1)}, {d["base_name"]} {pct(bl[i], 1)}'
        tw = round(24 + 6.4 * len(text))
        tx = cx + 12 if cx + 12 + tw < W else cx - 12 - tw
        cols.append(f'<g class="col" tabindex="0" aria-label="{esc(text)}"><rect class="hit" x="{cx - bw / 2:.1f}" y="{T}" width="{bw:.1f}" height="{B - T}"/>'
                    f'<line class="cross" x1="{cx:.1f}" x2="{cx:.1f}" y1="{T}" y2="{B}"/>'
                    f'<g class="tip"><rect x="{tx:.1f}" y="{T}" width="{tw}" height="30" rx="8"/>'
                    f'<text x="{tx + 12:.1f}" y="{T + 20}">{esc(text)}</text></g></g>')
    label = (f'{d["rise_name"]} went from {pct(ra[0])} to {pct(ra[-1])} of papers between {_month_label(months[0], True)} '
             f'and {_month_label(months[-1], True)}, while {d["base_name"]} went from {pct(bl[0])} to {pct(bl[-1])}.')
    return (f'<div class="sc-scroll"><svg class="chart ts-chart" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(label)}">'
            f'<g class="grid">{grid}</g><g class="xlab">{xl}</g>{area}{lines}{labels}<g class="cols">{"".join(cols)}</g></svg></div>')


def topic_shift_table(d: dict) -> str:
    rows = "".join(f'<tr><th scope=row>{_month_label(m, True)}</th><td>{pct(d["rise_line"][i], 1)}</td><td>{pct(d["base_line"][i], 1)}</td></tr>'
                   for i, m in enumerate(d["months"]))
    return (f'<table class="data-table"><thead><tr><th scope=col>Month</th><th scope=col>{esc(d["rise_name"])}</th>'
            f'<th scope=col>{esc(d["base_name"])}</th></tr></thead><tbody>{rows}</tbody></table>')


# ---------------------------------------------------------------------------
# 02 Momentum: every technology's change in share, grouped
# ---------------------------------------------------------------------------

def momentum_bars(stats: list[dict]) -> str:
    rated = [s for s in stats if s["status"] in dict(GROUPS) and s["growth"]]
    if not rated:
        return ""
    ch = {s["id"]: max(min((s["growth"] - 1) * 100, 300), -100) for s in rated}
    lo, hi = min(min(ch.values()), -40), max(max(ch.values()), 40)
    span = hi - lo
    zero = -lo / span * 100
    out = []
    for st, label in GROUPS:
        group = sorted((s for s in rated if s["status"] == st), key=lambda s: -s["growth"])
        if not group:
            continue
        out.append(f'<li class="mb-group g-{st}"><span>{label}</span></li>')
        for s in group:
            v = ch[s["id"]]
            w = max(abs(v) / span * 100, 0.6)
            left = zero if v >= 0 else zero - w
            strength = 0.45 + 0.55 * min(abs(v) / max(abs(hi), abs(lo)), 1)
            out.append(f'<li class="mb-row st-{st}"><a href="{_search(s["name"])}">'
                       f'<span class="mb-name">{esc(s["name"])}</span>'
                       f'<span class="mb-track" aria-hidden="true"><i class="mb-zero" style="left:{zero:.1f}%"></i>'
                       f'<i class="mb-bar" style="left:{left:.1f}%;width:{w:.1f}%;--k:{strength:.2f}"></i></span>'
                       f'<span class="mb-val">{change(s["growth"])}</span></a></li>')
    return f'<ol class="mb" aria-label="Change in each technology’s share of new papers">{"".join(out)}</ol>'


# ---------------------------------------------------------------------------
# 03 Research against practice
# ---------------------------------------------------------------------------

def case_shares(cases: list[dict]) -> tuple[dict[str, float], int]:
    """Share of company case studies that mention each technology, matched by keyword."""
    counts = Counter()
    for c in cases:
        text = " ".join([c.get("title") or "", c.get("summary") or "", c.get("issue") or "",
                         c.get("result") or "", " ".join(c.get("tags") or [])])
        counts.update(tag_technologies(text))
    n = len(cases)
    return ({t: counts[t] / n for t in counts} if n else {}), n


def research_vs_practice(stats: list[dict], cases: list[dict]) -> dict | None:
    cs, n = case_shares(cases)
    if n < MIN_CASES:
        return None
    rows = [{"name": s["name"], "paper": s["share"], "case": cs.get(s["id"], 0.0)}
            for s in stats if s["share"] > 0 or cs.get(s["id"])]
    practice = sorted((r for r in rows if r["case"] >= 0.05 and r["case"] > 1.3 * r["paper"]),
                      key=lambda r: -(r["case"] / max(r["paper"], 0.005)))[:4]
    research = sorted((r for r in rows if r["paper"] >= 0.03 and r["paper"] > 1.3 * r["case"]),
                      key=lambda r: -(r["paper"] / max(r["case"], 0.005)))[:6]
    if not practice or not research:
        return None
    return {"practice": practice, "research": research, "n": n}


def name_list(names: list[str], most: int = 3, chars: int = 40) -> str:
    """'tool use, retrieval and AI agents': up to three short names that fit in a headline."""
    short = [n.split(" (")[0] for n in names]
    short = [n if n.startswith("AI") else n[0].lower() + n[1:] for n in short]
    out = short[:1]
    for n in short[1:most]:
        if sum(len(x) for x in out) + len(n) > chars:
            break
        out.append(n)
    if len(out) == 1:
        return out[0]
    last = ", and " if len(out) > 2 and any(" and " in n for n in out) else " and "
    return ", ".join(out[:-1]) + last + out[-1]


def _gap(r: dict) -> str:
    if r["case"] == 0:
        return "papers only"
    if r["paper"] == 0:
        return "practice only"
    return _times(max(r["case"] / r["paper"], r["paper"] / r["case"]))


def research_vs_practice_chart(d: dict) -> str:
    top = max(max(r["paper"], r["case"]) for r in d["practice"] + d["research"]) * 1.08
    ticks = [t for t in (0, .1, .2, .3, .4, .5, .6, .7) if t <= top]
    out = []
    for key, label in (("practice", "Ahead in practice"), ("research", "Ahead in research")):
        out.append(f'<li class="rp-group g-{key}"><span>{label}</span></li>')
        for r in d[key]:
            a, b = r["paper"] / top * 100, r["case"] / top * 100
            lo, hi = min(a, b), max(a, b)
            out.append(f'<li class="rp-row {key}"><span class="rp-name">{esc(r["name"])}</span>'
                       f'<span class="rp-track" aria-hidden="true">'
                       f'<i class="rp-bar" style="left:{lo:.1f}%;width:{hi - lo:.1f}%"></i>'
                       f'<i class="rp-paper" style="left:{a:.1f}%" title="{pct(r["paper"], 1)} of papers"></i>'
                       f'<i class="rp-case" style="left:{b:.1f}%" title="{pct(r["case"], 1)} of case studies"></i></span>'
                       f'<span class="rp-gap">{_gap(r)}</span>'
                       f'<span class="rp-vals">{pct(r["paper"], 1)} of papers · {pct(r["case"], 1)} of case studies</span></li>')
    axis = "".join(f'<span style="left:{t / top * 100:.1f}%">{round(t * 100)}%</span>' for t in ticks)
    return (f'<div class="rp"><p class="rp-key"><span><i class="rp-paper"></i>Research papers</span>'
            f'<span><i class="rp-case"></i>Company case studies</span><b>Gap</b></p>'
            f'<ol class="rp-list">{"".join(out)}</ol><div class="rp-axis" aria-hidden="true"><span></span><span class="rp-ticks">{axis}</span></div></div>')


def research_vs_practice_table(d: dict) -> str:
    rows = "".join(f'<tr><th scope=row>{esc(r["name"])}</th><td>{pct(r["paper"], 1)}</td><td>{pct(r["case"], 1)}</td><td>{_gap(r)}</td></tr>'
                   for r in d["practice"] + d["research"])
    return ('<table class="data-table"><thead><tr><th scope=col>Technology</th><th scope=col>Papers, last 90 days</th>'
            f'<th scope=col>Case studies</th><th scope=col>Gap</th></tr></thead><tbody>{rows}</tbody></table>')


# ---------------------------------------------------------------------------
# 04 Off the peak
# ---------------------------------------------------------------------------

def off_peak(stats: list[dict], months: list[str], month_totals: Counter) -> list[dict]:
    """Cooling technologies, each one's best month against the latest full month."""
    use = full_months(months, month_totals)
    n = len(use)
    if n < 4:
        return []
    out = []
    for s in stats:
        if s["status"] != "cooling":
            continue
        line = s["line"][:n]
        i = max(range(n - 1), key=lambda j: line[j])
        peak, now = line[i], line[-1]
        if peak >= 0.01 and now < 0.8 * peak:
            out.append({"name": s["name"], "peak": peak, "peak_month": use[i], "now": now, "now_month": use[-1],
                        "drop": 1 - now / peak})
    return sorted(out, key=lambda r: -r["peak"])[:5]


def off_peak_chart(rows: list[dict]) -> str:
    top = max(r["peak"] for r in rows) / 0.72  # room for the peak label beside the longest bar
    out = []
    for r in rows:
        p, n_ = r["peak"] / top * 100, r["now"] / top * 100
        out.append(f'<li><span class="op-name">{esc(r["name"])}</span>'
                   f'<span class="op-track"><i class="op-peak" style="width:{p:.1f}%"></i>'
                   f'<i class="op-now" style="width:{n_:.1f}%"><b>{pct(r["now"], 1)}</b></i>'
                   f'<em style="left:{p:.1f}%">peak {pct(r["peak"], 1)}, {_month_label(r["peak_month"])}</em></span>'
                   f'<span class="op-drop">−{round(r["drop"] * 100)}%</span></li>')
    return f'<ol class="op">{"".join(out)}</ol>'


def off_peak_table(rows: list[dict]) -> str:
    body = "".join(f'<tr><th scope=row>{esc(r["name"])}</th><td>{pct(r["peak"], 1)} ({_month_label(r["peak_month"], True)})</td>'
                   f'<td>{pct(r["now"], 1)}</td><td>−{round(r["drop"] * 100)}%</td></tr>' for r in rows)
    return (f'<table class="data-table"><thead><tr><th scope=col>Technology</th><th scope=col>Best month</th>'
            f'<th scope=col>{_month_label(rows[0]["now_month"], True)}</th><th scope=col>Change</th></tr></thead><tbody>{body}</tbody></table>')


# ---------------------------------------------------------------------------
# 05 Words on the rise
# ---------------------------------------------------------------------------

def words_chart(words: list[dict]) -> str:
    top = max(max(w["now"], w["before"]) for w in words) * 1.1
    out = []
    for w in words:
        out.append(f'<li><a class="wr-word" href="papers.html?q={quote(w["word"])}">{esc(w["word"])}</a>'
                   f'<span class="wr-bars"><span><i class="wr-before" style="width:{w["before"] / top * 100:.1f}%"></i>{pct(w["before"], 1)} before</span>'
                   f'<span><i class="wr-now" style="width:{w["now"] / top * 100:.1f}%"></i><b>{pct(w["now"], 1)} now</b></span></span>'
                   f'<span class="wr-x">{w["ratio"]:.1f}×</span></li>')
    return f'<ol class="wr">{"".join(out)}</ol>'


def words_table(words: list[dict]) -> str:
    body = "".join(f'<tr><th scope=row>{esc(w["word"])}</th><td>{pct(w["before"], 1)}</td><td>{pct(w["now"], 1)}</td>'
                   f'<td>{w["ratio"]:.1f}×</td></tr>' for w in words)
    return ('<table class="data-table"><thead><tr><th scope=col>Word</th><th scope=col>Titles before</th>'
            f'<th scope=col>Titles, last 3 months</th><th scope=col>Change</th></tr></thead><tbody>{body}</tbody></table>')


# ---------------------------------------------------------------------------
# The opening: a headline and a sentence written from the numbers
# ---------------------------------------------------------------------------

def opening(shift: dict | None, stats: list[dict], rp: dict | None, code_now: tuple[str, float]) -> tuple[str, str, list]:
    """The headline, the paragraph under it, and four (number, tone, label) stats."""
    breakout = max((s for s in stats if s["status"] in ("breakout", "rising") and s["growth"]),
                   key=lambda s: s["growth"], default=None)
    cooling = [s for s in stats if s["status"] == "cooling" and s["growth"]]
    cool = min(cooling, key=lambda s: s["growth"], default=None)
    # The cooling technology companies still use most makes the best contrast
    if rp and cooling:
        in_practice = {r["name"]: r["case"] for r in rp["practice"] + rp["research"]}
        used = [s for s in cooling if in_practice.get(s["name"], 0) >= 0.05]
        if used:
            cool = max(used, key=lambda s: in_practice[s["name"]])
    sentences, stats_out = [], []
    if shift:
        phrase = TOPIC_PHRASE.get(shift["rise"])
        if phrase and shift["growth"] >= 1.5:
            head = f'AI research is becoming <span class="accent">{esc(phrase)}.</span>'
        else:
            head = f'<span class="accent">{esc(shift["rise_name"])}</span> is the fastest-growing topic in AI research.'
        r0, r1 = shift["rise_line"][0], shift["rise_line"][-1]
        sentences.append(f'Papers on {esc(shift["rise_name"].lower())} went from {pct(r0)} to {pct(r1)} of the field '
                         f'in {len(shift["months"])} months.')
        stats_out.append((_times(r1 / max(r0, 0.001)), "up", f'{esc(shift["rise_name"].lower())}, share in a year'))
    elif breakout:
        head = f'<span class="accent">{esc(breakout["name"])}</span> is the breakout technology of the season.'
    else:
        head = "What AI research is about right now."
    if breakout:
        g = breakout["growth"]
        if g >= 2:
            sentences.append(f'{esc(breakout["name"])} more than doubled its share in 90 days.')
        elif g >= 1.75:
            sentences.append(f'{esc(breakout["name"])} nearly doubled its share in 90 days.')
        else:
            sentences.append(f'{esc(breakout["name"])} grew its share by {change(g).lstrip("+")} in 90 days.')
        stats_out.append((change(g), "up", f'{esc(breakout["name"].lower())}, share in 90 days'))
    if cool:
        line = f'{esc(cool["name"])} is cooling in research'
        share_cases = rp and next((r["case"] for r in rp["practice"] + rp["research"] if r["name"] == cool["name"]), 0)
        if share_cases and share_cases >= 0.05:
            line += f', yet one company write-up in {round(1 / share_cases)} still runs on it'
        sentences.append(line + ".")
        stats_out.append((change(cool["growth"]), "down", f'{esc(cool["name"].lower())} in research'))
    stats_out.append((pct(code_now[1]), "ink", f'of {_month_label(code_now[0])}’s papers link to code'))
    return head, " ".join(sentences), stats_out[:4]
