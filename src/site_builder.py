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
from datetime import date, timedelta

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SRC_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from classifier import CATEGORIES
import trends

DATA_DIR = os.path.join(ROOT_DIR, "data")
SITE_DIR = os.path.join(ROOT_DIR, "site")
# Written by supabase_sync.py on each run, not committed: the year of papers in
# the database and our readers' most read list
EXPORT_DIR = os.path.join(ROOT_DIR, "build", "supabase")
ASSETS_DIR = os.path.join(SRC_DIR, "site_assets")

SITE_NAME = "AI Papers Daily"
TAGLINE = ("We read every new AI paper on arXiv and Hugging Face, choose the ones you can "
           "build something with, and explain why they matter in plain language.")
MORE_FROM_TODAY = 6  # non-featured papers shown on the home page

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

# The logo: four pixels, two orange and two ink, like a cursor blinking on a page.
FAVICON = ("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
           "<rect width='32' height='32' rx='6' fill='%230e0e10'/>"
           "<rect x='4' y='4' width='12' height='12' fill='%23ff4f00'/><rect x='16' y='16' width='12' height='12' fill='%23ff4f00'/>"
           "<rect x='16' y='4' width='12' height='12' fill='%23f2f0eb'/><rect x='4' y='16' width='12' height='12' fill='%23f2f0eb'/></svg>")


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
    """'2026-10-31' -> '31 Oct 2026', or 'Oct 31' without the year (the year
    is still shown when it isn't the current one)."""
    try:
        d = date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return iso or ""
    if with_year or d.year != date.today().year:
        return f"{d.day} {d:%b %Y}"
    return f"{d:%b} {d.day}"


def published(rec: dict) -> str:
    """When the paper came out on arXiv; the day we first saw it if unknown."""
    return (rec.get("submitted") or rec.get("first_seen") or "")[:10]


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
                    rec["slot"] = old.get("slot")
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

# Edition strip shown on every page; set by build_site
EDITION = ""

# Runs before first paint so a saved dark theme never flashes white
THEME_SCRIPT = ("<script>try{var t=localStorage.getItem('apd.theme')||(matchMedia('(prefers-color-scheme: dark)')"
                ".matches?'dark':'light');document.documentElement.dataset.theme=t}catch(e){}</script>")


def page(title: str, body: str, root: str = "", description: str = TAGLINE, active: str = "",
         edition: str = "", body_class: str = "") -> str:
    """Wrap body in the shared layout. root is the relative path to the site root."""
    edition = edition or EDITION
    full_title = f"{title} · {SITE_NAME}" if title != SITE_NAME else f"{SITE_NAME}: research papers worth building on"

    def nav(href, label, key, extra=""):
        current = ' aria-current="page"' if key == active else ""
        return f'<a href="{root}{href}"{current}>{label}{extra}</a>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="apd-track" content="{TRACK_URL}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta name="theme-color" content="#ff4f00">
{THEME_SCRIPT}
<link rel="preload" href="{root}assets/fonts/geist.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{root}assets/fonts/geist-pixel-square.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{root}assets/style.css">
<link rel="icon" href="{FAVICON}">
</head>
<body{f' class="{body_class}"' if body_class else ""}>
<a class="skip" href="#main">Skip to content</a>
<div class="ticker" aria-hidden="true"><div class="wrap ticker-in">{edition}<span class="ticker-next" data-next-edition>Updated every morning</span></div></div>
<header class="site-header">
  <div class="wrap bar-in">
    <a class="brand" href="{root}index.html" aria-label="{SITE_NAME}, home"><span class="brand-mark" aria-hidden="true"></span><span class="brand-name">AI PAPERS<em>/DAILY</em></span></a>
    <nav class="nav" aria-label="Main">
      {nav("index.html", "Today", "today")}
      {nav("papers.html", '<span class="nav-long">All papers</span><span class="nav-short">Papers</span>', "papers")}
      {nav("scout.html", "Scout", "scout")}
      {nav("trends.html", "Trends", "trends")}
      {nav("saved.html", "Saved", "saved", '<span class="nav-count" data-saved-count hidden></span>')}
    </nav>
    <div class="header-actions">
      <a class="cmdk" href="{root}papers.html" data-search-trigger>{icon("search", 15)}<span>Search papers or an idea</span><kbd>/</kbd></a>
      <span class="streak" data-streak hidden title="Days in a row you read a paper"></span>
      <button class="icon-button" type="button" data-theme-toggle aria-label="Switch light or dark theme" data-tip="Switch theme">{icon("moon", 17, "icon-moon")}{icon("sun", 17, "icon-sun")}</button>
    </div>
  </div>
</header>
<main class="wrap" id="main">
{body}
</main>
<footer class="site-footer">
  <div class="wrap foot-in">
    <span>Built from <a href="https://arxiv.org">arXiv</a> and <a href="https://huggingface.co/papers">Hugging Face Papers</a>. Updated every morning.</span>
    <span>Summaries are written by AI from the abstract. Check the paper.</span>
  </div>
