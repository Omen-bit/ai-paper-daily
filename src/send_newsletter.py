"""Send today's edition as an email through Buttondown's API (free plan).

Buttondown's RSS-to-email is a paid add-on, but its email API is free. After
the site is built, this reads today's edition from data/daily/<date>.json and
sends one short email with just the day's top pick and trending pick. If that file is missing it falls back to
the items in site/feed.xml. A marker file in data/newsletter/ makes sure each
day is sent only once, even if the workflow is run again by hand.

The email is plain HTML with inline styles and table layout, because that is
what email apps (Gmail, Outlook, Apple Mail) display reliably.

Environment:
  BUTTONDOWN_API_KEY   required; without it the script does nothing.
  BUTTONDOWN_SEND      "draft" to only create a draft (default: send now).
  SITE_URL             the site's address (default: the GitHub Pages one).

Preview without sending:  python src/send_newsletter.py --preview [YYYY-MM-DD]
"""
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "src"))

try:
    from classifier import CATEGORIES
    CATEGORY_NAMES = {slug: name for _, name, slug, _, _ in CATEGORIES}
except Exception:  # the email must not fail over a label
    CATEGORY_NAMES = {}

try:
    from case_studies import added_on as _site_added_on  # the site's rule for when a case study is new
except Exception:  # the email must not fail over case studies; a copy of the rule is below
    _site_added_on = None

DATA_DIR = os.path.join(ROOT_DIR, "data", "daily")
SITE_DIR = os.path.join(ROOT_DIR, "site")
FEED_PATH = os.path.join(SITE_DIR, "feed.xml")
MARKER_DIR = os.path.join(ROOT_DIR, "data", "newsletter")
CASES_PATH = os.path.join(ROOT_DIR, "data", "cases.json")
MAX_COMPANIES = 3  # companies named in the one-line case-study note before "and N more"
API_URL = "https://api.buttondown.com/v1/emails"
SITE_NAME = "AI Papers Daily"
SITE_URL = (os.environ.get("SITE_URL") or "https://omen-bit.github.io/ai-paper-daily/").rstrip("/") + "/"
MORE_PAPERS = 0  # other new papers listed (titles only) under the picks; 0 = picks only
SUBJECT_MAX = 60         # characters; longer subjects are cut at a whole word
KEY_RESULT_MAX = 170     # characters; a longer key result is left out rather than cut
CASES_SHOWN = 2          # case studies shown with their result in "AI at work"
CASE_NEW_FOR_DAYS = 14   # same as case_studies.NEW_FOR_DAYS
CASE_LOOKBACK_DAYS = 7   # never reach further back than a week for case studies
# Buttondown's "Classic" template adds only its footer (unsubscribe, manage, view online),
# so the email has no footer of its own. Its "Accent color" is forced onto every link,
# which is why link colours here are marked !important (see keep_link_colours).

# Brand colours, the same as the site's.
INK = "#0e0e10"
ORANGE = "#ff4f00"
PAPER = "#f2f0eb"
MUTED = "#5f5e5a"
LINE = "#e4e1da"
SOFT = "#faf8f4"
CARD = "#ffffff"
CHIP = "#f2f0eb"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


# ---------------------------------------------------------------------------
# Reading the edition
# ---------------------------------------------------------------------------

