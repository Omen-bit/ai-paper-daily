"""
tests/test_case_studies.py
The Case studies pipeline (case_studies.py) and pages (case_pages.py).
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import case_studies as cs
import case_pages
from case_sources import PROBLEMS, SOURCES, lines_at, shared_with
from paper_store import save_day
from site_builder import build_site

FEED = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Eng</title>
<item><title>Ranking the home feed with a two-tower model</title><link>http://eng.example.com/feed-ranking/?utm_source=rss</link>
<pubDate>Mon, 02 Nov 2026 10:00:00 GMT</pubDate><description>&lt;p&gt;How we &lt;b&gt;recommend&lt;/b&gt; posts.&lt;/p&gt;</description></item>
<item><title>We are hiring in Berlin</title><link>https://eng.example.com/hiring</link><pubDate>Mon, 02 Nov 2026 09:00:00 GMT</pubDate></item>
<item><title></title><link>https://eng.example.com/empty</link></item>
</channel></rss>"""


def _post(url, problem="recs", step=3, company="Netflix", **extra):
    post = {"url": url, "company": company, "title": f"Post {url[-1]}", "published": "2026-11-01",
            "problem": problem, "step": step, "summary": "What the team did."}
    post.update(extra)
    return post


def test_parse_feed_cleans_urls_and_text():
    posts = cs.parse_feed(FEED, "Netflix")
    assert [p["url"] for p in posts] == ["https://eng.example.com/feed-ranking", "https://eng.example.com/hiring"]
    assert posts[0]["published"] == "2026-11-02"
    assert posts[0]["text"] == "How we recommend posts."
    assert posts[0]["company"] == "Netflix"


def test_only_ai_posts_are_kept_and_sorted_by_keywords_without_groq():
    fetched = cs.parse_feed(FEED, "Netflix")
    posts, counts = cs.update([], fetched, "2026-11-07", use_groq=False)
    assert [p["url"] for p in posts] == ["https://eng.example.com/feed-ranking"]
    assert (posts[0]["problem"], posts[0]["step"]) == ("recs", 2)  # two-tower is candidate retrieval
    assert posts[0]["summary"] == ""  # never the blog's own words
    assert posts[0]["sorted_by"] == "rules" and counts["new"] == 1
    again, counts = cs.update(posts, fetched, "2026-11-08", use_groq=False)
    assert len(again) == 1 and counts["new"] == 0  # already saved


def test_keyword_rules_put_serving_and_evaluation_on_shared_stops():
    assert cs.rule_sort({"title": "Serving our ranking models on GPUs", "text": "recommendation"}) == ("recs", 4)
    assert cs.rule_sort({"title": "How we evaluate our LLM assistant", "text": ""}) == ("llm", 5)
    assert cs.rule_sort({"title": "A feature store for ads models", "text": ""}) == ("ads", 1)
    assert cs.rule_sort({"title": "Our new office", "text": ""}) is None


def test_groq_reply_parsing():
    ok = cs.parse_reply('Sure: {"ai_in_production": true, "problem": "search", "step": 2, "summary": "Built a retriever."}')
    assert ok == {"keep": True, "problem": "search", "step": 2, "summary": "Built a retriever."}
    assert cs.parse_reply('{"ai_in_production": false}') == {"keep": False}
    assert cs.parse_reply('{"ai_in_production": true, "problem": "music", "step": 2}') is None
    assert cs.parse_reply('{"ai_in_production": true, "problem": "recs", "step": 9}') is None
    assert cs.parse_reply("no json here") is None


def test_groq_results_are_used_and_rejections_skipped(monkeypatch):
    replies = iter([{"keep": True, "problem": "llm", "step": 2, "summary": "Agents fix builds."}, {"keep": False}])
    monkeypatch.setattr(cs, "groq_sort", lambda post: next(replies))
    fetched = [dict(url="https://a.example/1", company="Uber", title="An LLM agent for builds", published="2026-11-01", text=""),
               dict(url="https://a.example/2", company="Uber", title="Model of our office plants", published="2026-11-01", text="")]
    posts, counts = cs.update([], fetched, "2026-11-07")
    assert [(p["problem"], p["step"], p["summary"]) for p in posts] == [("llm", 2, "Agents fix builds.")]
    assert counts["groq"] == 2 and counts["skipped"] == 1


