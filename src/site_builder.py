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
import hashlib
import html
import json
import re
import os
import shutil
import sys
import urllib.parse
from collections import Counter
from datetime import date, timedelta

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SRC_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from classifier import CATEGORIES
import discovery
import labs
import lab_logos
import tech_trends
import trend_story
import trends
import case_pages
import case_studies
import ranking_pages

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

# Where the site lives. Used for canonical links, share images, the RSS feed and
# the sitemap. Override with the SITE_URL repository variable (for a custom domain).
SITE_URL = (os.environ.get("SITE_URL") or "https://omen-bit.github.io/ai-paper-daily/").rstrip("/") + "/"
# Google Search Console "HTML tag" code (only the content="..." part). Set it as the
# GOOGLE_SITE_VERIFICATION repository variable; nothing is added while it is empty.
GOOGLE_SITE_VERIFICATION = os.environ.get("GOOGLE_SITE_VERIFICATION", "").strip()
# Buttondown username for the email sign-up box. Set it as the BUTTONDOWN_USER
# repository variable; until then the box offers the RSS feed only.
BUTTONDOWN_USER = re.sub(r"[^A-Za-z0-9_-]", "", os.environ.get("BUTTONDOWN_USER", ""))
# Umami Cloud website ID (a UUID from cloud.umami.is > Settings > Websites) for visitor
# analytics: visitors, pages, sources, countries and key actions. No cookies.
# Set it as the UMAMI_WEBSITE_ID repository variable; nothing is added while it is empty.
UMAMI_WEBSITE_ID = re.sub(r"[^a-f0-9-]", "", os.environ.get("UMAMI_WEBSITE_ID", "").strip().lower())

CATEGORY_NAMES = {slug: name for _, name, slug, _, _ in CATEGORIES}
CATEGORY_NAMES["other-ml"] = "Other ML"

