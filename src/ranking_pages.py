"""
ranking_pages.py
How the ranking is shown to readers, so anyone can check it:

  why_ranked(rec)        the "Why this ranked" section on a paper's page: its place that
                         day, points per group, and the public numbers behind each one
  methodology_body(...)  the Methodology page: the formula, the sources, what the LLM
                         does and doesn't do, the scoreboard, and the data downloads
  score_exports(day)     the day's scores as JSON and CSV, linked from the Methodology page

Plain HTML strings; site_builder.py wraps them in the site's page layout.
"""
import csv
import html
import io
import json

import scorer

METHOD_HREF = "methodology.html"
REPO = "https://github.com/Omen-bit/ai-paper-daily"


def esc(text) -> str:
    return html.escape(str(text if text is not None else ""), quote=True)


def _n(x) -> str:
    x = float(x)
    return f"{x:,.0f}" if x == int(x) or x >= 100 else f"{x:,.1f}"


def _pts(x) -> str:
    return f"{x:g}" if x == int(x) else f"{x:.1f}"


def has_breakdown(rec: dict) -> bool:
    """Only records scored by the evidence-based scorer carry the numbers behind their score."""
    return isinstance(rec.get("evidence"), dict) and isinstance(rec.get("score_parts"), dict)


def evidence_lines(rec: dict) -> dict[str, list[str]]:
    """Plain-language lines per group, each built from a public number."""
    ev, parts = rec.get("evidence") or {}, rec.get("score_parts") or {}
    est = set(ev.get("estimated") or [])

    def mark(signal: str) -> str:
        return ' <span class="rk-est" title="This lookup failed or the source has no data yet, so the paper got the median of that day\'s papers">estimated</span>' if signal in est else ""

    out = {"builder": [], "community": [], "authors": [], "content": []}
    b = out["builder"]
    b.append("Code released" if ev.get("code") else "No public code found")
    if ev.get("stars") is not None:
        b.append(f"★ {_n(ev['stars'])} GitHub stars")
    if ev.get("stars_gain") is not None:
        b.append(f"+{_n(ev['stars_gain'])} stars since the day before{mark('stars_gain')}")
    arts = [(ev.get("hf_models"), "model"), (ev.get("hf_datasets"), "dataset"), (ev.get("hf_spaces"), "demo")]
    arts = [f"{k} {w}{'' if k == 1 else 's'}" for k, w in arts if k]
    if arts:
        b.append(", ".join(arts) + " on Hugging Face")

    c = out["community"]
    c.append(f"▲ {_n(ev.get('upvotes') or 0)} upvotes on Hugging Face")
    if ev.get("hn_points") is not None:
        txt = f"{_n(ev['hn_points'])} points on Hacker News"
        if ev.get("hn_url"):
            txt = f'<a href="{esc(ev["hn_url"])}" rel="noopener">{txt}</a>'
        c.append(txt + mark("hn"))

    a = out["authors"]
    if ev.get("h_index") is not None:
        a.append(f"Authors' median h-index {_n(ev['h_index'])} (Semantic Scholar){mark('h_index')}")
    if ev.get("lab"):
        a.append(f"From {esc(ev['lab'])}" + (" (a known lab)" if parts.get("lab") == scorer.KNOWN_LAB_POINTS else ""))

    t = out["content"]
    if ev.get("claims"):
        n = ev["claims"]
        t.append(f"{n} benchmark result{'' if n == 1 else 's'}, each found word for word in the abstract")
    if ev.get("novelty_pct") is not None:
        t.append(f"Less like recent papers than {round(100 * ev['novelty_pct'])}% of that day's candidates")
    return out


def why_ranked(rec: dict, root: str = "../") -> str:
    """The "Why this ranked" section, or '' for papers ranked before the evidence-based scorer."""
    if not has_breakdown(rec):
        return ""
    parts = rec["score_parts"]
    lines = evidence_lines(rec)
    place = ""
    if rec.get("rank") and rec.get("of"):
        place = f'#{int(rec["rank"])} of {int(rec["of"])} papers that day, '
    groups = []
    for g in scorer.group_points(parts):
        pct = 0 if not g["max"] else round(100 * g["points"] / g["max"])
        items = "".join(f"<li>{x}</li>" for x in lines.get(g["key"]) or []) or "<li>Nothing found</li>"
        groups.append(f'<div class="rk-g"><p class="rk-h"><span>{esc(g["label"])}</span>'
                      f'<b>{_pts(g["points"])}<small> / {g["max"]}</small></b></p>'
                      f'<div class="rk-bar" role="img" aria-label="{_pts(g["points"])} of {g["max"]} points"><i style="width:{pct}%"></i></div>'
                      f'<ul class="rk-ev">{items}</ul></div>')
    claims = ""
    if rec.get("claims"):
        rows = "".join(
            f'<li><b>{esc(c.get("benchmark"))}</b> <span>{esc(c.get("result"))}{(" " + esc(c["metric"])) if c.get("metric") else ""}</span>'
            f'<q>{esc(c.get("quote"))}</q></li>' for c in rec["claims"])
        claims = (f'<div class="rk-claims"><p class="rd-src rd-src-ai"><span class="rd-tag">Extracted by AI, checked by code</span>'
                  f'Each result was found by the model and kept only because its sentence and number appear word for word in the abstract.</p>'
                  f'<ol>{rows}</ol></div>')
    judge = ""
    if (rec.get("judge") or {}).get("tie_break"):
        j = rec["judge"]
        judge = (f'<p class="rk-judge"><b>Tie-break.</b> This paper was within {scorer.TIE_MARGIN} points of the next one, '
                 f'so an AI editor compared the leaders and preferred it in {int(j.get("wins") or 0)} of {int(j.get("of") or 0)} comparisons'
                 + (f': “{esc(j.get("reason"))}”' if j.get("reason") else ".") + "</p>")
    return f"""<section class="rd-sec rk" id="rank"><h2>Why this ranked</h2>
      <p class="rd-src rd-src-paper"><span class="rd-tag">Measured</span>Public numbers, not AI<a href="{root}{METHOD_HREF}">How ranking works</a></p>
      <p class="rk-total"><b>{int(rec.get("score") or 0)}<small> / 100</small></b><span>{place}from GitHub, Hugging Face, Hacker News and Semantic Scholar, looked up the morning it was ranked.</span></p>
      <div class="rk-grid">{"".join(groups)}</div>
      {claims}{judge}
    </section>"""


