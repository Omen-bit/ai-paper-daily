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
TAGLINE = ("We read every new AI paper on arXiv and Hugging Face, choose the ones you can "
           "build something with, and explain why they matter in plain language.")
MORE_FROM_TODAY = 10  # non-featured papers shown on the home page

CATEGORY_NAMES = {slug: name for _, name, slug, _, _ in CATEGORIES}
CATEGORY_NAMES["other-ml"] = "Other ML"

# Icons drawn from Lucide (ISC licence), inlined so the site makes no extra requests
ICONS = {
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "arrow": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "back": '<path d="m15 18-6-6 6-6"/>',
    "code": '<path d="m16 18 6-6-6-6"/><path d="m8 6-6 6 6 6"/>',
    "external": '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    "file": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M16 13H8M16 17H8M10 9H8"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2m-7.07-14.07 1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
    "moon": '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    "bookmark": '<path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/>',
    "share": '<path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><path d="m16 6-4-4-4 4"/><path d="M12 2v13"/>',
    "quote": '<path d="M17 6H3"/><path d="M21 12H8"/><path d="M21 18H8"/><path d="M3 12v6"/>',
    "next": '<path d="m9 18 6-6-6-6"/>',
}

# The logo: a page with a folded corner and its first line highlighted,
# the way a reader marks the sentence that matters.
LOGO_SVG = ('<svg class="logo-mark" width="28" height="28" viewBox="0 0 32 32" aria-hidden="true">'
            '<rect width="32" height="32" rx="9" fill="#ea580c"/>'
            '<path d="M10 6.5h9l4.5 4.5v13.5a1.5 1.5 0 0 1-1.5 1.5H10a1.5 1.5 0 0 1-1.5-1.5V8a1.5 1.5 0 0 1 1.5-1.5Z" fill="#fff"/>'
            '<path d="M19 6.5V11h4.5Z" fill="#fdba74"/>'
            '<rect x="10.75" y="13" width="10.5" height="3.6" rx="1.2" fill="#fed7aa"/>'
            '<path d="M11.75 14.8h8.5" stroke="#9a3412" stroke-width="1.5" stroke-linecap="round"/>'
            '<path d="M11.75 19.4h8.5M11.75 22.6h5.5" stroke="#a8a29e" stroke-width="1.5" stroke-linecap="round"/>'
            '</svg>')
FAVICON = ("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
           "<rect width='32' height='32' rx='9' fill='%23ea580c'/>"
           "<path d='M10 6.5h9l4.5 4.5v13.5a1.5 1.5 0 0 1-1.5 1.5H10a1.5 1.5 0 0 1-1.5-1.5V8a1.5 1.5 0 0 1 1.5-1.5Z' fill='white'/>"
           "<path d='M19 6.5V11h4.5Z' fill='%23fdba74'/>"
           "<rect x='10.75' y='13' width='10.5' height='3.6' rx='1.2' fill='%23fed7aa'/>"
           "<path d='M11.75 14.8h8.5' stroke='%239a3412' stroke-width='1.5' stroke-linecap='round'/>"
           "<path d='M11.75 19.4h8.5M11.75 22.6h5.5' stroke='%23a8a29e' stroke-width='1.5' stroke-linecap='round'/></svg>")


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


def long_date(iso: str) -> str:
    """'2026-10-31' -> 'Saturday 31 October 2026'."""
    try:
        d = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    return f"{d:%A} {d.day} {d:%B %Y}"


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
                for key in ("curator", "code_url"):
                    if not rec.get(key) and old.get(key):
                        rec[key] = old[key]
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
<link rel="icon" href="{FAVICON}">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site-header">
  <div class="container">
    <a class="logo" href="{root}index.html" aria-label="{SITE_NAME}, home">{LOGO_SVG}<span class="logo-text">AI Papers <span>Daily</span></span></a>
    <nav class="nav">
      {nav("index.html", "Today", "today")}
      {nav("papers.html", "All papers", "papers")}
      {nav("archive.html", "Archive", "archive")}
      <a href="{root}saved.html"{' aria-current="page"' if active == "saved" else ""}>Saved<span class="nav-count" data-saved-count hidden></span></a>
    </nav>
    <div class="header-actions">
      <a class="search-trigger" href="{root}papers.html" data-search-trigger>{icon("search", 15)}<span>Search papers…</span><kbd>/</kbd></a>
      <button class="icon-button" type="button" data-theme-toggle aria-label="Switch light or dark theme" data-tip="Switch theme">{icon("moon", 17, "icon-moon")}{icon("sun", 17, "icon-sun")}</button>
    </div>
  </div>