</footer>
<script src="{root}assets/app.js" defer></script>
</body>
</html>
"""


def ticker(days: list[dict]) -> str:
    """Edition number and date for the strip at the top of every page."""
    if not days:
        return ""
    d = days[0]["date"]
    try:
        stamp = f"{date.fromisoformat(d):%a %d %b %Y}".upper()
    except ValueError:
        stamp = d
    return f'<span>Edition {len(days):03d}</span><span class="ticker-date">{esc(stamp)}</span>'


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------

def slot_label(rec: dict, rank: int = 1) -> str:
    """What a featured paper was picked for. Days before the change have no slot."""
    slot = rec.get("slot")
    if slot == "trending":
        return "Trending"
    if slot == "runner-up":
        return "Runner-up"
    if slot == "most-read":
        return "Most read"
    if slot == "pick" or rank == 1:
        return "Today’s pick" if slot == "pick" else "Top pick"
    return f"Pick {rank:02d}"


def badges(rec: dict, root: str) -> str:
    out = []
    if rec.get("featured"):
        cls = "badge-hot" if rec.get("slot") == "trending" else "badge-pick"
        label = "Trending" if rec.get("slot") == "trending" else "Top pick"
        out.append(f'<span class="badge {cls}">{label}</span>')
    for c in rec.get("categories") or ["other-ml"]:
        out.append(f'<a class="badge topic t-{esc(c)}" href="{root}papers.html?cat={esc(c)}">{esc(category_name(c))}</a>')
    return f'<div class="badges">{"".join(out)}</div>'


def topic_dot(slug: str) -> str:
    return f'<span class="topic t-{esc(slug)}"><span class="dot"></span>{esc(category_name(slug))}</span>'


LEVELS = {"beginner": 1, "intermediate": 2, "advanced": 3}


def level_meter(difficulty: str) -> str:
    """Three bars, filled up to the difficulty, with the word next to them."""
    n = LEVELS.get(difficulty or "", 0)
    if not n:
        return ""
    bars = "".join(f'<i class="{"on" if k <= n else ""}"></i>' for k in (1, 2, 3))
    return f'<span class="level"><span class="level-bars" aria-hidden="true">{bars}</span>{esc(difficulty.capitalize())}</span>'


def pick_minutes(rec: dict) -> int:
    """Rough minutes to read our notes plus the abstract."""
    notes = rec.get("curator") or {}
    words = len((rec.get("abstract") or "").split())
    words += sum(len(str(v).split()) for v in notes.values() if isinstance(v, str))
    words += sum(len(i.split()) for i in notes.get("build_ideas", []))
    return max(1, round(words / 200))


def featured_card(rec: dict, rank: int, root: str) -> str:
    notes = rec.get("curator") or {}
    if notes.get("tldr"):
        blurb = f'<p class="pick-blurb"><b>In short</b>{esc(notes["tldr"])}</p>'
    else:
        summary = (rec.get("summary") or {}).get("text") or ""
        blurb = f'<p class="pick-blurb"><b>Why it matters</b>{esc(summary)}</p>' if summary else ""
        if not blurb and rec.get("abstract"):
            first = rec["abstract"].replace("\n", " ").split(". ")[0].strip().rstrip(".")
            if len(first) > 220:
                first = first[:217].rsplit(" ", 1)[0] + "…"
            blurb = f'<p class="pick-blurb"><b>From the abstract</b>{esc(first)}.</p>' if first else ""
    label = slot_label(rec, rank)
    why = ""
    if rec.get("slot") == "trending" and rec.get("hf_upvotes"):
        why = f'<span class="pick-why">{int(rec["hf_upvotes"])} upvotes on Hugging Face</span>'
    elif rec.get("slot") == "most-read":
        why = f'<span class="pick-why">{int(rec.get("readers") or 0)} readers this week</span>'
    elif rec.get("slot") == "pick":
        why = '<span class="pick-why">Best new paper by our score</span>'
    topic = (rec.get("categories") or ["other-ml"])[0]
    code = f'<span class="has-code">{icon("code", 14)}Code available</span>' if rec.get("code_url") else ""
    return f"""<article class="pick{' is-first' if rank == 1 else ''}" data-id="{esc(rec['id'])}" data-slot="{esc(rec.get('slot') or '')}">
  <header class="pick-top"><span class="pick-n">{label}</span>{why}<span class="pick-read" hidden>Read ✓</span></header>
  <h3><a href="{root}paper/{esc(rec['id'])}.html">{esc(rec['title'])}</a></h3>
  {blurb}
  <footer class="pick-foot">{topic_dot(topic)}{level_meter(notes.get("difficulty"))}{code}<span class="mins">{pick_minutes(rec)} min</span></footer>
</article>"""


def paper_row(rec: dict, root: str) -> str:
    return f"""<li class="row" data-id="{esc(rec['id'])}">
  <span class="row-date">{esc(nice_date(published(rec), with_year=False))}</span>
  <span class="row-title"><a href="{root}paper/{esc(rec['id'])}.html">{esc(rec['title'])}</a></span>
  <span class="row-authors">{esc(format_authors(rec.get('authors', []), 3))}</span>
  {badges(rec, root)}
</li>"""


def home_row(rec: dict, n: int) -> str:
    """A quieter row for the home page: number, title, one topic, authors, quick save."""
    topic = (rec.get("categories") or ["other-ml"])[0]
    return f"""<li class="row" data-id="{esc(rec['id'])}">
  <span class="row-n">{n:02d}</span>
  <span class="row-title"><a href="paper/{esc(rec['id'])}.html">{esc(rec['title'])}</a></span>
  <span class="row-authors">{topic_dot(topic)}<span class="sep"></span>{esc(format_authors(rec.get('authors', []), 2))}</span>
  <button class="quick-save" type="button" data-quick-save="{esc(rec['id'])}" data-title="{esc(rec['title'])}" aria-pressed="false" aria-label="Save for later">+</button>
