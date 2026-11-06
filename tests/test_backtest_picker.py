"""
tests/test_backtest_picker.py
Tests for scripts/backtest_picker.py: loading saved days, scoring a pick
against later upvotes, and the Hugging Face cache. No network is used.
"""
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import backtest_picker as bt


def record(pid, upvotes=0, abstract="We propose a method.", **extra):
    return {"id": pid, "title": f"Paper {pid}", "abstract": abstract, "authors": ["A"],
            "categories": ["llms"], "source": "HuggingFace" if upvotes else "arXiv",
            "hf_upvotes": upvotes, **extra}


def write_day(data_dir, day, papers, featured=()):
    path = os.path.join(data_dir, "daily", f"{day}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"date": day, "featured": list(featured), "papers": papers}, f)


def test_load_days_skips_days_without_abstracts(tmp_path):
    write_day(tmp_path, "2026-10-30", [record("1", abstract=""), record("2", abstract="")])
    write_day(tmp_path, "2026-10-31", [record("3", 5), record("4")], featured=["3"])
    with open(os.path.join(tmp_path, "daily", "broken.json"), "w") as f:
        f.write("{not json")
    days = bt.load_days(str(tmp_path))
    assert [d["date"] for d in days] == ["2026-10-31"]
    assert days[0]["featured"] == ["3"]
    assert days[0]["pool"][0]["hf_upvotes"] == 5


def test_judge_ranks_against_later_upvotes():
    pool = [{"id": str(i)} for i in range(5)]
    later = {"0": 50, "1": 40, "2": 40, "3": 0}
    best = bt.judge("0", pool, later, top_k=2)
    assert best["hit"] and best["pctile"] == 1.0 and best["capture"] == 1.0
    tied = bt.judge("2", pool, later, top_k=2)  # ties share second place
    assert tied["hit"] and tied["capture"] == 0.8
    none = bt.judge("4", pool, later, top_k=2)  # never on HF
    assert not none["hit"] and none["later_upvotes"] == 0 and none["capture"] == 0.0


def test_zero_upvotes_is_never_a_hit_even_in_a_quiet_pool():
    pool = [{"id": "a"}, {"id": "b"}]
    assert not bt.judge("a", pool, {}, top_k=10)["hit"]


def test_random_hit_rate():
    pool = [{"id": str(i)} for i in range(4)]
    assert bt.random_hit_rate(pool, {"0": 9, "1": 3}, top_k=1) == 0.25
    assert bt.random_hit_rate(pool, {"0": 9, "1": 3}, top_k=10) == 0.5


def test_run_backtest_skips_young_days_and_scores_each_picker():
    days = [
        {"date": "2026-11-01", "featured": [], "pool": [bt.to_paper(record("a", 30)), bt.to_paper(record("b", 1))]},
        {"date": "2026-11-05", "featured": [], "pool": [bt.to_paper(record("c", 9)), bt.to_paper(record("d"))]},
    ]
    later = {"a": 10, "b": 80}  # the paper with fewer upvotes at pick time won later
    result = bt.run_backtest(days, later, min_age=3, today=date(2026, 11, 6), top_k=1)
    assert result["days_judged"] == 1
    for name in ("current", "upvotes-now"):
        s = result["summary"][name]
        assert s["days"] == 1 and s["hit_rate"] == 0.0 and s["second_hit_rate"] == 1.0
    assert result["summary"]["_random"]["hit_rate"] == 0.5
    assert "2026-11-01" in bt.report(result)


def test_current_picker_does_not_change_the_saved_pool():
    pool = [bt.to_paper(record("a", 30)), bt.to_paper(record("b"))]
    before = json.dumps(pool, sort_keys=True)
    assert bt.pick_current(pool)[0] == "a"
    assert json.dumps(pool, sort_keys=True) == before


def test_hf_upvotes_are_cached_and_recent_lists_refreshed(tmp_path):
    days = [{"date": "2026-10-20", "featured": [], "pool": [bt.to_paper(record("old", 2))]},
            {"date": "2026-11-05", "featured": [], "pool": [bt.to_paper(record("new", 1))]}]
    calls = []

    def fetch(d):
        calls.append(d)
        return [{"id": "old", "hf_upvotes": 70}] if d == "2026-10-20" else [{"id": "new", "hf_upvotes": len(calls)}]

    cache = str(tmp_path / "hf.json")
    today = date(2026, 11, 6)
    later = bt.upvotes_from_hf(days, cache, fetch=fetch, today=today)
    assert later["old"] == 70 and later["new"] >= 1
    first = len(calls)
    assert first == len(bt.hf_dates(days, today))
    assert "2026-11-07" not in calls  # no lists from the future

    calls.clear()
    bt.upvotes_from_hf(days, cache, fetch=fetch, today=today)
    assert calls and all(d >= "2026-10-30" for d in calls)  # settled lists come from the cache


def test_failed_fetch_keeps_the_cached_list(tmp_path):
    days = [{"date": "2026-11-05", "featured": [], "pool": [bt.to_paper(record("x", 1))]}]
    cache = str(tmp_path / "hf.json")
    today = date(2026, 11, 6)
    bt.upvotes_from_hf(days, cache, fetch=lambda d: [{"id": "x", "hf_upvotes": 40}], today=today)
    later = bt.upvotes_from_hf(days, cache, fetch=lambda d: [], today=today)
    assert later["x"] == 40


def test_main_offline_prints_a_report(tmp_path, capsys):
    write_day(tmp_path, "2026-10-01", [record("a", 30), record("b", 1)])
    out_json = tmp_path / "result.json"
    assert bt.main(["--offline", "--data", str(tmp_path), "--json", str(out_json)]) == 0
    assert "current" in capsys.readouterr().out
    assert json.loads(out_json.read_text())["upvote_source"] == "saved files"


def test_late_days_pick_from_the_previous_day_with_newer_upvotes():
    days = [
        {"date": "2026-11-01", "featured": ["x"], "pool": [bt.to_paper(record("x", 50)), bt.to_paper(record("a", 2))]},
        {"date": "2026-11-02", "featured": ["a"], "pool": [bt.to_paper(record("a", 30)), bt.to_paper(record("b", 9)),
                                                           bt.to_paper(record("c"))]},
        {"date": "2026-11-03", "featured": [], "pool": [bt.to_paper(record("d", 1))]},
        {"date": "2026-11-09", "featured": [], "pool": [bt.to_paper(record("e")), bt.to_paper(record("f"))]},
    ]
    late = bt.late_days(days)
    # 11-02 would pick from 11-01 (minus x, featured that day): only "a" is left, too few
    # 11-03 picks from 11-02 minus the recent picks x and a; 11-09 is too far from 11-03
    assert [d["date"] for d in late] == ["2026-11-03"]
    assert [p["id"] for p in late[0]["pool"]] == ["b", "c"] and late[0]["from"] == "2026-11-02"


def test_late_days_refresh_upvotes_from_the_next_saved_day():
    days = [
        {"date": "2026-11-01", "featured": [], "pool": [bt.to_paper(record("a", 2)), bt.to_paper(record("b"))]},
        {"date": "2026-11-02", "featured": [], "pool": [bt.to_paper(record("a", 30))]},
    ]
    pool = bt.late_days(days)[0]["pool"]
    assert {p["id"]: p["hf_upvotes"] for p in pool} == {"a": 30, "b": 0}
    assert days[0]["pool"][0]["hf_upvotes"] == 2  # the saved day itself is untouched


def test_main_day_late_adds_its_row(tmp_path, capsys):
    write_day(tmp_path, "2026-10-01", [record("a", 30), record("b", 1), record("c", 4)], featured=["a"])
    write_day(tmp_path, "2026-10-02", [record("b", 20), record("d", 1)])
    assert bt.main(["--offline", "--day-late", "--data", str(tmp_path)]) == 0
    assert "day-late" in capsys.readouterr().out
