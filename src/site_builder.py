"""
site_builder.py
Builds the static website in site/ from the JSON records in data/.
Plain HTML, one CSS file and one small JS file: no frameworks, no npm.

Pages:
  index.html            hero, today's featured papers, more from today, categories
  papers.html           every paper, with search, category filter and sort (JS)
  archive.html          every day, newest first
  day/<date>.html       all papers of one day
  paper/<id>.html       one page per paper
  data/papers.json      compact list of all papers, read by papers.html
"""
import html
import json
import os
import shutil
import sys
from datetime import date

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SRC_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from classifier import CATEGORIES

DATA_DIR = os.path.join(ROOT_DIR, "data")
SITE_DIR = os.path.join(ROOT_DIR, "site")
ASSETS_DIR = os.path.join(SRC_DIR, "site_assets")

SITE_NAME = "AI Papers Daily"
TAGLINE = ("Every morning we read the newest AI papers on arXiv and Hugging Face, "
           "pick the ones worth your time, and explain why they matter.")
MORE_FROM_TODAY = 10  # non-featured papers shown on the home page

CATEGORY_NAMES = {slug: name for _, name, slug, _, _ in CATEGORIES}
CATEGORY_NAMES["other-ml"] = "Other ML"

# Icons drawn from Lucide (ISC licence), inlined so the site makes no extra requests
ICONS = {
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "arrow": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "back": '<path d="m15 18-6-6 6-6"/>',
    "external": '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    "file": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M16 13H8M16 17H8M10 9H8"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2m-7.07-14.07 1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
    "moon": '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
}