</li>"""


def section_head(title: str, sub: str = "", link: str = "") -> str:
    sub_html = f'<span class="sub">{sub}</span>' if sub else ""
    return f'<div class="block-head"><h2>{title}</h2>{sub_html}{link}</div>'


# ---------------------------------------------------------------------------
# Charts (plain SVG, drawn here so the page needs no chart library)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

# Views a paper needs in the last week before our own readers fill the second slot
MIN_MOST_READ_VIEWS = 20


def _load_export(export_dir: str, name: str) -> list[dict]:
    try:
        with open(os.path.join(export_dir, name), encoding="utf-8") as f:
            return [p for p in json.load(f).get("papers", []) if isinstance(p, dict) and p.get("id")]
    except (OSError, ValueError, AttributeError):
        return []


def load_most_read(export_dir: str = EXPORT_DIR) -> list[dict]:
    """Our readers' most viewed papers of the last week, written by supabase_sync.py."""
    return _load_export(export_dir, "most_read.json")


def load_archive(export_dir: str = EXPORT_DIR) -> list[dict]:
    """Every paper in the database (about a year), written by supabase_sync.py."""
    return _load_export(export_dir, "papers.json")


def archive_compact(row: dict) -> dict:
    """A database paper with no page on this site, in the papers.json short form."""
    authors = row.get("authors") or []
    return {
        "i": row["id"], "t": row.get("title") or row["id"], "a": authors[:3], "n": len(authors),
        "c": row.get("categories") or ["other-ml"],
        "d": (row.get("submitted") or row.get("first_seen") or "")[:10],
        "s": 0, "f": 0, "x": 1,
    }


def most_read_list(most_read: list[dict], papers: dict, limit: int = 5) -> str:
    rows = [(papers[m["id"]], m) for m in most_read if m["id"] in papers and m.get("views", 0) >= 3][:limit]
    if len(rows) < 3:
        return ""
    items = "".join(f"""<li><span class="mr-n">{n:02d}</span><a href="paper/{esc(r['id'])}.html">{esc(r['title'])}</a>
      <span class="mr-views">{m['views']} readers</span></li>""" for n, (r, m) in enumerate(rows, 1))
    return f"""<div class="block">{section_head("Most read this week", "By readers of this site")}
      <ol class="card pad most-read">{items}</ol></div>"""


def trends_teaser(rows: list[dict]) -> str:
    """One card on the home page that points to the Trends page with its headline facts."""
    months = trends.last_months(rows, 12)
    if len(rows) < 30 or len(months) < 4:
        return ""
    moves = [m for m in trends.movers(rows, months) if m["enough"]]
    if not moves:
        return ""
    up, down = moves[0], moves[-1]
    code = trends.code_share(rows, months)[-1]
    name = lambda t: esc(category_name(t))
    facts = [
        f'<li><span class="pulse-ch up">{trends.pts(up["delta"])}</span><span><b>{name(up["topic"])}</b> is rising fastest, now {trends.pct(up["now"], 1)} of papers.</span></li>',
        f'<li><span class="pulse-ch down">{trends.pts(down["delta"])}</span><span><b>{name(down["topic"])}</b> is falling the most.</span></li>',
        f'<li><span class="pulse-ch flat">{trends.pct(code[1])}</span><span>of papers in {trends._month_label(code[0], True)} link to code.</span></li>',
    ]
    return f"""<section class="block">
  {section_head("Trends", "The last 3 months against the 9 before")}
  <a class="card teaser" href="trends.html">
    <ul class="teaser-facts">{"".join(facts)}</ul>
    <div class="teaser-chart"><span class="topic t-{esc(up["topic"])}"><span class="dot"></span>{name(up["topic"])}, 12 months</span>
      {trends._spark(up["line"], w=300, h=64, cls="spark teaser-spark", lo=0)}</div>
    <span class="teaser-go">See all trends →</span>
  </a>
</section>"""


