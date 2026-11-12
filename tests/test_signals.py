"""
tests/test_signals.py
Measured signals: repo detection, star growth, snapshots and failure handling.
Every outside service is replaced by a fake.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import signals


def _p(pid, **extra):
    return {"id": pid, "title": f"Paper {pid}", "abstract": "We study models.", "hf_upvotes": 3, **extra}


def fakes(calls=None, **over):
    calls = calls if calls is not None else []

    def gh(repo):
        calls.append(("gh", repo))
        return {"stars": 120, "created": "2026-01-01", "license": True}

    def hf(pid):
        calls.append(("hf", pid))
        return {"hf_models": 1, "hf_datasets": 0, "hf_spaces": 2}

    def hn(pid):
        calls.append(("hn", pid))
        return {"hn_points": 42, "hn_comments": 7, "hn_url": "https://news.ycombinator.com/item?id=1"}

    def s2(ids):
        calls.append(("s2", tuple(ids)))
        return {pid: {"h_index": 12.0, "authors_found": 3} for pid in ids if pid != "new"}

    src = {"github": gh, "hf": hf, "hn": hn, "s2": s2}
    src.update(over)
    return src, calls


def test_repo_is_found_in_any_of_the_usual_places():
    assert signals.repo_of({"github_repo": "https://github.com/a/b"}) == "a/b"
    assert signals.repo_of({"code_url": "https://github.com/a/b.git/tree/main"}) == "a/b"
    assert signals.repo_of({"abstract": "Code at https://github.com/org/proj."}) == "org/proj"
    assert signals.repo_of({"code_url": "https://gitlab.com/a/b"}) == ""
    assert signals.repo_of({"abstract": "See https://github.com for details."}) == ""


def test_star_gain():
    assert signals.stars_gain(150, {"stars": 100}, "2025-01-01", "2026-11-12") == 50
    assert signals.stars_gain(90, {"stars": 100}, "2025-01-01", "2026-11-12") == 0
    assert signals.stars_gain(80, {}, "2026-11-05", "2026-11-12") == 80   # a new repo: all stars are new
    assert signals.stars_gain(80, {}, "2025-01-01", "2026-11-12") is None  # an old repo seen for the first time
    assert signals.stars_gain(None, {"stars": 1}, "", "2026-11-12") is None


def test_collect_looks_up_the_leaders_and_saves_a_snapshot(tmp_path):
    papers = [_p("a", github_repo="https://github.com/x/y"), _p("b"), _p("c")]
    src, calls = fakes()
    out = signals.collect(papers, "2026-11-12", data_dir=str(tmp_path), limit=2, sources=src)
    assert set(out) == {"a", "b"}
    assert ("gh", "x/y") in calls and ("hf", "c") not in calls
    assert papers[0]["signals"]["stars"] == 120 and papers[0]["signals"]["h_index"] == 12.0
    assert papers[1]["signals"]["stars"] is None and papers[1]["signals"]["repo"] is None
    assert "signals" not in papers[2]
    saved = json.load(open(tmp_path / "signals" / "2026-11-12.json"))
    assert saved["papers"]["a"]["hn_points"] == 42


def test_growth_comes_from_the_previous_snapshot(tmp_path):
    signals.save_snapshot("2026-11-11", {"a": {"stars": 100}}, str(tmp_path))
    papers = [_p("a", github_repo="https://github.com/x/y")]
    src, _ = fakes()
    signals.collect(papers, "2026-11-12", data_dir=str(tmp_path), sources=src)
    assert papers[0]["signals"]["stars_gain"] == 20


def test_a_paper_is_looked_up_once_a_day(tmp_path):
    papers = [_p("a")]
    src, calls = fakes()
    signals.collect(papers, "2026-11-12", data_dir=str(tmp_path), sources=src)
    n = len(calls)
    again = [_p("a")]
    signals.collect(again, "2026-11-12", data_dir=str(tmp_path), sources=src)
    assert len(calls) == n and again[0]["signals"]["hn_points"] == 42


def test_failures_leave_signals_unknown(tmp_path):
    def boom(*a):
        raise RuntimeError("rate limited")

    papers = [_p("a", github_repo="https://github.com/x/y"), _p("new")]
    src, _ = fakes(github=boom, hn=boom, s2=boom)
    signals.collect(papers, "2026-11-12", data_dir=str(tmp_path), sources=src)
    sig = papers[0]["signals"]
    assert sig["fetched"] and sig["stars"] is None and sig["hn_points"] is None and sig["h_index"] is None
    assert sig["hf_spaces"] == 2  # the sources that worked still count


def test_papers_semantic_scholar_has_not_indexed_stay_unknown(tmp_path):
    papers = [_p("a"), _p("new")]
    src, _ = fakes()
    signals.collect(papers, "2026-11-12", data_dir=str(tmp_path), sources=src)
    assert papers[0]["signals"]["h_index"] == 12.0 and papers[1]["signals"]["h_index"] is None


def test_s2_median_and_hn_parsing(monkeypatch):
    def post(url, body, headers=None, params=None):
        assert body == {"ids": ["ARXIV:1", "ARXIV:2"]}
        return [{"authors": [{"hIndex": 2}, {"hIndex": 40}, {"hIndex": 10}, {"hIndex": None}]}, None]

    monkeypatch.setattr(signals, "_post_json", post)
    assert signals.s2_authors(["1", "2"]) == {"1": {"h_index": 10, "authors_found": 3}}

    def get(url, headers=None, params=None):
        return {"hits": [{"url": "https://arxiv.org/abs/2611.00001", "points": 80, "num_comments": 20, "objectID": "9"},
                         {"url": "https://arxiv.org/abs/2611.00001v2", "points": 5, "num_comments": 1, "objectID": "8"},
                         {"url": "https://example.com/other", "points": 500, "num_comments": 1, "objectID": "7"}]}

    monkeypatch.setattr(signals, "_get_json", get)
    assert signals.hn_mentions("2611.00001") == {"hn_points": 85, "hn_comments": 21,
                                                 "hn_url": "https://news.ycombinator.com/item?id=9"}