def load_edition(day: str, data_dir: str | None = None) -> dict | None:
    path = os.path.join(data_dir or DATA_DIR, f"{day}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def split_edition(edition: dict, more: int = MORE_PAPERS) -> tuple[list[dict], list[dict]]:
    """(the day's picks in order, the next best new papers)."""
    papers = edition.get("papers") or []
    by_id = {p.get("id"): p for p in papers}
    picks = [by_id[i] for i in edition.get("featured") or [] if i in by_id]
    pick_ids = {p["id"] for p in picks}
    rest = [p for p in papers if p.get("id") not in pick_ids]
    rest.sort(key=lambda p: (-(p.get("score") or 0), -(p.get("hf_upvotes") or 0)))
    return picks, rest[:more]


def todays_items(feed_xml: str, day: str) -> list[dict]:
    """Fallback: the feed items whose pubDate falls on `day` (YYYY-MM-DD, UTC)."""
    items = []
    for item in ET.fromstring(feed_xml).iter("item"):
        pub = item.findtext("pubDate") or ""
        try:
            pub_day = parsedate_to_datetime(pub).strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            continue
        if pub_day == day:
            items.append({
                "title": (item.findtext("title") or "").strip(),
                "link": (item.findtext("link") or "").strip(),
                "description": (item.findtext("description") or "").strip(),
            })
    return items


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def esc(text) -> str:
    return html.escape(str(text or ""), quote=True)


def paper_url(pid: str) -> str:
    return f"{SITE_URL}paper/{pid}.html?ref=email"


def short_title(title: str, limit: int = 60) -> str:
    """The part before a colon ('L3G-World: Real-Time ...' -> 'L3G-World'), trimmed."""
    head = title.split(":", 1)[0].strip() if ":" in title[:70] else title.strip()
    return head if len(head) <= limit else head[: limit - 1].rstrip() + "…"


def clip(text, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def category_label(slug: str) -> str:
    return CATEGORY_NAMES.get(slug) or slug.replace("-", " ").title()


def logo() -> str:
    """The site's four-pixel logo, drawn with table cells so it shows without images."""
    cell = '<td style="width:9px;height:9px;padding:0;font-size:0;line-height:0;background:{c};">&nbsp;</td>'
    return ('<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="border-collapse:separate;'
            f'background:{INK};border-radius:5px;"><tr><td style="padding:4px;">'
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;">'
            f'<tr>{cell.format(c=ORANGE)}{cell.format(c=PAPER)}</tr>'
            f'<tr>{cell.format(c=PAPER)}{cell.format(c=ORANGE)}</tr>'
            '</table></td></tr></table>')


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def header(day: str, new_papers: int, n_picks: int) -> str:
    """Logo, name and date on one line, then the day's promise in one bold line."""
    d = date.fromisoformat(day)
    short_day = f"{d:%a}, {d.day} {d:%b}"
    worth = "1 paper worth your time today" if n_picks == 1 else f"{n_picks} papers worth your time today"
    source = (f"Picked from {new_papers:,} new AI papers on arXiv and Hugging Face." if new_papers
              else "Picked from today's new AI papers on arXiv and Hugging Face.")
    return (
        '<tr><td style="padding:28px 28px 0 28px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td style="width:30px;vertical-align:middle;">{logo()}</td>'
        f'<td style="vertical-align:middle;padding-left:10px;font-family:{FONT};font-size:15px;font-weight:800;'
        f'color:{INK};"><a href="{SITE_URL}?ref=email" style="color:{INK};text-decoration:none;">{SITE_NAME}</a></td>'
        f'<td align="right" style="vertical-align:middle;font-family:{FONT};font-size:13px;color:{MUTED};'
        f'white-space:nowrap;">{esc(short_day)}</td></tr></table>'
        f'<p style="margin:22px 0 0 0;font-family:{FONT};font-size:24px;line-height:30px;font-weight:800;'
        f'letter-spacing:-.02em;color:{INK};">{esc(worth)}</p>'
        f'<p style="margin:6px 0 0 0;font-family:{FONT};font-size:14px;line-height:21px;color:{MUTED};">{esc(source)}</p>'
        '</td></tr>'
    )


def _org_name(name: str) -> str:
    """'agentic learning ai lab' -> 'Agentic Learning AI Lab'; names with capitals are kept as they are."""
    name = " ".join(str(name or "").split())
    if not name or name != name.lower():
        return name
    small = {"ai": "AI", "ml": "ML", "nlp": "NLP", "of": "of", "and": "and", "for": "for"}
    return " ".join(small.get(w, w.capitalize()) for w in name.split())


def byline(p: dict) -> str:
    """'Tsinghua University · 11 authors': who made it, in one muted line."""
    n = len(p.get("authors") or [])
    parts = [_org_name(p.get("org"))] if p.get("org") else []
    if n:
        parts.append("1 author" if n == 1 else f"{n} authors")
    return " · ".join(x for x in parts if x)


def proof(p: dict) -> list[str]:
    """Short public signs that people care: upvotes, Hacker News points, GitHub stars, code or not."""
    ev = p.get("evidence") or {}
    out = []
    upvotes = max(int(p.get("hf_upvotes") or 0), int(ev.get("upvotes") or 0))
    hn = int(ev.get("hn_points") or 0)
    stars = int(ev.get("stars") or 0)
    if upvotes:
        out.append(f"▲ {upvotes:,} upvote{'s' if upvotes != 1 else ''}" + ("" if hn or stars else " on Hugging Face"))
    if hn:
        out.append(f"{hn:,} points on Hacker News")
    if stars:
        out.append(f"★ {stars:,} GitHub stars")
    if not p.get("code_url"):
        out.append("No code yet")
    return out


def _chip(text: str) -> str:
    return (f'<span style="display:inline-block;margin:0 6px 6px 0;padding:3px 10px;border-radius:999px;'
            f'background:{CHIP};font-family:{FONT};font-size:13px;line-height:20px;color:{MUTED};'
            f'white-space:nowrap;">{esc(text)}</span>')


def _button(url: str, text: str) -> str:
    """A big orange button made from a table cell, which Outlook draws too."""
    return ('<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="display:inline-table;'
            f'vertical-align:middle;"><tr><td style="border-radius:8px;background:{ORANGE};">'
            f'<a href="{esc(url)}" style="display:inline-block;padding:11px 18px;font-family:{FONT};font-size:15px;'
            f'font-weight:700;line-height:20px;color:#ffffff;text-decoration:none;border-radius:8px;">{esc(text)}</a>'
            '</td></tr></table>')


def _small_link(url: str, text: str) -> str:
    return (f'<a href="{esc(url)}" style="font-family:{FONT};font-size:14px;font-weight:600;color:{INK};'
            f'text-decoration:underline;margin-left:16px;">{esc(text)}</a>')


def pick_card(p: dict) -> str:
    """One pick: tag, title, who made it, the plain summary, the key result, why it matters,
    proof, then one button to the breakdown with Code and Paper beside it."""
    notes = p.get("curator") or {}
    url = paper_url(p["id"])
    slot = "Trending" if p.get("slot") == "trending" else "Top pick"
    cats = (p.get("categories") or [])[:1]
    tag = (f'<span style="color:{ORANGE if slot == "Top pick" else INK};">{esc(slot)}</span>'
           + (f'<span style="color:{MUTED};"> &nbsp;·&nbsp; {esc(category_label(cats[0]))}</span>' if cats else ""))
    by = byline(p)
    by_html = (f'<p style="margin:6px 0 0 0;font-family:{FONT};font-size:13px;line-height:19px;color:{MUTED};">'
               f'{esc(by)}</p>') if by else ""
    # The plain version first: the email is read by people new to the topic too
    summary = clip(notes.get("tldr_simple") or notes.get("tldr") or (p.get("summary") or {}).get("text")
                   or p.get("abstract"), 220)
    key = " ".join(str(notes.get("key_result") or "").split())
    key_html = (f'<p style="margin:14px 0 0 0;padding:2px 0 2px 14px;border-left:3px solid {ORANGE};font-family:{FONT};'
                f'font-size:15px;line-height:23px;color:{INK};"><strong>Key result:</strong> {esc(key)}</p>'
                ) if key and len(key) <= KEY_RESULT_MAX else ""
    why = clip(notes.get("why_it_matters"), 170)
    why_html = (f'<p style="margin:12px 0 0 0;font-family:{FONT};font-size:15px;line-height:23px;color:{MUTED};">'
                f'<strong style="color:{INK};">Why it matters:</strong> {esc(why)}</p>') if why else ""
    chips = proof(p)
    chips_html = (f'<p style="margin:14px 0 0 0;">{"".join(_chip(c) for c in chips)}</p>') if chips else ""
    links = ""
    if p.get("code_url"):
        links += _small_link(p["code_url"], "Code")
    paper_link = p.get("url") or f"https://arxiv.org/abs/{p['id']}"
    links += _small_link(paper_link, "Paper")
    return (
        '<tr><td style="padding:24px 28px 0 28px;">'
        f'<div style="padding:24px 0 0 0;border-top:1px solid {LINE};">'
        f'<p style="margin:0 0 10px 0;font-family:{FONT};font-size:11px;font-weight:700;letter-spacing:.09em;'
        f'text-transform:uppercase;">{tag}</p>'
        f'<p style="margin:0;font-family:{FONT};font-size:21px;line-height:28px;font-weight:800;'
        f'letter-spacing:-.015em;"><a href="{esc(url)}" style="color:{INK};text-decoration:none;">'
        f'{esc(p.get("title"))}</a></p>'
        f'{by_html}'
        f'<p style="margin:14px 0 0 0;font-family:{FONT};font-size:16px;line-height:25px;color:{INK};">{esc(summary)}</p>'
        f'{key_html}{why_html}{chips_html}'
        f'<p style="margin:12px 0 0 0;">{_button(url, "Read the breakdown →")}{links}</p>'
        '</div></td></tr>'
    )


def more_papers(rest: list[dict]) -> str:
    """Titles only: a quick scan of what else came out."""
    if not rest:
        return ""
    items = "".join(
        f'<tr><td style="width:16px;vertical-align:top;font-family:{FONT};font-size:14px;line-height:22px;'
        f'color:{ORANGE};">•</td><td style="padding-bottom:6px;font-family:{FONT};font-size:14px;line-height:22px;">'
        f'<a href="{esc(paper_url(p["id"]))}" style="color:{INK};text-decoration:none;">'
        f'{esc(clip(p.get("title"), 140))}</a></td></tr>' for p in rest)
    return (
        '<tr><td style="padding:24px 28px 0 28px;">'
        f'<div style="padding:18px 0 0 0;border-top:1px solid {LINE};">'
        f'<p style="margin:0 0 10px 0;font-family:{FONT};font-size:11px;font-weight:700;letter-spacing:.08em;'
        f'text-transform:uppercase;color:{MUTED};">Also new today</p>'
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0">{items}</table>'
        '</div></td></tr>'
    )


# ---------------------------------------------------------------------------
# Case studies
# ---------------------------------------------------------------------------

def _added_on(post: dict) -> str:
    """When a case study counts as new on the site. The site's own rule (case_studies.added_on):
    a post that was already old when it was added (a back catalogue or a backfill) counts from
    its publish date, so it never shows up as new."""
    if _site_added_on:
        try:
            return _site_added_on(post)
        except Exception:
            pass
    added, published = str(post.get("added") or "")[:10], str(post.get("published") or "")[:10]
    if str(post.get("added_at") or ""):
        return str(post["added_at"])[:10]
    if not added or not published:
        return added or published
    try:
        late = (date.fromisoformat(added) - date.fromisoformat(published)).days > CASE_NEW_FOR_DAYS
    except ValueError:
        return added
    return published if late else max(added, published)


def last_email_day(day: str, marker_dir: str | None = None) -> str | None:
    """The newest day before `day` that an email went out for (from the send markers)."""
    try:
        names = os.listdir(marker_dir or MARKER_DIR)
    except OSError:
        return None
    days = sorted(n[:-5] for n in names if n.endswith(".json") and len(n) == 15 and n[:-5] < day)
    return days[-1] if days else None


def new_case_studies(day: str, path: str = CASES_PATH, since: str | None = None) -> list[dict]:
    """Case studies that became new on the site after the last email, up to `day`: posts added
    later in the day than that email went out are not lost. Only really new posts count.
    Newest first. Most days there are none."""
    try:
        with open(path, encoding="utf-8") as f:
            posts = json.load(f).get("posts", [])
    except (OSError, ValueError):
        return []
    if since is None:
        since = last_email_day(day) or (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    since = max(since, (date.fromisoformat(day) - timedelta(days=CASE_LOOKBACK_DAYS)).isoformat())
    fresh = [p for p in posts if since < _added_on(p) <= day
             and str(p.get("url", "")).startswith("https://") and p.get("title")]
    fresh.sort(key=lambda p: (_added_on(p), p.get("published") or ""), reverse=True)
    return fresh


def company_list(posts: list[dict], limit: int = MAX_COMPANIES) -> str:
    """'NVIDIA, Pinterest and Shopify' or 'NVIDIA, Pinterest, Shopify and 4 more', each company once."""
    names = list(dict.fromkeys(str(p.get("company") or "").strip() for p in posts if p.get("company")))
    if not names:
        return ""
    if len(names) > limit:
        return f"{', '.join(names[:limit])} and {len(names) - limit} more"
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def with_results(posts: list[dict], n: int = CASES_SHOWN) -> list[dict]:
    """The posts that report a measured result, at most one per company, up to n.
    How-to guides and product news rarely have one, so they are left out of the email."""
    out, seen = [], set()
    for p in posts:
        result = " ".join(str(p.get("result") or "").split())
        company = str(p.get("company") or "").strip()
        if not result or not company or company in seen:
            continue
        seen.add(company)
        out.append(p)
        if len(out) == n:
            break
    return out


def case_studies(posts: list[dict]) -> str:
    """'AI at work': up to two new case studies with a measured result (company, title, result),
    then a link to all of them. When none has a result, one line with the count instead."""
    if not posts:
        return ""
    n = len(posts)
    what = "1 new case study" if n == 1 else f"{n} new case studies"
    link = (f'<p style="margin:16px 0 0 0;"><a href="{SITE_URL}case-studies/index.html?ref=email" '
            f'style="font-family:{FONT};font-size:14px;font-weight:700;color:{ORANGE};text-decoration:none;">'
            f'See {"it" if n == 1 else f"all {n}"} →</a></p>')
    shown = with_results(posts)
    if shown:
        items = ""
        for p in shown:
            company = str(p.get("company") or "").strip()
            initial = esc(company[:1].upper())
            items += (
                '<tr><td style="width:36px;vertical-align:top;padding:14px 14px 0 0;">'
                f'<div style="width:36px;height:36px;line-height:36px;border-radius:8px;background:{CHIP};'
                f'text-align:center;font-family:{FONT};font-size:13px;font-weight:800;color:{INK};">{initial}</div></td>'
                '<td style="vertical-align:top;padding:14px 0 0 0;">'
                f'<p style="margin:0;font-family:{FONT};font-size:15px;line-height:22px;color:{INK};">'
                f'<strong>{esc(company)}</strong> · <a href="{esc(p["url"])}" style="color:{INK};text-decoration:none;">'
                f'{esc(clip(p.get("title"), 90))}</a></p>'
                f'<p style="margin:2px 0 0 0;font-family:{FONT};font-size:14px;line-height:21px;color:{MUTED};">'
                f'Result: <strong style="color:{INK};">{esc(clip(p.get("result"), 90))}</strong></p></td></tr>')
        body = f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{items}</table>'
    else:
        who = company_list(posts)
        body = (f'<p style="margin:0;font-family:{FONT};font-size:15px;line-height:22px;color:{MUTED};">'
                f'<strong style="color:{INK};">{what}</strong>{f" from {esc(who)}" if who else ""}.</p>')
    return (
        '<tr><td style="padding:26px 28px 0 28px;">'
        f'<div style="padding:24px 0 0 0;border-top:1px solid {LINE};">'
        f'<p style="margin:0;font-family:{FONT};font-size:11px;font-weight:700;letter-spacing:.09em;'
        f'text-transform:uppercase;"><span style="color:{INK};">AI at work</span>'
        f'<span style="color:{MUTED};"> &nbsp;·&nbsp; {esc(what)}</span></p>'
        f'{body}{link}</div></td></tr>'
    )


def browse_all(total: int) -> str:
    what = f"Browse all {total:,} ranked papers →" if total else "Browse all of today’s papers →"
    return (
        '<tr><td style="padding:26px 28px 0 28px;">'
        f'<p style="margin:0;padding:20px 0 24px 0;border-top:1px solid {LINE};font-family:{FONT};font-size:15px;'
        f'line-height:23px;color:{MUTED};">Not your topic today? <a href="{SITE_URL}?ref=email" '
        f'style="font-weight:700;color:{ORANGE};text-decoration:none;">{what}</a></p>'
        '</td></tr>'
    )


_LINK_STYLE = re.compile(r'(<a\s[^>]*?style="[^"]*?)(?<![-\w])color:\s*(#[0-9a-fA-F]{3,8})(?![0-9a-fA-F])(?!\s*!important)')
_LINK_LINE = re.compile(r'(<a\s[^>]*?style="[^"]*?)text-decoration:\s*(none|underline)\b(?!\s*!important)')


def keep_link_colours(html_text: str) -> str:
    """Buttondown's template paints every link in its accent colour, over the colours set here
    (titles would turn orange and the button's white text would vanish on orange).
    An inline !important beats any stylesheet, so each link keeps its own colour."""
    previous = None
    while previous != html_text:  # one colour per link tag each pass
        previous = html_text
        html_text = _LINK_STYLE.sub(r"\1color:\2 !important", html_text)
        html_text = _LINK_LINE.sub(r"\1text-decoration:\2 !important", html_text)
    return html_text


def wrap(rows: str, preheader: str) -> str:
    # Everything on one line with no indentation: Buttondown reads the body as
    # Markdown, where indented or blank-line-separated HTML can be mangled.
    # One white card on the brand's paper colour: no boxes inside boxes.
    hidden = (f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">'
              f'{esc(preheader)}{"&#847;&zwnj;&nbsp;" * 30}</div>')
    return keep_link_colours(
        hidden
        + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{PAPER};">'
        '<tr><td align="center" style="padding:16px 0 28px 0;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="max-width:600px;background:{CARD};border-radius:14px;border-collapse:separate;">'
        f'{rows}'
        '</table>'
        '</td></tr></table>'
    )


# ---------------------------------------------------------------------------
# Building and sending the email
# ---------------------------------------------------------------------------

def _cut(text: str, limit: int) -> str:
    """Cut at a whole word, never mid-word."""
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:·-–—") + "…"


def subject_line(picks: list[dict]) -> str:
    """The top pick's plain headline (written with its notes), else its short name or title,
    cut at a whole word. No "plus 1 more pick": the preview text names the second pick."""
    lead = picks[0]
    hook = ((lead.get("curator") or {}).get("headline") or "").strip()
    if hook:
        return _cut(hook, SUBJECT_MAX)
    return _cut(lead.get("title", ""), SUBJECT_MAX)


def preheader_text(picks: list[dict], new_papers: int) -> str:
    """The grey line after the subject in the inbox: the second pick, then the count."""
    n = len(picks)
    count = f"{n} pick{'s' if n != 1 else ''} from {new_papers:,} new papers." if new_papers else ""
    if n > 1:
        second = _cut(short_title(picks[1].get("title", ""), 70), 70)
        org = _org_name(picks[1].get("org"))
        return " ".join(x for x in [f"+ {second}{f' from {org}' if org else ''}.", count] if x)
    notes = picks[0].get("curator") or {}
    lead = notes.get("tldr_simple") or notes.get("tldr") or (picks[0].get("summary") or {}).get("text") or ""
    return " ".join(x for x in [clip(lead, 110), count] if x)


def new_paper_count(edition: dict) -> int:
    """Papers not seen in an earlier run (new_count), else everything the run read (older files)."""
    n = edition.get("new_count")
    return n if isinstance(n, int) and not isinstance(n, bool) else (edition.get("scanned") or 0)


def build_email_from_edition(edition: dict, day: str, cases: list[dict] | None = None) -> dict | None:
    picks, rest = split_edition(edition)
    if not picks:
        return None
    new_papers = new_paper_count(edition)
    rows = header(day, new_papers, len(picks))
    for p in picks:
        rows += pick_card(p)
    rows += more_papers(rest)
    rows += case_studies(new_case_studies(day) if cases is None else cases)
    rows += browse_all(len(edition.get("papers") or []))
    return {"subject": subject_line(picks), "body": wrap(rows, preheader_text(picks, new_papers))}


def build_email(items: list[dict], day: str) -> dict:
    """Fallback email from feed items, used only when the day's data file is missing."""
    d = date.fromisoformat(day)
    nice_day = f"{d:%A}, {d.day} {d:%B %Y}"
    lead = items[0]["title"].split(": ", 1)[-1] if items else ""
    subject = short_title(lead) if lead else f"{SITE_NAME}, {nice_day}"
    parts = [f"<p><em>{SITE_NAME} · {nice_day}</em></p>"]
    for it in items:
        link = it["link"].replace("ref=rss", "ref=email")
        parts.append(f'<h2><a href="{esc(link)}">{esc(it["title"])}</a></h2>')
        parts.append(it["description"].replace("ref=rss", "ref=email"))
    return {"subject": subject, "body": "\n".join(parts)}


def compose(day: str) -> dict | None:
    edition = load_edition(day)
    if edition:
        email = build_email_from_edition(edition, day)
        if email:
            return email
    if os.path.exists(FEED_PATH):
        with open(FEED_PATH, encoding="utf-8") as f:
            items = todays_items(f.read(), day)
        if items:
            return build_email(items, day)
    return None


def post_email(api_key: str, payload: dict) -> dict:
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json",
            # Required by Buttondown the first time a key sends for real.
            "X-Buttondown-Live-Dangerously": "true",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode() or "{}")


def preview(day: str, out: str = "preview.html") -> int:
    email = compose(day)
    if not email:
        print(f"No edition for {day}.")
        return 1
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"<!doctype html><html><head><meta charset='utf-8'>"
                f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{esc(email['subject'])}"
                f"</title></head><body style='margin:0;background:{PAPER}'>{email['body']}</body></html>")
    print(f"Wrote {out} (subject: {email['subject']})")
    return 0


def main(day: str | None = None) -> int:
    api_key = os.environ.get("BUTTONDOWN_API_KEY", "").strip()
    if not api_key:
        print("BUTTONDOWN_API_KEY is not set; skipping the email.")
        return 0
    day = day or datetime.now().strftime("%Y-%m-%d")
    marker = os.path.join(MARKER_DIR, f"{day}.json")
    if os.path.exists(marker):
        print(f"The email for {day} was already sent; skipping.")
        return 0
    try:
        import weekly_edition
        if weekly_edition.replaces_daily(day):
            print(f"{day} is a Sunday and The Weekly Express is ready; it replaces the daily email.")
            return 0
    except Exception as exc:  # never lose the daily email over the weekly check
        print(f"Weekly check failed ({exc}); sending the daily email.")
    email = compose(day)
    if not email:
        print(f"No edition for {day}; nothing to send.")
        return 0

    mode = "draft" if os.environ.get("BUTTONDOWN_SEND", "").strip().lower() == "draft" else "about_to_send"
    try:
        result = post_email(api_key, {**email, "status": mode})
    except urllib.error.HTTPError as e:
        print(f"Buttondown refused the email ({e.code}): {e.read().decode(errors='replace')}")
        return 1
    os.makedirs(MARKER_DIR, exist_ok=True)
    with open(marker, "w", encoding="utf-8") as f:
        json.dump({"id": result.get("id"), "subject": email["subject"], "status": mode}, f, indent=2)
    print(f"Buttondown email created ({mode}): {email['subject']}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--preview":
        sys.exit(preview(sys.argv[2] if len(sys.argv) > 2 else datetime.now().strftime("%Y-%m-%d")))
    sys.exit(main())