</header>
<main class="container" id="main">
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
        out.append(f'<a class="badge topic t-{esc(c)}" href="{root}papers.html?cat={esc(c)}">{esc(category_name(c))}</a>')
    return f'<div class="badges">{"".join(out)}</div>'


LEVELS = {"beginner": 1, "intermediate": 2, "advanced": 3}


def level_meter(difficulty: str) -> str:
    """Three bars, filled up to the difficulty, with the word next to them."""
    n = LEVELS.get(difficulty or "", 0)
    if not n:
        return ""
    bars = "".join(f'<i class="{"on" if k <= n else ""}"></i>' for k in (1, 2, 3))
    return f'<span class="level"><span class="level-bars" aria-hidden="true">{bars}</span>{esc(difficulty.capitalize())}</span>'


def featured_card(rec: dict, rank: int, root: str) -> str:
    notes = rec.get("curator") or {}
    if notes.get("tldr"):
        summary_html = f'<p class="why"><b>In short</b>{esc(notes["tldr"])}</p>'
    else:
        summary = (rec.get("summary") or {}).get("text") or ""
        summary_html = f'<p class="why"><b>Why it matters</b>{esc(summary)}</p>' if summary else ""
    extras = level_meter(notes.get("difficulty"))
    if rec.get("code_url"):
        extras += f'<span class="has-code">{icon("code", 14)}Code available</span>'
    extras_html = f'<div class="card-extras">{extras}</div>' if extras else ""
    label = '<span class="badge badge-pick">Top pick</span>' if rank == 1 else f'<span class="rank">Pick {rank}</span>'
    topic = (rec.get("categories") or ["other-ml"])[0]
    return f"""<article class="card t-{esc(topic)}">
  <div class="card-meta">{label}<span class="mono">{esc(rec['id'])}</span></div>
  <h3><a href="{root}paper/{esc(rec['id'])}.html">{esc(rec['title'])}</a></h3>
  <p class="authors">{esc(format_authors(rec.get('authors', []), 3))}</p>
  {summary_html}
  {extras_html}
  {badges(dict(rec, featured=False), root)}
</article>"""


def paper_row(rec: dict, root: str) -> str:
    return f"""<li class="row" data-id="{esc(rec['id'])}">
  <span class="row-date">{esc(nice_date(rec.get('first_seen', ''), with_year=False))}</span>
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
                f'See all {len(latest["papers"])} papers from today</a>')
        more = f"""<section class="section">
  {section_head("More from today", "Also new, ranked by our score.", link)}
  <ul class="list">{rows}</ul>
</section>"""

    cats = "".join(
        f'<a class="cat t-{esc(slug)}" href="papers.html?cat={esc(slug)}"><span>{esc(category_name(slug))}</span><span class="count">{n}</span></a>'
        for slug, n in sorted(counts.items(), key=lambda kv: -kv[1]))

    first = days[-1]["date"]
    body = f"""<section class="hero">
  <p class="edition">Edition {len(days)}, {esc(long_date(latest['date']))}</p>
  <h1>The AI papers worth building on, picked every morning.</h1>
  <p class="lead">{esc(TAGLINE)}</p>
  <label class="hero-search-label" for="hero-q">Search papers by title or author</label>
  <form class="hero-search" action="papers.html" role="search">
    <label class="input-wrap">{icon("search", 16)}<input class="input input-lg" id="hero-q" name="q" type="search" placeholder="e.g. diffusion, Llama, retrieval"></label>
    <button class="btn btn-primary btn-lg">Search papers</button>
  </form>
  <p class="hero-note">{len(papers)} papers tracked across {len(counts)} topics since {esc(nice_date(first))}. <a href="papers.html">Browse all papers</a></p>
</section>
<section class="section" data-continue hidden>
  {section_head("Continue reading", "Papers you opened recently, newest first.")}
  <ul class="list" data-continue-list></ul>
</section>
<section class="section" id="today">
  {section_head("Today's picks", f"Chosen from {len(latest['papers'])} new papers.")}
  <div class="grid">{cards}</div>
</section>
{more}
<section class="section">
  {section_head("Browse by topic", "Every paper we have tracked, grouped by what it is about.")}
  <div class="cats">{cats}</div>
