import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import send_newsletter as sn  # noqa: E402

FEED = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>AI Papers Daily</title>
<item><title>Top pick: Paper A</title><link>https://x/paper/a.html?ref=rss</link>
<pubDate>Mon, 02 Nov 2026 01:30:00 +0000</pubDate>
<description><![CDATA[<p>A does things.</p><p><a href="https://x/paper/a.html?ref=rss">Read</a></p>]]></description></item>
<item><title>Trending: Paper B</title><link>https://x/paper/b.html?ref=rss</link>
<pubDate>Mon, 02 Nov 2026 01:30:00 +0000</pubDate><description>B</description></item>
<item><title>Top pick: Old</title><link>https://x/paper/o.html</link>
<pubDate>Sun, 01 Nov 2026 01:30:00 +0000</pubDate><description>old</description></item>
</channel></rss>"""


def test_picks_only_todays_items():
    items = sn.todays_items(FEED, "2026-11-02")
    assert [i["title"] for i in items] == ["Top pick: Paper A", "Trending: Paper B"]


def test_email_subject_and_links():
    email = sn.build_email(sn.todays_items(FEED, "2026-11-02"), "2026-11-02")
    assert email["subject"] == "Paper A"
    assert "ref=email" in email["body"] and "ref=rss" not in email["body"]
    assert "Monday, 2 November 2026" in email["body"]


def test_no_key_does_nothing(monkeypatch):
    monkeypatch.delenv("BUTTONDOWN_API_KEY", raising=False)
    assert sn.main("2026-11-02") == 0


def test_sends_once(monkeypatch, tmp_path):
    feed = tmp_path / "feed.xml"
    feed.write_text(FEED, encoding="utf-8")
    monkeypatch.setattr(sn, "FEED_PATH", str(feed))
    monkeypatch.setattr(sn, "MARKER_DIR", str(tmp_path / "newsletter"))
    monkeypatch.setattr(sn, "DATA_DIR", str(tmp_path / "none"))
    monkeypatch.setenv("BUTTONDOWN_API_KEY", "k")
    calls = []
    monkeypatch.setattr(sn, "post_email", lambda key, p: calls.append(p) or {"id": "e1"})
    assert sn.main("2026-11-02") == 0
    assert sn.main("2026-11-02") == 0
    assert len(calls) == 1 and calls[0]["status"] == "about_to_send"


EDITION = {
    "date": "2026-11-02",
    "scanned": 916,
    "featured": ["p1", "p2"],
    "papers": [
        {"id": "p3", "title": "Other <b>paper</b>", "score": 30, "categories": ["llms"],
         "summary": {"text": "Short summary."}},
        {"id": "p1", "title": "SpecSlot: Spectral slots", "score": 34, "slot": "pick", "authors": ["A", "B", "C", "D"],
         "categories": ["generative-ai"], "hf_upvotes": 25, "code_url": "https://github.com/x/y",
         "pdf_url": "https://arxiv.org/pdf/p1",
         "curator": {"tldr": "TLDR one.", "whats_new": "New thing.", "key_result": "FID -2.8.",
                     "why_it_matters": "Cheaper.", "difficulty": "advanced",
                     "check_question": "How does it work?", "build_ideas": ["Idea A.", "Idea B.", "Idea C."]}},
        {"id": "p2", "title": "Does Scaling Work", "score": 33, "slot": "trending", "categories": ["reasoning-agents"]},
    ],
}


def test_edition_email_layout(tmp_path):
    email = sn.build_email_from_edition(EDITION, "2026-11-02", cases=[])
    body = email["body"]
    assert email["subject"] == "SpecSlot: Spectral slots"  # no "plus 1 more pick"
    assert "2 papers worth your time today" in body and "Picked from 916 new AI papers" in body
    assert body.index("SpecSlot") < body.rindex("Does Scaling Work")  # (the preview text names it first)
    assert "Other" not in body and "Also new today" not in body  # picks only
    assert "TLDR one." in body and "Cheaper." in body and "https://github.com/x/y" in body
    assert "Key result:</strong> FID -2.8." in body and "4 authors" in body
    assert "▲ 25 upvotes on Hugging Face" in body and "Read the breakdown →" in body
    assert "No code yet" in body  # the trending pick has no code
    assert "Browse all 3 ranked papers" in body
    assert "Unsubscribe" not in body  # Buttondown's own footer has it
    # kept short: no long notes, quiz or build ideas
    assert "New thing." not in body and "How does it work?" not in body and "Idea A" not in body
    assert "ref=email" in body and "\n" not in body  # one line, nothing for Markdown to mangle
    assert len(body) < 16000


def test_subject_uses_headline_and_never_cuts_mid_word():
    long = {"id": "x", "title": "The Surprising Effectiveness of Deleting Weights in LLM Post-Training"}
    subject = sn.subject_line([long])
    assert subject == "The Surprising Effectiveness of Deleting Weights in LLM…"
    assert len(subject) <= sn.SUBJECT_MAX + 1
    hooked = {**long, "curator": {"headline": "Delete 0.05% of an LLM's weights, skip fine-tuning"}}
    assert sn.subject_line([hooked]) == "Delete 0.05% of an LLM's weights, skip fine-tuning"


def test_preheader_names_the_second_pick_and_the_count():
    picks = [{"id": "a", "title": "A"}, {"id": "b", "title": "APEX: Few-step video", "org": "Tsinghua University"}]
    assert sn.preheader_text(picks, 955) == "+ APEX from Tsinghua University. 2 picks from 955 new papers."


def test_new_count_wins_over_scanned():
    assert sn.new_paper_count({"scanned": 955, "new_count": 610}) == 610
    assert sn.new_paper_count({"scanned": 955}) == 955
    assert sn.new_paper_count({"scanned": 955, "new_count": 0}) == 0


def test_org_names_are_tidied():
    assert sn._org_name("agentic learning ai lab") == "Agentic Learning AI Lab"
    assert sn._org_name("HKUSTGZ") == "HKUSTGZ"


def test_compose_prefers_edition_file(monkeypatch, tmp_path):
    import json
    (tmp_path / "2026-11-02.json").write_text(json.dumps(EDITION), encoding="utf-8")
    monkeypatch.setattr(sn, "DATA_DIR", str(tmp_path))
    assert sn.compose("2026-11-02")["subject"].startswith("SpecSlot")


def test_case_studies_without_results_are_one_line_with_a_count():
    posts = [{"company": "NVIDIA"}, {"company": "Pinterest"}, {"company": "NVIDIA"}, {"company": "Meta"},
             {"company": "Stripe"}]
    row = sn.case_studies(posts)
    assert "5 new case studies</strong> from NVIDIA, Pinterest, Meta and 1 more." in row
    assert "case-studies/index.html?ref=email" in row and "See all 5" in row
    assert "1 new case study</strong> from Apple" in sn.case_studies([{"company": "Apple"}])
    assert sn.case_studies([]) == ""


def test_case_studies_show_two_with_a_result():
    posts = [{"company": "Postman", "title": "How to migrate tests", "url": "https://p", "result": ""},
             {"company": "Meta", "title": "Better ads", "url": "https://m", "result": "About 10% better ranking"},
             {"company": "Meta", "title": "Other", "url": "https://m2", "result": "Faster"},
             {"company": "DXC", "title": "Bedrock", "url": "https://d", "result": "Resolution time down 95%"},
             {"company": "Ramp", "title": "Third", "url": "https://r", "result": "2x"}]
    row = sn.case_studies(posts)
    assert "AI at work" in row and "5 new case studies" in row
    assert "About 10% better ranking" in row and "Resolution time down 95%" in row
    assert "How to migrate tests" not in row and "Other" not in row and "Third" not in row


def test_new_case_studies_skip_old_posts_and_catch_up_since_last_email(tmp_path):
    import json
    posts = [
        {"url": "https://a", "title": "Fresh", "company": "A", "added": "2026-11-12", "published": "2026-11-11"},
        {"url": "https://b", "title": "Backfilled", "company": "B", "added": "2026-11-12", "published": "2026-06-01"},
        {"url": "https://c", "title": "Today", "company": "C", "added": "2026-11-13", "published": "2026-11-13"},
        {"url": "https://d", "title": "Already sent", "company": "D", "added": "2026-11-10", "published": "2026-11-10"},
    ]
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"posts": posts}), encoding="utf-8")
    got = sn.new_case_studies("2026-11-13", path=str(path), since="2026-11-11")
    assert [p["title"] for p in got] == ["Today", "Fresh"]


def test_last_email_day_reads_the_markers(tmp_path):
    for d in ("2026-11-10", "2026-11-12", "2026-11-13"):
        (tmp_path / f"{d}.json").write_text("{}", encoding="utf-8")
    assert sn.last_email_day("2026-11-13", str(tmp_path)) == "2026-11-12"
    assert sn.last_email_day("2026-11-01", str(tmp_path)) is None


def test_link_colours_survive_the_accent_colour():
    email = sn.build_email_from_edition(EDITION, "2026-11-02", cases=[])
    import re
    links = re.findall(r"<a\s[^>]*>", email["body"])
    assert links and all("!important" in a for a in links if "color:" in a)
    assert "color:#ffffff !important" in email["body"]  # the button's text stays white
    assert sn.keep_link_colours('<a href="x" style="color:#111;background-color:#fff;">') == \
        '<a href="x" style="color:#111 !important;background-color:#fff;">'
