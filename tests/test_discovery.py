"""
tests/test_discovery.py
The files that help people find the site: share images, RSS feed, sitemap,
canonical links and the subscribe box.
"""
import sys
import os
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import discovery
import site_builder
from paper_store import save_day
from site_builder import build_site

SITE = "https://omen-bit.github.io/ai-paper-daily/"


def _paper(pid, score=1.0, **extra):
    paper = {"id": pid, "title": f"Paper <{pid}> & friends", "authors": ["A", "B"], "abstract": "Abs.",
             "submitted": "2026-10-30", "categories": ["llms"], "score": score, "badges": []}
    paper.update(extra)
    return paper


def _build(tmp_path):
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    papers = [_paper("2610.1", 9), _paper("2610.2", 3)]
    save_day(papers, [dict(papers[0], why_it_matters="Fast.", summary_source="groq")],
             "2026-10-31", data_dir=data_dir)
    build_site(data_dir, site_dir)
    return site_dir


def _read(site_dir, rel):
    with open(os.path.join(site_dir, rel), encoding="utf-8") as f:
        return f.read()


def test_feed_lists_the_picks_with_tagged_links(tmp_path):
    site_dir = _build(tmp_path)
    root = ET.fromstring(_read(site_dir, "feed.xml"))  # valid XML despite < and & in titles
    items = root.findall("./channel/item")
    assert [i.findtext("title") for i in items] == ["Top pick: Paper <2610.1> & friends"]
    assert items[0].findtext("link") == SITE + "paper/2610.1.html?ref=rss"
    assert "Sat, 31 Oct 2026" in items[0].findtext("pubDate")


def test_sitemap_lists_public_pages_but_not_the_reading_list(tmp_path):
    site_dir = _build(tmp_path)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [e.text for e in ET.fromstring(_read(site_dir, "sitemap.xml")).findall("s:url/s:loc", ns)]
    assert SITE in locs and SITE + "paper/2610.2.html" in locs and SITE + "day/2026-10-31.html" in locs
    assert not any("saved.html" in u for u in locs)
    assert "noindex" in _read(site_dir, "saved.html")


def test_paper_pages_have_canonical_link_and_their_own_share_image(tmp_path):
    site_dir = _build(tmp_path)
    html = _read(site_dir, "paper/2610.1.html")
    assert f'<link rel="canonical" href="{SITE}paper/2610.1.html">' in html
    assert f'<meta property="og:image" content="{SITE}og/2610.1.png">' in html
    assert 'name="twitter:card" content="summary_large_image"' in html
    assert 'type="application/rss+xml"' in html
    from PIL import Image
    with Image.open(os.path.join(site_dir, "og", "2610.1.png")) as img:
        assert img.size == (1200, 630)
    assert os.path.exists(os.path.join(site_dir, "og", "site.png"))
    assert f'content="{SITE}og/site.png"' in _read(site_dir, "index.html")


def test_old_papers_share_the_site_image():
    old = {"id": "1", "first_seen": "2026-10-01"}
    assert not discovery.wants_image(old, "2026-10-31")
    assert discovery.wants_image(dict(old, featured=True), "2026-10-31")
    assert discovery.wants_image({"id": "2", "first_seen": "2026-10-30"}, "2026-10-31")


def test_subscribe_box_offers_rss_until_buttondown_is_set(tmp_path, monkeypatch):
    site_dir = _build(tmp_path)
    index = _read(site_dir, "index.html")
    assert "Get tomorrow’s pick" in index and 'href="feed.xml" data-subscribe="rss"' in index
    assert "buttondown" not in index
    assert 'href="../feed.xml"' in _read(site_dir, "paper/2610.1.html")

    monkeypatch.setattr(site_builder, "BUTTONDOWN_USER", "aipapers")
    box = site_builder.subscribe_box()
    assert 'action="https://buttondown.com/api/emails/embed-subscribe/aipapers"' in box
    assert 'type="email"' in box and "data-subscribe-form" in box


def test_search_console_tag_only_when_set(monkeypatch):
    assert "google-site-verification" not in site_builder.page("T", "", path="")
    monkeypatch.setattr(site_builder, "GOOGLE_SITE_VERIFICATION", "abc123")
    assert '<meta name="google-site-verification" content="abc123">' in site_builder.page("T", "", path="")


def test_email_signup_stays_on_the_site_once_buttondown_is_set(tmp_path, monkeypatch):
    monkeypatch.setattr(site_builder, "BUTTONDOWN_USER", "aipapers")
    site_dir = _build(tmp_path)
    index = _read(site_dir, "index.html")
    assert "data-sub-box" in index and "data-sub-done" in index and "data-sub-mini" in index
    assert 'data-sub-jump' in index and "Subscribe free" in index  # header button
    assert 'name="embed" value="1"' in index

    youre_in = _read(site_dir, "subscribed.html")
    assert "You’re in." in youre_in and "data-sub-confirmed" in youre_in
    assert "noindex" in youre_in  # a thank-you page has no place in search results


def test_no_header_button_without_buttondown(tmp_path):
    site_dir = _build(tmp_path)
    assert "data-sub-jump" not in _read(site_dir, "index.html")
