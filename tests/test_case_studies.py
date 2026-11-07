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
from case_sources import SOURCES, TAG_NAMES, TOPICS, topic_of
from paper_store import save_day
from site_builder import build_site

FEED = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Eng</title>
<item><title>Ranking the home feed with a two-tower model</title><link>http://eng.example.com/feed-ranking/?utm_source=rss</link>
<pubDate>Mon, 02 Nov 2026 10:00:00 GMT</pubDate><description>&lt;p&gt;How we &lt;b&gt;recommend&lt;/b&gt; posts.&lt;/p&gt;</description></item>
<item><title>We are hiring in Berlin</title><link>https://eng.example.com/hiring</link><pubDate>Mon, 02 Nov 2026 09:00:00 GMT</pubDate></item>
<item><title></title><link>https://eng.example.com/empty</link></item>
</channel></rss>"""


def _post(url, problem="recs", company="Netflix", **extra):
    post = {"url": url, "company": company, "title": f"Post {url[-1]}", "published": "2026-11-01",
            "problem": problem, "summary": "What the team did."}
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
    assert posts[0]["problem"] == "recs" and "step" not in posts[0]
    assert posts[0]["summary"] == ""  # never the blog's own words
    assert posts[0]["sorted_by"] == "rules" and counts["new"] == 1
    assert posts[0]["tags"] == ["Two-tower"]
    again, counts = cs.update(posts, fetched, "2026-11-08", use_groq=False)
    assert len(again) == 1 and counts["new"] == 0  # already saved


def test_keyword_rules_prefer_the_specific_llm_topics():
    assert cs.rule_sort({"title": "How we evaluate our LLM assistant", "text": ""}) == "evals"
    assert cs.rule_sort({"title": "Cutting LLM costs with semantic caching", "text": ""}) == "cost"
    assert cs.rule_sort({"title": "Hybrid search with BM25 and vectors", "text": ""}) == "rag"
    assert cs.rule_sort({"title": "An agent that triages tickets", "text": ""}) == "agents"
    assert cs.rule_sort({"title": "A feature store for ads models", "text": ""}) == "ads"
    assert cs.rule_sort({"title": "New home screen", "text": "We recommend shows."}) == "recs"  # the title first, then text
    assert cs.rule_sort({"title": "Our new office", "text": ""}) is None


def test_groq_reply_parsing():
    ok = cs.parse_reply('Sure: {"ai_in_production": true, "topic": "RAG", "summary": "Built a retriever."}')
    assert ok == {"keep": True, "topic": "rag", "summary": "Built a retriever.", "tags": []}
    assert cs.parse_reply('{"ai_in_production": false}') == {"keep": False}
    assert cs.parse_reply('{"ai_in_production": true, "topic": "music"}') is None
    assert cs.parse_reply("no json here") is None


def test_groq_results_are_used_and_rejections_skipped(monkeypatch):
    replies = iter([{"keep": True, "topic": "agents", "summary": "Agents fix builds."}, {"keep": False}])
    monkeypatch.setattr(cs, "groq_sort", lambda post: next(replies))
    fetched = [dict(url="https://a.example/1", company="Uber", title="An LLM agent for builds", published="2026-11-01", text=""),
               dict(url="https://a.example/2", company="Uber", title="Model of our office plants", published="2026-11-01", text="")]
    posts, counts = cs.update([], fetched, "2026-11-07")
    assert [(p["problem"], p["summary"]) for p in posts] == [("agents", "Agents fix builds.")]
    assert counts["groq"] == 2 and counts["skipped"] == 1


def test_save_keeps_newest_first(tmp_path):
    path = str(tmp_path / "cases.json")
    cs.save([_post("https://x/1", published="2026-01-01"), _post("https://x/2", published="2026-03-01")], path)
    assert [p["url"] for p in cs.load(path)] == ["https://x/2", "https://x/1"]
    assert cs.load(str(tmp_path / "missing.json")) == []


def test_posts_saved_under_the_old_problems_move_to_topics():
    assert topic_of({"problem": "llm", "step": 4}) == "cost"
    assert topic_of({"problem": "llm", "step": 5}) == "evals"
    assert topic_of({"problem": "llm"}) == "llm"
    assert topic_of({"problem": "search", "step": 2}) == "rag"
    assert topic_of({"problem": "recs", "step": 4}) == "recs"
    assert topic_of({"problem": "nope"}) is None
    old = {"url": "https://x/1", "company": "Uber", "title": "Faster LLM answers", "problem": "llm", "step": 4,
           "tags": ["Evaluation", "LLMs"]}
    new = cs.migrate(old)
    assert new["problem"] == "cost" and "step" not in new and new["tags"] == ["LLMs"]


def test_sources_and_tags_are_well_formed():
    names = [s[0] for s in SOURCES]
    assert len(names) == len(set(names))
    for name, feed, home, slug, colour in SOURCES:
        assert feed.startswith("https://") and home.startswith("https://") and len(colour) == 6
    assert len(TAG_NAMES) == len(set(TAG_NAMES))


def test_tags_come_from_the_list_and_keywords():
    assert cs.rule_tags({"title": "RAG for support agents", "text": "We use embeddings and GPUs."}) == ["RAG", "Agents", "Embeddings"]
    assert cs.rule_tags({"title": "Semantic caching cut our LLM bill", "text": ""})[:2] == ["Semantic caching", "LLMs"]
    ok = cs.parse_reply('{"ai_in_production": true, "topic": "rag", "summary": "x", "tags": ["rag", "Made up", "LLMs"]}')
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
                        {"keep": True, "topic": "rag", "summary": "Built it.", "tags": []})
    fetched = [dict(url="https://a.example/1", company="Uber", title="Semantic search for menus", published="2026-11-01", text="short")]
    posts, _ = cs.update([], fetched, "2026-11-07", reader=lambda url: "The full post text about vector search and embeddings.")
    assert seen == ["The full post text about vector search and embeddings."]
    assert posts[0]["tags"] == ["Vector search", "Embeddings"]  # Groq gave none, so keywords filled them


def test_case_studies_are_split_by_topic(tmp_path):
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    paper = {"id": "2611.1", "title": "Two-tower retrieval for feed ranking", "authors": ["A"],
             "abstract": "We study two-tower retrieval for feed ranking at scale.", "submitted": "2026-11-01",
             "categories": ["llms"], "score": 5, "badges": []}
    save_day([paper], [], "2026-11-07", data_dir=data_dir)
    posts = [_post("https://netflixtechblog.com/a", title="Two-tower retrieval <in> the home feed ranking", tags=["Two-tower"]),
             _post("https://engineering.fb.com/b", company="Meta", problem="ads", summary=""),
             _post("https://booking.ai/c", company="Booking.com", problem="llm", step=3),  # saved before topics: Guardrails
             _post("ftp://bad/d"), _post("https://x/e", problem="nope")]
    with open(os.path.join(data_dir, "cases.json"), "w", encoding="utf-8") as f:
        json.dump({"posts": posts}, f)
    build_site(data_dir, site_dir)
    folder = os.path.join(site_dir, "case-studies")
    assert sorted(os.listdir(folder)) == ["ads.html", "guardrails.html", "index.html", "recommendations.html"]
    page = open(os.path.join(folder, "index.html"), encoding="utf-8").read()
    assert "Two-tower retrieval &lt;in&gt; the home feed ranking" in page
    assert 'href="https://netflixtechblog.com/a"' in page and 'rel="noopener"' in page
    assert "ftp://bad" not in page and "https://x/e" not in page  # bad records are left out
    assert 'id="recommendations"' in page and 'href="guardrails.html"' in page and 'id="vision"' not in page
    results = page.split("data-cs-results", 1)[1]
    assert results.count("data-cs-item") == 3  # the search list holds every write-up once
    assert 'id="b-netflix"' in page and "cs-mono" in page  # real logo, initial for Booking.com
    assert 'data-cs-tag="Two-tower"' in page and 'data-cs-save="cs:https://netflixtechblog.com/a"' in page
    assert '<option value="Meta">Meta (1)</option>' in page
    assert "../paper/2611.1.html" in page  # a related paper from our library
    ads = open(os.path.join(folder, "ads.html"), encoding="utf-8").read()
    assert ads.count("data-cs-item") == 1 and 'href="ads.html" style="--c:var(--l-ads)" aria-current="page"' in ads
    home = open(os.path.join(site_dir, "index.html"), encoding="utf-8").read()
    assert 'href="case-studies/index.html"' in home
    sitemap = open(os.path.join(site_dir, "sitemap.xml"), encoding="utf-8").read()
    assert "case-studies/index.html" in sitemap and "case-studies/guardrails.html" in sitemap


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


def test_every_blog_gets_a_turn_and_the_rest_wait(monkeypatch):
    monkeypatch.setattr(cs, "groq_sort", lambda post: {"keep": True, "topic": "llm", "summary": "x", "tags": []})
    fetched = [dict(url=f"https://{co}.example/{i}", company=co, title=f"LLM post {i}", published=f"2026-11-0{i}", text="")
               for co in ("Google", "Meta", "Uber") for i in range(1, 6)]
    posts, counts = cs.update([], fetched, "2026-11-07", max_calls=6, per_blog=10)
    assert sorted(p["company"] for p in posts) == ["Google", "Google", "Meta", "Meta", "Uber", "Uber"]
    assert all(p["url"].endswith(("/5", "/4")) for p in posts)  # newest of each blog first
    assert counts["waiting"] == 9
    posts, counts = cs.update([], fetched, "2026-11-07", max_calls=60, per_blog=2)
    assert len(posts) == 6 and counts["waiting"] == 9


def test_rejected_posts_are_remembered(monkeypatch, tmp_path):
    asked = []
    monkeypatch.setattr(cs, "groq_sort", lambda post: asked.append(post["url"]) or {"keep": False})
    fetched = [dict(url="https://a.example/1", company="Uber", title="Our model office", published="2026-11-01", text="")]
    rejected = set()
    cs.update([], fetched, "2026-11-07", rejected=rejected)
    path = str(tmp_path / "cases.json")
    cs.save([], path, rejected, waiting=3)
    saved = cs.load_all(path)
    assert saved["rejected"] == ["https://a.example/1"] and saved["waiting"] == 3
    cs.update([], fetched, "2026-11-08", rejected=set(saved["rejected"]))
    assert asked == ["https://a.example/1"]  # not asked twice


def test_a_failed_groq_call_waits_for_the_next_run(monkeypatch):
    replies = iter([{"keep": True, "topic": "llm", "summary": "x", "tags": []}, None])
    monkeypatch.setattr(cs, "groq_sort", lambda post: next(replies))
    monkeypatch.setattr(cs, "GROQ_PAUSE", 0)
    fetched = [dict(url=f"https://a.example/{i}", company=c, title="LLM post", published="2026-11-01", text="")
               for i, c in ((1, "Uber"), (2, "Lyft"))]
    posts, counts = cs.update([], fetched, "2026-11-07")
    assert len(posts) == 1 and counts["waiting"] == 1


def test_old_posts_are_sorted_again_with_half_the_calls(monkeypatch):
    monkeypatch.setattr(cs, "groq_sort", lambda post: {"keep": True, "topic": "evals", "summary": "New line.", "tags": ["Evals"]})
    old = [dict(url=f"https://x/{i}", company="Uber", title="Testing LLM answers", published=f"2026-10-0{i}",
                problem="llm", step=4, summary="Old line.", tags=["LLMs"], sorted_by="groq") for i in range(1, 6)]
    posts, counts = cs.update(old, [], "2026-11-07", max_calls=6, reader=lambda url: "")
    redone = [p for p in posts if not p.get("resort")]
    assert counts["resorted"] == 3 and counts["waiting"] == 2
    assert {p["problem"] for p in redone} == {"evals"} and redone[0]["summary"] == "New line."
    assert all(p["problem"] == "cost" for p in posts if p.get("resort"))  # moved by the old step until then