def build_index(days: list[dict], papers: dict, most_read: list[dict] | None = None,
                trend_rows: list[dict] | None = None) -> str:
    most_read = most_read or []
    trend_rows = trend_rows if trend_rows is not None else trends.trend_rows([], papers)[0]
    if not days:
        body = '<section class="hero"><div><h1>No papers yet.</h1><p class="lead">The first edition arrives tomorrow morning.</p></div></section>'
        return page(SITE_NAME, body, active="today")

    latest = days[0]
    featured_ids = latest.get("featured", [])
    featured = [papers[i] for i in featured_ids if i in papers]
    # Once our own readers are enough, the second slot shows what they read most
    top = next((m for m in most_read if m["id"] in papers and m["id"] not in featured_ids[:1]), None)
    if featured and top and top.get("views", 0) >= MIN_MOST_READ_VIEWS:
        featured = featured[:1] + [dict(papers[top["id"]], slot="most-read", readers=top["views"])]
    others = [papers[p["id"]] for p in latest["papers"] if p["id"] not in featured_ids][:MORE_FROM_TODAY]
    n_today = len(latest["papers"])
    minutes = sum(pick_minutes(r) for r in featured)

    cards = "\n".join(featured_card(r, n, "") for n, r in enumerate(featured, 1))
    more = ""
    if others:
        rows = "\n".join(home_row(r, n) for n, r in enumerate(others, len(featured) + 1))
        link = f'<a class="more" href="day/{esc(latest["date"])}.html">See all {n_today} papers from today</a>'
        more = f"""<div class="block">
    {section_head("Also new today", "Ranked by our score", link)}
    <ol class="list list-home">{rows}</ol>
  </div>"""

    chart = trends_teaser(trend_rows)

    body = f"""<section class="hero">
  <div>
    <h1>Papers worth<br>building on.</h1>
    <p class="lead">The best new AI paper each day, plus the one everyone is reading. Picked from everything new on arXiv and Hugging Face, and explained so you can build with it.</p>
  </div>
  <div class="daily card" data-daily data-picks="{esc(' '.join(r['id'] for r in featured))}" data-minutes="{minutes}">
    <div class="ring" data-ring style="--p:0"><span class="ring-n" data-ring-n>0/{len(featured)}</span></div>
    <div class="daily-copy"><span class="label">Today’s reading</span><strong data-daily-title>{len(featured)} picks today.</strong>
      <span data-daily-sub>About {minutes} minutes to read both.</span>
      <span class="week" data-week aria-hidden="true"></span></div>
  </div>
</section>
<section class="block" id="today">
  {section_head("Today’s picks", f"Chosen from {n_today} new papers")}
  <div class="picks">{cards}</div>
</section>
<section class="block" data-foryou data-url="{RECOMMEND_URL}" data-names="{esc(json.dumps(CATEGORY_NAMES))}" hidden>
  {section_head("For you", "Recent papers close in meaning to what you’ve read. Worked out from this browser’s history only.")}
  <ol class="foryou" data-foryou-list aria-busy="true">{'<li class="foryou-item skeleton" aria-hidden="true"></li>' * 3}</ol>
</section>
<section class="split">
  <div class="split-main">{more}{most_read_list(most_read, papers)}</div>
  <aside class="block side">
    {section_head("Topic pulse", "Share of this week’s papers, against the 4 weeks before", '<a class="more" href="trends.html">All trends</a>')}
    <div class="card pad">{trends.pulse_rows(trends.weekly_pulse(trend_rows), CATEGORY_NAMES)}</div>
    <div class="block" data-continue hidden>
      {section_head("Continue reading")}
      <ul class="list" data-continue-list></ul>
    </div>
  </aside>
</section>
{chart}"""
    return page(SITE_NAME, body, active="today", edition=ticker(days))


# The search function in Supabase (supabase/functions/search). Public by design:
# it only answers this site and is rate limited per visitor.
SEARCH_URL = "https://nmelkepelhwyhlfdznpf.supabase.co/functions/v1/search"
# The "For you" function (supabase/functions/recommend), same rules as search
RECOMMEND_URL = "https://nmelkepelhwyhlfdznpf.supabase.co/functions/v1/recommend"

SKELETON_ROWS = '<li class="row skeleton" aria-hidden="true"><span></span><span></span></li>' * 6


def papers_tabs(current: str, root: str = "") -> str:
    """All papers and the day-by-day archive are two views of the same papers."""
    tab = lambda href, label, key: (f'<a href="{root}{href}"{" aria-current=page" if key == current else ""}>{label}</a>')
    return f'<nav class="tabs" aria-label="Papers views">{tab("papers.html", "All papers", "papers")}{tab("archive.html", "By day", "archive")}</nav>'


def build_papers_page() -> str:
    options = "".join(f'<option value="{esc(slug)}">{esc(name)}</option>'
                      for slug, name in CATEGORY_NAMES.items())
    body = f"""<section class="page-head">
  {papers_tabs("papers")}
  <h1>All papers</h1>
  <p>Every paper we have tracked, newest first. Search by title or author, or turn on Search by meaning to find papers about an idea in your own words.</p>
</section>
<div class="toolbar">
  <div class="field field-grow"><label class="field-label" for="q">Search</label>
    <span class="input-wrap">{icon("search", 15)}<input class="input" id="q" type="search" placeholder="Title or author" autocomplete="off"></span></div>
  <div class="field"><label class="field-label" for="cat">Topic</label>
    <select class="select" id="cat"><option value="">All topics</option>{options}</select></div>
  <div class="field"><label class="field-label" for="sort">Sort by</label>
    <select class="select" id="sort"><option value="new">Newest first</option><option value="score">Highest score</option></select></div>
  <label class="toggle"><input id="feat" type="checkbox"> Top picks only</label>
  <label class="toggle toggle-meaning"><input id="meaning" type="checkbox"> Search by meaning</label>
</div>
<div class="result-meta"><span id="count">Loading papers…</span></div>
<ul class="list" id="results" aria-busy="true" data-search-url="{SEARCH_URL}">{SKELETON_ROWS}</ul>
<div class="center"><button class="btn btn-outline" id="more" type="button" hidden>Show more</button></div>
<noscript><p class="empty">Turn on JavaScript to search, or browse the <a href="archive.html">archive</a>.</p></noscript>"""
    return page("All papers", body, active="papers")


# Anonymous view counts and feedback (supabase/functions/track)
TRACK_URL = "https://nmelkepelhwyhlfdznpf.supabase.co/functions/v1/track"

# "Ask this paper" (supabase/functions/ask), same rules as search
ASK_URL = "https://nmelkepelhwyhlfdznpf.supabase.co/functions/v1/ask"
ASK_SUGGESTIONS = ["What problem does it solve?", "What would I need to try it?", "How did they test it?"]

# Project Scout (supabase/functions/scout), same rules as search
SCOUT_URL = "https://nmelkepelhwyhlfdznpf.supabase.co/functions/v1/scout"

