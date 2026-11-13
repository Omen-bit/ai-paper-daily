"""
tests/test_case_new_and_follow.py
"New this week" (added_at and the strip), topic follows on the Case studies pages, and the weekly
email's "How companies built it this week" block.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import case_pages
import case_studies as cs
import weekly_edition as we

TODAY = "2026-11-13"


def _post(n, problem="rag", published="2026-11-10", added=None, score=None, **extra):
    post = {"url": f"https://eng.example.com/{n}", "company": f"Co{n}", "title": f"Post {n}", "problem": problem,
            "published": published, "summary": "What they built.", "issue": f"Problem {n}."}
    if added:
        post["added"] = added
    if score is not None:
        post["build_score"] = score
    post.update(extra)
    return post


# ---------- added_at

def test_added_at_is_the_day_added_unless_the_post_was_already_old():
    assert cs.added_at_for("2026-11-10", "2026-11-12") == "2026-11-12"  # found two days after it came out
    assert cs.added_at_for("2026-10-01", "2026-11-12") == "2026-10-01"  # back catalogue: counts from its own date
    assert cs.added_at_for("", "2026-11-12") == "2026-11-12"
    assert cs.added_at_for("2026-11-14", "2026-11-12") == "2026-11-14"  # never before it was published
    assert cs.added_on({"published": "2026-11-01"}) == "2026-11-01"
    assert cs.added_on({"added_at": "2026-11-05", "published": "2026-01-01"}) == "2026-11-05"


def test_new_and_saved_posts_get_added_at(monkeypatch):
    monkeypatch.setattr(cs, "groq_sort", lambda post: {"keep": True, "topic": "rag", "issue": "i", "summary": "s",
                                                       "result": "", "tags": []})
    fetched = [{"url": "https://a.example/new", "company": "A", "title": "An LLM agent", "published": "2026-11-12", "text": ""},
               {"url": "https://a.example/old", "company": "A", "title": "An old LLM agent", "published": "2026-09-01", "text": ""}]
    saved = [{"url": "https://a.example/saved", "company": "A", "title": "Saved", "published": "2026-11-01",
              "added": "2026-11-08", "problem": "rag", "summary": "x", "issue": "y", "v": cs.VERSION, "tags": []}]
    posts, _ = cs.update(saved, fetched, TODAY)
    by_url = {p["url"]: p for p in posts}
    assert by_url["https://a.example/new"]["added_at"] == TODAY
    assert by_url["https://a.example/old"]["added_at"] == "2026-09-01"
    assert by_url["https://a.example/saved"]["added_at"] == "2026-11-08"  # filled in for posts saved before


# ---------- New this week on the page

def _page(tmp_path, posts):
    written = {}
    case_pages.build_all(posts, {}, lambda title, body, **kw: body,
                         lambda path, text: written.__setitem__(path, text), str(tmp_path), today=TODAY)
    return written


def test_new_this_week_lists_up_to_six_most_detailed_first(tmp_path):
    posts = [_post(i, added="2026-11-12", score=i % 6) for i in range(8)]
    posts += [_post(20, published="2026-10-01", added="2026-11-12", score=5),   # back catalogue: not new
              _post(21, published="2026-11-02", added="2026-11-03", score=5)]   # added ten days ago: not new
    marked = case_pages.mark_new(case_pages._clean(posts), TODAY)
    fresh = case_pages.new_this_week(marked)
    assert len(fresh) == 8 and [p["build_score"] for p in fresh][:3] == [5, 4, 3]
    page = _page(tmp_path, posts)[os.path.join(str(tmp_path), "case-studies", "index.html")]
    strip = page.split('class="cs-sec cf-sec cf-new"', 1)[1].split("</section>", 1)[0]
    assert "New this week" in strip and "See all 8 new" in strip and "data-cf-fresh" in strip
    assert strip.count("data-cs-item") == 6
    assert 'href="https://eng.example.com/20"' not in strip and 'href="https://eng.example.com/21"' not in strip
    assert page.index("cf-browse") < page.index("cf-new") < page.index("data-cf-sections")  # under the chips


def test_the_strip_is_hidden_when_nothing_is_new(tmp_path):
    page = _page(tmp_path, [_post(1, published="2026-10-01", added="2026-10-02")])[
        os.path.join(str(tmp_path), "case-studies", "index.html")]
    assert "cf-new" not in page and "New this week" not in page


def test_new_posts_carry_the_new_pill_everywhere(tmp_path):
    written = _page(tmp_path, [_post(1, added="2026-11-12"), _post(2, published="2026-10-01", added="2026-10-02")])
    index = written[os.path.join(str(tmp_path), "case-studies", "index.html")]
    one = index.split('href="https://eng.example.com/1"', 1)[0].rsplit("<li ", 1)[1]
    assert '<span class="cs-new">New</span>' in one
    topic = written[os.path.join(str(tmp_path), "case-studies", "rag.html")]
    two = topic.split('href="https://eng.example.com/2"', 1)[0].rsplit("<li ", 1)[1]
    assert "cs-new" in topic and "cs-new" not in two
    import json
    rows = {r["u"]: r for r in json.loads(index.split('id="cf-index">', 1)[1].split("</script>", 1)[0])["posts"]}
    assert rows["https://eng.example.com/1"]["nw"] == 1 and rows["https://eng.example.com/1"]["a"] == "2026-11-12"
    assert "nw" not in rows["https://eng.example.com/2"]


# ---------- follows

def test_every_topic_can_be_followed_and_the_page_has_your_topics(tmp_path):
    written = _page(tmp_path, [_post(1, "rag", added="2026-11-12"), _post(2, "evals", added="2026-11-12")])
    index = written[os.path.join(str(tmp_path), "case-studies", "index.html")]
    assert 'data-follow="rag" aria-pressed="false" aria-label="Follow RAG and search"' in index
    assert 'data-follow="evals"' in index
    assert 'data-cf-mine aria-pressed="false" hidden>' in index  # shown by the page once something is followed
    assert 'data-cf-badge="rag" hidden' in index
    topic = written[os.path.join(str(tmp_path), "case-studies", "evaluation.html")]
    assert 'class="cf-topic-follow"><button class="cf-follow" type="button" data-follow="evals"' in topic


def test_follows_stay_in_the_browser():
    app = open(os.path.join(os.path.dirname(__file__), "..", "src", "site_assets", "app.js"), encoding="utf-8").read()
    block = app.split("Case studies: Follow a topic", 1)[1].split("// ----", 1)[0]
    assert 'localStorage.setItem(KEY' in block and "try {" in block and "fetch(" not in block


# ---------- the weekly email

WEEK = ("2026-11-09", "2026-11-15")


def test_the_week_block_picks_the_most_detailed_new_cases():
    posts = [_post(1, added="2026-11-10", score=2), _post(2, added="2026-11-11", score=5),
             _post(3, added="2026-11-12", score=3), _post(4, added="2026-11-12", score=4),
             _post(5, published="2026-06-01", added="2026-11-12", score=5),  # old post found late: not this week's
             _post(6, published="2026-11-02", added="2026-11-03", score=5)]  # last week's
    cases, total = we.pick_week_cases(posts, *WEEK)
    assert [c["company"] for c in cases] == ["Co2", "Co4", "Co3"] and total == 4
    assert cases[0]["issue"] == "Problem 2." and cases[0]["build_score"] == 5


def test_followed_topics_come_first():
    posts = [_post(1, "rag", added="2026-11-10", score=5), _post(2, "evals", added="2026-11-11", score=1),
             _post(3, "rag", added="2026-11-12", score=4)]
    cases, _ = we.pick_week_cases(posts, *WEEK, prefer_topics=["evals"], n=2)
    assert [c["company"] for c in cases] == ["Co2", "Co1"]


def test_the_block_renders_company_title_problem_and_build_details():
    posts = [_post(1, added="2026-11-10", score=4, title="How we built <RAG>"), _post(2, added="2026-11-11")]
    cases, total = we.pick_week_cases(posts, *WEEK)
    row = we.cases_row(cases, total)
    assert "How companies built it this week" in row and "More case studies" in row
    assert 'href="https://eng.example.com/1"' in row and "How we built &lt;RAG&gt;" in row
    assert "Problem 1." in row and "Build details 4/5" in row
    assert row.count("Build details") == 1  # an untagged case gets no build note
    assert "case-studies/index.html?ref=email" in row
    assert we.cases_row([], 0) == ""  # nothing new: no block
    assert we.pick_week_cases([], *WEEK) == ([], 0)
