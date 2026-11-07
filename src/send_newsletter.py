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
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime
from email.utils import parsedate_to_datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "src"))

try:
    from classifier import CATEGORIES
    CATEGORY_NAMES = {slug: name for _, name, slug, _, _ in CATEGORIES}
except Exception:  # the email must not fail over a label
    CATEGORY_NAMES = {}

DATA_DIR = os.path.join(ROOT_DIR, "data", "daily")
SITE_DIR = os.path.join(ROOT_DIR, "site")
FEED_PATH = os.path.join(SITE_DIR, "feed.xml")
MARKER_DIR = os.path.join(ROOT_DIR, "data", "newsletter")
CASES_PATH = os.path.join(ROOT_DIR, "data", "cases.json")
MAX_CASES = 3  # case studies shown in the email on days new ones came in
API_URL = "https://api.buttondown.com/v1/emails"
SITE_NAME = "AI Papers Daily"
SITE_URL = (os.environ.get("SITE_URL") or "https://omen-bit.github.io/ai-paper-daily/").rstrip("/") + "/"
MORE_PAPERS = 0  # other new papers listed (titles only) under the picks; 0 = picks only

# Brand colours, the same as the site's.
INK = "#0e0e10"
ORANGE = "#ff4f00"
PAPER = "#f2f0eb"
MUTED = "#5f5e5a"
LINE = "#e4e1da"
SOFT = "#faf8f4"
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

def header(day: str, scanned: int, n_picks: int) -> str:
    d = date.fromisoformat(day)
    short_day = f"{d:%a}, {d.day} {d:%b}"
    count = f"{scanned:,} new papers read." if scanned else "Today's new papers, read for you."
    worth = "1 worth your time." if n_picks == 1 else f"{n_picks} worth your time."
    return (
        '<tr><td style="padding:24px 28px 4px 28px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td style="width:30px;vertical-align:middle;">{logo()}</td>'
        f'<td style="vertical-align:middle;padding-left:10px;font-family:{FONT};font-size:15px;font-weight:800;'
        f'color:{INK};"><a href="{SITE_URL}?ref=email" style="color:{INK};text-decoration:none;">{SITE_NAME}</a></td>'
        f'<td align="right" style="vertical-align:middle;font-family:{FONT};font-size:12px;color:{MUTED};'
        f'white-space:nowrap;">{esc(short_day)}</td></tr></table>'
        f'<p style="margin:18px 0 0 0;font-family:{FONT};font-size:15px;line-height:22px;color:{MUTED};">'
        f'{esc(count)} <strong style="color:{INK};">{esc(worth)}</strong></p>'
        '</td></tr>'
    )


def pick_card(p: dict) -> str:
    """One pick in five lines: tag, title, what it is, why it matters, link."""
    notes = p.get("curator") or {}
    url = paper_url(p["id"])
    slot = "Trending" if p.get("slot") == "trending" else "Top pick"
    cats = (p.get("categories") or [])[:1]
    tag = (f'<span style="color:{ORANGE if slot == "Top pick" else INK};">{esc(slot)}</span>'
           + (f'<span style="color:{MUTED};"> &nbsp;·&nbsp; {esc(category_label(cats[0]))}</span>' if cats else ""))
    tldr = clip(notes.get("tldr") or (p.get("summary") or {}).get("text") or p.get("abstract"), 200)
    why = clip(notes.get("why_it_matters"), 160)
    why_html = (f'<p style="margin:8px 0 0 0;font-family:{FONT};font-size:14px;line-height:21px;color:{MUTED};">'
                f'<strong style="color:{INK};">Why it matters:</strong> {esc(why)}</p>') if why else ""
    extras = ""
    if p.get("code_url"):
        extras = (f' &nbsp;<a href="{esc(p["code_url"])}" style="font-family:{FONT};font-size:14px;color:{MUTED};'
                  'text-decoration:underline;">Code</a>')
    return (
        f'<tr><td style="padding:20px 28px 0 28px;">'
        f'<div style="padding:18px 0 0 0;border-top:1px solid {LINE};">'
        f'<p style="margin:0 0 6px 0;font-family:{FONT};font-size:11px;font-weight:700;letter-spacing:.08em;'
        f'text-transform:uppercase;">{tag}</p>'
        f'<p style="margin:0 0 8px 0;font-family:{FONT};font-size:19px;line-height:26px;font-weight:800;'
        f'letter-spacing:-.01em;"><a href="{esc(url)}" style="color:{INK};text-decoration:none;">'
        f'{esc(p.get("title"))}</a></p>'
        f'<p style="margin:0;font-family:{FONT};font-size:16px;line-height:24px;color:{INK};">{esc(tldr)}</p>'
        f'{why_html}'
        f'<p style="margin:12px 0 0 0;"><a href="{esc(url)}" style="font-family:{FONT};font-size:14px;'
        f'font-weight:700;color:{ORANGE};text-decoration:none;">Read the breakdown →</a>{extras}</p>'
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
        f'<p style="margin:6px 0 0 0;"><a href="{SITE_URL}?ref=email" style="font-family:{FONT};font-size:14px;'
        f'font-weight:700;color:{ORANGE};text-decoration:none;">See all of today’s papers →</a></p>'
        '</div></td></tr>'
    )