# ---------------------------------------------------------------- methodology page

SOURCES = [
    ("GitHub", "https://docs.github.com/en/rest/repos/repos", "stars, stars gained since the day before, licence"),
    ("Hugging Face", "https://huggingface.co/docs/hub/en/paper-pages", "upvotes, and models, datasets and demos that link the paper"),
    ("Hacker News", "https://hn.algolia.com/api", "stories linking the paper: points and comments"),
    ("Semantic Scholar", "https://www.semanticscholar.org/product/api", "authors' h-index now; citations for the 30-day scoreboard"),
    ("arXiv", "https://info.arxiv.org/help/api/index.html", "titles and abstracts, for novelty and claims"),
]

SIGNAL_TEXT = {
    "code": "Public code is linked from Hugging Face or the abstract",
    "stars": "GitHub stars on that code, 2 points per doubling",
    "stars_gain": "Stars gained since the previous day, 1.5 per doubling (a repo under 2 weeks old counts all its stars)",
    "artifacts": "Models 3, datasets 2, demos 1 on Hugging Face that link the paper",
    "upvotes": "Hugging Face upvotes, 3 per doubling",
    "hn": "Hacker News points on stories linking the paper, 1.5 per doubling",
    "h_index": "Median h-index of the authors on Semantic Scholar, 2 per doubling",
    "lab": "A known lab 5, any named lab 2.5",
    "claims": "4 per benchmark result that is quoted word for word from the abstract",
    "novelty": "Where the paper stands among the day's candidates on distance from the last 90 days of papers (TF-IDF)",
}

RANKER_TEXT = {
    "live": "The ranking as published that day",
    "hf-upvotes": "Hugging Face upvotes alone",
    "v1": "First scorer (keyword rules, until 5 Nov 2026)",
    "v2": "Second scorer (upvotes, code, lab, until 12 Nov 2026)",
    "v3 on saved fields": "Current scorer on the fields older days saved",
    "random": "Picking at random",
}


def scoreboard_html(board: dict | None) -> str:
    if not board or not board.get("rankers"):
        first = "30 days after the first full day is saved"
        return (f'<p>The first results arrive {first}, because citations and stars need time to build up. '
                f'The table appears here automatically once the weekly check has data.</p>')
    rows = []
    for name, r in board["rankers"].items():
        label = RANKER_TEXT.get(name) or name.replace("live minus ", "Without ").capitalize()
        rows.append(f'<tr><th scope="row">{esc(label)}</th><td>{r["days"]}</td><td>{round(100 * r["hit"])}%</td>'
                    f'<td>{round(100 * r["p10"])}%</td><td>{r["spearman"]:.2f}</td></tr>')
    return (f'<p>{board["days"]} days from {esc(board.get("first"))} to {esc(board.get("last"))}, each at least '
            f'{board["min_age"]} days old. Impact = the average of where a paper stands that day on Semantic Scholar citations '
            f'and on GitHub stars, measured now. Last checked {esc((board.get("generated_at") or "")[:10])}.</p>'
            f'<div class="mt-table"><table><thead><tr><th scope="col">Ranking</th><th scope="col">Days</th>'
            f'<th scope="col">Top pick in top 10</th><th scope="col">Top 10 overlap</th><th scope="col">Rank correlation</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>'
            f'<p class="rd-note">"Without …" rows drop one group of signals, to show which ones carry the ranking. '
            f'We publish the result even when a simpler ranking does as well.</p>')