SCOUT_EXAMPLES = [
    "A voice notes app that turns speech into text fully offline on an Android phone, with no server.",
    "A helper that reads our customer support tickets and drafts replies, running on one laptop without a GPU.",
    "A chatbot for my college library that answers questions from our PDF catalogue and cites the page it used.",
]


def build_scout_page() -> str:
    examples = "".join(f'<button class="example" type="button" data-example="{esc(e)}">{esc(e)}</button>'
                       for e in SCOUT_EXAMPLES)
    body = f"""<section class="page-head scout-head">
  <h1>Project Scout</h1>
  <p>Describe what you want to build. Scout searches more than 8,000 AI papers and gives you a short reading plan, in order, with what each paper adds to your project.</p>
</section>
<div class="scout">
  <form class="card pad scout-form" data-scout data-url="{SCOUT_URL}" data-names="{esc(json.dumps(CATEGORY_NAMES))}" novalidate>
    <label class="field-label" for="desc">Describe your project</label>
    <p class="field-hint" id="desc-hint">Plain words, no code. Say what it does, who it's for, and any limits, like “runs on a phone” or “no GPU”.</p>
    <textarea class="input textarea" id="desc" rows="7" maxlength="1000" aria-describedby="desc-hint desc-error"></textarea>
    <div class="field-foot"><span class="field-error" id="desc-error" role="alert" hidden></span><span class="char-count" data-count>0 / 1000</span></div>
    <button class="btn btn-primary btn-block" type="submit" data-scout-go>Find papers</button>
    <div class="examples"><span class="label">Or try an example</span>{examples}</div>
    <p class="fine">Your description goes to our search service and to Groq, which plans the search. We don't store it.</p>
  </form>
  <section class="scout-out" data-scout-out aria-live="polite">
    <div class="card pad scout-intro">
      <span class="label">How it works</span>
      <ol class="how">
        <li><b>You describe</b> the project in a few sentences.</li>
        <li><b>Scout searches</b> by meaning, from a few angles at once.</li>
        <li><b>You get a plan:</b> what to read first, what to build on, and what can wait.</li>
      </ol>
    </div>
  </section>
</div>
<noscript><p class="empty">Turn on JavaScript to use Project Scout.</p></noscript>"""
    return page("Project Scout", body, active="scout",
                description="Describe your project and get a reading plan of AI papers, in order.")


def build_trends_page(rows: list[dict], source: str, n_all: int) -> str:
    months = trends.last_months(rows, 12)
    if len(rows) < 30 or len(months) < 3:
        body = """<section class="page-head"><h1>Trends</h1>
  <p>Trends need at least three months of papers. They appear here once the history has loaded.</p></section>"""
        return page("Trends", body, active="trends")
    names = CATEGORY_NAMES
    per = trends.topic_counts(rows, months)
    top = trends.top_topics(per, 5)
    moves = trends.movers(rows, months)
    end = max(r["day"] for r in rows)
    last30 = sum(1 for r in rows if r["day"] > (date.fromisoformat(end) - timedelta(days=30)).isoformat())
    code = trends.code_share(rows, months)
    rising = next((m for m in moves if m["enough"] and m["delta"] > 0), None)
    tiles = [
        ("Papers in a year", f"{len(rows):,}", f"of {n_all:,} in our database" if n_all > len(rows) else "in our database"),
        ("Last 30 days", f"{last30:,}", "new papers"),
        ("Share code", trends.pct(code[-1][1]), f"in {trends._month_label(code[-1][0], True)}"),
        ("Rising fastest", esc(names.get(rising["topic"], rising["topic"])) if rising else "—",
         trends.pts(rising["delta"]) + " in 3 months" if rising else "Needs more history"),
    ]
    tiles_html = "".join(
        '<div class="stat"><span class="label">{}</span><strong{}>{}</strong><span>{}</span></div>'.format(
            k, ' class="stat-text"' if len(v) > 8 else "", v, s)
        for k, v, s in tiles)
    words = trends.rising_words(rows, months)
    field = trends.field_shares_json(rows, months)
    first, last = trends._month_label(months[0], True), trends._month_label(months[-1], True)
    body = f"""<section class="page-head">
  <h1>Trends</h1>
  <p>What AI research is about right now, from {len(rows):,} {esc(source)}, {first} to {last}. Updated every morning.</p>
</section>
<div class="stats">{tiles_html}</div>

<section class="block">
  {section_head("Topic share, month by month", "Each band is a topic’s share of that month’s papers. Hover or tab through the months.")}
  <div class="card pad chart-box">{trends.share_area(per, months, top, names)}
    <details class="table-view"><summary>Show as a table</summary>{trends.share_table(per, months, top, names)}</details></div>
</section>

<section class="block">
  {section_head("Rising and falling", "Share in the last 3 months, change against the 9 months before. Each line has its own scale.")}
  {trends.mover_cards(moves, names, months)}
</section>

<section class="split split-even">
  <div class="block">
    {section_head("Words on the rise", "Title words used much more in the last 3 months than before")}
    <div class="card pad">{trends.word_rows(words, months)}</div>
  </div>
  <div class="block">
    {section_head("You vs the field", "Topics of the papers you opened here, against the last 3 months")}
    <div class="card pad" data-you-field data-field='{esc(field)}' data-names="{esc(json.dumps(names))}">
      <p class="empty-note" data-you-empty>Open a few papers and this chart shows how your reading compares with what’s being published. It uses this browser’s history only.</p>
      <div data-you-chart hidden></div>
    </div>
  </div>
</section>

<section class="block">
  {section_head("The year in papers", "Papers per day. Stronger colour means a busier day.")}
  <div class="card pad">{trends.calendar(trends.daily_counts(rows), end)}</div>
</section>

<section class="block">
  {section_head("How many papers share code", "Share of each month’s papers that link to a code repository")}
  <div class="card pad chart-box">{trends.code_chart(code)}</div>
</section>"""
    return page("Trends", body, active="trends",
                description="What AI research is about right now: topic shares, rising topics and words, and code availability.")


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
  {papers_tabs("archive")}
  <h1>Every edition</h1>
  <p>{len(days)} days of papers, newest first. Each day lists its top picks and everything else we found.</p>
