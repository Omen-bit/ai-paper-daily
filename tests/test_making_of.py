"""The "How I built AI Papers Daily" case study: its page, its Markdown copy and its card on Case studies."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import making_of
from site_builder import ASSETS_DIR, build_site

URL = "https://example.org/apd/"


def _post(url, company, day):
    return {"url": url, "company": company, "title": f"Post from {company}", "published": f"2026-11-0{day}",
            "problem": "agents", "summary": "What the team did.", "tags": ["Tool calling"]}


def _build(tmp_path, posts):
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, "cases.json"), "w", encoding="utf-8") as f:
        json.dump({"posts": posts}, f)
    build_site(data_dir, site_dir)
    return site_dir


def test_page_is_built_with_card_and_sitemap_entry(tmp_path):
    posts = [_post("https://a.example/1", "Vercel", 9), _post("https://a.example/2", "Vercel", 8),
             _post("https://b.example/3", "Meta", 7), _post("https://c.example/4", "Netflix", 6), _post("https://d.example/5", "Spotify", 5)]
    site_dir = _build(tmp_path, posts)
    folder = os.path.join(site_dir, "case-studies")
    page = open(os.path.join(folder, f"{making_of.SLUG}.html"), encoding="utf-8").read()
    # Indexable, with the site name in the title and the heading
    assert "<title>How I built AI Papers Daily · AI Papers Daily</title>" in page
    assert page.count("<h1>") == 1 and "<h1>How I built AI Papers Daily</h1>" in page
    assert f'case-studies/{making_of.SLUG}.html"' in page and 'rel="canonical"' in page
    assert '"@type":"TechArticle"' in page
    # Every section in the table of contents has its heading, in order
    ids = re.findall(r'<h2 id="([a-z]+)">', page)
    assert ids == [i for i, _ in making_of.TOC]
    # Figures are numbered from 1 without gaps
    numbers = [int(n) for n in re.findall(r"\[ Fig\. (\d+) \]", page) if n != "0"]
    assert numbers == list(range(1, len(numbers) + 1))
    # Related articles: three different companies, linking to their own posts
    related = page.split("/Related articles", 1)[1]
    assert related.count('rel="noopener" target="_blank"><div class="rel-art">') == 3
    assert "https://a.example/1" in related and "https://a.example/2" not in related
    # The newest company write-ups lead the Case studies page and the card follows them; the page is in the sitemap
    index = open(os.path.join(folder, "index.html"), encoding="utf-8").read()
    newest = index.split("<h2>Newest</h2>", 1)[1].split("</section>", 1)[0]
    assert newest.index("data-cs-item") < newest.index(f'href="{making_of.SLUG}.html"')
    assert 1 <= newest.count("data-cs-item") <= 4
    sitemap = open(os.path.join(site_dir, "sitemap.xml"), encoding="utf-8").read()
    assert f"case-studies/{making_of.SLUG}.html" in sitemap


def test_every_video_and_image_the_page_uses_is_shipped():
    html = making_of.page_html([], URL)
    used = set(re.findall(r'(?:src|poster)="\.\./assets/(making-of/[^"]+)"', html))
    assert used and {u.split("/")[1] for u in used} == {"video", "img"}
    for path in used:
        assert os.path.isfile(os.path.join(ASSETS_DIR, path)), path
    assert len([u for u in used if u.endswith(".mp4")]) == len(making_of.VIDEOS)
    assert os.path.isfile(os.path.join(ASSETS_DIR, "making-of.css"))


def test_videos_are_silent_loops_with_a_poster():
    html = making_of.page_html([], URL)
    videos = re.findall(r"<video [^>]+>", html)
    assert len(videos) == len(making_of.VIDEOS)
    for v in videos:
        assert all(k in v for k in ("muted", "loop", "playsinline", "poster="))


def test_markdown_copy_reads_well_for_dev_to():
    md = making_of.markdown(URL)
    assert md.startswith("---\ntitle: How I built AI Papers Daily\n")
    assert f"canonical_url: {URL}case-studies/{making_of.SLUG}.html" in md
    assert "\n# How I built AI Papers Daily\n" in md
    assert all(f"\n## {title}\n" in md for _, title in making_of.TOC)
    assert "<" not in md.split("---", 2)[2].replace("<!--", "")  # no HTML left over
    assert f"]({URL}assets/making-of/video/morning.mp4)" in md  # videos link to the file, with the poster shown
    assert f"({URL}assets/making-of/img/paper.png)" in md  # images use full links
    assert "| Signal | Why it counts | How much |" in md
    assert "Copy for LLM" not in md and "Fig." not in md


def test_dev_to_link_shows_only_once_set(monkeypatch):
    assert "dev.to" not in making_of.page_html([], URL)
    monkeypatch.setattr(making_of, "DEVTO_URL", "https://dev.to/someone/how-i-built")
    html = making_of.page_html([], URL)
    assert 'href="https://dev.to/someone/how-i-built"' in html


def test_card_has_the_pixel_cover_and_links_to_the_page():
    card = making_of.card()
    assert card.startswith('<li class="cs-own">') and f'href="{making_of.SLUG}.html"' in card
    assert '<rect class="pick"' in card and "Behind the build" in card
    assert f"{len(making_of.VIDEOS)} videos" in card