def new_case_studies(day: str, path: str = CASES_PATH, limit: int = MAX_CASES) -> list[dict]:
    """The case studies added on this day, newest first. Most days there are none."""
    try:
        with open(path, encoding="utf-8") as f:
            posts = json.load(f).get("posts", [])
    except (OSError, ValueError):
        return []
    fresh = [p for p in posts if p.get("added") == day and str(p.get("url", "")).startswith("https://") and p.get("title")]
    fresh.sort(key=lambda p: p.get("published") or "", reverse=True)
    return fresh[:limit]


def case_studies(posts: list[dict]) -> str:
    """New write-ups from company engineering blogs: company, title and our one line about it."""
    if not posts:
        return ""
    items = ""
    for p in posts:
        summary = (f'<p style="margin:4px 0 0 0;font-family:{FONT};font-size:14px;line-height:21px;color:{MUTED};">'
                   f'{esc(clip(p.get("summary"), 180))}</p>') if p.get("summary") else ""
        items += (f'<div style="padding:0 0 14px 0;">'
                  f'<p style="margin:0 0 2px 0;font-family:{FONT};font-size:13px;font-weight:700;color:{MUTED};">{esc(p.get("company"))}</p>'
                  f'<p style="margin:0;font-family:{FONT};font-size:16px;line-height:23px;font-weight:700;">'
                  f'<a href="{esc(p["url"])}" style="color:{INK};text-decoration:none;">{esc(clip(p.get("title"), 140))}</a></p>'
                  f'{summary}</div>')
    return (
        '<tr><td style="padding:24px 28px 0 28px;">'
        f'<div style="padding:18px 0 0 0;border-top:1px solid {LINE};">'
        f'<p style="margin:0 0 12px 0;font-family:{FONT};font-size:11px;font-weight:700;letter-spacing:.08em;'
        f'text-transform:uppercase;color:{MUTED};">From company blogs</p>'
        f'{items}'
        f'<p style="margin:0;"><a href="{SITE_URL}case-studies/index.html?ref=email" style="font-family:{FONT};font-size:14px;'
        f'font-weight:700;color:{ORANGE};text-decoration:none;">See all case studies →</a></p>'
        '</div></td></tr>'
    )


def footer() -> str:
    return (
        '<tr><td style="padding:24px 28px 26px 28px;">'
        f'<p style="margin:0;padding-top:16px;border-top:1px solid {LINE};font-family:{FONT};font-size:12px;'
        f'line-height:18px;color:{MUTED};"><a href="{SITE_URL}?ref=email" style="color:{INK};font-weight:600;">'
        f'See all of today’s papers</a> &nbsp;·&nbsp; You get this because you subscribed at {SITE_NAME}.</p>'
        '</td></tr>'
    )


def wrap(rows: str, preheader: str) -> str:
    # Everything on one line with no indentation: Buttondown reads the body as
    # Markdown, where indented or blank-line-separated HTML can be mangled.
    hidden = (f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">'
              f'{esc(preheader)}{"&#847;&zwnj;&nbsp;" * 30}</div>')
    return (
        hidden
        + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{PAPER};">'
        '<tr><td align="center" style="padding:16px 8px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="max-width:600px;background:{SOFT};border-radius:14px;border-collapse:separate;">'
        f'{rows}'
        '</table></td></tr></table>'
    )


# ---------------------------------------------------------------------------
# Building and sending the email
# ---------------------------------------------------------------------------

def build_email_from_edition(edition: dict, day: str, cases: list[dict] | None = None) -> dict | None:
    picks, rest = split_edition(edition)
    if not picks:
        return None
    rows = header(day, edition.get("scanned") or 0, len(picks))
    for p in picks:
        rows += pick_card(p)
    rows += more_papers(rest)
    rows += case_studies(new_case_studies(day) if cases is None else cases)
    rows += footer()

    names = [short_title(p.get("title", "")) for p in picks]
    subject = names[0] if len(names) == 1 else f"{names[0]} · plus {len(names) - 1} more pick{'s' if len(names) > 2 else ''}"
    preheader = (picks[0].get("curator") or {}).get("tldr") or (picks[0].get("summary") or {}).get("text") or ""
    return {"subject": subject, "body": wrap(rows, clip(preheader, 140))}


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