</section>
<ul class="list">{''.join(rows)}</ul>"""
    return page("Archive", body, active="papers")


def build_day(day: dict, papers: dict) -> str:
    featured_ids = day.get("featured", [])
    featured = [papers[i] for i in featured_ids if i in papers]
    rest = [papers[p["id"]] for p in day["papers"] if p["id"] not in featured_ids]
    cards = "\n".join(featured_card(r, n, "../") for n, r in enumerate(featured, 1))
    rest_html = ""
    if rest:
        rows = "\n".join(paper_row(r, "../") for r in rest)
        rest_html = f'<section class="block">{section_head("Everything else", f"{len(rest)} more papers from this day")}<ul class="list">{rows}</ul></section>'
    body = f"""<section class="page-head">
  <a class="crumbs" href="../archive.html">{icon("back", 15)} Archive</a>
  <h1>{esc(nice_date(day['date']))}</h1>
  <p>{len(day['papers'])} papers that day.</p>
</section>
<section class="block">{section_head("Picks that day")}<div class="picks">{cards}</div></section>
{rest_html}"""
    return page(nice_date(day["date"]), body, root="../", active="papers")


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
        return f'<p data-highlightable><span class="lede">{esc(lede)}</span> {esc(rest)}</p>'
    return f"<p data-highlightable>{esc(text)}</p>"


def related_item(rec: dict, root: str) -> str:
    topic = (rec.get("categories") or ["other-ml"])[0]
    return (f'<li><a href="{root}paper/{esc(rec["id"])}.html">{esc(rec["title"])}</a>'
            f'<span class="t-{esc(topic)}"><span class="dot"></span>{esc(category_name(topic))}</span></li>')


def build_paper(rec: dict, related: list[dict] = (), prev: dict = None, nxt: dict = None,
                next_pick: dict = None, day_picks: list[str] = ()) -> str:
    notes = rec.get("curator") or {}
    summary = (rec.get("summary") or {}).get("text")
    abstract = rec.get("abstract") or ""
    layers, toc = [], []

    def layer(key, tag, label, inner, first=False):
        toc.append(f'<a href="#{key}" data-toc="{key}">{label}</a>')
        layers.append(f'<section class="layer{" layer-first" if first else ""}" id="{key}" data-layer>'
                      f'<span class="layer-tag">{tag}</span>{inner}</section>')

    short = notes.get("tldr") or summary
    if short:
        layer("l-short", "10 sec", "In 10 seconds", f'<p class="tldr">{esc(short)}</p>', first=True)
    if notes.get("tldr"):
        rows = [("What's new", notes.get("whats_new"), False), ("Key result", notes.get("key_result"), True),
                ("Why it matters", notes.get("why_it_matters"), False)]
        grid = "".join(f"<div><dt>{k}</dt><dd>{f'<mark>{esc(v)}</mark>' if hl else esc(v)}</dd></div>"
                       for k, v, hl in rows if v)
        layer("l-minute", "1 min", "In 1 minute", f"<h2>Curator's notes</h2><dl class=\"facts3\">{grid}</dl>")
        ideas = "".join(f"<li><span>{i + 1:02d}</span>{esc(x)}</li>" for i, x in enumerate(notes.get("build_ideas", [])))
        reason = notes.get("difficulty_reason")
        level = level_meter(notes.get("difficulty"))
        level_html = f'<p class="level-note">{level}{f"<span>{esc(reason)}</span>" if reason else ""}</p>' if level else ""
        layer("l-build", "Build", "Build with it", f"<h2>What you could build</h2><ol class=\"ideas\">{ideas}</ol>{level_html}")
    if abstract:
        layer("l-abstract", f"{reading_minutes(abstract)} min", "Abstract",
              f'<div class="prose" data-prose><h2>Abstract<span>Select any sentence to highlight it or add a note</span></h2>{abstract_html(abstract)}</div>')
    ask_panel = ask_fab = ""
    if abstract:
        # Beside the text while reading on wide screens; a sheet behind a button on smaller ones
        chips = "".join(f'<button class="qchip" type="button" data-ask-suggest>{q}</button>' for q in ASK_SUGGESTIONS)
        ask_panel = f"""<section class="ask ask-panel" id="ask" data-ask data-url="{ASK_URL}" aria-labelledby="ask-title">
      <div class="ask-head"><h2 id="ask-title">Ask this paper</h2>
        <button class="icon-button ask-close" type="button" data-ask-close aria-label="Close questions">×</button></div>
      <p class="ask-sub">Answers come from the full paper, with the section and sentence they rely on. Or select any sentence and press Ask.</p>
      <ol class="ask-log" data-ask-log aria-live="polite"></ol>
      <div class="ask-suggest">{chips}</div>
      <form class="ask-form" data-ask-form>
        <label class="sr-only" for="ask-q">Your question about this paper</label>
        <input class="input" id="ask-q" maxlength="300" autocomplete="off" placeholder="Ask anything about it">
        <button class="btn btn-primary" type="submit">Ask</button>
      </form>
      <p class="field-error" data-ask-error role="alert" hidden></p>
    </section>"""
        ask_fab = '<button class="ask-fab" type="button" data-ask-open aria-controls="ask" aria-expanded="false">Ask this paper</button>'
    if notes.get("check_question"):
        answer = notes.get("check_answer")
        answer_html = (f'<p class="check-a" data-check-answer hidden>{esc(answer)}</p>'
                       f'<div class="check-actions"><button class="btn btn-primary" type="button" data-check-show>Show the answer</button></div>') if answer else ""
        layer("l-check", "Check", "Check yourself",
              f'<div class="check"><h2>Could you explain it to a friend?</h2><p class="check-q">{esc(notes["check_question"])}</p>{answer_html}</div>')

    facts = [("Published", nice_date(published(rec)))]
    if rec.get("featured_on"):
        facts.append(("Top pick on", f'<a href="../day/{esc(rec["featured_on"])}.html">{esc(nice_date(rec["featured_on"]))}</a>'))
    if rec.get("hf_upvotes"):
        facts.append(("HF upvotes", str(rec["hf_upvotes"])))
    facts.append(("Authors", str(len(rec.get("authors", [])))))
    facts_html = "".join(f"<div><dt>{k}</dt><dd>{v if k == 'Top pick on' else esc(v)}</dd></div>" for k, v in facts)
    code_btn = (f'<a class="btn btn-outline" href="{esc(rec["code_url"])}" rel="noopener">{icon("code", 15)} View the code</a>'
                if rec.get("code_url") else "")

    done = ""
    if next_pick:
        done = f"""<section class="done-card" data-done data-picks="{esc(' '.join(day_picks))}">
    <div><span class="label">Edition progress</span><strong data-done-title>{len(day_picks)} picks in this edition.</strong><span data-done-sub>Read both to keep your streak going.</span></div>
    <a class="next-card" href="{esc(next_pick['id'])}.html"><span class="label">Next pick</span>{esc(next_pick['title'])} →</a>
  </section>"""
    pager = ""
    if prev or nxt:
        prev_html = (f'<a class="pager-link" href="{esc(prev["id"])}.html" rel="prev"><span>Previous paper</span>{esc(prev["title"])}</a>'
                     if prev else "<span></span>")
        next_html = (f'<a class="pager-link next" href="{esc(nxt["id"])}.html" rel="next"><span>Next paper</span>{esc(nxt["title"])}</a>'
                     if nxt else "<span></span>")
        pager = f'<nav class="pager" aria-label="More papers from the same day">{prev_html}{next_html}</nav>'

    related_html = ""
    if related:
        related_html = (f'<section class="read-next"><h2 class="label">Read next, same idea</h2>'
                        f'<ol class="nextlist nextlist-grid">{"".join(related_item(r, "../") for r in related)}</ol></section>')

    kicker = f'<span class="pick-n">{esc(slot_label(rec))}</span>' if rec.get("featured") else ""
    topic = (rec.get("categories") or ["other-ml"])[0]
    minutes = pick_minutes(rec)
    title = esc(rec["title"])
    body = f"""<div class="progress" aria-hidden="true"><span data-progress></span></div>