</section>"""
    return page(SITE_NAME, body, active="today")


SKELETON_ROWS = '<li class="row skeleton" aria-hidden="true"><span></span><span></span></li>' * 6


def build_papers_page() -> str:
    options = "".join(f'<option value="{esc(slug)}">{esc(name)}</option>'
                      for slug, name in CATEGORY_NAMES.items())
    body = f"""<section class="page-head">
  <h1>All papers</h1>
  <p>Every paper we have tracked, newest first. Search by title or author, or narrow it down by topic.</p>
</section>
<div class="toolbar">
  <div class="field field-grow"><label class="field-label" for="q">Search</label>
    <span class="input-wrap">{icon("search", 15)}<input class="input" id="q" type="search" placeholder="Title or author" autocomplete="off"></span></div>
  <div class="field"><label class="field-label" for="cat">Topic</label>
    <select class="select" id="cat"><option value="">All topics</option>{options}</select></div>
  <div class="field"><label class="field-label" for="sort">Sort by</label>
    <select class="select" id="sort"><option value="new">Newest first</option><option value="score">Highest score</option></select></div>
  <label class="toggle"><input id="feat" type="checkbox"> Top picks only</label>
</div>
<div class="result-meta"><span id="count">Loading papers…</span></div>
<ul class="list" id="results" aria-busy="true">{SKELETON_ROWS}</ul>
<div class="center"><button class="btn btn-outline" id="more" type="button" hidden>Show more</button></div>
<noscript><p class="empty">Turn on JavaScript to search, or browse the <a href="archive.html">archive</a>.</p></noscript>"""
    return page("All papers", body, active="papers")


def build_archive(days: list[dict], papers: dict) -> str:
    rows = []
    for day in days:
        picks = "; ".join(esc(papers[i]["title"]) for i in day.get("featured", []) if i in papers)
        rows.append(f"""<li class="row">
  <span class="row-date">{esc(nice_date(day['date'], with_year=False))}</span>
  <span class="row-title"><a href="day/{esc(day['date'])}.html">{esc(nice_date(day['date']))}</a></span>
  <span class="row-authors">{picks}</span>
  <div class="badges"><span class="meta-text">{len(day.get('papers', []))} papers</span></div>
</li>""")
    body = f"""<section class="page-head">
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


def bibtex(rec: dict) -> str:
    """A BibTeX entry in the form arXiv uses for preprints."""
    year = (rec.get("submitted") or rec.get("first_seen") or "")[:4]
    authors = " and ".join(rec.get("authors", []))
    return (f"@misc{{arxiv{rec['id'].replace('.', '_')},\n"
            f"  title = {{{rec['title']}}},\n"
            f"  author = {{{authors}}},\n"
            f"  year = {{{year}}},\n"
            f"  eprint = {{{rec['id']}}},\n"
            f"  archivePrefix = {{arXiv}},\n"
            f"  url = {{https://arxiv.org/abs/{rec['id']}}}\n}}")


def reading_minutes(text: str) -> int:
    return max(1, round(len((text or "").split()) / 230))


def abstract_html(abstract: str) -> str:
    """Abstract with its first sentence set as a lede, so the eye has a way in."""
    text = (abstract or "").strip()
    if not text:
        return ""
    cut = text.find(". ")
    if 40 < cut < 400:
        lede, rest = text[:cut + 1], text[cut + 2:]
        return f'<p><span class="lede">{esc(lede)}</span> {esc(rest)}</p>'
    return f"<p>{esc(text)}</p>"


def mini_row(rec: dict, root: str) -> str:
    return f"""<li class="row" data-id="{esc(rec['id'])}">
  <span class="row-title"><a href="{root}paper/{esc(rec['id'])}.html">{esc(rec['title'])}</a></span>
  <span class="row-authors">{esc(format_authors(rec.get('authors', []), 3))}</span>
  {badges(rec, root)}
</li>"""