def methodology_body(board: dict | None, latest_date: str = "") -> str:
    groups = []
    for key, label, sigs in scorer.GROUPS:
        rows = "".join(f'<tr><td>{esc(SIGNAL_TEXT[s])}</td><td>{m}</td></tr>' for s, m in sigs)
        total = sum(m for _, m in sigs)
        groups.append(f'<tbody><tr class="mt-group"><th scope="rowgroup">{esc(label)}</th><th>{total}</th></tr>{rows}</tbody>')
    sources = "".join(f'<li><a href="{esc(u)}" rel="noopener">{esc(n)}</a>: {esc(t)}</li>' for n, u, t in SOURCES)
    downloads = ""
    if latest_date:
        downloads = (f'<p><a class="rd-pill" href="data/scores-latest.csv" download>Download {esc(latest_date)} scores (CSV)</a> '
                     f'<a class="rd-pill" href="data/scores-latest.json" download>JSON</a></p>')
    return f"""<div class="mt prose">
  <p class="rd-lbl">/ Methodology</p>
  <h1>How papers are ranked</h1>
  <p class="mt-lede">Every candidate paper gets a score out of 100 from public numbers we look up each morning.
  An LLM does not pick the papers. It writes the summaries, and it lists the benchmark results an abstract claims, which code then checks word for word.</p>

  <h2>In short</h2>
  <ul class="mt-short">
    <li><b>Do people use it?</b> Code on GitHub, how fast it gains stars, and models or demos built on it.</li>
    <li><b>Are people talking about it?</b> Upvotes on Hugging Face and points on Hacker News.</li>
    <li><b>Who wrote it?</b> How often the authors' past work is cited, and whether a known lab is behind it.</li>
    <li><b>What does it show?</b> Real benchmark results in the abstract, and how new the idea is compared with recent papers.</li>
  </ul>
  <p>The details below are for readers who want the exact formula.</p>

  <h2>The formula</h2>
  <p>Four groups, each capped, so no single source decides the pick. Counts use a log scale: every doubling adds the same points, so one viral number can't swamp the rest.</p>
  <div class="mt-table"><table><thead><tr><th scope="col">Signal</th><th scope="col">Max points</th></tr></thead>{"".join(groups)}</table></div>
  <p>If a lookup fails, or Semantic Scholar hasn't indexed a new paper yet, that signal gets the median of the day's papers and is marked
  <span class="rk-est">estimated</span> on the paper's page. An unknown value is never counted as zero. When the top papers are within {scorer.TIE_MARGIN} points,
  an AI editor compares them in pairs to break the tie, and the page says so.</p>

  <h2>Where the numbers come from</h2>
  <ul>{sources}</ul>
  <p>Every day's numbers are saved in the open, in <a href="{REPO}/tree/main/data/signals" rel="noopener">data/signals</a>, so anyone can see how attention to a paper grew over its first days.</p>

  <h2>Does it work?</h2>
  <p>Once a week we check each saved day against what happened 30 days later, and compare the ranking with simpler ones on the same papers.
  The target is not Hugging Face upvotes, because the ranking reads those itself.</p>
  {scoreboard_html(board)}

  <h2>Known limits</h2>
  <ul>
    <li>These signals measure attention and adoption, not whether a paper is correct.</li>
    <li>Author h-index favours established researchers. It is capped at 10 of 100 points for that reason.</li>
    <li>Papers without code or a Hugging Face page have fewer ways to score, which favours applied work over theory.</li>
    <li>Novelty is measured on words, so a new idea described in familiar terms can look less novel than it is.</li>
  </ul>

  <h2>Get the data</h2>
  <p>Scores, signals and the scoreboard are all in the <a href="{REPO}/tree/main/data" rel="noopener">public repository</a>. The code is in
  <a href="{REPO}/blob/main/src/scorer.py" rel="noopener">scorer.py</a>.</p>
  {downloads}
</div>"""


CSV_COLUMNS = ["rank", "id", "title", "score"] + [f"pts_{s}" for _, _, sigs in scorer.GROUPS for s, _ in sigs] + \
              ["stars", "stars_gain", "upvotes", "hn_points", "h_index", "claims", "novelty", "estimated"]


def score_exports(day: dict | None) -> tuple[str, str]:
    """(JSON, CSV) of a saved day's scores, best first. Empty strings when the day has no breakdowns."""
    if not day:
        return "", ""
    recs = [r for r in day.get("papers") or [] if has_breakdown(r)]
    if not recs:
        return "", ""
    recs.sort(key=lambda r: (r.get("rank") or 10**6, -(r.get("score") or 0)))
    rows = []
    for r in recs:
        ev, parts = r["evidence"], r["score_parts"]
        row = {"rank": r.get("rank"), "id": r["id"], "title": r.get("title", ""), "score": r.get("score")}
        row.update({f"pts_{s}": parts.get(s, 0) for _, _, sigs in scorer.GROUPS for s, _ in sigs})
        row.update({k: ev.get(k) for k in ("stars", "stars_gain", "upvotes", "hn_points", "h_index", "claims", "novelty")})
        row["estimated"] = " ".join(ev.get("estimated") or [])
        rows.append(row)
    js = json.dumps({"date": day.get("date"), "max_points": scorer.MAX_POINTS, "papers": rows}, ensure_ascii=False, indent=1)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return js, buf.getvalue()