<button class="btn btn-outline btn-sm focus-exit" type="button" data-focus-exit>Exit focus <kbd>Esc</kbd></button>
<div class="read-grid">
  <aside class="rail" aria-label="Reading tools">
    <a class="crumbs" href="../papers.html">{icon("back", 15)} All papers</a>
    <div class="rail-box"><span class="label">Your progress</span><span class="pixbar" data-pixbar>{'<i></i>' * 8}</span><span class="rail-small" data-left>About {minutes} min to read</span></div>
    <nav class="toc" aria-label="Sections">{"".join(toc)}</nav>
    <div class="rail-notes" data-notes><span class="label">Your notes</span>
      <p class="rail-small" data-notes-empty>Select text in the abstract to highlight it or add a note. They stay in this browser.</p>
      <ol class="note-list" data-notes-list></ol></div>
    <div class="rail-actions">
      <button class="btn btn-outline btn-sm" type="button" data-save aria-pressed="false">{icon("bookmark", 15)}<span>Save</span></button>
      <details class="tools">
        <summary class="btn btn-outline btn-sm"><span>More tools</span></summary>
        <div class="tools-menu">
          <details class="cite">
            <summary class="btn btn-outline btn-sm">{icon("quote", 15)}<span>Cite</span></summary>
            <div class="cite-box"><pre data-bibtex>{esc(bibtex(rec))}</pre><button class="btn btn-primary btn-sm" type="button" data-copy-bibtex>Copy BibTeX</button></div>
          </details>
          <button class="btn btn-outline btn-sm" type="button" data-share>{icon("share", 15)}<span>Share</span></button>
          <button class="btn btn-outline btn-sm" type="button" data-focus>Focus mode <kbd>F</kbd></button>
          <div class="text-size" role="group" aria-label="Text size"><button type="button" data-size="-1" aria-label="Make text smaller">A</button><button type="button" data-size="1" aria-label="Make text larger">A</button></div>
        </div>
      </details>
    </div>
  </aside>
  <article class="paper" data-paper-id="{esc(rec['id'])}" data-title="{title}" data-topics="{esc(' '.join(rec.get('categories') or ['other-ml']))}">
    <p class="paper-kicker">{kicker}<span>arXiv <span class="mono">{esc(rec['id'])}</span></span></p>
    <h1>{title}</h1>
    <p class="byline">{esc(', '.join(rec.get('authors', [])))}</p>
    <div class="paper-meta">{topic_dot(topic)}{level_meter(notes.get("difficulty"))}<span class="mins">{minutes} min read</span>{f'<a class="code-link" href="{esc(rec["code_url"])}" rel="noopener">&lt;/&gt; Code</a>' if rec.get("code_url") else ""}</div>
    {"".join(layers)}
    <div class="source">
      <dl class="facts">{facts_html}</dl>
      <div class="actions">
        <a class="btn btn-primary" href="{esc(rec.get('url'))}" rel="noopener">Read on arXiv {icon("external", 15)}</a>{code_btn}
        <a class="text-link" href="{esc(rec.get('pdf_url'))}" rel="noopener">PDF</a>
        <a class="text-link" href="https://huggingface.co/papers/{esc(rec['id'])}" rel="noopener">Hugging Face</a>
      </div>
    </div>
    <div class="feedback" data-feedback="{esc(rec['id'])}">
      <span data-feedback-q>Was this paper worth your time?</span>
      <button class="btn btn-outline btn-sm" type="button" data-vote="useful">Yes, useful</button>
      <button class="btn btn-outline btn-sm" type="button" data-vote="not_useful">Not for me</button>
    </div>
    {done}
    {related_html}
    {pager}
  </article>
  <aside class="margin" aria-label="Ask this paper">
    {ask_panel}
  </aside>