def curator_notes(notes: dict) -> str:
    """The Curator's reading notes for a top pick."""
    rows = [("What's new", notes.get("whats_new")), ("Key result", notes.get("key_result")),
            ("Why it matters", notes.get("why_it_matters"))]
    grid = "".join(f"<div><dt>{k}</dt><dd>{esc(v)}</dd></div>" for k, v in rows if v)
    ideas = "".join(f"<li>{esc(i)}</li>" for i in notes.get("build_ideas", []))
    reason = notes.get("difficulty_reason")
    level = level_meter(notes.get("difficulty"))
    level_html = f'<p class="notes-level">{level}{f"<span>{esc(reason)}</span>" if reason else ""}</p>' if level else ""
    return f"""<section class="notes" aria-labelledby="notes-title">
    <h2 class="notes-label" id="notes-title">Curator's notes</h2>
    <p class="notes-tldr">{esc(notes["tldr"])}</p>
    <dl class="notes-grid">{grid}</dl>
    <div class="notes-build"><h3>What you could build</h3><ul>{ideas}</ul></div>
    {level_html}
    <p class="notes-foot">Written by AI from the abstract. Check the paper before you rely on a detail.</p>
  </section>"""


def build_paper(rec: dict, related: list[dict] = (), prev: dict = None, nxt: dict = None) -> str:
    summary = (rec.get("summary") or {}).get("text")
    notes = rec.get("curator")
    if notes and notes.get("tldr"):
        summary_html = curator_notes(notes)
    else:
        summary_html = (f'<div class="callout"><span class="callout-label">Why it matters</span><p>{esc(summary)}</p></div>'
                        if summary else "")
    code_html = (f'\n    <a class="btn btn-outline" href="{esc(rec["code_url"])}" rel="noopener">{icon("code", 15)} View the code</a>'
                 if rec.get("code_url") else "")
    abstract = rec.get("abstract")
    abstract_block = ""
    if abstract:
        abstract_block = (f'<div class="prose"><h2>Abstract <span>{reading_minutes(abstract)} min read</span></h2>'
                          f'{abstract_html(abstract)}</div>')

    facts = [("Submitted", nice_date(rec.get("submitted", ""))), ("Added", nice_date(rec.get("first_seen", "")))]
    if rec.get("featured_on"):
        facts.append(("Top pick on", f'<a href="../day/{esc(rec["featured_on"])}.html">{esc(nice_date(rec["featured_on"]))}</a>'))
    if rec.get("hf_upvotes"):
        facts.append(("HF upvotes", str(rec["hf_upvotes"])))
    facts.append(("Authors", str(len(rec.get("authors", [])))))
    facts_html = "".join(f"<div><dt>{k}</dt><dd>{v if k == 'Top pick on' else esc(v)}</dd></div>" for k, v in facts)

    related_html = ""
    if related:
        rows = "\n".join(mini_row(r, "../") for r in related)
        related_html = f"""<section class="section related">
  {section_head("Read next", "Papers on the same ideas, picked by topic and wording.")}
  <ul class="list">{rows}</ul>
</section>"""

    pager = ""
    if prev or nxt:
        prev_html = (f'<a class="pager-link" href="{esc(prev["id"])}.html" rel="prev"><span>Previous paper</span>{esc(prev["title"])}</a>'
                     if prev else "<span></span>")
        next_html = (f'<a class="pager-link next" href="{esc(nxt["id"])}.html" rel="next"><span>Next paper</span>{esc(nxt["title"])}</a>'
                     if nxt else "<span></span>")
        pager = f'<nav class="pager" aria-label="More papers from the same day">{prev_html}{next_html}</nav>'

    title = esc(rec["title"])
    body = f"""<div class="progress" aria-hidden="true"><span data-progress></span></div>
<article class="paper" data-paper-id="{esc(rec['id'])}" data-title="{title}">
  <div class="crumbs"><a href="../papers.html">{icon("back", 15)} All papers</a><span>/</span><span>arXiv <span class="mono">{esc(rec['id'])}</span></span></div>
  <h1>{title}</h1>
  <p class="authors">{esc(', '.join(rec.get('authors', [])))}</p>
  {badges(rec, '../')}
  <div class="reader-tools">
    <button class="btn btn-outline btn-sm" type="button" data-save aria-pressed="false">{icon("bookmark", 15)}<span>Save</span></button>
    <button class="btn btn-outline btn-sm" type="button" data-share>{icon("share", 15)}<span>Share</span></button>
    <details class="cite">
      <summary class="btn btn-outline btn-sm">{icon("quote", 15)}<span>Cite</span></summary>
      <div class="cite-box"><pre data-bibtex>{esc(bibtex(rec))}</pre><button class="btn btn-primary btn-sm" type="button" data-copy-bibtex>Copy BibTeX</button></div>
    </details>
    <div class="text-size" role="group" aria-label="Text size">
      <button type="button" data-size="-1" aria-label="Make text smaller" data-tip="Smaller text">A</button><button type="button" data-size="1" aria-label="Make text larger" data-tip="Larger text">A</button>
    </div>
  </div>
  {summary_html}
  {abstract_block}
  <dl class="facts">{facts_html}</dl>
  <div class="actions">
    <a class="btn btn-primary" href="{esc(rec.get('url'))}" rel="noopener">Read on arXiv {icon("external", 15)}</a>{code_html}
    <a class="btn btn-outline" href="{esc(rec.get('pdf_url'))}" rel="noopener">{icon("file", 15)} Open PDF</a>
    <a class="btn btn-outline" href="https://huggingface.co/papers/{esc(rec['id'])}" rel="noopener">View on Hugging Face {icon("external", 15)}</a>
  </div>
  {pager}
</article>
{related_html}"""
    desc = (notes or {}).get("tldr") or summary or (abstract or "")[:160]
    return page(rec["title"], body, root="../", description=desc)


