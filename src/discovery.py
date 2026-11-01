"""
discovery.py
The files that help people find the site and come back to it:
  feed.xml       RSS feed of the daily picks (feed readers, and email via Buttondown)
  sitemap.xml    every public page, for Google and Bing
  og/<id>.png    the preview image shown when a paper page is shared
  og/site.png    the preview image for every other page
Called by site_builder.build_site().
"""
import os
import re
from functools import lru_cache
from datetime import date, datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape as xml_escape

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(SRC_DIR, "share_fonts")

FEED_ITEMS = 30  # newest picks kept in feed.xml
SHARE_IMAGE_DAYS = 3  # papers first seen in the last 3 days get their own preview image (plus every pick)


def absolute(site_url: str, path: str) -> str:
    """'https://x.io/site/' + 'paper/1.html' -> 'https://x.io/site/paper/1.html'."""
    return site_url.rstrip("/") + "/" + path.lstrip("/")


def _day(iso: str) -> datetime:
    """A date as 07:00 IST (01:30 UTC), when the edition comes out."""
    d = date.fromisoformat(str(iso)[:10])
    return datetime(d.year, d.month, d.day, 1, 30, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# RSS
# ---------------------------------------------------------------------------

def feed_entries(papers: dict) -> list[dict]:
    """Every featured paper, newest pick first."""
    picks = [p for p in papers.values() if p.get("featured") and p.get("featured_on")]
    picks.sort(key=lambda p: (p["featured_on"], p.get("slot") != "trending"), reverse=True)
    return picks[:FEED_ITEMS]


def _summary(rec: dict) -> str:
    notes = rec.get("curator") or {}
    return (notes.get("tldr") or (rec.get("summary") or {}).get("text")
            or (rec.get("abstract") or "")[:300]).strip()


def build_feed(papers: dict, site_url: str, site_name: str, tagline: str) -> str:
    items = []
    for rec in feed_entries(papers):
        link = absolute(site_url, f"paper/{rec['id']}.html?ref=rss")
        notes = rec.get("curator") or {}
        parts = [f"<p>{xml_escape(_summary(rec))}</p>"]
        if notes.get("why_it_matters"):
            parts.append(f"<p><strong>Why it matters:</strong> {xml_escape(notes['why_it_matters'])}</p>")
        parts.append(f'<p><a href="{xml_escape(link)}">Read the plain-language breakdown, or ask the paper a question</a></p>')
        label = "Trending" if rec.get("slot") == "trending" else "Top pick"
        items.append(f"""    <item>
      <title>{xml_escape(f"{label}: {rec['title']}")}</title>
      <link>{xml_escape(link)}</link>
      <guid isPermaLink="false">ai-papers-daily-{xml_escape(rec['id'])}</guid>
      <pubDate>{format_datetime(_day(rec['featured_on']))}</pubDate>
      <description><![CDATA[{"".join(parts).replace("]]>", "]]&gt;")}]]></description>
    </item>""")
    built = format_datetime(_day(feed_entries(papers)[0]["featured_on"])) if items else format_datetime(datetime.now(timezone.utc))
    return f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{xml_escape(site_name)}</title>
    <link>{xml_escape(absolute(site_url, ""))}</link>
    <atom:link href="{xml_escape(absolute(site_url, "feed.xml"))}" rel="self" type="application/rss+xml"/>
    <description>{xml_escape(tagline)}</description>
    <language>en</language>
    <lastBuildDate>{built}</lastBuildDate>
{chr(10).join(items)}
  </channel>
</rss>
"""


# ---------------------------------------------------------------------------
# Sitemap
# ---------------------------------------------------------------------------

def build_sitemap(site_url: str, pages: list[tuple[str, str]]) -> str:
    """pages: (path, last-modified ISO date or "")."""
    rows = []
    for path, lastmod in pages:
        mod = f"<lastmod>{xml_escape(lastmod[:10])}</lastmod>" if lastmod else ""
        rows.append(f"  <url><loc>{xml_escape(absolute(site_url, path))}</loc>{mod}</url>")
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(rows) + "\n</urlset>\n")


# ---------------------------------------------------------------------------
# Share images (1200 x 630, the size X, LinkedIn, Reddit and WhatsApp expect)
# ---------------------------------------------------------------------------

W, H = 1200, 630
PAD = 72
INK, PAPER, MUTED, ACCENT = (14, 14, 16), (242, 240, 235), (155, 153, 161), (255, 79, 0)


@lru_cache(maxsize=None)
def _font(path: str, size: int, weight: int | None):
    from PIL import ImageFont
    f = ImageFont.truetype(path, size)
    if weight:
        try:
            f.set_variation_by_axes([weight])
        except (OSError, AttributeError):
            pass  # an older FreeType: stay at the default weight
    return f


def _fonts():
    sans = os.path.join(FONT_DIR, "geist.ttf")
    pixel = os.path.join(FONT_DIR, "geist-pixel-square.ttf")

    def make(path, size, weight=None):
        return _font(path, size, weight)
    return make, sans, pixel


def _supported(text: str, font) -> str:
    """Drop characters the font has no glyph for, so nothing prints as a box."""
    out = []
    for ch in text:
        if ch.isspace() or ch.isascii():
            out.append(ch)
            continue
        try:
            mask = font.getmask(ch)
            out.append(ch if mask.getbbox() else "")
        except Exception:
            out.append("")
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _wrap(draw, text: str, font, width: int, max_lines: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            line = trial
            continue
        if line:
            lines.append(line)
        line = word
        if len(lines) == max_lines:
            break
    if line and len(lines) < max_lines:
        lines.append(line)
    if len(lines) == max_lines and " ".join(lines) != " ".join(words):
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > width:
            last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
        lines[-1] = last.rstrip(",.;:") + "…"
    return lines


def _brand(draw, make, pixel):
    # The logo: four squares, two orange and two light, as in the site header
    s, x, y = 18, PAD, PAD
    draw.rectangle([x, y, x + s, y + s], fill=ACCENT)
    draw.rectangle([x + s, y + s, x + 2 * s, y + 2 * s], fill=ACCENT)
    draw.rectangle([x + s, y, x + 2 * s, y + s], fill=PAPER)
    draw.rectangle([x, y + s, x + s, y + 2 * s], fill=PAPER)
    font = make(pixel, 30)
    draw.text((x + 2 * s + 18, y + s), "AI PAPERS", font=font, fill=PAPER, anchor="lm")
    w = draw.textlength("AI PAPERS", font=font)
    draw.text((x + 2 * s + 18 + w, y + s), "/DAILY", font=font, fill=ACCENT, anchor="lm")


def _card(kicker: str, title: str, footer: str, path: str) -> None:
    from PIL import Image, ImageDraw
    make, sans, pixel = _fonts()
    img = Image.new("RGB", (W, H), INK)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, H - 10, W, H], fill=ACCENT)
    _brand(draw, make, pixel)

    small = make(sans, 26, 500)
    draw.text((PAD, 190), kicker.upper(), font=small, fill=ACCENT)

    # Largest title size that fits in four lines
    for size in (64, 58, 52, 46):
        big = make(sans, size, 650)
        title_text = _supported(title, big)
        lines = _wrap(draw, title_text, big, W - 2 * PAD, 4)
        if len(lines) <= 3 or size == 46:
            break
    y = 236
    for line in lines:
        draw.text((PAD, y), line, font=big, fill=PAPER)
        y += int(size * 1.18)

    draw.text((PAD, H - PAD - 10), _supported(footer, small), font=small, fill=MUTED, anchor="ls")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # A few flat colours only, so a palette PNG is about a third of the size
    img.quantize(colors=32, method=Image.Quantize.FASTOCTREE).save(path, "PNG")


def paper_card(rec: dict, topic: str, path: str) -> None:
    kicker = "Top pick" if rec.get("featured") and rec.get("slot") != "trending" else topic
    if rec.get("slot") == "trending":
        kicker = "Trending paper"
    _card(kicker, rec["title"], "Plain-language breakdown  ·  Ask this paper  ·  Free", path)


def site_card(path: str) -> None:
    _card("Free for AI builders", "The best new AI paper each day, explained so you can build with it.",
          "Daily picks  ·  Ask any paper  ·  Project Scout", path)


def wants_image(rec: dict, newest: str) -> bool:
    """Every pick, and any paper first seen in the last SHARE_IMAGE_DAYS days.
    Older papers share og/site.png, which keeps the daily build fast."""
    if rec.get("featured"):
        return True
    try:
        age = (date.fromisoformat(newest[:10]) - date.fromisoformat(str(rec.get("first_seen"))[:10])).days
    except ValueError:
        return False
    return age < SHARE_IMAGE_DAYS


def build_share_images(papers: dict, topic_name, out_dir: str) -> set[str]:
    """Write og/site.png and og/<id>.png. Returns the IDs that got an image.
    Without Pillow the site still builds, just without preview images."""
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("  [share] Pillow is not installed, so pages get no preview image")
        return set()
    done = set()
    site_card(os.path.join(out_dir, "site.png"))
    newest = max((str(r.get("first_seen") or "") for r in papers.values()), default="")
    for rec in papers.values():
        if not wants_image(rec, newest):
            continue
        topic = topic_name((rec.get("categories") or ["other-ml"])[0])
        try:
            paper_card(rec, topic, os.path.join(out_dir, f"{rec['id']}.png"))
            done.add(rec["id"])
        except Exception as e:  # one bad title must not stop the build
            print(f"  [share] No image for {rec['id']}: {e}")
    return done