def icon(name: str, size: int = 16, cls: str = "") -> str:
    klass = f' class="{cls}"' if cls else ""
    return (f'<svg{klass} width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


def esc(text) -> str:
    return html.escape(str(text or ""), quote=True)


def category_name(slug: str) -> str:
    return CATEGORY_NAMES.get(slug, "Other ML")


def format_authors(authors: list, limit: int = 4) -> str:
    if len(authors) <= limit:
        return ", ".join(authors)
    return ", ".join(authors[:limit]) + f" + {len(authors) - limit} more"


def nice_date(iso: str, with_year: bool = True) -> str:
    """'2026-10-31' -> '31 Oct 2026' (or 'Oct 31' without the year)."""
    try:
        d = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    return f"{d.day} {d:%b %Y}" if with_year else f"{d:%b} {d.day}"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_days(data_dir: str = DATA_DIR) -> list[dict]:
    """All daily files, newest first."""
    daily_dir = os.path.join(data_dir, "daily")
    if not os.path.isdir(daily_dir):
        return []
    days = []
    for name in sorted(os.listdir(daily_dir), reverse=True):
        if name.endswith(".json"):
            with open(os.path.join(daily_dir, name), encoding="utf-8") as f:
                days.append(json.load(f))
    return days


def merge_papers(days: list[dict]) -> dict[str, dict]:
    """
    One record per paper ID. A paper fetched on several days keeps its newest
    record, but stays featured (with its summary) if it was ever featured.
    """
    papers: dict[str, dict] = {}
    for day in reversed(days):  # oldest first, so newer records overwrite
        for rec in day.get("papers", []):
            old = papers.get(rec["id"])
            rec = dict(rec)
            rec.setdefault("first_seen", day["date"])
            if old:
                rec["first_seen"] = old["first_seen"]
                if old.get("featured") and not rec.get("featured"):
                    rec["featured"] = True
                    rec["summary"] = rec.get("summary") or old.get("summary")
                    rec["featured_on"] = old.get("featured_on")
                if not rec.get("abstract"):
                    rec["abstract"] = old.get("abstract", "")
            if rec.get("featured") and not rec.get("featured_on"):
                rec["featured_on"] = day["date"]
            papers[rec["id"]] = rec
    return papers


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

# Runs before first paint so a saved dark theme never flashes white
THEME_SCRIPT = ("<script>try{var t=localStorage.getItem('apd.theme')||(matchMedia('(prefers-color-scheme: dark)')"
                ".matches?'dark':'light');document.documentElement.dataset.theme=t}catch(e){}</script>")


def page(title: str, body: str, root: str = "", description: str = TAGLINE, active: str = "") -> str:
    """Wrap body in the shared layout. root is the relative path to the site root."""
    full_title = f"{title} · {SITE_NAME}" if title != SITE_NAME else f"{SITE_NAME}: research papers worth building on"

    def nav(href, label, key):
        current = ' aria-current="page"' if key == active else ""
        return f'<a href="{root}{href}"{current}>{label}</a>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(description)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta name="theme-color" content="#ea580c">
{THEME_SCRIPT}
<link rel="preload" href="{root}assets/fonts/geist.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{root}assets/style.css">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='8' fill='%23ea580c'/><text x='16' y='23' font-family='Georgia' font-style='italic' font-size='20' fill='white' text-anchor='middle'>P</text></svg>">
</head>
<body>
<header class="site-header">
  <div class="container">
    <a class="logo" href="{root}index.html"><span class="logo-mark">P</span><span class="logo-text">{SITE_NAME}</span></a>
    <nav class="nav">
      {nav("index.html", "Today", "today")}
      {nav("papers.html", "All papers", "papers")}
      {nav("archive.html", "Archive", "archive")}
    </nav>
    <div class="header-actions">
      <a class="search-trigger" href="{root}papers.html" data-search-trigger>{icon("search", 15)}<span>Search papers…</span><kbd>/</kbd></a>
      <button class="icon-button" type="button" data-theme-toggle aria-label="Toggle dark mode">{icon("moon", 17, "icon-moon")}{icon("sun", 17, "icon-sun")}</button>
    </div>
  </div>
</header>
<main class="container">
{body}
</main>
<footer class="site-footer">
  <div class="container">
    <p>Built from <a href="https://arxiv.org">arXiv</a> and <a href="https://huggingface.co/papers">Hugging Face Papers</a>. Updated every morning.</p>
    <p>Summaries are written by AI. Always check the paper.</p>
  </div>
</footer>
<script src="{root}assets/app.js" defer></script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------

def badges(rec: dict, root: str) -> str:
    out = []
    if rec.get("featured"):
        out.append('<span class="badge badge-pick">Top pick</span>')
    for c in rec.get("categories") or ["other-ml"]:
        out.append(f'<a class="badge" href="{root}papers.html?cat={esc(c)}">{esc(category_name(c))}</a>')
    return f'<div class="badges">{"".join(out)}</div>'


def featured_card(rec: dict, rank: int, root: str) -> str:
    summary = (rec.get("summary") or {}).get("text") or ""
    summary_html = f'<p class="why"><b>Why it matters</b>{esc(summary)}</p>' if summary else ""
    top = '<span class="badge badge-pick">Top pick</span>' if rank == 1 else ""
    return f"""<article class="card">
  <div class="card-meta"><span class="mono">#{rank} · {esc(rec['id'])}</span>{top}</div>
  <h3><a href="{root}paper/{esc(rec['id'])}.html">{esc(rec['title'])}</a></h3>
  <p class="authors">{esc(format_authors(rec.get('authors', []), 3))}</p>
  {summary_html}
  {badges(dict(rec, featured=False), root)}
</article>"""


def paper_row(rec: dict, root: str) -> str:
    return f"""<li class="row">
  <span class="row-date mono">{esc(nice_date(rec.get('first_seen', ''), with_year=False))}</span>
  <span class="row-title"><a href="{root}paper/{esc(rec['id'])}.html">{esc(rec['title'])}</a></span>
  <span class="row-authors">{esc(format_authors(rec.get('authors', []), 3))}</span>
  {badges(rec, root)}
</li>"""


def section_head(title: str, sub: str = "", link: str = "") -> str:
    sub_html = f"<p>{sub}</p>" if sub else ""
    return f'<div class="section-head"><div><h2>{title}</h2>{sub_html}</div>{link}</div>'


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def build_index(days: list[dict], papers: dict) -> str:
    if not days:
        body = '<section class="hero"><h1>No papers yet</h1><p class="lead">The first digest arrives tomorrow morning.</p></section>'
        return page(SITE_NAME, body, active="today")

    latest = days[0]
    featured_ids = latest.get("featured", [])
    featured = [papers[i] for i in featured_ids if i in papers]
    others = [papers[p["id"]] for p in latest["papers"] if p["id"] not in featured_ids][:MORE_FROM_TODAY]

    counts: dict[str, int] = {}
    for rec in papers.values():
        for c in rec.get("categories") or ["other-ml"]:
            counts[c] = counts.get(c, 0) + 1

    cards = "\n".join(featured_card(r, n, "") for n, r in enumerate(featured, 1))
    more = ""
    if others:
        rows = "\n".join(paper_row(r, "") for r in others)
        link = (f'<a class="link-arrow" href="day/{esc(latest["date"])}.html">'
                f'All {len(latest["papers"])} from today {icon("arrow", 14)}</a>')
        more = f"""<section class="section">
  {section_head("More from today", "Also new, ranked by our score.", link)}
  <ul class="list">{rows}</ul>
</section>"""

    cats = "".join(
        f'<a class="cat" href="papers.html?cat={esc(slug)}">{esc(category_name(slug))}<span class="mono">{n}</span></a>'
        for slug, n in sorted(counts.items(), key=lambda kv: -kv[1]))

    body = f"""<section class="hero">
  <a class="announce" href="#today"><span class="badge badge-solid">New</span>{len(featured)} top picks for {esc(nice_date(latest['date']))} {icon("arrow", 14)}</a>
  <h1>Research papers worth <em>building</em> on.</h1>
  <p class="lead">{esc(TAGLINE)}</p>
  <div class="hero-actions">
    <a class="btn btn-primary" href="papers.html">Browse all papers {icon("arrow", 15)}</a>
    <a class="btn btn-outline" href="archive.html">See the archive</a>
  </div>
  <div class="stats"><span><strong>{len(papers)}</strong>papers tracked</span><span><strong>{len(days)}</strong>days</span><span><strong>{len(counts)}</strong>topics</span></div>
</section>
<section class="section" id="today">
  {section_head("Today's picks", esc(nice_date(latest['date'])) + " · chosen from " + str(len(latest['papers'])) + " new papers")}
  <div class="grid">{cards}</div>
</section>
{more}
<section class="section">
  {section_head("Browse by topic", "Every paper we have tracked, grouped by what it is about.")}
  <div class="cats">{cats}</div>
</section>"""
    return page(SITE_NAME, body, active="today")


def build_papers_page() -> str:
    options = "".join(f'<option value="{esc(slug)}">{esc(name)}</option>'
                      for slug, name in CATEGORY_NAMES.items())
    body = f"""<section class="page-head">
  <span class="eyebrow">Library</span>
  <h1>All papers</h1>
  <p>Every paper we have tracked, newest first. Search by title or author, or narrow it down by topic.</p>
</section>
<div class="toolbar">
  <label class="input-wrap">{icon("search", 15)}<input class="input" id="q" type="search" placeholder="Search title or author…" aria-label="Search papers" autocomplete="off"></label>
  <select class="select" id="cat" aria-label="Topic"><option value="">All topics</option>{options}</select>
  <select class="select" id="sort" aria-label="Sort"><option value="new">Newest first</option><option value="score">Highest score</option></select>
  <label class="toggle"><input id="feat" type="checkbox"> Top picks only</label>
</div>
<div class="result-meta"><span id="count">Loading papers…</span></div>
<ul class="list" id="results"></ul>
<div class="center"><button class="btn btn-outline" id="more" type="button" hidden>Show more</button></div>
<noscript><p class="empty">Turn on JavaScript to search, or browse the <a href="archive.html">archive</a>.</p></noscript>"""
    return page("All papers", body, active="papers")


def build_archive(days: list[dict], papers: dict) -> str:
    rows = []
    for day in days:
        picks = " · ".join(esc(papers[i]["title"]) for i in day.get("featured", []) if i in papers)
        rows.append(f"""<li class="row">
  <span class="row-date mono">{esc(nice_date(day['date'], with_year=False))}</span>
  <span class="row-title"><a href="day/{esc(day['date'])}.html">{esc(nice_date(day['date']))}</a></span>
  <span class="row-authors">{picks}</span>
  <div class="badges"><span class="badge">{len(day.get('papers', []))} papers</span></div>
</li>""")
    body = f"""<section class="page-head">
  <span class="eyebrow">Archive</span>
  <h1>Every edition</h1>
  <p>{len(days)} days of papers, newest first. Each day lists its top picks and everything else we found.</p>
</section>
<ul class="list">{''.join(rows)}</ul>"""
    return page("Archive", body, active="archive")


def build_day(day: dict, papers: dict) -> str:
    featured_ids = day.get("featured", [])
    featured = [papers[i] for i in featured_ids if i in papers]
    rest = [papers[p["id"]] for p in day["papers"] if p["id"] not in featured_ids]
    cards = "\n".join(featured_card(r, n, "../") for n, r in enumerate(featured, 1))
    rest_html = ""
    if rest:
        rows = "\n".join(paper_row(r, "../") for r in rest)
        rest_html = f'<section class="section">{section_head("Everything else", f"{len(rest)} more papers from this day.")}<ul class="list">{rows}</ul></section>'
    body = f"""<section class="page-head">
  <a class="crumbs" href="../archive.html">{icon("back", 15)} Archive</a>
  <h1>{esc(nice_date(day['date']))}</h1>
  <p>{len(day['papers'])} papers that day.</p>
</section>
<section class="section">{section_head("Top picks")}<div class="grid">{cards}</div></section>
{rest_html}"""
    return page(nice_date(day["date"]), body, root="../", active="archive")


def build_paper(rec: dict) -> str:
    summary = (rec.get("summary") or {}).get("text")
    summary_html = (f'<div class="callout"><span class="eyebrow">Why it matters</span><p>{esc(summary)}</p></div>'
                    if summary else "")
    abstract = rec.get("abstract")
    abstract_html = f'<div class="prose"><h2>Abstract</h2><p>{esc(abstract)}</p></div>' if abstract else ""

    facts = [("Submitted", nice_date(rec.get("submitted", ""))), ("Added", nice_date(rec.get("first_seen", "")))]
    if rec.get("featured_on"):
        facts.append(("Top pick on", f'<a href="../day/{esc(rec["featured_on"])}.html">{esc(nice_date(rec["featured_on"]))}</a>'))
    if rec.get("hf_upvotes"):
        facts.append(("HF upvotes", str(rec["hf_upvotes"])))
    facts.append(("Authors", str(len(rec.get("authors", [])))))
    facts_html = "".join(f"<div><dt>{k}</dt><dd>{v if k == 'Top pick on' else esc(v)}</dd></div>" for k, v in facts)

    body = f"""<article class="paper" data-paper-id="{esc(rec['id'])}">
  <div class="crumbs"><a href="../papers.html">{icon("back", 15)} All papers</a><span>/</span><span class="mono">arXiv {esc(rec['id'])}</span></div>
  <h1>{esc(rec['title'])}</h1>
  <p class="authors">{esc(', '.join(rec.get('authors', [])))}</p>
  {badges(rec, '../')}
  {summary_html}
  {abstract_html}
  <dl class="facts">{facts_html}</dl>
  <div class="actions">
    <a class="btn btn-primary" href="{esc(rec.get('url'))}" rel="noopener">Read on arXiv {icon("external", 15)}</a>
    <a class="btn btn-outline" href="{esc(rec.get('pdf_url'))}" rel="noopener">{icon("file", 15)} PDF</a>
    <a class="btn btn-outline" href="https://huggingface.co/papers/{esc(rec['id'])}" rel="noopener">Hugging Face {icon("external", 15)}</a>
  </div>
</article>"""
    desc = summary or (abstract or "")[:160]
    return page(rec["title"], body, root="../", description=desc)


def compact(rec: dict) -> dict:
    """The fields papers.html needs, with short keys to keep the file small."""
    return {
        "i": rec["id"],
        "t": rec["title"],
        "a": rec.get("authors", [])[:3],
        "n": len(rec.get("authors", [])),
        "c": rec.get("categories") or ["other-ml"],
        "d": rec.get("first_seen", ""),
        "s": rec.get("score") or 0,
        "f": 1 if rec.get("featured") else 0,
    }


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def build_site(data_dir: str = DATA_DIR, site_dir: str = SITE_DIR) -> int:
    """Rebuild site_dir from scratch. Returns the number of paper pages written."""
    days = load_days(data_dir)
    papers = merge_papers(days)

    if os.path.isdir(site_dir):
        shutil.rmtree(site_dir)
    shutil.copytree(ASSETS_DIR, os.path.join(site_dir, "assets"))

    _write(os.path.join(site_dir, "index.html"), build_index(days, papers))
    _write(os.path.join(site_dir, "papers.html"), build_papers_page())
    _write(os.path.join(site_dir, "archive.html"), build_archive(days, papers))
    for day in days:
        _write(os.path.join(site_dir, "day", f"{day['date']}.html"), build_day(day, papers))
    for rec in papers.values():
        _write(os.path.join(site_dir, "paper", f"{rec['id']}.html"), build_paper(rec))

    listing = sorted(papers.values(), key=lambda r: (r.get("first_seen", ""), r.get("score") or 0),
                     reverse=True)
    _write(os.path.join(site_dir, "data", "papers.json"),
           json.dumps([compact(r) for r in listing], ensure_ascii=False, separators=(",", ":")))
    # GitHub Pages: serve files as-is, no Jekyll processing
    _write(os.path.join(site_dir, ".nojekyll"), "")

    print(f"  [site] Built {len(papers)} paper pages and {len(days)} day pages in {site_dir}")
    return len(papers)


if __name__ == "__main__":
    build_site()