def build_saved_page() -> str:
    body = """<section class="page-head">
  <h1>Your reading list</h1>
  <p>Papers you save are kept in this browser, so no account is needed. They stay here until you remove them.</p>
</section>
<ul class="list" data-saved-list></ul>
<div class="empty" data-saved-empty hidden><strong>Nothing saved yet.</strong>Open any paper and press Save to keep it here for later.
  <p><a class="btn btn-primary" href="index.html">See today's picks</a></p></div>
<noscript><p class="empty">Turn on JavaScript to see your reading list.</p></noscript>"""
    return page("Your reading list", body, active="saved")


STOPWORDS = set("""a an and are as at be by for from has have in into is it its of on or our that the their
this to via we with which while using use used based new show shows can these than more over between
both such also not only how what when where who model models method methods paper approach results""".split())


def _tokens(rec: dict) -> set[str]:
    text = f"{rec.get('title', '')} {rec.get('abstract', '')}".lower()
    words = "".join(ch if ch.isalnum() or ch == "-" else " " for ch in text).split()
    return {w for w in words if len(w) > 3 and w not in STOPWORDS}


def related_papers(papers: dict, k: int = 4) -> dict[str, list[str]]:
    """
    For every paper, the k most similar papers: shared rare words in the title and
    abstract, plus a bonus for each shared topic. Uses an inverted index so it stays
    fast with tens of thousands of papers.
    """
    import math
    tokens = {pid: _tokens(rec) for pid, rec in papers.items()}
    index: dict[str, list[str]] = {}
    for pid, toks in tokens.items():
        for t in toks:
            index.setdefault(t, []).append(pid)
    limit = max(30, len(papers) // 20)  # words in more than 5% of papers say little
    result = {}
    for pid, toks in tokens.items():
        scores: dict[str, float] = {}
        for t in toks:
            posting = index[t]
            if len(posting) > limit:
                continue
            weight = 1.0 / math.log(len(posting) + 1.5)
            for other in posting:
                if other != pid:
                    scores[other] = scores.get(other, 0.0) + weight
        cats = set(papers[pid].get("categories") or [])
        for other in list(scores):
            shared = cats & set(papers[other].get("categories") or [])
            scores[other] += 0.75 * len(shared - {"other-ml"})
        best = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
        result[pid] = [o for o, sc in best if sc >= 1.0]
    return result


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
    _write(os.path.join(site_dir, "saved.html"), build_saved_page())

    # Previous and next paper follow the order of the day the paper first appeared
    neighbours: dict[str, tuple] = {}
    for day in days:
        _write(os.path.join(site_dir, "day", f"{day['date']}.html"), build_day(day, papers))
        ids = [p["id"] for p in day["papers"] if papers.get(p["id"], {}).get("first_seen") == day["date"]]
        for n, pid in enumerate(ids):
            neighbours[pid] = (ids[n - 1] if n > 0 else None, ids[n + 1] if n + 1 < len(ids) else None)

    related = related_papers(papers)
    for rec in papers.values():
        prev_id, next_id = neighbours.get(rec["id"], (None, None))
        _write(os.path.join(site_dir, "paper", f"{rec['id']}.html"),
               build_paper(rec, [papers[i] for i in related.get(rec["id"], [])],
                           papers.get(prev_id), papers.get(next_id)))

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