# Icons drawn from Lucide (ISC licence), inlined so the site makes no extra requests
ICONS = {
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "github": '<path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4"/><path d="M9 18c-4.51 2-5-2-7-2"/>',
    "arrow-up-right": '<path d="M7 17 17 7"/><path d="M8 7h9v9"/>',
    "ask": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
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
    "calendar": '<path d="M8 2v4M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/>',
    "compass": '<circle cx="12" cy="12" r="10"/><path d="m16.24 7.76-2.12 6.36-6.36 2.12 2.12-6.36z"/>',
    "briefcase": '<path d="M16 20V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/><rect width="20" height="14" x="2" y="6" rx="2"/>',
    "trend": '<path d="M22 7 13.5 15.5 8.5 10.5 2 17"/><path d="M16 7h6v6"/>',
    "copy": '<rect width="13" height="13" x="9" y="9" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
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


OLDER_DAYS = 30  # a paper that reached Hugging Face this long after arXiv is "older, trending now"


def is_older(rec: dict) -> bool:
    """True when the paper came out on arXiv well before it started trending."""
    try:
        out = date.fromisoformat(str(rec.get("submitted"))[:10])
        seen = date.fromisoformat(str(rec.get("first_seen"))[:10])
    except ValueError:
        return False
    return (seen - out).days > OLDER_DAYS


OLDER_FLAG = '<span class="old-flag">Older paper, trending now</span>'


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
        if not name.endswith(".json"):
            continue
        # One damaged file must not stop the whole site from building
        try:
            with open(os.path.join(daily_dir, name), encoding="utf-8") as f:
                day = json.load(f)
            if not isinstance(day, dict) or not day.get("date"):
                raise ValueError("no date")
        except (OSError, ValueError) as exc:
            print(f"  [site] WARNING: skipped {name}, it could not be read ({exc})")
            continue
        day["papers"] = [p for p in day.get("papers") or [] if isinstance(p, dict) and p.get("id") and p.get("title")]
        day.setdefault("featured", [])
        days.append(day)
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
                    # Its page explains the ranking of the day it was picked
                    for key in ("score", "score_parts", "evidence", "claims", "rank", "of", "judge"):
                        if old.get(key) is not None:
                            rec[key] = old[key]
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

# The site's open-source code, and who made it (shown in the header and footer)
REPO_URL = "https://github.com/Omen-bit/ai-paper-daily"
MADE_BY = "Darshan Chougule"
STAR_SVG = ('<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
            '<path d="m12 2 3.1 6.3 6.9 1-5 4.9 1.2 6.8L12 17.8 5.8 21l1.2-6.8-5-4.9 6.9-1z"/></svg>')

# Edition strip shown on every page; set by build_site
EDITION = ""
# Lab name -> its official logo file in assets/logos/ (lab_logos.py); set by build_site
LOGOS: dict[str, str] = {}
# Another name of a lab -> the name the site shows, for names that share a Wikidata id; set by build_site
SAME_LAB: dict[str, str] = {}
# True when any saved logo came from Logo.dev, whose free plan asks for a visible credit
LOGO_DEV_CREDIT = False

# Runs before first paint so a saved dark theme never flashes white
def _asset_version() -> str:
    """Changes whenever style.css or app.js changes, so browsers never keep an old copy."""
    h = hashlib.sha1()
    for name in ("style.css", "app.js", "labs.svg"):
        with open(os.path.join(ASSETS_DIR, name), "rb") as f:
            h.update(f.read())
    return h.hexdigest()[:10]


ASSET_V = _asset_version()
THEME_SCRIPT = ("<script>try{var t=localStorage.getItem('apd.theme')||(matchMedia('(prefers-color-scheme: dark)')"
                ".matches?'dark':'light');document.documentElement.dataset.theme=t}catch(e){}</script>")


# The Trends tab stays out of the menu until there is enough history to show
# (build_site decides). The page itself is still built, so links to it work.
SHOW_TRENDS = True


def trends_ready(rows: list[dict]) -> bool:
    return len(rows) >= 30 and len(trends.last_months(rows, 12)) >= 3


def page(title: str, body: str, root: str = "", description: str = TAGLINE, active: str = "",
         edition: str = "", body_class: str = "", path: str | None = None, image: str = "og/site.png",
         og_type: str = "website") -> str:
    """Wrap body in the shared layout. root is the relative path to the site root.
    path is this page's address from the site root ("" for the home page); pages
    without one (the reading list) are kept out of search engines."""
    edition = edition or EDITION
    full_title = f"{title} · {SITE_NAME}" if title != SITE_NAME else f"{SITE_NAME}: research papers worth building on"
    if path is None:
        seo = '<meta name="robots" content="noindex">'
    else:
        url = discovery.absolute(SITE_URL, path)
        seo = (f'<link rel="canonical" href="{esc(url)}">\n'
               f'<meta property="og:url" content="{esc(url)}">')
    seo += (f'\n<meta property="og:type" content="{og_type}">'
            f'\n<meta property="og:site_name" content="{SITE_NAME}">'
            f'\n<meta property="og:image" content="{esc(discovery.absolute(SITE_URL, image))}">'
            '\n<meta property="og:image:width" content="1200">\n<meta property="og:image:height" content="630">'
            '\n<meta name="twitter:card" content="summary_large_image">'
            f'\n<link rel="alternate" type="application/rss+xml" title="{SITE_NAME}: daily picks" href="{SITE_URL}feed.xml">')
    if GOOGLE_SITE_VERIFICATION:
        seo += f'\n<meta name="google-site-verification" content="{esc(GOOGLE_SITE_VERIFICATION)}">'
    if UMAMI_WEBSITE_ID:
        # app.js sends the page view itself (auto-track off), so it can read the ?ref=
        # tag before tidying it out of the address bar.
        seo += (f'\n<script id="umami-script" defer src="https://cloud.umami.is/script.js"'
                f' data-website-id="{UMAMI_WEBSITE_ID}" data-auto-track="false"></script>')

    def nav(href, label, key, ic, extra=""):
        current = ' aria-current="page"' if key == active else ""
        return f'<a href="{root}{href}"{current}>{icon(ic, 18, "nav-ic")}<span class="nav-label">{label}</span>{extra}</a>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="apd-track" content="{TRACK_URL}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
{seo}
<meta name="theme-color" content="#ff4f00">
{THEME_SCRIPT}
<link rel="preload" href="{root}assets/fonts/geist.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{root}assets/fonts/geist-pixel-square.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{root}assets/style.css?v={ASSET_V}">
<link rel="icon" href="{FAVICON}">
<script type="speculationrules">{{"prerender":[{{"where":{{"selector_matches":".nav a"}},"eagerness":"moderate"}}],"prefetch":[{{"where":{{"and":[{{"href_matches":"/*"}},{{"not":{{"href_matches":"*.md"}}}}]}},"eagerness":"moderate"}}]}}</script>
</head>
<body{f' class="{body_class}"' if body_class else ""}>
<a class="skip" href="#main">Skip to content</a>
<header class="site-header">
  <div class="wrap bar-in">
    <a class="brand" href="{root}index.html" aria-label="{SITE_NAME}, home"><span class="brand-mark" aria-hidden="true"></span><span class="brand-name">AI PAPERS<em>/DAILY</em></span></a>
    <nav class="nav" aria-label="Main">
      {nav("index.html", "Today", "today", "calendar")}
      {nav("papers.html", '<span class="nav-long">All papers</span><span class="nav-short">Papers</span>', "papers", "file")}
      {nav("scout.html", "Scout", "scout", "compass")}
      {nav("case-studies/index.html", '<span class="nav-long">Case studies</span><span class="nav-short">Cases</span>', "cases", "briefcase")}
      {nav("trends.html", "Trends", "trends", "trend") if SHOW_TRENDS or active == "trends" else ""}
      {nav("saved.html", "Saved", "saved", "bookmark", '<span class="nav-count" data-saved-count hidden></span>')}
    </nav>
    <div class="header-actions">
      {f'<a class="btn btn-primary hdr-sub" href="{root}index.html#subscribe" data-sub-jump>Subscribe free</a>' if BUTTONDOWN_USER else ""}
      <span class="oss">
        <a class="oss-btn" href="{REPO_URL}" rel="noopener" aria-describedby="oss-tip">
          <span class="oss-main">{icon("github", 17)}<span class="oss-txt"><small>Open source</small><span>View on GitHub</span></span>{icon("arrow-up-right", 13, "oss-arrow")}</span>
          <span class="oss-star">{STAR_SVG}<span>Star</span></span>
        </a>
        <span class="oss-tip" id="oss-tip" role="tooltip"><b>This project is open source</b>Read the code or use it in your own project. If you like it, don’t forget to give it a ★ star on GitHub.</span>
      </span>
      <button class="icon-button" type="button" data-theme-toggle aria-label="Switch light or dark theme" data-tip="Switch theme">{icon("moon", 17, "icon-moon")}{icon("sun", 17, "icon-sun")}</button>
    </div>
  </div>
</header>
<main class="wrap" id="main">
{body}
</main>
<footer class="site-footer">
  <div class="wrap foot-in">
    <span>Built from <a href="https://arxiv.org">arXiv</a> and <a href="https://huggingface.co/papers">Hugging Face Papers</a>. Updated every morning.{' Some lab logos by <a href="https://logo.dev" rel="noopener">Logo.dev</a>.' if LOGO_DEV_CREDIT else ""}</span>
    <span>Summaries are written by AI. Papers are ranked by measured signals, not by AI: <a href="{root}methodology.html">how ranking works</a>.</span>
    <span><a href="{root}feed.xml" data-subscribe="rss">RSS feed</a>{f' · <a href="https://buttondown.com/{BUTTONDOWN_USER}" rel="noopener">Free newsletter</a>' if BUTTONDOWN_USER else ""} · Built by <a href="{REPO_URL}" rel="noopener">{MADE_BY}</a>, open source on GitHub</span>
  </div>
</footer>
<script src="{root}assets/app.js?v={ASSET_V}" defer></script>
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


def featured_card(rec: dict, rank: int, root: str, past: bool = False) -> str:
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
    if past and label == "Today’s pick":
        label = "Pick of the day"  # a past day's page is not "today"
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
  <p class="pick-date">Published {esc(nice_date(published(rec)))}{OLDER_FLAG if is_older(rec) else ""}</p>
  <footer class="pick-foot">{topic_dot(topic)}{level_meter(notes.get("difficulty"))}{code}<span class="mins">{pick_minutes(rec)} min</span></footer>
  {seen_check(rec)}
</article>"""


# Slots whose cards ask "Seen this already?". The answers, and the clicks on
# each card, show whether readers get something from us that Hugging Face
# didn't already give them.
MEASURED_SLOTS: tuple = ()


def seen_check(rec: dict) -> str:
    slot = rec.get("slot")
    if slot not in MEASURED_SLOTS:
        return ""
    return f"""<div class="seen" data-seen="{esc(rec['id'])}">
    <span data-seen-q>Seen this paper before today?</span>
    <button class="btn btn-outline btn-sm" type="button" data-seen-vote="yes" aria-pressed="false">Yes</button>
    <button class="btn btn-outline btn-sm" type="button" data-seen-vote="no" aria-pressed="false">No, new to me</button>
  </div>"""


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


def subscribe_box(root: str = "") -> str:
    """Ask readers to come back tomorrow: email (once Buttondown is set up) or RSS.
    With email, app.js sends the form in the background and swaps in the "check your
    inbox" step, and readers who already signed up see one small line instead."""
    rss = f'<a class="text-link" href="{root}feed.xml" data-subscribe="rss">{"Or follow by RSS" if BUTTONDOWN_USER else "Add the RSS feed"}</a>'
    if not BUTTONDOWN_USER:
        return f"""<section class="subscribe" id="subscribe" aria-labelledby="sub-title">
  <div class="subscribe-copy"><h2 id="sub-title">Get tomorrow’s pick</h2><p>Paste the feed link into Feedly, Inoreader or any feed reader to get each day’s picks.</p></div>
  <div class="subscribe-act">{rss}</div>
</section>"""
    action = f"https://buttondown.com/api/emails/embed-subscribe/{BUTTONDOWN_USER}"
    return f"""<section class="subscribe" id="subscribe" aria-labelledby="sub-title" data-sub-box>
  <div class="subscribe-copy"><h2 id="sub-title">Subscribe to the free newsletter</h2><p>One paper a day in your inbox, explained in plain language. Free forever, and you can leave any time.</p></div>
  <div class="subscribe-act" data-sub-ask>
    <form class="subscribe-form" action="{action}" method="post" target="_blank" data-subscribe-form>
      <label class="sr-only" for="sub-email">Email address</label>
      <input class="input" id="sub-email" type="email" name="email" required autocomplete="email" placeholder="you@example.com">
      <input type="hidden" name="embed" value="1">
      <button class="btn btn-primary" type="submit">Subscribe for free</button>
    </form>
    {rss}
  </div>
  <div class="sub-done" data-sub-done role="status" aria-live="polite" hidden>
    <span class="sub-tick" aria-hidden="true">✓</span>
    <div><strong>Almost done. Check your inbox.</strong>
      <p>We sent a confirm link to <span data-sub-email>your email</span>. Not there in a minute? Look in Spam or Promotions, or <button class="link-button" type="button" data-sub-resend>send it again</button>.</p></div>
  </div>
</section>
<p class="sub-mini" data-sub-mini hidden><span class="sub-tick" aria-hidden="true">✓</span>You’re subscribed. Tomorrow’s pick arrives by email.</p>"""


def build_subscribed_page() -> str:
    """Where the confirm link in the Buttondown email lands (set it as the
    confirmation redirect in Buttondown): what happens next, and something to do now."""
    body = """<section class="youre-in" data-sub-confirmed>
  <span class="sub-tick sub-tick-lg" aria-hidden="true">✓</span>
  <h1>You’re in.</h1>
  <p class="lead">Your subscription to AI Papers Daily is confirmed. Here’s what happens next.</p>
  <ol class="expect">
    <li><b>1</b><div><strong>Tomorrow around 7am IST</strong><span>Your first email: the day’s best new AI paper, explained in plain language.</span></div></li>
    <li><b>2</b><div><strong>Every day after that</strong><span>One pick plus the trending paper. Unsubscribe with one click at the bottom of any email.</span></div></li>
    <li><b>3</b><div><strong>Don’t want to wait?</strong><span>Read today’s pick now, or describe your project in Scout and get the papers that fit it.</span></div></li>
  </ol>
  <p class="youre-in-actions"><a class="btn btn-primary" href="index.html#today">Read today’s pick</a><a class="btn btn-outline" href="scout.html">Try Scout</a></p>
</section>"""
    return page("You’re in", body, description="Your subscription to AI Papers Daily is confirmed.")


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


def load_links(data_dir: str = DATA_DIR) -> dict:
    """Code, models and citations per paper, written by paper_links.py. Empty when missing."""
    try:
        with open(os.path.join(data_dir, "links.json"), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_archive(export_dir: str = EXPORT_DIR) -> list[dict]:
    """Every paper in the database (about a year), written by supabase_sync.py."""
    return _load_export(export_dir, "papers.json")


def archive_compact(row: dict) -> dict:
    """A database paper with no page on this site, in the papers.json short form (see compact)."""
    authors = row.get("authors") or []
    out = {
        "i": row["id"], "t": row.get("title") or row["id"], "a": authors[:3], "n": len(authors),
        "c": row.get("categories") or ["other-ml"],
        "d": (row.get("submitted") or row.get("first_seen") or "")[:10],
        "w": (row.get("first_seen") or row.get("submitted") or "")[:10],
        "s": 0, "f": 0, "x": 1,
        "m": row.get("lead") or "",
        "u": int(row.get("hf_upvotes") or 0),
    }
    if row.get("code_url"):
        out["k"] = 1
    if not out["u"] and row.get("source") == "arXiv":
        out["h"] = 1
    return out


def lead_sentence(text: str, limit: int = 180) -> str:
    """The first sentence of an abstract, cut at a word if it runs long. Stands in
    for a one-line summary on cards until the paper has notes of its own."""
    text = " ".join((text or "").split())
    if not text:
        return ""
    m = re.search(r"(?<=[A-Za-z0-9)\]][.!?])\s+(?=[A-Z])", text)
    first = text[:m.start()] if m else text
    if len(first) > limit:
        first = first[:limit - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return first


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
        return page(SITE_NAME, body, active="today", path="")

    latest = days[0]
    featured_ids = latest.get("featured", [])
    featured = [papers[i] for i in featured_ids if i in papers]
    # Once our own readers are enough, the second slot shows what they read most
    top = next((m for m in most_read if m["id"] in papers and m["id"] not in featured_ids[:1]), None)
    if featured and top and top.get("views", 0) >= MIN_MOST_READ_VIEWS:
        featured = featured[:1] + [dict(papers[top["id"]], slot="most-read", readers=top["views"])]
    others = [papers[p["id"]] for p in latest["papers"] if p["id"] not in featured_ids][:MORE_FROM_TODAY]
    n_today = len(latest["papers"])
    # Newer editions read every arXiv paper but store only the best ("scanned" counts them all)
    n_scanned = max(latest.get("scanned") or 0, n_today)

    cards = "\n".join(featured_card(r, n, "") for n, r in enumerate(featured, 1))
    more = ""
    if others:
        rows = "\n".join(home_row(r, n) for n, r in enumerate(others, len(featured) + 1))
        link = f'<a class="more" href="day/{esc(latest["date"])}.html">{"See all " if n_scanned == n_today else "See the top "}{n_today} papers from today</a>'
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
</section>
<section class="block" id="today">
  {section_head("Today’s picks", f"Chosen from {n_scanned:,} new papers")}
  <div class="picks">{cards}</div>
</section>
{subscribe_box()}
<section class="block" data-foryou data-url="{RECOMMEND_URL}" data-names="{esc(json.dumps(CATEGORY_NAMES))}" hidden>
  {section_head("For you", "Recent papers close in meaning to what you’ve read. Worked out from this browser’s history only.")}
  <ol class="foryou" data-foryou-list aria-busy="true">{'<li class="foryou-item skeleton" aria-hidden="true"></li>' * 3}</ol>
</section>
<section class="block" data-watch data-url="{SEARCH_URL}" hidden>
  {section_head("Your projects", "New papers for the projects you watch in Scout. Checked once a day, from this browser only.", '<a class="more" href="scout.html">Open Scout</a>')}
  <div class="watch-list" data-watch-list aria-busy="true"></div>
</section>
<section class="split">
  <div class="split-main">{more}{most_read_list(most_read, papers)}</div>
  <aside class="block side" data-continue hidden>
    {section_head("Continue reading")}
    <ul class="list" data-continue-list></ul>
  </aside>
</section>
{chart}"""
    return page(SITE_NAME, body, active="today", edition=ticker(days), path="")


# The search function in Supabase (supabase/functions/search). Public by design:
# it only answers this site and is rate limited per visitor.
SEARCH_URL = "https://nmelkepelhwyhlfdznpf.supabase.co/functions/v1/search"
# The "For you" function (supabase/functions/recommend), same rules as search
RECOMMEND_URL = "https://nmelkepelhwyhlfdznpf.supabase.co/functions/v1/recommend"

SKELETON_CARDS = "".join('<div class="pcard skeleton" aria-hidden="true"><span></span><span></span><span></span></div>' for _ in range(6))


def papers_tabs(current: str, root: str = "") -> str:
    """All papers and the day-by-day archive are two views of the same papers."""
    tab = lambda href, label, key: (f'<a href="{root}{href}"{" aria-current=page" if key == current else ""}>{label}</a>')
    return (f'<nav class="tabs" aria-label="Papers views">{tab("papers.html", "All papers", "papers")}'
            f'{tab("labs.html", "By lab", "labs")}</nav>')


# Quick views on the papers page: value, label
PAPER_VIEWS = [
    ("", "Recommended"),
    ("new", "Newest"),
    ("week", "Trending this week"),
    ("nothf", "Not on Hugging Face yet"),
    ("picks", "Our picks"),
    ("code", "Has code"),
    ("easy", "Beginner-friendly"),
]


def build_papers_page() -> str:
    options = "".join(f'<option value="{esc(slug)}">{esc(name)}</option>'
                      for slug, name in CATEGORY_NAMES.items())
    chips = "".join(f'<button class="chip" type="button" data-view="{v}" aria-pressed="{"true" if not v else "false"}">{esc(label)}</button>'
                    for v, label in PAPER_VIEWS)
    body = f"""<section class="page-head page-head-tight">
  {papers_tabs("papers")}
  <h1>All papers</h1>
  <p>Every AI paper we track, each with a one-line summary. Search by title or author, or describe an idea in a few words.</p>
</section>
<div class="pbar">
  <div class="pbar-search">
    <label class="sr-only" for="q">Search papers</label>
    <span class="input-wrap">{icon("search", 16)}<input class="input" id="q" type="search" placeholder="Search titles and authors, or describe an idea" autocomplete="off"></span>
    <label class="toggle toggle-meaning" hidden><input id="meaning" type="checkbox"> By meaning</label>
  </div>
  <div class="chips" role="group" aria-label="Show">
    {chips}
    <label class="sr-only" for="cat">Topic</label>
    <select class="select chip-select" id="cat"><option value="">All topics</option>{options}</select>
  </div>
</div>
<div class="result-meta"><span id="count">Loading papers…</span></div>
<div class="cards" id="results" aria-busy="true" data-search-url="{SEARCH_URL}">{SKELETON_CARDS}</div>
<div class="center"><button class="btn btn-outline" id="more" type="button" hidden>Show more</button></div>
<noscript><p class="empty">Turn on JavaScript to search, or browse the <a href="archive.html">archive</a>.</p></noscript>"""
    return page("All papers", body, active="papers", path="papers.html")


# Anonymous view counts and feedback (supabase/functions/track)
TRACK_URL = "https://nmelkepelhwyhlfdznpf.supabase.co/functions/v1/track"

# "Ask this paper" (supabase/functions/ask), same rules as search
ASK_URL = "https://nmelkepelhwyhlfdznpf.supabase.co/functions/v1/ask"
# The breakdown function (supabase/functions/breakdown): the paper's own
# contributions, results, limitations and conclusion, read from arXiv's HTML.
BREAKDOWN_URL = "https://nmelkepelhwyhlfdznpf.supabase.co/functions/v1/breakdown"
ASK_SUGGESTIONS = ["What problem does it solve?", "What would I need to try it?", "How did they test it?"]

# Project Scout (supabase/functions/scout), same rules as search
SCOUT_URL = "https://nmelkepelhwyhlfdznpf.supabase.co/functions/v1/scout"

SCOUT_EXAMPLES = [
    ("Offline voice notes", "A voice notes app that turns speech into text fully offline on an Android phone, with no server."),
    ("Support reply drafts", "A helper that reads our customer support tickets and drafts replies, running on one laptop without a GPU."),
    ("Library chatbot", "A chatbot for my college library that answers questions from our PDF catalogue and cites the page it used."),
]


def scout_brands(posts: list[dict]) -> str:
    """What Scout needs to draw case study covers like the Case studies page: per company its logo
    (sprite id, brand colour, saved icon file, drawn in ink), and the name of each problem."""
    companies = sorted({p["company"] for p in posts if p.get("company")})
    brands = {co: [case_pages._slug(co), case_pages.brand_hex(co), case_pages.LOGO_FILES.get(co, ""),
                   int(case_pages._dark_brand(co))] for co in companies}
    problems = {k: case_pages.problem_name(k) for k in case_pages.TOPIC_INFO}
    return json.dumps({"c": brands, "p": problems, "svg": "data/case-brands.svg"}, separators=(",", ":"))


def brand_sprite_file(posts: list[dict]) -> str:
    """The case study logos as one SVG file, so Scout's case cards can point at them with <use>."""
    sprite = case_pages.sprite(p["company"] for p in posts if p.get("company"))
    if not sprite:
        return '<svg xmlns="http://www.w3.org/2000/svg"></svg>'
    return sprite.replace('<svg class="cs-sprite" aria-hidden="true" focusable="false">',
                          '<svg xmlns="http://www.w3.org/2000/svg">', 1)


def _scout_preview() -> str:
    """The right side of the empty Scout page: a small sample brief, so people see what they will get."""
    parts = [("01", "Read the PDFs", "Covered", "", "s-strong s-strong s-rel"),
             ("02", "Find the passage", "Covered", "", "s-strong s-strong s-strong"),
             ("03", "Cite the page", "Gap", " is-gap", "x x x")]
    part_html = "".join(
        f'<li class="shp-part{gap}"><p class="sb-part-top"><span>{n}</span><span class="sb-pill">{st}</span></p>'
        f'<b>{label}</b><p class="sb-seg">{"".join(f"<i class={chr(34)}{c}{chr(34)}></i>" for c in seg.split())}</p></li>'
        for n, label, st, gap, seg in parts)
    teams = "".join(f'<i style="background:{c}">{t}</i>' for t, c in (("U", "#111"), ("D", "#FF3621"), ("N", "#E50914")))
    return f"""<div class="sh-preview" aria-hidden="true">
      <div class="shp-top">
        <div class="sb-ring-big shp-ring"><svg viewBox="0 0 104 104"><circle class="rg-gap" cx="52" cy="52" r="44"/><circle class="rg-ok" cx="52" cy="52" r="44" pathLength="100" stroke-dasharray="64 36" transform="rotate(-90 52 52)"/></svg><b>2/3</b><span>Ready</span></div>
        <div><p class="shp-kicker">Sample brief</p><p class="shp-h">Library chatbot that cites the page</p><p class="shp-sub">2 of 3 parts have a strong paper. 1 is an open problem.</p></div>
      </div>
      <ol class="shp-parts">{part_html}</ol>
      <div class="shp-row">
        <div class="shp-paper"><span class="shp-cover">PARSE</span><div><p class="shp-score"><b>91</b> Strong fit</p><p class="shp-t">Youtu-Parsing-Omni: one encoder for every page layout</p><p class="shp-why">Keeps each block’s page number, so part 03 can cite it.</p></div></div>
        <div class="shp-cases"><span class="shp-teams">{teams}</span><p><b>3 teams</b> shipped something like this</p></div>
      </div>
    </div>"""


def build_scout_page(brands: str = "", n_cases: int = 0) -> str:
    examples = "".join(f'<button class="example" type="button" data-example="{esc(text)}"><b>{esc(title)}</b>'
                       f'<span>{esc(text)}</span></button>' for title, text in SCOUT_EXAMPLES)
    cases = f" · {n_cases:,} case studies" if n_cases else ""
    body = f"""<section class="page-head scout-head sh">
  <p class="sb-eyebrow"><b>/ Project Scout</b> · 8,000+ papers{cases}</p>
  <h1 class="sh-h">What do you want to build?</h1>
  <p class="sh-lede">Describe it in plain words. Scout splits it into parts, finds the papers that fit each part, shows teams that built something similar, and says plainly where research has no answer yet.</p>
</section>
<div class="scout">
  <form class="card scout-form" data-scout data-url="{SCOUT_URL}" data-names="{esc(json.dumps(CATEGORY_NAMES))}" data-brands="{esc(brands)}" novalidate>
    <label class="field-label" for="desc">Describe your project</label>
    <p class="field-hint" id="desc-hint">Plain words, no code. Say what it does, who it's for, and any limits, like “runs on a phone” or “no GPU”.</p>
    <div class="sh-box">
      <textarea class="input textarea" id="desc" rows="6" maxlength="1000" aria-describedby="desc-hint desc-error" placeholder="e.g. An app that…"></textarea>
      <div class="sh-box-foot"><span class="char-count" data-count>0 / 1000</span><button class="btn btn-primary" type="submit" data-scout-go>Find papers</button></div>
    </div>
    <div class="field-foot"><span class="field-error" id="desc-error" role="alert" hidden></span></div>
    <div class="examples"><span class="label">Or start from an example</span>{examples}</div>
    <p class="fine">Your description goes to our search service and to Groq, which plans the search. We don't store it.</p>
  </form>
  <section class="scout-out" data-scout-out aria-live="polite">
    <div class="scout-intro">
      <p class="sb-label"><span>What you get</span><span>A build brief for your project</span></p>
      {_scout_preview()}
      <ol class="how">
        <li><b>Parts, not keywords.</b> Scout splits your idea into the pieces it needs. You can edit them before it searches.</li>
        <li><b>Papers scored for fit.</b> Each part gets the best papers, with why each one fits and a reading order.</li>
        <li><b>Real teams and real gaps.</b> Case studies from teams that shipped something similar, and the parts no paper covers yet.</li>
      </ol>
    </div>
  </section>
</div>
<noscript><p class="empty">Turn on JavaScript to use Project Scout.</p></noscript>"""
    return page("Project Scout", body, active="scout", body_class="page-scout", path="scout.html",
                description="Describe your project and get the AI papers most relevant to it, best first.")


def build_trends_page(rows: list[dict], source: str, n_all: int, on_site: set[str] | None = None,
                      cases: list[dict] | None = None) -> str:
    months = trends.last_months(rows, 12)
    if not trends_ready(rows):
        body = """<section class="page-head"><h1>Trends</h1>
  <p>Trends need at least three months of papers. They appear here once the history has loaded.</p></section>"""
        return page("Trends", body, active="trends", path="trends.html")
    names = CATEGORY_NAMES
    per = trends.topic_counts(rows, months)
    top = trends.top_topics(per, 5)
    month_totals = Counter(r["day"][:7] for r in rows)
    code = trends.code_share(rows, months)
    code_months = trend_story.full_months(months, month_totals)
    code_now = next((m, v) for m, v, _ in code if m == code_months[-1])
    tech = tech_trends.tech_stats(rows, months)
    words = trends.rising_words(rows, months)
    field = trends.field_shares_json(rows, months)
    first, last = trends._month_label(months[0], True), trends._month_label(months[-1], True)

    shift = trend_story.topic_shift(per, months, names)
    rp = trend_story.research_vs_practice(tech, cases or [])
    peaks = trend_story.off_peak(tech, months, month_totals)
    head, lede, stats = trend_story.opening(shift, tech, rp, code_now)
    stats_html = "".join(f'<p class="th-stat tone-{tone}"><strong>{v}</strong><span>{label}</span></p>'
                         for v, tone, label in stats)
    src_note = f"Source: {esc(source)}, {first} to {last}."
    cards = []
    if shift:
        g = shift["rise_line"][-1] / max(shift["rise_line"][0], 0.001)
        flat = abs(shift["base_line"][-1] - shift["base_line"][0]) < 0.15 * max(shift["base_line"][0], 0.001)
        title = (f'{esc(shift["rise_name"])} grew {trend_story._times(g)} while {esc(shift["base_name"])} '
                 f'{"stayed flat" if flat else "moved less"}')
        cards.append(trend_story.card(
            "01", "The topic shift", title,
            "Each line is a topic’s share of that month’s papers. Hover or tab through the months.",
            trend_story._times(g), f"share of all papers, {trends._month_label(shift['months'][0])} to "
            f"{trends._month_label(shift['months'][-1])}", "up",
            trend_story.topic_shift_chart(shift), src_note, trend_story.topic_shift_table(shift)))
    mb = trend_story.momentum_bars(tech)
    if mb:
        rated = [t for t in tech if t["growth"] and t["status"] in ("breakout", "rising", "steady", "cooling")]
        best = max(rated, key=lambda t: t["growth"])
        second = (sorted((t["growth"] for t in rated), reverse=True) + [1.0])[1]
        title = (f'{esc(best["name"])} grew almost twice as fast as anything else' if best["growth"] - 1 >= 1.7 * (second - 1) > 0
                 else f'{esc(best["name"])} is growing fastest' if best["growth"] >= 1.05
                 else "No technology is gaining share this season")
        cards.append(trend_story.card(
            "02", f"Momentum, all {len(rated)} technologies", title,
            "Change in each technology’s share of new papers, last 90 days against the 90 before. Click one to see its papers.",
            tech_trends.change(best["growth"]), f"{esc(best['name'].lower())}, the season’s fastest grower", "up",
            mb, src_note, tech_trends.leaderboard(tech, months)))
    if rp:
        lead = rp["practice"][0]
        names_p = trend_story.name_list([r["name"] for r in rp["practice"]])
        names_r = trend_story.name_list([r["name"] for r in rp["research"]])
        ratio = lead["case"] / lead["paper"] if lead["paper"] else 0
        cards.append(trend_story.card(
            "03", "Research against production",
            f"Companies build with {esc(names_p)}; research has moved on to {esc(names_r)}",
            f"Share of new papers against share of the {rp['n']} company case studies that mention each technology.",
            trend_story._times(ratio) if ratio else "—", f"more common in production: {esc(lead['name'].lower())}", "up",
            trend_story.research_vs_practice_chart(rp),
            "Case studies matched by keyword in their title, summary and tags. " + src_note,
            trend_story.research_vs_practice_table(rp)))
    if peaks:
        deep = max(peaks, key=lambda r: r["drop"])
        n_words = ["No", "One", "Two", "Three", "Four", "Five"][len(peaks)]
        cards.append(trend_story.card(
            "04", "Off the peak",
            f'{n_words} technolog{"y is" if len(peaks) == 1 else "ies are"} well below {"its" if len(peaks) == 1 else "their"} best month',
            f"The hatched bar is each one’s highest monthly share this year; the solid bar is {trends._month_label(peaks[0]['now_month'])}.",
            f"−{round(deep['drop'] * 100)}%", f"{esc(deep['name'].lower())}, peak to now", "down",
            trend_story.off_peak_chart(peaks), src_note, trend_story.off_peak_table(peaks)))
    if words:
        lead = words[0]
        cards.append(trend_story.card(
            "05", "Words on the rise", f"“{esc(lead['word'])}” is the word of the season",
            "Title words used much more in the last three months than in the months before. Click one to see its papers.",
            f"{lead['ratio']:.1f}×", f"“{esc(lead['word'])}” in titles", "up",
            trend_story.words_chart(words[:6]), "Share of paper titles containing each word. " + src_note,
            trend_story.words_table(words)))
    body = f"""<section class="trend-hero">
  <p class="th-eyebrow">/ Trends · {len(rows):,} papers · {first} to {last}</p>
  <h1>{head}</h1>
  <p class="th-lede">{lede}</p>
  <div class="th-stats">{stats_html}</div>
  <p class="th-source">From {len(rows):,} {esc(source)}{f", of {n_all:,} in our database" if n_all > len(rows) else ""}. Updated every morning.</p>
</section>
<div class="story">{"".join(cards)}</div>

<div class="trend-more">
<section class="block">
  {section_head("Topic share, month by month", "Each band is a topic’s share of that month’s papers. Hover or tab through the months.")}
  <div class="card pad chart-box">{trends.share_area(per, months, top, names)}
    <details class="table-view"><summary>Show as a table</summary>{trends.share_table(per, months, top, names)}</details></div>
</section>

<section class="split split-even">
  <div class="block">
    {section_head("You vs the field", "Topics of the papers you opened here, against the last 3 months")}
    <div class="card pad" data-you-field data-field='{esc(field)}' data-names="{esc(json.dumps(names))}">
      <p class="empty-note" data-you-empty>Open a few papers and this chart shows how your reading compares with what’s being published. It uses this browser’s history only.</p>
      <div data-you-chart hidden></div>
    </div>
  </div>
  <div class="block">
    {section_head("Code with the paper", "Share of papers that link to their code, month by month")}
    <div class="card pad code-months">{code_bars(code)}</div>
  </div>
</section>

<section class="block">
  {section_head("The year in papers", "Papers per day. Stronger colour means a busier day.")}
  <div class="card pad">{trends.calendar(trends.daily_counts(rows), end_day(rows))}</div>
</section>
</div>"""
    return page("Trends", body, active="trends", path="trends.html",
                description="Which AI technologies are growing in research right now: agents, reasoning, RAG and more, plus topic shares and code availability.")


def end_day(rows: list[dict]) -> str:
    return max(r["day"] for r in rows)


def code_bars(code: list[tuple[str, float, int]]) -> str:
    """One small bar per month: the share of that month's papers with a code link."""
    if not code:
        return ""
    top = max(v for _, v, _ in code) or 1
    bars = "".join(f'<li title="{esc(trends._month_label(m, True))}: {trends.pct(v)} of {n:,} papers">'
                   f'<span class="cm-v">{trends.pct(v)}</span><i style="height:{v / top * 100:.1f}%"></i>'
                   f'<span class="cm-m">{trends._month_label(m)}</span></li>' for m, v, n in code)
    return f'<ol class="cm" aria-label="Share of papers with code, by month">{bars}</ol>'


LAB_KINDS = [("", "All"), ("company", "Companies"), ("university", "Universities"), ("lab", "Labs and startups")]


def lab_href(lab: str, root: str = "") -> str:
    return f"{root}papers.html?lab={urllib.parse.quote(lab)}"


def build_labs_page(papers: dict, links: dict) -> str:
    """Every lab or company we know a paper came from: most papers first, with its topics and newest papers."""
    by_lab: dict[str, list[dict]] = {}
    for rec in papers.values():
        lab = lab_of(rec, links.get(rec["id"]))
        if lab:
            by_lab.setdefault(lab, []).append(rec)
    newest = lambda r: (r.get("first_seen") or "", published(r))
    ranked = sorted(by_lab.items(), key=lambda kv: (-len(kv[1]), -max(int(r.get("hf_upvotes") or 0) for r in kv[1]), kv[0].lower()))
    n_papers = sum(len(v) for v in by_lab.values())

    def card(lab: str, recs: list[dict]) -> str:
        recs = sorted(recs, key=newest, reverse=True)
        topics = {}
        for r in recs:
            for t in (r.get("categories") or ["other-ml"])[:1]:
                topics[t] = topics.get(t, 0) + 1
        top = sorted(topics.items(), key=lambda kv: (-kv[1], kv[0]))[:2]
        chips = "".join(f'<span class="sig sig-topic t-{esc(t)}"><span class="dot"></span>{esc(category_name(t))}'
                        f'{f" <b>{n}</b>" if n > 1 else ""}</span>' for t, n in top)
        items = "".join(f'<li><a href="paper/{esc(r["id"])}.html">{esc(r["title"])}</a>'
                        f'<time datetime="{esc(published(r))}">{esc(nice_date(published(r), with_year=False))}</time></li>'
                        for r in recs[:3])
        upvotes = sum(int(r.get("hf_upvotes") or 0) for r in recs)
        stats = f'{len(recs)} paper{"" if len(recs) == 1 else "s"}' + (f" · ▲ {upvotes:,} upvotes" if upvotes else "")
        more = (f'<a class="lab-all" href="{esc(lab_href(lab))}">See all {len(recs)} papers →</a>' if len(recs) > 3
                else f'<a class="lab-all" href="{esc(lab_href(lab))}">Show as cards →</a>')
        return f"""<article class="lab-card" data-kind="{labs.kind(lab)}">
  <header class="lab-head">{lab_mark(lab, "")}<div><h2><a href="{esc(lab_href(lab))}">{esc(lab)}</a></h2><p>{esc(stats)}</p></div></header>
  <div class="lab-topics">{chips}</div>
  <ol class="lab-papers">{items}</ol>
  {more}
</article>"""

    kinds = "".join(f'<button class="chip" type="button" data-lab-kind="{k}" aria-pressed="{"true" if not k else "false"}">{esc(label)}</button>'
                    for k, label in LAB_KINDS)
    cards = "".join(card(lab, recs) for lab, recs in ranked)
    body = f"""<section class="page-head page-head-tight">
  {papers_tabs("labs")}
  <h1>By lab</h1>
  <p>The companies, universities and labs behind the papers, with the most papers first. A lab shows here when Hugging Face, the paper's code or its authors' listed institutions name it, so it grows every day.</p>
</section>
<div class="pbar"><div class="chips" role="group" aria-label="Show">{kinds}</div></div>
<div class="result-meta"><span data-lab-count>{len(ranked)} labs behind {n_papers} papers</span></div>
<div class="lab-grid" data-labs>{cards or '<p class="empty">No labs found yet. They fill in with each daily update.</p>'}</div>"""
    return page("Papers by lab", body, active="papers", path="labs.html",
                description="The companies, universities and labs behind new AI papers, with their latest work.")


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
    return page("Archive", body, active="papers", path="archive.html")


def build_day(day: dict, papers: dict) -> str:
    featured_ids = day.get("featured", [])
    featured = [papers[i] for i in featured_ids if i in papers]
    rest = [papers[p["id"]] for p in day["papers"] if p["id"] not in featured_ids]
    cards = "\n".join(featured_card(r, n, "../", past=True) for n, r in enumerate(featured, 1))
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
    return page(nice_date(day["date"]), body, root="../", active="papers", path=f"day/{day['date']}.html")


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



_TEX = [(r"\\times", "×"), (r"\\%", "%"), (r"\\approx", "≈"), (r"\\sim", "~"), (r"\\pm", "±"),
        (r"\\(?:leq|le)\b", "≤"), (r"\\(?:geq|ge)\b", "≥"), (r"\\(?:rightarrow|to)\b", "→"), (r"\\leftarrow\b", "←"),
        (r"\\cdot\b", "·"), (r"\{,\}", ","),
        # Font commands keep their text: \boldsymbol{300\times} becomes 300×
        (r"\\(?:mathrm|text|textbf|textit|mathbf|mathcal|mathit|mathbb|boldsymbol|bm|operatorname|emph)\s*", ""),
        (r"\\[,;! ]", " "), (r"[{}]", "")]


def tidy_tex(text: str) -> str:
    """Simple inline LaTeX in abstracts, made readable: $38.6\\times$ becomes 38.6×."""
    def fix(m):
        inner = m.group(1)
        if not re.search(r"[\\^_{]", inner):
            return m.group(0)  # not maths, e.g. prices like $5 and $6
        for pat, repl in _TEX:
            inner = re.sub(pat, repl, inner)
        return re.sub(r"\s{2,}", " ", inner).strip()
    return re.sub(r"\$([^$]{1,80})\$", fix, text or "")


def split_sentences(text: str) -> list[str]:
    """Sentences of an abstract. Keeps "e.g." and decimals like 3.5 together."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(\"“])", (text or "").strip())
    out: list[str] = []
    for part in parts:
        if out and re.search(r"\b(?:e\.g|i\.e|et al|vs|Fig|Eq)\.$", out[-1]):
            out[-1] += " " + part
        else:
            out.append(part)
    return [p for p in out if p]


# Words that mark what a sentence of an abstract is doing, for the skim colours
_SKIM_RESULT = re.compile(r"\b(achiev|outperform|surpass|improv|state-of-the-art|sota|beat|exceed|reduc\w* .{0,30}\bby\b|"
                          r"results? (?:show|demonstrat|indicat)|experiments? (?:show|demonstrat)|we (?:show|demonstrate|find|observe)|"
                          r"demonstrat\w* that|gains?|speed-?ups?|faster|accuracy|competitive|generaliz)", re.I)
_SKIM_METHOD = re.compile(r"^(?:to (?:address|tackle|solve|this end)|here,? |in this (?:paper|work)|we (?:propose|introduce|present|develop|design|build|construct|"
                          r"formulate|train|leverage|use|adopt|release|curate|collect))|\bour (?:approach|method|framework|model|system|key idea)\b|"
                          r"\b(?:we|this paper|this work) (?:propose|introduce|present)", re.I)
_SKIM_GOAL = re.compile(r"\b(however|but|challeng|limit|remain|lack|struggl|fail|difficult|costly|expensive|bottleneck|"
                        r"require|problem|gap|open question|unclear|suffer|hinder|prone)", re.I)


def skim_label(sentence: str, index: int) -> str:
    """'goal', 'method', 'result' or '' for one sentence. Plain rules, no AI."""
    if _SKIM_METHOD.search(sentence):
        return "method"
    if _SKIM_RESULT.search(sentence) and index > 0:
        return "result"
    if index == 0 or (index < 3 and _SKIM_GOAL.search(sentence)):
        return "goal"
    return ""


def abstract_html(abstract: str, terms: list[dict] = ()) -> str:
    """
    The abstract, with each sentence that states the problem, the method or a result
    marked for the skim colours. Rule-based, so it costs nothing and can't invent text.
    """
    text = tidy_tex((abstract or "").strip())
    if not text:
        return ""
    parts = []
    for n, sentence in enumerate(split_sentences(text)):
        kind = skim_label(sentence, n)
        body = with_terms(esc(sentence), terms)
        parts.append(f'<span class="skim skim-{kind}">{body}</span>' if kind else body)
    return f"<p data-highlightable>{' '.join(parts)}</p>"


def with_terms(escaped: str, terms: list[dict], used: set | None = None) -> str:
    """Give the first use of each defined term a definition that opens on hover or tap."""
    used = used if used is not None else set()
    for t in terms or ():
        term = t.get("term") or ""
        if not term or term.lower() in used:
            continue
        m = re.search(r"(?<![\w\u2010\u2011-])" + re.escape(esc(term)) + r"(?![\w\u2010\u2011-])", escaped, re.I)
        if not m or "<" in escaped[max(0, m.start() - 60):m.start()].rsplit(">", 1)[-1]:
            continue
        used.add(term.lower())
        tip = (f'<span class="term" tabindex="0">{m.group(0)}<span class="term-tip" role="tooltip">'
               f'<b>{esc(term)}</b>{esc(t.get("meaning"))}</span></span>')
        escaped = escaped[:m.start()] + tip + escaped[m.end():]
    return escaped


# A number worth a tile: a percentage, a multiple, a size or a count of something
_NUMBER = re.compile(r"(?<![\w.,-])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(\s?(?:%|×|x\b|-fold|-bit|[BMK]\b))?"
                     r"(\s?→\s?\d[\d,.]*)?")
_NUMBER_NOUN = re.compile(r"^\s*(?:[a-z-]+\s){0,4}?(tasks|benchmarks|languages|datasets|environments|websites|examples|samples|"
                          r"problems|questions|hours|videos|images|tokens|parameters|models|agents|tools|domains|categories|"
                          r"points|steps|layers|users|papers|games|robots|scenes|pairs|instructions|annotations)\b", re.I)


def key_numbers(abstract: str, limit: int = 3) -> list[dict]:
    """
    Up to three headline numbers from the abstract, each with the words around it.
    Plain code, so a number shown here is always one the authors wrote.
    """
    text = tidy_tex(abstract or "")
    found, seen = [], set()
    for sentence in split_sentences(text):
        last_end = -100
        for m in _NUMBER.finditer(sentence):
            raw, unit, arrow = m.group(1), (m.group(2) or "").strip(), m.group(3) or ""
            value = float(raw.replace(",", ""))
            after = sentence[m.end():]
            if 1900 <= value <= 2100 and not unit:
                continue  # a year
            noun = _NUMBER_NOUN.match(after)
            if not unit and not arrow and not (noun and value >= 10):
                continue
            if re.match(r"[-\w]", after) or (unit in ("B", "M", "K") and not noun):
                continue  # part of a name, like Qwen3-8B or "4B-level"
            shown = raw + ("×" if unit in ("x", "×") else unit) + (" → " + arrow.split("→")[1].strip() if arrow else "")
            # "from 9.9% to 1.0%" reads best as one change
            to = re.match(r"\s*to\s+(\d[\d,.]*\s?(?:%|×|x\b)?)", after)
            if to and re.search(r"\bfrom\s+$", sentence[:m.start()]):
                arrow = to.group(1).strip().replace("x", "×")
                shown += " → " + arrow
                seen.add(arrow)
            if shown in seen:
                continue
            seen.add(shown)
            weight = 3 if unit in ("%", "×", "x", "-fold") or arrow else 2 if unit else 1
            context = number_context(sentence, m.start(), m.end())
            near = bool(re.fullmatch(r"\s*(?:,|and|or|,\s*and)?\s*", sentence[max(0, last_end):m.start()])) if last_end >= 0 else False  # "4.3× and 6.1×": one tile
            last_end = m.end() + (len(to.group(0)) if to and arrow else 0)
            if near and any(f["context"] == context for f in found):
                continue
            found.append({"value": shown, "context": context, "w": weight})
    found.sort(key=lambda n: -n["w"])
    return [{"value": n["value"], "context": n["context"]} for n in found[:limit]]


def number_context(sentence: str, start: int, end: int, words: int = 16) -> str:
    """The clause around a number, about a dozen words, with an ellipsis where it was cut."""
    bounds = [0] + [m.end() for m in re.finditer(r",\s|[;:()]", sentence)] + [len(sentence) + 1]
    a, b = 0, len(sentence)
    for i in range(len(bounds) - 1):
        if bounds[i] <= start < bounds[i + 1]:
            a, b = bounds[i], max(bounds[i + 1] - 1, end)
            # A clause that is little more than the number borrows the clause before it
            if len(re.sub(r"[\d,.%×→]+", " ", sentence[a:b]).split()) < 4 and i > 0:
                a = bounds[i - 1]
            break
    clause = sentence[a:b].strip(" ,;:()")
    if clause.count("(") > clause.count(")"):
        clause += ")"
    toks = clause.split()
    if len(toks) <= words:
        return clause.rstrip(".") if clause.endswith(".") and not clause.endswith("..") else clause
    # Keep the words nearest the number
    pre = len(sentence[a:start].split())
    lo = max(0, min(pre - words // 2, len(toks) - words))
    out = " ".join(toks[lo:lo + words])
    return ("…" if lo else "") + out + ("…" if lo + words < len(toks) else "")


# The cover's headline: a number from the notes or the title, else the upvotes, else "New"
_COVER_STAT = re.compile(r"(^|[\s(])([−-]?\d+(?:\.\d+)?)(\s?[x×%]|-bit)(?=[\s,.;:)]|$)", re.I)
_STAT_WORDS = re.compile(r"^(faster|slower|less|more|fewer|smaller|larger|bigger|cheaper|better|higher|lower|speedup|"
                         r"reduction|improvement|gain|memory|compute|accuracy|cost|latency|throughput|parameters|tokens|"
                         r"compression|error|errors)$", re.I)


def cover_stat(rec: dict) -> tuple[str, str]:
    notes = rec.get("curator") or {}
    for text in (notes.get("whats_new") or "", notes.get("tldr") or "", rec.get("title") or ""):
        m = _COVER_STAT.search(text)
        if not m:
            continue
        unit = m.group(3).strip().lower()
        value = m.group(2).replace("-", "−") + ("×" if unit in ("x", "×") else unit)
        nxt = [w.strip(".,;:)") for w in text[m.end():].split()[:2]]
        caption = " ".join(w for w in nxt[:2] if _STAT_WORDS.match(w))
        if not caption:  # "compress frames 300×": the words just before the number
            before = [w.strip(".,;:(") for w in text[:m.start() + len(m.group(1))].split()[-2:]]
            caption = " ".join(before) if before and all(w.isalpha() for w in before) else "key number"
        return value, caption
    if rec.get("hf_upvotes"):
        return f'<small aria-hidden="true">▲</small>{int(rec["hf_upvotes"])}', "upvotes on Hugging Face"
    return "New", "added " + nice_date(rec.get("first_seen") or published(rec), with_year=False)


COVER_WORD = {"llms": "LLM", "generative-ai": "GEN AI", "computer-vision": "VISION", "audio-speech": "AUDIO",
              "alignment": "ALIGN", "reasoning-agents": "AGENTS", "ml-theory": "THEORY", "ai-science": "SCIENCE",
              "code-ai": "CODE", "safety-privacy": "SAFETY", "efficient-ai": "EFF AI", "multimodal": "MULTI", "other-ml": "ML"}



_CODE_LINK = re.compile(r"https?://(?:www\.)?(?:github\.com|gitlab\.com)/[\w.\-]+/[\w.\-]+", re.I)


def code_link(rec: dict) -> str:
    """The paper's code: the saved link, else a GitHub or GitLab link written in the abstract."""
    if rec.get("code_url"):
        return rec["code_url"]
    m = _CODE_LINK.search(rec.get("abstract") or "")
    return m.group(0).rstrip(".,;)") if m else ""


def _fmt_count(n: int) -> str:
    return f"{n / 1000:.1f}".rstrip("0").rstrip(".") + "k" if n >= 1000 else str(n)


def glance_tiles(rec: dict, notes: dict, links: dict) -> str:
    """Four boxes of the same size: upvotes, difficulty, reading time, code."""
    tiles = []
    up = int(rec.get("hf_upvotes") or 0)
    tiles.append((f"▲ {up}", "upvotes on Hugging Face", "") if up else ("—", "not on Hugging Face yet", "na"))
    level = notes.get("difficulty")
    if level in LEVELS:
        tiles.append((esc(level.capitalize()), esc(notes.get("difficulty_reason") or "to use or reproduce"), ""))
    else:
        tiles.append((str(len(rec.get("authors") or [])), "authors", ""))
    tiles.append((f"{pick_minutes(rec)} min", "to read this page", ""))
    if rec.get("code_url"):
        stars = links.get("stars")
        tiles.append((f"★ {_fmt_count(stars)}" if stars else "Code", "stars on GitHub" if stars else "released", ""))
    else:
        tiles.append(("—", "no code released yet", "na"))
    return "".join(f'<div class="{c}"><b>{v}</b><span>{k}</span></div>' for v, k, c in tiles)


def lineage_html(s2: dict, papers: dict, rec: dict) -> str:
    """Builds on → this paper → built on by, from Semantic Scholar's citation data."""
    if not s2 or not s2.get("found"):
        return ""

    def item(r):
        aid = r.get("arxiv")
        href = f"{esc(aid)}.html" if aid and aid in papers else (f"https://arxiv.org/abs/{esc(aid)}" if aid else "")
        meta = " · ".join(x for x in (str(r.get("year") or ""), f'{_fmt_count(r.get("cites") or 0)} citations') if x)
        inner = f'{esc(r["title"])}<small>{meta}</small>'
        if not href:
            return f'<div class="lin-item">{inner}</div>'
        rel = "" if aid in papers else ' rel="noopener"'
        return f'<a class="lin-item" href="{href}"{rel}>{inner}</a>'
    refs = "".join(item(r) for r in s2.get("refs") or [])
    if not refs:
        refs = '<div class="lin-empty">Semantic Scholar has no reference list for it yet.</div>'
    cites = "".join(item(r) for r in s2.get("cites") or [])
    n = int(s2.get("cited_by") or 0)
    if not cites:
        cites = '<div class="lin-empty">No papers cite it yet. We check again every week.</div>'
    more = ""
    if n:
        closely = f", {int(s2['influential'])} of them closely" if s2.get("influential") else ""
        more = f" <small>{n} papers cite it{closely}</small>"
    topic = (rec.get("categories") or ["other-ml"])[0]
    return f"""<section class="np-sec" id="fits"><h2>Where it fits <small>The most cited papers it builds on, and the papers that build on it</small></h2>
  <div class="lin t-{esc(topic)}">
    <div class="lin-col"><span class="label">Builds on</span>{refs}</div>
    <div class="lin-arrow" aria-hidden="true">→</div>
    <div class="lin-col"><span class="label">This paper</span><div class="lin-item here">{esc(rec["title"])}<small>{esc(nice_date(published(rec)))}</small></div></div>
    <div class="lin-arrow" aria-hidden="true">→</div>
    <div class="lin-col"><span class="label">Built on by{more}</span>{cites}</div>
  </div>
  <p class="np-note">From <a href="https://www.semanticscholar.org/arxiv/{esc(rec["id"])}" rel="noopener">Semantic Scholar</a>, updated weekly.</p></section>"""


def try_it_html(rec: dict, links: dict) -> str:
    """Code, models, demos and datasets that use the paper, as four boxes of the same size."""
    hf = links.get("hf")
    if not hf and not rec.get("code_url"):
        return ""
    tiles = []
    if rec.get("code_url"):
        stars = links.get("stars")
        tiles.append(("on", "Code", (f"★ {_fmt_count(stars)} on GitHub" if stars else "Released by the authors"),
                      esc(rec["code_url"]), "code"))
    else:
        tiles.append(("off", "No code yet", "Not released by the authors", "", ""))
    labels = {"models": ("model", "models", "https://huggingface.co/"), "spaces": ("demo", "demos", "https://huggingface.co/spaces/"),
              "datasets": ("dataset", "datasets", "https://huggingface.co/datasets/")}
    for kind in ("models", "spaces", "datasets"):
        if not hf:
            continue
        one, many, base = labels[kind]
        info = hf.get(kind) or {}
        n = int(info.get("n") or 0)
        top = (info.get("top") or [{}])[0].get("id")
        if n and top:
            tiles.append(("on", f"{n} {one if n == 1 else many}", esc(top), base + esc(top), "hf"))
        else:
            tiles.append(("off", f"0 {many}", "on Hugging Face", "", ""))
    html_tiles = "".join(
        (f'<a class="try-tile" href="{href}" rel="noopener" data-out="{out}"><b>{title}</b><span>{sub}</span></a>' if href
         else f'<div class="try-tile off"><b>{title}</b><span>{sub}</span></div>')
        for _, title, sub, href, out in tiles)
    return (f'<section class="np-sec" id="try"><h2>Try it <small>Code, models and demos that use this paper</small></h2>'
            f'<div class="try">{html_tiles}</div></section>')


def lab_of(rec: dict, links: dict | None = None) -> str:
    """The lab or company behind a paper: saved with the record, found later by paper_links, or the code's owner."""
    lab = (rec.get("org") or (links or {}).get("org")
           or labs.from_code_url(rec.get("code_url") or code_link(rec) or "") or "")
    lab = labs.canonical(lab) or lab  # names saved before an alias was added still get their logo
    return SAME_LAB.get(lab, lab)


def same_lab_names(groups: dict[str, list[str]], counts: dict[str, int]) -> dict[str, str]:
    """
    {other name: shown name} for names that are one organization. The shown name is the one the site
    already knows (labs.LABS), else a written-out name over a handle ("ucas"), else the one with the
    most papers, else the shortest.
    """
    out = {}
    for names in groups.values():
        names = [n for n in names if counts.get(n)]
        if len(names) < 2:
            continue
        shown = max(names, key=lambda n: (n in labs.LABS, " " in n and n != n.lower(), counts[n], -len(n), n))
        out.update({n: shown for n in names if n != shown})
    return out


def lab_mark(lab: str, root: str = "../") -> str:
    """The lab's square mark: its official logo when we have one, else an outline logo or its initials on its brand colour."""
    if LOGOS.get(lab):
        return (f'<span class="org-mark has-img" aria-hidden="true"><img src="{root}assets/logos/{esc(LOGOS[lab])}" '
                f'alt="" width="40" height="40" loading="lazy" decoding="async"></span>')
    logo, colour = labs.brand(lab)
    style = f' style="--lab:#{colour};--lab-ink:#{labs.ink_on(colour)}"' if colour else ""
    if logo:
        inner = f'<svg viewBox="0 0 24 24"><use href="{root}assets/labs.svg?v={ASSET_V}#lab-{logo}"></use></svg>'
    else:
        mark = labs.initials(lab)
        inner = f'<span class="lm-{min(len(mark), 4)}">{esc(mark)}</span>'
    return f'<span class="org-mark{" has-logo" if logo else ""}"{style} aria-hidden="true">{inner}</span>'


def on_this_page(rec: dict, notes: dict, sections: str) -> str:
    """The sticky contents bar on a paper page, with a thin bar that fills as you read.
    It lists only the sections this page really has."""
    items = [("minute", "Curator's notes" if notes.get("tldr") else "In short"), ("numbers", "Key numbers"),
             ("abstract", "Abstract"), ("full", "Full paper"), ("build", "What you could build"),
             ("fits", "Where it fits"), ("try", "Try it"), ("ask-sec", "Ask this paper")]
    items = [(k, v) for k, v in items if f'class="np-sec" id="{k}"' in sections]
    links = "".join(f'<a href="#{k}">{esc(v)}</a>' for k, v in items)
    return (f'<nav class="np-otp" aria-label="On this page" data-otp><div class="np-otp-in">'
            f'<b>On this page</b>{links}<span class="np-otp-time">{pick_minutes(rec)} min read</span></div>'
            f'<div class="np-otp-bar" data-otp-bar></div></nav>')


def paper_markdown(rec: dict, links: dict | None = None) -> str:
    """The paper page as plain Markdown, for "Copy for LLM" and "View as Markdown"."""
    if not rec.get("code_url") and code_link(rec):
        rec = dict(rec, code_url=code_link(rec))
    links = links or {}
    notes = rec.get("curator") or {}
    abstract = tidy_tex(rec.get("abstract") or "")
    one = lambda t: " ".join(str(t).split())
    out = [f"# {one(rec['title'])}", ""]
    meta = []
    if rec.get("authors"):
        meta.append(f"**Authors:** {', '.join(rec['authors'])}")
    facts = []
    lab = lab_of(rec, links)
    if lab:
        facts.append(f"**Lab:** {lab}")
    if published(rec):
        facts.append(f"**Published:** {nice_date(published(rec))}")
    if rec.get("hf_upvotes"):
        facts.append(f"**Upvotes:** {int(rec['hf_upvotes'])}")
    if notes.get("difficulty") in LEVELS:
        facts.append(f"**Level:** {notes['difficulty'].capitalize()}")
    if facts:
        meta.append(" · ".join(facts))
    arxiv = rec.get("url") or "https://arxiv.org/abs/" + rec["id"]
    refs = [f"[arXiv]({arxiv})"]
    if rec.get("pdf_url"):
        refs.append(f"[PDF]({rec['pdf_url']})")
    if rec.get("code_url"):
        refs.append(f"[Code]({rec['code_url']})")
    refs.append(f"[This page]({SITE_URL}paper/{rec['id']}.html)")
    meta.append("**Links:** " + " · ".join(refs))
    out += ["  \n".join(meta), ""]
    short = notes.get("tldr") or (rec.get("summary") or {}).get("text")
    if short:
        out += ["## Curator's notes" if notes.get("tldr") else "## In short", "", f"**TL;DR:** {one(short)}", ""]
        rows = [("What's new", notes.get("whats_new")), ("Key result", notes.get("key_result")),
                ("Why it matters", notes.get("why_it_matters"))]
        rows = [f"- **{k}:** {one(v)}" for k, v in rows if v]
        if rows:
            out += rows + [""]
    numbers = key_numbers(rec.get("abstract") or "")
    if numbers:
        out += ["## Key numbers", ""] + [f"- **{n['value']}**: {one(n['context'])}" for n in numbers] + [""]
    if abstract:
        out += ["## Abstract", "", one(abstract), ""]
    if notes.get("build_ideas"):
        out += ["## What you could build", ""] + [f"{i + 1}. {one(x)}" for i, x in enumerate(notes["build_ideas"])] + [""]
    if notes.get("check_question"):
        out += ["## Quiz yourself", "", one(notes["check_question"])]
        if notes.get("check_answer"):
            out += ["", f"**Answer:** {one(notes['check_answer'])}"]
        out.append("")
    out += ["---", "", "Notes written by AI from the paper, numbers copied from the abstract. "
            "Check the paper before you rely on them. From AI Papers Daily.", ""]
    return "\n".join(out)


def dot_date(iso: str) -> str:
    """2026-11-05 → 2026.11.05, the way the paper page writes dates."""
    return (iso or "")[:10].replace("-", ".")


def rd_title_size(title: str) -> str:
    """Long titles get a smaller size so the opening screen stays one screen."""
    n = len(title or "")
    return "rd-len-xl" if n > 140 else "rd-len-l" if n > 90 else ""


def rd_row(label: str, value: str, cls: str = "") -> str:
    """One line of the paper details table: a label on the left, the value on the right."""
    if not value:
        return ""
    klass = f' class="{cls}"' if cls else ""
    return f'<div{klass}><dt>{esc(label)}</dt><dd>{value}</dd></div>'


def rd_resources(rec: dict, links: dict) -> str:
    """Code, models, demos and datasets that use the paper, as rows of the details table.
    Only what really exists is listed, and with nothing to try there is no section at all."""
    hf = links.get("hf") or {}
    rows = []
    if rec.get("code_url"):
        stars = links.get("stars")
        label = f"★ {_fmt_count(stars)} on GitHub" if stars else "Released by the authors"
        rows.append(rd_row("Code:", f'<a class="rd-chip" href="{esc(rec["code_url"])}" rel="noopener" data-out="code">{label} ↗</a>'))
    labels = {"models": ("Models:", "model", "models", "https://huggingface.co/"),
              "spaces": ("Demos:", "demo", "demos", "https://huggingface.co/spaces/"),
              "datasets": ("Datasets:", "dataset", "datasets", "https://huggingface.co/datasets/")}
    for kind in ("models", "spaces", "datasets"):
        label, one, many, base = labels[kind]
        info = hf.get(kind) or {}
        n = int(info.get("n") or 0)
        top = (info.get("top") or [{}])[0].get("id")
        if n and top:
            rows.append(rd_row(label, f'<a class="rd-chip" href="{base}{esc(top)}" rel="noopener" data-out="hf">{esc(top)} ↗</a>'
                               f'<span class="rd-none">{n} {one if n == 1 else many} on Hugging Face</span>'))
    if not rows:
        return ""
    return (f'<section class="rd-sec" id="try"><h2>Try it</h2><p class="rd-src">Code, models and demos that use this paper.</p>'
            f'<dl class="rd-md">{"".join(rows)}</dl></section>')


def rd_fits(s2: dict, papers: dict, rec: dict) -> str:
    """Where it fits, as plain ruled rows: what the paper builds on, then what builds on it."""
    if not s2 or not s2.get("found"):
        return ""

    def row(r):
        aid = r.get("arxiv")
        here = bool(aid and aid in papers)
        href = f"{esc(aid)}.html" if here else (f"https://arxiv.org/abs/{esc(aid)}" if aid else "")
        cites = int(r.get("cites") or 0)
        meta = (f'<span class="rd-fit-y">{esc(str(r.get("year") or "—"))}</span>'
                f'<span class="rd-fit-c">{_fmt_count(cites)} cited</span>')
        title = f'<span class="rd-fit-h">{esc(r["title"])}{"" if here or not href else " ↗"}</span>'
        if not href:
            return f'<li><div class="rd-fit-row">{meta}{title}</div></li>'
        rel = "" if here else ' rel="noopener"'
        return f'<li><a class="rd-fit-row" href="{href}"{rel}>{meta}{title}</a></li>'

    refs = s2.get("refs") or []
    cites = s2.get("cites") or []
    n = int(s2.get("cited_by") or 0)
    closely = f", {int(s2['influential'])} closely" if n and s2.get("influential") else ""
    refs_html = (f'<ol class="rd-fit">{"".join(row(r) for r in refs)}</ol>' if refs
                 else '<p class="rd-fit-none">Semantic Scholar has no reference list for it yet.</p>')
    cites_html = (f'<ol class="rd-fit">{"".join(row(r) for r in cites)}</ol>' if cites
                  else '<p class="rd-fit-none">No papers cite it yet. We check again every week.</p>')
    return f"""<section class="rd-sec" id="fits"><h2>Where it fits</h2>
      <p class="rd-src">The most cited papers it builds on, and the papers that build on it.</p>
      <p class="rd-lbl">/ Builds on <span>{len(refs)} most cited</span></p>
      {refs_html}
      <p class="rd-lbl rd-lbl-gap">/ Built on by <span>{f"{n} paper{'' if n == 1 else 's'} cite it{closely}" if n else "None yet"}</span></p>
      {cites_html}
      <p class="rd-src rd-fit-src">From <a href="https://www.semanticscholar.org/arxiv/{esc(rec["id"])}" rel="noopener">Semantic Scholar</a>, updated weekly.</p>
    </section>"""


def build_paper(rec: dict, related: list[dict] = (), prev: dict = None, nxt: dict = None,
                next_pick: dict = None, day_picks: list[str] = (), has_image: bool = False,
                links: dict | None = None, papers: dict | None = None) -> str:
    """
    The paper page, laid out for reading: the title opens large across the page, then shrinks into a
    sticky column of paper details while the summary, numbers and abstract read down the right.
    """
    if not rec.get("code_url") and code_link(rec):
        rec = dict(rec, code_url=code_link(rec))
    notes = rec.get("curator") or {}
    links = links or {}
    summary = (rec.get("summary") or {}).get("text")
    abstract = rec.get("abstract") or ""
    terms = notes.get("terms") or []
    topic = (rec.get("categories") or ["other-ml"])[0]
    title = esc(rec["title"])
    pid = esc(rec["id"])
    size_cls = rd_title_size(rec["title"])

    # --- The opening screen: where the paper sits on the site, then the title at full size ---
    kicker = ['<a href="../papers.html">All papers</a>',
              f'<a class="rd-topic" href="../papers.html?cat={esc(topic)}">{esc(category_name(topic))}</a>']
    # "Top pick on <day>" already says it was picked; the badge stays only for other slots like Trending
    if rec.get("featured") and not (rec.get("featured_on") and rec.get("slot") in (None, "pick")):
        kicker.append(f'<span class="rd-badge">{"" if rec.get("slot") == "trending" else "★ "}{esc(slot_label(rec))}</span>')
    if rec.get("featured_on"):
        kicker.append(f'<a href="../day/{esc(rec["featured_on"])}.html">Top pick on {esc(nice_date(rec["featured_on"], with_year=False))}</a>')
    if is_older(rec):
        kicker.append(f'<span>Trending since {esc(nice_date(rec["first_seen"], with_year=False))}</span>')
    hero_lab = lab_of(rec, links)
    if hero_lab:
        kicker.append(f'<a class="rd-kicker-lab" href="{esc(lab_href(hero_lab, "../"))}">{lab_mark(hero_lab)}{esc(hero_lab)}</a>')
    hero = f"""<header class="rd-hero">
    <p class="rd-kicker">{'<span aria-hidden="true">/</span>'.join(kicker)}</p>
    <h1 class="rd-big {size_cls}" data-rd-big>{title}</h1>
  </header>"""

    # --- Paper details: the sticky column on the left ---
    authors = rec.get("authors") or []
    chips = "".join(f'<span class="rd-chip">{esc(a)}</span>' for a in authors[:3])
    if len(authors) > 3:
        chips += (f'<details class="rd-more"><summary class="rd-chip">+{len(authors) - 3} more</summary>'
                  f'<span>{esc(", ".join(authors[3:]))}</span></details>')
    lab = lab_of(rec, links)
    # The lab leads the details, set larger, so who did the work is the first thing read
    lab_lead = (f'<p class="rd-labhead">{lab_mark(lab)}<span><small>Research from</small>'
                f'<a class="org-name" href="{esc(lab_href(lab, "../"))}" title="More papers from {esc(lab)}">{esc(lab)}</a></span></p>') if lab else ""
    pub = published(rec)
    added = rec.get("first_seen") or pub
    when = f'<time datetime="{esc(pub)}">{esc(dot_date(pub))}</time>'
    when += f'<span class="rd-sub">· {pick_minutes(rec)} min read</span>'
    if added and added != pub:
        # Shown only when it was added today or yesterday, by the reader's calendar
        when += f'<span class="rd-sub" data-added="{esc(added)}" hidden>· added <time datetime="{esc(added)}">{esc(dot_date(added))}</time></span>'
    topics = "".join(f'<a class="rd-chip{" rd-chip-t" if i == 0 else ""}" href="../papers.html?cat={esc(c)}">{esc(category_name(c))}</a>'
                     for i, c in enumerate((rec.get("categories") or ["other-ml"])[:3]))
    signals = []
    if notes.get("difficulty") in LEVELS:
        signals.append(level_meter(notes["difficulty"]))
    if rec.get("hf_upvotes"):
        signals.append(f'<a href="https://huggingface.co/papers/{pid}" rel="noopener" data-out="hf">▲ {int(rec["hf_upvotes"])} on Hugging Face</a>')
    code_pill = (f'<a class="rd-pill" href="{esc(rec["code_url"])}" rel="noopener" data-out="code">{icon("code", 15)}Code</a>'
                 if rec.get("code_url") else "")
    details = f"""<section class="rd-details" aria-label="Paper details">
      <p class="rd-lbl">/ Paper details</p>
      {lab_lead}
      <dl class="rd-md">
        {rd_row("Published:", when)}
        {rd_row("Authors:", chips)}
        {rd_row("Topics:", topics)}
        {rd_row("Signals:", '<span class="rd-dot" aria-hidden="true">·</span>'.join(signals))}
      </dl>
      <div class="rd-actions"><a class="rd-pill rd-pill-solid" href="{esc(rec.get('pdf_url'))}" rel="noopener" data-out="pdf">Read the PDF {icon("external", 14)}</a>
          {'<button class="rd-pill rd-pill-explain" type="button" data-explain>' + icon("ask", 15) + '<span>Explain this paper</span></button>' if abstract else ""}
          <button class="rd-pill" type="button" data-save aria-pressed="false">{icon("bookmark", 15)}<span>Save</span></button>
          <a class="rd-pill" href="{esc(rec.get('url'))}" rel="noopener" data-out="arxiv">arXiv</a>{code_pill}
          <button class="rd-pill" type="button" data-md-copy data-md="{pid}.md">{icon("copy", 15)}<span>Copy for LLM</span></button>
          <a class="rd-pill" href="{pid}.md" data-md-view>{icon("file", 15)}<span>Markdown</span></a>
          <details class="cite rd-cite">
            <summary class="rd-pill">{icon("quote", 15)}<span>BibTeX</span></summary>
            <div class="cite-box"><pre data-bibtex>{esc(bibtex(rec))}</pre><button class="btn btn-primary btn-sm" type="button" data-copy-bibtex>Copy BibTeX</button></div>
          </details>
          <button class="rd-pill" type="button" data-share>{icon("share", 15)}<span>Share</span></button></div>
    </section>"""

    # --- In short: the summary is the opening paragraph ---
    used_terms: set = set()
    short = notes.get("tldr") or summary
    levels = ""
    if notes.get("tldr") and (notes.get("tldr_simple") or notes.get("tldr_expert")):
        opts = [("simple", "New to this", notes.get("tldr_simple")), ("standard", "Practitioner", notes["tldr"]),
                ("expert", "Researcher", notes.get("tldr_expert"))]
        levels = ('<div class="rd-levels" role="group" aria-label="How deep to explain it" data-levels>' + "".join(
            f'<button type="button" data-level="{k}" aria-pressed="{"true" if k == "standard" else "false"}">{label}</button>'
            for k, label, text in opts if text) + "</div>")
        level_texts = "".join(f'<template data-level-text="{k}">{with_terms(esc(text), terms, set())}</template>'
                              for k, _, text in opts if text)
    else:
        level_texts = ""
    if short:
        tldr_html = with_terms(esc(short), terms, used_terms)
        src = "Written by AI from the paper" if notes.get("tldr") else "Written by AI from the abstract"
    else:
        tldr_html = ""
        src = ""
    rows = [("What's new", notes.get("whats_new")), ("Key result", notes.get("key_result")),
            ("Why it matters", notes.get("why_it_matters") if notes.get("tldr") else None)]
    rows = [r for r in rows if r[1]]
    parts = "".join(f'<h3>{k}</h3><p>{with_terms(esc(v), terms, used_terms)}</p>' for k, v in rows)
    checked = ""
    if notes.get("tldr"):
        nums = re.findall(r"\d[\d,.]*\d|\d", " ".join(str(r[1]) for r in rows) + " " + notes["tldr"])
        if nums:
            plain = tidy_tex(abstract).replace(",", "")
            ok = sum(1 for x in nums if x.replace(",", "") in plain)
            checked = ('<span class="rd-ok">Every number here appears in the abstract</span>' if ok == len(nums)
                       else f'<span>{ok} of {len(nums)} numbers here appear in the abstract</span>')
    heading = "Curator's notes" if notes.get("tldr") else "In short"
    minute = f"""<section class="rd-sec rd-first" id="minute" data-bd-short-box{"" if short else " hidden"}><h2 class="sr-only">{heading}</h2>
      {levels}<p class="rd-lede" data-bd-short-text data-level-out>{tldr_html}</p>{level_texts}
      <p class="rd-src rd-src-ai"><span class="rd-tag">{heading}</span><span data-bd-short-src>{src}</span>{checked}<a href="https://github.com/Omen-bit/ai-paper-daily/issues/new?title=Mistake%20on%20{pid}" rel="noopener">Report a mistake</a></p>
      {parts}
    </section>"""

    numbers = key_numbers(abstract)
    numbers_html = ""
    if numbers:
        numbers_html = (f'<section class="rd-sec" id="numbers"><h2>Key numbers</h2>'
                        f'<div class="rd-nums rd-nums-{len(numbers)}">' + "".join(
                            f'<div><b>{esc(n["value"])}</b><span>{esc(n["context"])}</span></div>' for n in numbers)
                        + '</div><p class="rd-src rd-src-paper"><span class="rd-tag">From the paper</span>Copied from the abstract, not written by AI.</p></section>')

    abstract_sec = ""
    if abstract:
        abstract_sec = f"""<section class="rd-sec" id="abstract"><h2>Abstract</h2>
      <p class="rd-src rd-src-paper"><span class="rd-tag">From the paper</span>The authors' own words.</p>
      <div class="np-abs rd-abs prose" data-prose>{abstract_html(abstract, [t for t in terms if t["term"].lower() not in used_terms])}</div>
    </section>"""

    want_summary = "" if short else ' data-summary="1"'
    full = f"""<section class="rd-sec" id="full" data-layer><h2>From the full paper</h2>
      <p class="rd-src rd-src-paper"><span class="rd-tag">From the paper</span>Copied from the paper itself by our code.</p>
      <div class="bd np-bd rd-bd" data-breakdown="{pid}" data-url="{BREAKDOWN_URL}"{want_summary}>
        <p class="bd-note" data-bd-note>Reading the paper on arXiv…</p>
        <button class="rd-pill" type="button" data-bd-load hidden>Read the full breakdown</button>
        <div class="bd-out" data-bd-out aria-live="polite"></div>
      </div>
    </section>""" if abstract else ""

    ideas_html = ""
    if notes.get("build_ideas"):
        reason = notes.get("difficulty_reason")
        level = level_meter(notes.get("difficulty"))
        ideas_html = (f'<section class="rd-sec" id="build"><h2>What you could build</h2>'
                      f'<p class="rd-src rd-src-ai"><span class="rd-tag">Written by AI</span>{level}{esc(reason) if reason else ""}</p>'
                      f'<ol class="rd-ideas">' + "".join(f'<li>{esc(x)}</li>' for x in notes["build_ideas"]) + "</ol></section>")

    fits = rd_fits(links.get("s2"), papers or {}, rec)

    ask_html = ""
    if abstract:
        chips_q = "".join(f'<button class="qchip" type="button" data-ask-suggest>{q}</button>' for q in ASK_SUGGESTIONS)
        quiz = ""
        if notes.get("check_question"):
            answer = notes.get("check_answer")
            answer_html = (f'<p class="check-a" data-check-answer hidden>{esc(answer)}</p>'
                           f'<button class="rd-pill" type="button" data-check-show>Show the answer</button>') if answer else ""
            quiz = f'<div class="rd-quiz"><p class="rd-lbl">/ Quiz yourself</p><p class="check-q">{esc(notes["check_question"])}</p>{answer_html}</div>'
        ask_html = f"""<section class="rd-sec" id="ask-sec"><h2>Ask this paper</h2>
      <div class="ask np-ask rd-ask" id="ask" data-ask data-url="{ASK_URL}">
        <p class="rd-ask-head"><span>/ Ask a question</span><span>Answers come from the full paper and name the section</span></p>
        <ol class="ask-log" data-ask-log aria-live="polite"></ol>
        <form class="ask-form" data-ask-form>
          <label class="sr-only" for="ask-q">Your question about this paper</label>
          <input class="input" id="ask-q" maxlength="300" autocomplete="off" placeholder="Ask anything about it">
          <button class="rd-pill rd-pill-solid" type="submit">Ask</button>
        </form>
        <div class="ask-suggest">{chips_q}</div>
        <p class="field-error" data-ask-error role="alert" hidden></p>
        {quiz}
      </div>
    </section>"""

    ask_jump = (f'<button class="rd-askbar" type="button" data-ask-jump aria-controls="ask">{icon("ask", 16)}'
                f'<span>Ask this paper a question</span><kbd>A</kbd></button>') if abstract else ""
    sections = "\n    ".join(x for x in (minute, numbers_html, ranking_pages.why_ranked(rec), abstract_sec, full, ideas_html, fits,
                                         rd_resources(rec, links), ask_html) if x)

    done = ""
    if next_pick:
        done = (f'<a class="rd-next" href="{esc(next_pick["id"])}.html"><span class="rd-lbl">/ Next pick</span>'
                f'<span class="rd-next-h">{esc(next_pick["title"])}</span></a>')
    related_html = ""
    if related:
        related_html = (f'<section class="rd-related" aria-labelledby="rd-rel-h"><p class="rd-lbl" id="rd-rel-h">/ Read next, same idea</p>'
                        f'<div class="cards rd-rel-cards">{"".join(related_card(r) for r in related[:4])}</div></section>')

    body = f"""<div class="rd t-{esc(topic)}">
  {hero}
  <article class="paper rd-cols" data-paper-id="{pid}" data-title="{title}" data-topics="{esc(' '.join(rec.get('categories') or ['other-ml']))}">
    <aside class="rd-side"><div class="rd-stick" data-rd-stick>
      <p class="rd-small {size_cls}" data-rd-small aria-hidden="true">{title}</p>
      {ask_jump}
      {details}
    </div></aside>
    <div class="rd-main">
      <p class="rd-lbl rd-lbl-main">/ Paper <span>arXiv {pid}</span></p>
      {sections}
      <div class="rd-notes" data-notes><p class="rd-lbl">/ Your notes</p>
        <p class="rd-note" data-notes-empty>Select text in the abstract to highlight it or add a note. They stay in this browser.</p>
        <ol class="note-list" data-notes-list></ol></div>
      {done}
    </div>
  </article>
  {related_html}
  {subscribe_box("../")}
</div>
<div class="np-mbar">
  <a class="btn btn-primary" href="{esc(rec.get('pdf_url'))}" rel="noopener" data-out="pdf">Read the PDF {icon("external", 14)}</a>
  {'<button class="btn btn-outline" type="button" data-ask-open aria-controls="ask">Ask</button>' if abstract else ""}
  <button class="btn btn-outline btn-icon" type="button" data-save aria-pressed="false" aria-label="Save this paper">{icon("bookmark", 16)}<span class="sr-only">Save</span></button>
</div>"""
    desc = notes.get("tldr") or summary or abstract[:160]
    return page(rec["title"], body, root="../", description=desc, path=f"paper/{rec['id']}.html", body_class="rd-page",
                image=f"og/{rec['id']}.png" if has_image else "og/site.png", og_type="article")


def related_card(rec: dict) -> str:
    """The All papers card, server-rendered with the same parts as the one app.js draws:
    topic and badge, cover number, lab and authors, title, summary, signals, dates and Save."""
    topic = (rec.get("categories") or ["other-ml"])[0]
    notes = rec.get("curator") or {}
    stat, cap = cover_stat(rec)
    pid = esc(rec["id"])
    badge = ""
    if rec.get("featured"):
        badge = ('<span class="pc-badge pc-badge-hot">Trending</span>' if rec.get("slot") == "trending"
                 else '<span class="pc-badge pc-badge-pick">★ Our pick</span>')
    authors = rec.get("authors") or []
    by = ", ".join(esc(a) for a in authors[:2]) + (f" +{len(authors) - 2}" if len(authors) > 2 else "")
    lab = lab_of(rec)
    lab_html = (f'{lab_mark(lab)}<a class="org-name" href="{esc(lab_href(lab, "../"))}" title="More papers from {esc(lab)}">{esc(lab)}</a>'
                + ('<span class="by-sep">·</span>' if by else "")) if lab else ""
    chips = ""
    if rec.get("hf_upvotes") and "upvotes" not in cap:
        chips += f'<span class="sig sig-up" title="Upvotes on Hugging Face">▲ {int(rec["hf_upvotes"])}</span>'
    if rec.get("code_url") or code_link(rec):
        chips += '<span class="sig">Code</span>'
    if notes.get("difficulty") in LEVELS:
        chips += f'<span class="sig">{esc(notes["difficulty"].capitalize())}</span>'
    for t in (rec.get("categories") or [])[1:3]:
        chips += (f'<a class="sig sig-topic t-{esc(t)}" href="../papers.html?cat={esc(t)}"><span class="dot"></span>'
                  f'{esc(category_name(t))}</a>')
    pub = published(rec)
    added = (rec.get("first_seen") or "")[:10]
    added_pill = (f'<span class="date-pill is-added"><span class="dp-k">Added</span><time datetime="{esc(added)}">'
                  f'{esc(nice_date(added, with_year=False))}</time></span>') if added and added != pub else ""
    summary = notes.get("tldr") or lead_sentence(tidy_tex(rec.get("abstract") or ""))
    return f"""<article class="pcard t-{esc(topic)}" data-id="{pid}">
  <div class="pc-cover"><div class="pc-cover-top"><a class="pc-topic" href="../papers.html?cat={esc(topic)}"><span class="dot"></span>{esc(category_name(topic))}</a>{badge}</div>
    <div class="pc-word" aria-hidden="true">{esc(COVER_WORD.get(topic, "ML"))}</div>
    <div class="pc-stat"><b>{stat}</b><span>{esc(cap)}</span></div></div>
  <div class="pc-body"><p class="pcard-by">{lab_html}<span class="by-auth">{by}</span></p>
    <h3 title="{esc(rec["title"])}"><a href="../paper/{pid}.html">{esc(rec["title"])}</a></h3>
    <p class="pcard-sum">{esc(summary)}</p>
    <div class="pcard-tags">{chips}</div>
    <div class="pcard-foot"><p class="pcard-dates"><span class="date-pill is-pub"><span class="dp-k">Published</span><time datetime="{esc(pub)}">{esc(nice_date(pub, with_year=False))}</time></span>{added_pill}</p>
      <button class="quick-save" type="button" data-quick-save="{pid}" data-title="{esc(rec["title"])}" aria-pressed="false" aria-label="Save this paper">+</button></div>
  </div>
</article>"""


def build_saved_page() -> str:
    body = """<section class="page-head">
  <h1>Your reading list</h1>
  <p>Papers you save are kept in this browser, so no account is needed. They stay here until you remove them.</p>
</section>
<ul class="list" data-saved-list></ul>
<div class="empty" data-saved-empty hidden><strong>Nothing saved yet.</strong>Press Save on any paper or case study to keep it here for later.
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


def compact(rec: dict, links: dict | None = None) -> dict:
    """
    The fields papers.html needs, with short keys to keep the file small:
    i id, t title, a first authors, n author count, c topics, d published (arXiv) date,
    w the day we added it, s score,
    f 1 our pick / 2 trending, m one-line summary, u HF upvotes, k has code,
    h 1 when the paper is not on Hugging Face, l difficulty (b/i/a), o lab or company.
    """
    notes = rec.get("curator") or {}
    out = {
        "i": rec["id"],
        "t": rec["title"],
        "a": rec.get("authors", [])[:3],
        "n": len(rec.get("authors", [])),
        "c": rec.get("categories") or ["other-ml"],
        "d": published(rec),
        "w": (rec.get("first_seen") or published(rec))[:10],
        "ac": ((rec.get("arxiv_categories") or [""])[0] or ""),
        "s": rec.get("score") or 0,
        "f": (2 if rec.get("slot") == "trending" else 1) if rec.get("featured") else 0,
        "m": notes.get("tldr") or lead_sentence(rec.get("abstract") or ""),
        "u": int(rec.get("hf_upvotes") or 0),
    }
    if rec.get("code_url"):
        out["k"] = 1
    if not out["u"] and rec.get("source") == "arXiv":
        out["h"] = 1
    if notes.get("difficulty") in LEVELS:
        out["l"] = notes["difficulty"][0]
    lab = lab_of(rec, links)
    if lab:
        out["o"] = lab
        if LOGOS.get(lab):
            out["oi"] = LOGOS[lab]
        logo, colour = labs.brand(lab)
        if logo:
            out["ol"] = logo
        if colour:
            out["oc"] = colour + ("" if labs.ink_on(colour) == "fff" else "/1a1a1a")
    return out


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _making_of_head() -> str:
    """The favicon and visit counting for "How I built AI Papers Daily", which has its own page layout."""
    head = f'\n<link rel="icon" href="{FAVICON}">'
    if UMAMI_WEBSITE_ID:  # this page has no app.js, so Umami counts the visit itself
        head += (f'\n<script defer src="https://cloud.umami.is/script.js" data-website-id="{UMAMI_WEBSITE_ID}"></script>')
    return head


def copy_weekly_figures(data_dir: str, site_dir: str) -> int:
    """Figures for The Weekly Express email (weekly_edition.py) live in data/weekly/<week>/
    and are served from site/weekly/<week>/, so images in past emails keep working."""
    weekly = os.path.join(data_dir, "weekly")
    copied = 0
    if not os.path.isdir(weekly):
        return 0
    for week in sorted(os.listdir(weekly)):
        src = os.path.join(weekly, week)
        if not os.path.isdir(src):
            continue
        for name in os.listdir(src):
            if name.lower().endswith((".jpg", ".jpeg", ".png")):
                os.makedirs(os.path.join(site_dir, "weekly", week), exist_ok=True)
                shutil.copy2(os.path.join(src, name), os.path.join(site_dir, "weekly", week, name))
                copied += 1
    return copied


def build_site(data_dir: str = DATA_DIR, site_dir: str = SITE_DIR, export_dir: str = EXPORT_DIR) -> int:
    """Rebuild site_dir from scratch. Returns the number of paper pages written."""
    global EDITION, LOGOS, LOGO_DEV_CREDIT, SAME_LAB
    days = load_days(data_dir)
    papers = merge_papers(days)
    EDITION = ticker(days)

    if os.path.isdir(site_dir):
        shutil.rmtree(site_dir)
    shutil.copytree(ASSETS_DIR, os.path.join(site_dir, "assets"))
    logo_index = os.path.join(data_dir, "logos", "index.json")
    LOGOS = lab_logos.index(logo_index)
    SAME_LAB = {}
    links = load_links(data_dir)
    counts: dict[str, int] = {}
    for rec in papers.values():
        name = lab_of(rec, links.get(rec["id"]))
        if name:
            counts[name] = counts.get(name, 0) + 1
    SAME_LAB = same_lab_names(lab_logos.same_org(logo_index), counts)
    for other, shown in SAME_LAB.items():
        if other in LOGOS and shown not in LOGOS:
            LOGOS[shown] = LOGOS[other]  # the shown name borrows the other name's logo
    if SAME_LAB:
        print(f"  [site] One lab, two names: {', '.join(f'{o} -> {s}' for o, s in sorted(SAME_LAB.items()))}")
    LOGO_DEV_CREDIT = any((e or {}).get("source") == "Logo.dev" and lab in LOGOS
                          for lab, e in lab_logos.load_index(logo_index).items())
    if LOGOS:
        os.makedirs(os.path.join(site_dir, "assets", "logos"), exist_ok=True)
        for file in set(LOGOS.values()):
            shutil.copy2(os.path.join(data_dir, "logos", file), os.path.join(site_dir, "assets", "logos", file))

    copy_weekly_figures(data_dir, site_dir)

    archive = load_archive(export_dir)
    rows, source = trends.trend_rows(archive, papers)
    global SHOW_TRENDS
    SHOW_TRENDS = trends_ready(rows)
    if not SHOW_TRENDS:
        print("  [site] Trends hidden: it needs 3 months of papers and only the site's own papers are here. "
              "For a local build, run: python src/supabase_sync.py --export-only")
    _write(os.path.join(site_dir, "index.html"), build_index(days, papers, load_most_read(export_dir), rows))
    _write(os.path.join(site_dir, "trends.html"), build_trends_page(rows, source, len(archive) or len(papers), set(papers),
                                                                       case_studies.load(os.path.join(data_dir, "cases.json"))))
    _write(os.path.join(site_dir, "papers.html"), build_papers_page())
    _write(os.path.join(site_dir, "archive.html"), build_archive(days, papers))
    _write(os.path.join(site_dir, "saved.html"), build_saved_page())
    _write(os.path.join(site_dir, "subscribed.html"), build_subscribed_page())

    # Previous and next paper follow the order of the day the paper first appeared
    neighbours: dict[str, tuple] = {}
    for day in days:
        try:
            _write(os.path.join(site_dir, "day", f"{day['date']}.html"), build_day(day, papers))
        except Exception as exc:  # one bad day page must not stop the edition
            print(f"  [site] WARNING: day page {day.get('date')} failed: {exc}")
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

    # Preview images for links shared on X, LinkedIn, Reddit, WhatsApp and the rest
    try:
        with_image = discovery.build_share_images(papers, category_name, os.path.join(site_dir, "og"))
    except Exception as exc:  # pages fall back to no preview image
        print(f"  [site] WARNING: share images failed: {exc}")
        with_image = set()

    related = related_papers(papers)
    _write(os.path.join(site_dir, "labs.html"), build_labs_page(papers, links))
    case_paths: list[str] = []
    try:  # engineering write-ups from company blogs; the rest of the site never waits on them
        case_paths = case_pages.build_all(case_studies.load(os.path.join(data_dir, "cases.json")), papers,
                                          page, _write, site_dir, os.path.join(data_dir, "case_logos"),
                                          SITE_URL, THEME_SCRIPT, _making_of_head())
    except Exception as exc:
        print(f"  [site] WARNING: case study pages failed: {exc}")
    # Scout draws case study covers like the Case studies page, so it is built after them (they save the logos)
    posts = case_studies.load(os.path.join(data_dir, "cases.json"))
    try:
        _write(os.path.join(site_dir, "data", "case-brands.svg"), brand_sprite_file(posts))
        brands = scout_brands(posts)
    except Exception as exc:  # Scout falls back to initials on brand colours
        print(f"  [site] WARNING: Scout case logos failed: {exc}")
        brands = ""
    _write(os.path.join(site_dir, "scout.html"), build_scout_page(brands, len(posts)))
    failed = 0
    for rec in papers.values():
        prev_id, next_id = neighbours.get(rec["id"], (None, None))
        try:
            html_out = build_paper(rec, [papers[i] for i in related.get(rec["id"], [])],
                                   papers.get(prev_id), papers.get(next_id),
                                   papers.get(next_pick.get(rec["id"])), picks_of.get(rec["id"], []),
                                   has_image=rec["id"] in with_image, links=links.get(rec["id"]) or {}, papers=papers)
            _write(os.path.join(site_dir, "paper", f"{rec['id']}.html"), html_out)
            _write(os.path.join(site_dir, "paper", f"{rec['id']}.md"), paper_markdown(rec, links.get(rec["id"]) or {}))
        except Exception as exc:  # one bad record must not stop the other pages
            failed += 1
            print(f"  [site] WARNING: paper page {rec.get('id')} failed: {exc}")
    if failed:
        print(f"  [site] WARNING: {failed} paper page(s) were skipped. The rest of the site is fine.")

    # RSS feed of the picks, and a sitemap of every public page for search engines
    try:
        _write(os.path.join(site_dir, "feed.xml"), discovery.build_feed(papers, SITE_URL, SITE_NAME, TAGLINE))
    except Exception as exc:  # readers keep yesterday's feed items; the site still publishes
        print(f"  [site] WARNING: RSS feed failed: {exc}")
    # How ranking works, with the newest day's scores to download
    latest = next((d for d in days if any(ranking_pages.has_breakdown(r) for r in d.get("papers") or [])), None)
    js, csv_text = ranking_pages.score_exports(latest)
    if js:
        _write(os.path.join(site_dir, "data", "scores-latest.json"), js)
        _write(os.path.join(site_dir, "data", "scores-latest.csv"), csv_text)
    board = None
    try:
        with open(os.path.join(data_dir, "scoreboard.json"), encoding="utf-8") as f:
            board = json.load(f)
    except (OSError, ValueError):
        pass
    _write(os.path.join(site_dir, "methodology.html"),
           page("How papers are ranked", ranking_pages.methodology_body(board, latest["date"] if js else ""),
                description="How AI Papers Daily ranks papers: a published formula over GitHub, Hugging Face, "
                            "Hacker News and Semantic Scholar numbers, checked against citations 30 days later.",
                path="methodology.html"))

    newest = days[0]["date"] if days else ""
    pages = [("", newest), ("papers.html", newest), ("methodology.html", newest), ("scout.html", ""), ("archive.html", newest), ("labs.html", newest)]
    if SHOW_TRENDS:
        pages.append(("trends.html", newest))
    pages += [(p, newest) for p in case_paths]
    pages += [(f"day/{d['date']}.html", d["date"]) for d in days]
    pages += [(f"paper/{r['id']}.html", r.get("featured_on") or r.get("first_seen") or "")
              for r in sorted(papers.values(), key=lambda r: r.get("first_seen") or "", reverse=True)]
    _write(os.path.join(site_dir, "sitemap.xml"), discovery.build_sitemap(SITE_URL, pages))

    # Papers with a page here, plus the rest of the database's year (linking to Hugging Face)
    listing = [compact(r, links.get(r["id"])) for r in papers.values()]
    listing += [archive_compact(r) for r in archive if r["id"] not in papers]
    # Newest batch first; inside a day, papers people are upvoting lead, then our score
    listing.sort(key=lambda p: (p["w"], p["u"], p["s"], p["d"]), reverse=True)
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