def test_save_keeps_newest_first(tmp_path):
    path = str(tmp_path / "cases.json")
    cs.save([_post("https://x/1", published="2026-01-01"), _post("https://x/2", published="2026-03-01")], path)
    assert [p["url"] for p in cs.load(path)] == ["https://x/2", "https://x/1"]
    assert cs.load(str(tmp_path / "missing.json")) == []


def test_map_shares_steps_between_lines():
    assert set(shared_with("recs", 4)) == set(PROBLEMS) - {"recs"}
    assert shared_with("search", 1) == []
    assert lines_at("ads", 1) == ["ads", "recs", "predict"]
    for name, feed, home, slug, colour in SOURCES:
        assert feed.startswith("https://") and home.startswith("https://") and len(colour) == 6


def test_cover_shows_the_step_and_its_neighbours():
    own = case_pages.cover_route("search", 2)
    assert "Retrieval" in own and "Indexing" in own and "Re-ranking" in own and "Step 3 of 6" in own
    shared = case_pages.cover_route("recs", 4)
    assert "Shared with all six problems" in shared


def test_case_study_pages_are_built_and_escaped(tmp_path):
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    paper = {"id": "2611.1", "title": "Two-tower retrieval for feed ranking", "authors": ["A"],
             "abstract": "We study two-tower retrieval for feed ranking at scale.", "submitted": "2026-11-01",
             "categories": ["llms"], "score": 5, "badges": []}
    save_day([paper], [], "2026-11-07", data_dir=data_dir)
    posts = [_post("https://netflixtechblog.com/a", title="Two-tower retrieval <in> the home feed ranking", step=2),
             _post("https://engineering.fb.com/b", company="Meta", problem="ads", step=1, summary=""),
             _post("https://booking.ai/c", company="Booking.com", problem="llm", step=3),
             _post("ftp://bad/d"), _post("https://x/e", problem="nope")]
    with open(os.path.join(data_dir, "cases.json"), "w", encoding="utf-8") as f:
        json.dump({"posts": posts}, f)
    build_site(data_dir, site_dir)
    folder = os.path.join(site_dir, "case-studies")
    for name in ["index.html", "companies.html", "latest.html", "recommendations.html", "ads.html", "forecasting.html"]:
        assert os.path.exists(os.path.join(folder, name)), name
    latest = open(os.path.join(folder, "latest.html"), encoding="utf-8").read()
    assert "Two-tower retrieval &lt;in&gt; the home feed ranking" in latest
    assert 'href="https://netflixtechblog.com/a"' in latest and 'rel="noopener"' in latest
    assert "ftp://bad" not in latest and "https://x/e" not in latest  # bad records are left out
    assert latest.count("data-cs-item") == 3
    assert 'id="b-netflix"' in latest and "cs-mono" in latest  # real logo, initials for Booking.com
    recs = open(os.path.join(folder, "recommendations.html"), encoding="utf-8").read()
    assert "engineering.fb.com/b" in recs  # Feature pipelines is shared with Ads
    assert "../paper/2611.1.html" in recs  # a related paper from our library
    home = open(os.path.join(site_dir, "index.html"), encoding="utf-8").read()
    assert 'href="case-studies/index.html"' in home
    assert "case-studies/latest.html" in open(os.path.join(site_dir, "sitemap.xml"), encoding="utf-8").read()


def test_case_study_pages_without_posts(tmp_path):
    build_site(str(tmp_path / "data"), str(tmp_path / "site"))
    index = open(tmp_path / "site" / "case-studies" / "index.html", encoding="utf-8").read()
    assert "The first write-ups arrive with the next daily update." in index
    latest = open(tmp_path / "site" / "case-studies" / "latest.html", encoding="utf-8").read()
    assert "No write-ups yet." in latest
