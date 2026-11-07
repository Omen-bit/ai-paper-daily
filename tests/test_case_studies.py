"""
tests/test_case_studies.py
The Case studies pipeline (case_studies.py), page (case_pages.py) and email section.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import case_studies as cs
import case_pages
from case_sources import PROBLEMS, SOURCES, TAG_NAMES, lines_at, shared_with
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
    assert posts[0]["tags"] == ["Two-tower"]
    again, counts = cs.update(posts, fetched, "2026-11-08", use_groq=False)
    assert len(again) == 1 and counts["new"] == 0  # already saved


def test_keyword_rules_put_serving_and_evaluation_on_shared_stops():
    assert cs.rule_sort({"title": "Serving our ranking models on GPUs", "text": "recommendation"}) == ("recs", 4)
    assert cs.rule_sort({"title": "How we evaluate our LLM assistant", "text": ""}) == ("llm", 5)
    assert cs.rule_sort({"title": "A feature store for ads models", "text": ""}) == ("ads", 1)
    assert cs.rule_sort({"title": "Our new office", "text": ""}) is None


def test_groq_reply_parsing():
    ok = cs.parse_reply('Sure: {"ai_in_production": true, "problem": "search", "step": 2, "summary": "Built a retriever."}')
    assert ok == {"keep": True, "problem": "search", "step": 2, "summary": "Built a retriever.", "tags": []}
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
    assert len(TAG_NAMES) == len(set(TAG_NAMES))


def test_tags_come_from_the_list_and_keywords():
    assert cs.rule_tags({"title": "RAG for support agents", "text": "We use embeddings and GPUs."}) == ["RAG", "Agents", "Embeddings"]
    ok = cs.parse_reply('{"ai_in_production": true, "problem": "llm", "step": 1, "summary": "x", "tags": ["rag", "Made up", "LLMs"]}')
    assert ok["tags"] == ["RAG", "LLMs"]


def test_blogs_are_read_on_run_days_only():
    from datetime import datetime
    assert cs.is_run_day(datetime(2026, 11, 9), "mon,thu")       # a Monday
    assert not cs.is_run_day(datetime(2026, 11, 7), "mon,thu")   # a Saturday
    assert cs.is_run_day(datetime(2026, 11, 7), "daily")


def test_article_text_reads_the_post_not_the_page_chrome():
    page = ("<html><nav><p>Home About Careers Blog Jobs Contact</p></nav><article><h1>T</h1>"
            "<p>We rebuilt our ranking model to use two towers and fresh features.</p><p>Short.</p></article>"
            "<footer><p>Copyright and other legal words go here</p></footer></html>")
    assert cs.article_text(page) == "We rebuilt our ranking model to use two towers and fresh features."


def test_new_posts_are_read_once_before_groq(monkeypatch):
    seen = []
    monkeypatch.setattr(cs, "groq_sort", lambda post: seen.append(post["text"]) or
                        {"keep": True, "problem": "search", "step": 2, "summary": "Built it.", "tags": []})
    fetched = [dict(url="https://a.example/1", company="Uber", title="Semantic search for menus", published="2026-11-01", text="short")]
    posts, _ = cs.update([], fetched, "2026-11-07", reader=lambda url: "The full post text about vector search and embeddings.")
    assert seen == ["The full post text about vector search and embeddings."]
    assert posts[0]["tags"] == ["Vector search", "Embeddings"]  # Groq gave none, so keywords filled them


def test_case_study_page_is_one_feed(tmp_path):
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    paper = {"id": "2611.1", "title": "Two-tower retrieval for feed ranking", "authors": ["A"],
             "abstract": "We study two-tower retrieval for feed ranking at scale.", "submitted": "2026-11-01",
             "categories": ["llms"], "score": 5, "badges": []}
    save_day([paper], [], "2026-11-07", data_dir=data_dir)
    posts = [_post("https://netflixtechblog.com/a", title="Two-tower retrieval <in> the home feed ranking", step=2, tags=["Two-tower"]),
             _post("https://engineering.fb.com/b", company="Meta", problem="ads", step=1, summary=""),
             _post("https://booking.ai/c", company="Booking.com", problem="llm", step=3),
             _post("ftp://bad/d"), _post("https://x/e", problem="nope")]
    with open(os.path.join(data_dir, "cases.json"), "w", encoding="utf-8") as f:
        json.dump({"posts": posts}, f)
    build_site(data_dir, site_dir)
    folder = os.path.join(site_dir, "case-studies")
    assert sorted(os.listdir(folder)) == ["index.html"]
    page = open(os.path.join(folder, "index.html"), encoding="utf-8").read()
    assert "Two-tower retrieval &lt;in&gt; the home feed ranking" in page
    assert 'href="https://netflixtechblog.com/a"' in page and 'rel="noopener"' in page
    assert "ftp://bad" not in page and "https://x/e" not in page  # bad records are left out
    assert page.count("data-cs-item") == 3
    assert 'id="b-netflix"' in page and "cs-mono" in page  # real logo, initial for Booking.com
    assert 'data-cs-tag="Two-tower"' in page and 'data-cs-save="cs:https://netflixtechblog.com/a"' in page
    assert 'data-cs-topic="ads"' in page and 'data-cs-topic="vision"' not in page  # only topics with write-ups
    assert '<option value="Meta">Meta (1)</option>' in page
    assert "../paper/2611.1.html" in page  # a related paper from our library
    home = open(os.path.join(site_dir, "index.html"), encoding="utf-8").read()
    assert 'href="case-studies/index.html"' in home
    assert "case-studies/index.html" in open(os.path.join(site_dir, "sitemap.xml"), encoding="utf-8").read()


def test_case_study_page_without_posts(tmp_path):
    build_site(str(tmp_path / "data"), str(tmp_path / "site"))
    page = open(tmp_path / "site" / "case-studies" / "index.html", encoding="utf-8").read()
    assert "No write-ups yet." in page and "data-cs-q" not in page


def test_email_lists_case_studies_added_today(tmp_path):
    import send_newsletter as nl
    path = str(tmp_path / "cases.json")
    cs.save([_post("https://x/1", added="2026-11-09", title="Fresh one"), _post("https://x/2", added="2026-11-05")], path)
    fresh = nl.new_case_studies("2026-11-09", path)
    assert [p["url"] for p in fresh] == ["https://x/1"]
    block = nl.case_studies(fresh)
    assert "From company blogs" in block and "Fresh one" in block and 'href="https://x/1"' in block
    assert nl.case_studies([]) == ""
