"""
tests/test_case_backfill.py
Growing the Case studies page (case_studies.backfill): the sources, one post per address and
title, reading older feed pages, and the stop rules (target, call cap, Groq's daily limit).
No network and no Groq: feeds and replies are stand-ins.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import case_studies as cs
from case_sources import BY_NAME, EXTRA_FEEDS, SOURCES

TODAY = "2026-11-13"


def _rss(items):
    body = "".join(f"<item><title>{t}</title><link>{u}</link><pubDate>{d}</pubDate>"
                   f"<description>How we built an LLM agent with RAG.</description></item>" for t, u, d in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{body}</channel></rss>'.encode()


def _saved_post(n, company="Acme", published="2026-10-01"):
    return {"url": f"https://acme.example/saved-{n}", "company": company, "title": f"Saved post {n}",
            "published": published, "problem": "rag", "summary": "x", "issue": "y", "tags": [], "v": cs.VERSION}


def _keep(post):
    return {"keep": True, "topic": "rag", "issue": "A problem.", "summary": "A fix.", "result": "", "tags": ["RAG"],
            "finder": {"techniques": ["rag"], "industry": "saas",
                       "build_details": {"architecture": True, "stack": False, "evaluation": False,
                                         "failure_modes": False, "numbers": False}, "build_score": 1}}


# ---------- sources

def test_new_sources_are_well_formed_and_not_duplicates():
    names = [s[0] for s in SOURCES]
    feeds = [s[1] for s in SOURCES] + [f for extra in EXTRA_FEEDS.values() for f in extra]
    assert len(names) == len(set(names)) and len(feeds) == len(set(feeds))
    for name in ("Figma", "Zapier", "Linear", "Plaid", "Affirm", "Character.AI", "Zepto", "Instawork", "eBay"):
        assert name in BY_NAME, name
    for name, extra in EXTRA_FEEDS.items():
        assert name in BY_NAME and all(f.startswith("https://") for f in extra)
    assert cs.feeds_of("Spotify", BY_NAME["Spotify"][1]) == [BY_NAME["Spotify"][1], "https://research.atspotify.com/feed/"]
    assert cs.feeds_of("Netflix", "https://netflixtechblog.com/feed") == ["https://netflixtechblog.com/feed"]


def test_every_new_source_has_a_logo_site():
    import case_logos
    for name in ("Figma", "Zapier", "Linear", "Plaid", "Affirm", "Character.AI", "Zepto", "Instawork", "eBay"):
        assert case_logos.SITES[name].startswith("https://"), name


# ---------- one post per address and title

def test_addresses_are_canonical():
    assert cs.normalise_url("http://Eng.Example.COM/Post-A/?utm_source=x#top") == "https://eng.example.com/Post-A"


def test_titles_match_however_they_are_written_but_only_within_a_company():
    assert cs.title_key("How we built  RAG &amp; agents!", "Acme") == cs.title_key("how we built rag agents", "Acme")
    assert cs.title_key("Intro", "Acme") != cs.title_key("Intro", "Other")
    assert cs.title_key("", "Acme") == ""


def test_the_same_post_under_a_second_address_is_skipped(monkeypatch):
    monkeypatch.setattr(cs, "groq_sort", _keep)
    saved = [{**_saved_post(1), "title": "Building an LLM agent"}]
    fetched = [{"url": "https://medium.com/acme/building-an-llm-agent-123", "company": "Acme",
                "title": "Building an LLM Agent", "published": "2026-11-01", "text": "LLM agent"},
               {"url": "https://acme.example/new", "company": "Acme", "title": "A new LLM post", "published": "2026-11-02", "text": ""},
               {"url": "https://acme.example/new-copy", "company": "Acme", "title": "A new LLM post", "published": "2026-11-02", "text": ""}]
    rejected = set()
    posts, counts = cs.update(saved, fetched, TODAY, rejected=rejected)
    assert counts["new"] == 1 and [p["url"] for p in posts][-1] == "https://acme.example/new"
    assert "https://medium.com/acme/building-an-llm-agent-123" in rejected


# ---------- reading further back

def test_older_pages_by_kind_of_blog():
    assert cs.older_pages("https://medium.com/feed/acme-tech")[0] == "https://medium.com/feed/acme-tech/tagged/machine-learning"
    assert "https://eng.acme.com/feed/?paged=2" in cs.older_pages("https://eng.acme.com/feed/")
    assert "https://blog.acme.com/rss/2/" in cs.older_pages("https://blog.acme.com/rss/")
    assert cs.older_pages("https://acme.com/blog/atom.xml") == []


def test_paging_stops_at_the_cutoff_and_when_pages_repeat():
    pages = {
        "https://eng.acme.com/feed/": _rss([("LLM post A", "https://eng.acme.com/a", "Mon, 02 Nov 2026 10:00:00 GMT")]),
        "https://eng.acme.com/feed/?paged=2": _rss([("LLM post B", "https://eng.acme.com/b", "Mon, 05 Jan 2026 10:00:00 GMT")]),
        "https://eng.acme.com/feed/?paged=3": _rss([("LLM post C", "https://eng.acme.com/c", "Mon, 06 Oct 2025 10:00:00 GMT")]),
        "https://eng.acme.com/feed/?paged=4": _rss([("LLM post D", "https://eng.acme.com/d", "Mon, 01 Sep 2025 10:00:00 GMT")]),
    }
    asked = []

    def fetch(url):
        asked.append(url)
        if url not in pages:
            raise OSError("404")
        return pages[url]
    got = cs.read_deep("Acme", "https://eng.acme.com/feed/", "2025-11-13", fetch)
    assert sorted(p["url"] for p in got) == ["https://eng.acme.com/a", "https://eng.acme.com/b"]
    assert "https://eng.acme.com/feed/?paged=4" not in asked  # page 3 was all older than the cutoff
    assert cs.read_deep("Acme", "https://down.example/feed/", "2025-11-13", fetch) == []


def test_candidates_skip_saved_rejected_old_and_non_ai_posts():
    saved = {"posts": [_saved_post(1)], "rejected": ["https://acme.example/no"],
             "queue": [{"url": "https://acme.example/queued", "company": "Acme", "title": "An LLM agent for support",
                        "published": "2026-09-01", "text": ""}]}
    feed = _rss([("Saved post 1", "https://acme.example/saved-copy", "Mon, 02 Nov 2026 10:00:00 GMT"),
                 ("Rejected one", "https://acme.example/no", "Mon, 02 Nov 2026 10:00:00 GMT"),
                 ("Fresh LLM post", "https://acme.example/fresh", "Mon, 02 Nov 2026 10:00:00 GMT"),
                 ("Old LLM post", "https://acme.example/old", "Mon, 01 Sep 2025 10:00:00 GMT"),
                 ("Now generally available: LLM thing", "https://acme.example/launch", "Mon, 02 Nov 2026 10:00:00 GMT")])
    cands, per = cs.backfill_candidates(saved, TODAY, fetch=lambda url: feed, deep=False,
                                        sources=[("Acme", "https://acme.example/feed.xml", "https://acme.example/", "", "000000")])
    assert sorted(p["url"] for p in cands) == ["https://acme.example/fresh", "https://acme.example/queued"]
    assert per == {"Acme": 2}


# ---------- the run: stops, cap, resume

def _setup(tmp_path, n_saved, n_candidates):
    path = str(tmp_path / "cases.json")
    cs.save([_saved_post(i, published="2026-10-0" + str(1 + i % 9)) for i in range(n_saved)], path,
            rejected=["https://acme.example/old-no"], last_fetch="2026-11-09")
    feed = _rss([(f"LLM agent post {i}", f"https://acme.example/c{i}", "Mon, 02 Nov 2026 10:00:00 GMT")
                 for i in range(n_candidates)])
    return path, (lambda url: feed if url == "https://acme.example/feed.xml" else (_ for _ in ()).throw(OSError("404")))


def _run(monkeypatch, tmp_path, n_saved, n_candidates, sorter, **kw):
    path, fetch = _setup(tmp_path, n_saved, n_candidates)
    monkeypatch.setattr(cs, "SOURCES", [("Acme", "https://acme.example/feed.xml", "https://acme.example/", "", "000000")])
    monkeypatch.setattr(cs, "EXTRA_FEEDS", {})
    return path, cs.backfill(path, fetch=fetch, sorter=sorter, reader=lambda url: "", sleep=lambda s: None,
                             today=TODAY, **kw)


def test_dry_run_counts_and_estimates_without_calling_groq(monkeypatch, tmp_path):
    def no_groq(post):
        raise AssertionError("the dry run called Groq")
    path, before = _setup(tmp_path, 3, 10)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    path, report = _run(monkeypatch, tmp_path, 3, 10, no_groq, target=5, dry_run=True)
    assert report["candidates"] == 10 and report["shown_before"] == 3 and report["need"] == 2
    assert report["estimated_calls"] == 5 and report["calls"] == 0 and report["stopped"] == "dry run"
    with open(path, encoding="utf-8") as f:
        assert f.read() == text  # nothing saved


def test_backfill_stops_at_the_target(monkeypatch, tmp_path):
    path, report = _run(monkeypatch, tmp_path, 3, 10, _keep, target=6)
    assert report["kept"] == 3 and report["calls"] == 3 and report["shown_after"] == 6
    assert report["stopped"] == "target reached"
    saved = cs.load_all(path)
    assert len(saved["posts"]) == 6 and saved["last_fetch"] == "2026-11-09"
    assert len(saved["queue"]) == 7  # the rest wait for the next run
    new = [p for p in saved["posts"] if p["url"].startswith("https://acme.example/c")]
    assert all(p["sorted_by"] == "groq" and p["industry"] == "saas" and p["issue"] for p in new)


def test_backfill_stops_at_the_call_cap_and_remembers_turn_downs(monkeypatch, tmp_path):
    replies = iter([{"keep": False}, None, _keep(None), {"keep": False}, _keep(None)])
    path, report = _run(monkeypatch, tmp_path, 1, 10, lambda post: next(replies), target=100, max_calls=4)
    assert report["calls"] == 4 and report["stopped"] == "call cap reached"
    assert (report["kept"], report["turned_down"], report["failed"]) == (1, 2, 1)
    saved = cs.load_all(path)
    assert len(saved["rejected"]) == 3  # the old one plus the two turned down
    assert len(saved["queue"]) == 10 - 3  # the unusable reply stays a candidate


def test_backfill_stops_at_groqs_daily_limit_and_carries_on_next_time(monkeypatch, tmp_path):
    calls = []

    def sorter(post):
        calls.append(post["url"])
        if len(calls) > 2:
            raise cs.GroqOutOfCalls("every model is at its daily limit")
        return _keep(post)
    path, report = _run(monkeypatch, tmp_path, 0, 5, sorter, target=100)
    assert report["kept"] == 2 and report["calls"] == 2 and report["stopped"].startswith("Groq out of calls")
    saved = cs.load_all(path)
    assert len(saved["posts"]) == 2 and len(saved["queue"]) == 3  # saved so far, and the rest left for tomorrow


def test_backfill_resumes_from_the_queue(monkeypatch, tmp_path):
    def sorter(post):
        raise cs.GroqOutOfCalls("limit")
    path, report = _run(monkeypatch, tmp_path, 0, 4, sorter, target=100)
    assert report["calls"] == 0 and len(cs.load_all(path)["queue"]) == 4
    # Next day: the feed has nothing new, but the queued posts are asked about
    monkeypatch.setattr(cs, "SOURCES", [("Acme", "https://acme.example/feed.xml", "https://acme.example/", "", "000000")])
    report = cs.backfill(path, fetch=lambda url: _rss([]), sorter=_keep, reader=lambda url: "", sleep=lambda s: None,
                         today=TODAY, target=100)
    assert report["kept"] == 4 and cs.load_all(path)["queue"] == []
