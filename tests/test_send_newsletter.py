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
    assert "Monday, 02 November 2026" in email["body"]


def test_no_key_does_nothing(monkeypatch):
    monkeypatch.delenv("BUTTONDOWN_API_KEY", raising=False)
    assert sn.main("2026-11-02") == 0


def test_sends_once(monkeypatch, tmp_path):
    feed = tmp_path / "feed.xml"
    feed.write_text(FEED, encoding="utf-8")
    monkeypatch.setattr(sn, "FEED_PATH", str(feed))
    monkeypatch.setattr(sn, "MARKER_DIR", str(tmp_path / "newsletter"))
    monkeypatch.setenv("BUTTONDOWN_API_KEY", "k")
    calls = []
    monkeypatch.setattr(sn, "post_email", lambda key, p: calls.append(p) or {"id": "e1"})
    assert sn.main("2026-11-02") == 0
    assert sn.main("2026-11-02") == 0
    assert len(calls) == 1 and calls[0]["status"] == "about_to_send"