</div>
{ask_fab}"""
    desc = notes.get("tldr") or summary or abstract[:160]
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
        "d": published(rec),
        "s": rec.get("score") or 0,
        "f": (2 if rec.get("slot") == "trending" else 1) if rec.get("featured") else 0,
    }


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def build_site(data_dir: str = DATA_DIR, site_dir: str = SITE_DIR, export_dir: str = EXPORT_DIR) -> int:
    """Rebuild site_dir from scratch. Returns the number of paper pages written."""
    global EDITION
    days = load_days(data_dir)
    papers = merge_papers(days)
    EDITION = ticker(days)

    if os.path.isdir(site_dir):
        shutil.rmtree(site_dir)
    shutil.copytree(ASSETS_DIR, os.path.join(site_dir, "assets"))

    archive = load_archive(export_dir)
    rows, source = trends.trend_rows(archive, papers)
    _write(os.path.join(site_dir, "index.html"), build_index(days, papers, load_most_read(export_dir), rows))
    _write(os.path.join(site_dir, "trends.html"), build_trends_page(rows, source, len(archive) or len(papers)))
    _write(os.path.join(site_dir, "papers.html"), build_papers_page())
    _write(os.path.join(site_dir, "scout.html"), build_scout_page())
    _write(os.path.join(site_dir, "archive.html"), build_archive(days, papers))
    _write(os.path.join(site_dir, "saved.html"), build_saved_page())

    # Previous and next paper follow the order of the day the paper first appeared
    neighbours: dict[str, tuple] = {}
    for day in days:
        _write(os.path.join(site_dir, "day", f"{day['date']}.html"), build_day(day, papers))
        ids = [p["id"] for p in day["papers"] if papers.get(p["id"], {}).get("first_seen") == day["date"]]
        for n, pid in enumerate(ids):
            neighbours[pid] = (ids[n - 1] if n > 0 else None, ids[n + 1] if n + 1 < len(ids) else None)

    # Each top pick points to the next pick of its edition, so a reader always has one more step
    next_pick: dict[str, str] = {}
    picks_of: dict[str, list[str]] = {}
    for day in days:
        ids = [i for i in day.get("featured", []) if i in papers]
        for n, pid in enumerate(ids):
            if pid not in picks_of:
                picks_of[pid] = ids
                if len(ids) > 1:
                    next_pick[pid] = ids[(n + 1) % len(ids)]

    related = related_papers(papers)
    for rec in papers.values():
        prev_id, next_id = neighbours.get(rec["id"], (None, None))
        _write(os.path.join(site_dir, "paper", f"{rec['id']}.html"),
               build_paper(rec, [papers[i] for i in related.get(rec["id"], [])],
                           papers.get(prev_id), papers.get(next_id),
                           papers.get(next_pick.get(rec["id"])), picks_of.get(rec["id"], [])))

    # Papers with a page here, plus the rest of the database's year (linking to Hugging Face)
    listing = [compact(r) for r in papers.values()]
    listing += [archive_compact(r) for r in archive if r["id"] not in papers]
    listing.sort(key=lambda p: (p["d"], p["s"]), reverse=True)
    _write(os.path.join(site_dir, "data", "papers.json"),
           json.dumps(listing, ensure_ascii=False, separators=(",", ":")))
    # Which papers have a page here; other "For you" results link to Hugging Face
    _write(os.path.join(site_dir, "data", "ids.json"),
           json.dumps(sorted(papers), separators=(",", ":")))
    # GitHub Pages: serve files as-is, no Jekyll processing
    _write(os.path.join(site_dir, ".nojekyll"), "")

    print(f"  [site] Built {len(papers)} paper pages and {len(days)} day pages in {site_dir}")
    return len(papers)


if __name__ == "__main__":
    build_site()
