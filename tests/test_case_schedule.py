"""
tests/test_case_schedule.py
The blogs behind the Case studies pages are read once a week: reruns and the daily edition
reuse the saved posts, and posts left over when Groq runs out wait in a queue for next week.
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import case_studies as cs
from case_sources import SOURCES


def _saved(tmp_path, **data):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"posts": [{"url": "https://a.example/1", "company": "Uber", "title": "x",
                                           "published": "2026-11-01", "problem": "llm"}], **data}))
    return str(path)


def test_read_this_week_uses_monday_to_sunday_weeks():
    assert cs.read_this_week("2026-11-09", datetime(2026, 11, 15))      # Monday, then that Sunday
    assert not cs.read_this_week("2026-11-08", datetime(2026, 11, 9))   # Sunday, then the next Monday
    assert not cs.read_this_week("", datetime(2026, 11, 9))
    assert not cs.read_this_week("not a date", datetime(2026, 11, 9))


def test_a_second_run_in_the_same_week_reads_no_feeds(tmp_path, monkeypatch):
    today = datetime.now(cs.IST).strftime("%Y-%m-%d")
    path = _saved(tmp_path, last_fetch=today, waiting=900)  # posts still waiting do not start a new read
    monkeypatch.setattr(cs, "fetch_feed", lambda url: (_ for _ in ()).throw(AssertionError("feed read")))
    assert cs.run(path) == 0
    assert cs.load_all(path)["last_fetch"] == today


def test_a_new_week_reads_the_feeds_and_records_the_day(tmp_path, monkeypatch):
    path = _saved(tmp_path, last_fetch="2026-01-05")
    read = []
    monkeypatch.setattr(cs, "fetch_feed", lambda url: read.append(url) or b"<rss></rss>")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "case_logos", None)  # no logo downloads in tests
    cs.run(path)
    assert len(read) == len(SOURCES)
    assert cs.load_all(path)["last_fetch"] == datetime.now(cs.IST).strftime("%Y-%m-%d")


def test_force_reads_again_in_the_same_week(tmp_path, monkeypatch):
    path = _saved(tmp_path, last_fetch=datetime.now(cs.IST).strftime("%Y-%m-%d"))
    read = []
    monkeypatch.setattr(cs, "fetch_feed", lambda url: read.append(url) or b"<rss></rss>")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "case_logos", None)
    cs.run(path, force=True)
    assert read


def test_all_feeds_down_leaves_the_week_open(tmp_path, monkeypatch):
    path = _saved(tmp_path, last_fetch="2026-01-05")
    def down(url):
        raise OSError("no network")
    monkeypatch.setattr(cs, "fetch_feed", down)
    monkeypatch.setitem(sys.modules, "case_logos", None)
    cs.run(path)
    assert cs.load_all(path)["last_fetch"] == "2026-01-05"  # the next run tries again


def test_posts_left_waiting_are_queued_for_next_week(monkeypatch, tmp_path):
    monkeypatch.setattr(cs, "groq_sort", lambda post: {"keep": True, "topic": "llm", "summary": "x", "issue": "y", "tags": []})
    fetched = [dict(url=f"https://{co}.example/{i}", company=co, title=f"LLM post {i}", published=f"2026-11-0{i}", text="t")
               for co in ("Google", "Meta") for i in range(1, 4)]
    posts, counts = cs.update([], fetched, "2026-11-09", max_calls=2)
    assert len(posts) == 2 and len(counts["left"]) == 4
    path = str(tmp_path / "cases.json")
    cs.save(posts, path, set(), counts["waiting"], "2026-11-09", counts["left"])
    saved = cs.load_all(path)
    assert len(saved["queue"]) == 4 and set(saved["queue"][0]) == {"url", "company", "title", "published", "text"}
    # Next week the queue is sorted along with the new feeds, and nothing is asked twice
    new = dict(url="https://Meta.example/9", company="Meta", title="LLM post 9", published="2026-11-15", text="t")
    nxt = cs.merge_queue(saved["queue"], [new, fetched[0]])  # a post in both is kept once
    assert len(nxt) == 5
    posts, counts = cs.update(posts, nxt, "2026-11-16", max_calls=60)
    assert len(posts) == 7 and counts["left"] == []


def test_sources_are_unique_and_cover_small_and_large_companies():
    names = [s[0] for s in SOURCES]
    feeds = [s[1] for s in SOURCES]
    assert len(names) == len(set(names)) and len(feeds) == len(set(feeds))
    assert len(SOURCES) >= 120
    for name, feed, home, slug, colour in SOURCES:
        assert feed.startswith("https://") and home.startswith("https://")
        assert len(colour) == 6 and int(colour, 16) >= 0


def test_customer_stories_on_cloud_blogs_show_the_customer(monkeypatch):
    reply = '{"kind": "build", "topic": "rag", "issue": "Agents could not find answers.", "summary": "x", "tags": [], "customer": "Acme Insurance"}'
    assert cs.parse_reply(reply)["customer"] == "Acme Insurance"
    monkeypatch.setattr(cs, "groq_sort", lambda post: cs.parse_reply(reply))
    fetched = [dict(url="https://aws.example/acme", company="AWS", title="How Acme built RAG with an LLM", published="2026-11-01", text=""),
               dict(url="https://uber.example/rag", company="Uber", title="Our RAG with an LLM", published="2026-11-01", text="")]
    posts, _ = cs.update([], fetched, "2026-11-09")
    by_url = {p["url"]: p for p in posts}
    assert by_url["https://aws.example/acme"]["company"] == "Acme Insurance"
    assert by_url["https://aws.example/acme"]["via"] == "AWS"
    assert by_url["https://uber.example/rag"]["company"] == "Uber" and "via" not in by_url["https://uber.example/rag"]
