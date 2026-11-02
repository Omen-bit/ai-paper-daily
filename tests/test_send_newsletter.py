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
    email = sn.build_email_from_edition(EDITION, "2026-11-02")
    body = email["body"]
    assert email["subject"] == "SpecSlot · plus 1 more pick"
    assert "916 new papers read." in body and "2 worth your time." in body
    assert body.index("SpecSlot") < body.index("Does Scaling Work")
    assert "Other" not in body and "Also new today" not in body  # picks only
    assert "TLDR one." in body and "Cheaper." in body and "https://github.com/x/y" in body
    # kept short: no long notes, quiz or build ideas
    assert "New thing." not in body and "How does it work?" not in body and "Idea A" not in body
    assert "ref=email" in body and "\n    " not in body  # no indented lines for Markdown to mangle
    assert len(body) < 12000


def test_compose_prefers_edition_file(monkeypatch, tmp_path):
    import json
    (tmp_path / "2026-11-02.json").write_text(json.dumps(EDITION), encoding="utf-8")
    monkeypatch.setattr(sn, "DATA_DIR", str(tmp_path))
    assert sn.compose("2026-11-02")["subject"].startswith("SpecSlot")
