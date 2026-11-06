"""
tests/test_pick_pool.py
Tests for pick_pool.py: picking from today's papers or yesterday's candidates.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import paper_store
import pick_pool


def _rec(pid, upvotes=0, **extra):
    return {"id": pid, "title": f"Paper {pid}", "authors": ["A"], "abstract": "We study models.",
            "categories": ["llms"], "source": "HuggingFace" if upvotes else "arXiv",
            "hf_upvotes": upvotes, "featured": False, **extra}


def _save(data_dir, day, papers, featured=()):
    path = os.path.join(data_dir, "daily", f"{day}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"date": day, "featured": list(featured), "papers": papers}, f)


def test_mode_defaults_to_today_and_rejects_unknown_values(monkeypatch):
    monkeypatch.delenv("PICK_FROM", raising=False)
    assert pick_pool.mode() == "today"
    assert pick_pool.mode(" Yesterday ") == "yesterday"
    assert pick_pool.mode("last-week") == "today"
    monkeypatch.setenv("PICK_FROM", "yesterday")
    assert pick_pool.mode() == "yesterday"


def test_today_mode_returns_todays_papers_unchanged(tmp_path):
    today = [{"id": "t1"}]
    papers, source = pick_pool.candidates("2026-11-06", today, set(), pick_from="today", data_dir=str(tmp_path))
    assert papers is today and source == "today"


def test_yesterday_mode_uses_the_previous_day_with_fresh_upvotes(tmp_path):
    _save(tmp_path, "2026-11-05", [_rec("a", 3, featured=True), _rec("b", 2), _rec("c"), _rec("d", 1)],
          featured=["a"])
    todays = [{"id": "b", "source": "HuggingFace", "hf_upvotes": 40, "github_repo": "https://github.com/x/b"}]
    hf_list = [{"id": "c", "source": "HuggingFace", "hf_upvotes": 9, "hf_org": {"name": "nvidia"}},
               {"id": "b", "source": "HuggingFace", "hf_upvotes": 25}]
    asked = []

    def fetch(d):
        asked.append(d)
        return hf_list

    papers, source = pick_pool.candidates("2026-11-06", todays, {"d"}, pick_from="yesterday",
                                          data_dir=str(tmp_path), fetch_for_date=fetch)
    assert source == "2026-11-05" and asked == ["2026-11-05"]
    by_id = {p["id"]: p for p in papers}
    assert set(by_id) == {"b", "c"}  # a was featured that day, d recently
    assert by_id["b"]["hf_upvotes"] == 40 and by_id["b"]["github_repo"] == "https://github.com/x/b"
    assert by_id["c"]["hf_upvotes"] == 9 and by_id["c"]["source"] == "arXiv + HuggingFace"
    assert by_id["c"]["hf_org"] == {"name": "nvidia"}
    assert by_id["c"]["categories"] == ["llms"]


def test_yesterday_mode_falls_back_to_today(tmp_path):
    today = [{"id": "t1"}]
    # Nothing saved at all
    assert pick_pool.candidates("2026-11-06", today, set(), "yesterday", str(tmp_path))[1] == "today"
    # Everything from yesterday was already featured
    _save(tmp_path, "2026-11-05", [_rec("a", 3)], featured=["a"])
    assert pick_pool.candidates("2026-11-06", today, set(), "yesterday", str(tmp_path))[1] == "today"


def test_a_failed_refresh_keeps_the_saved_upvotes(tmp_path):
    _save(tmp_path, "2026-11-05", [_rec("a", 7), _rec("b")])

    def boom(d):
        raise RuntimeError("HF is down")

    papers, source = pick_pool.candidates("2026-11-06", [], set(), "yesterday", str(tmp_path), fetch_for_date=boom)
    assert source == "2026-11-05" and {p["id"]: p["hf_upvotes"] for p in papers} == {"a": 7, "b": 0}


def test_previous_day_skips_gaps_but_not_too_far(tmp_path):
    _save(tmp_path, "2026-11-01", [_rec("a")])
    assert paper_store.previous_day("2026-11-04", str(tmp_path))["date"] == "2026-11-01"
    assert paper_store.previous_day("2026-11-06", str(tmp_path)) is None
    with open(os.path.join(tmp_path, "daily", "2026-11-05.json"), "w") as f:
        f.write("{broken")
    assert paper_store.previous_day("2026-11-06", str(tmp_path)) is None


def test_to_paper_round_trips_a_saved_record():
    rec = paper_store.to_record({"id": "2611.1", "title": "T", "abstract": "A", "hf_upvotes": 4,
                                 "categories": [{"slug": "llms"}], "org": "NVIDIA",
                                 "badges": [("⭐", "Top Pick")]}, "2026-11-05", featured=True)
    paper = paper_store.to_paper(rec)
    assert paper["categories"] == ["llms"] and paper["org"] == "NVIDIA" and paper["hf_upvotes"] == 4
    assert "badges" not in paper and "curator" not in paper
    again = paper_store.to_record(dict(paper, org_avatar="https://x/logo.png"), "2026-11-06", featured=True)
    assert again["org_avatar"] == "https://x/logo.png"
