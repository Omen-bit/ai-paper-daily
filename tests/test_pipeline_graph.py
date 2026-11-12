"""
tests/test_pipeline_graph.py
The daily pipeline graph, end to end, with every outside call replaced.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pipeline_graph


def _p(pid, upvotes=0, topic="llms"):
    return {"id": pid, "title": f"Paper {pid}", "abstract": "We study models.", "authors": ["A"],
            "source": "HuggingFace" if upvotes else "arXiv", "hf_upvotes": upvotes,
            "submitted": "2026-11-05", "categories": [{"slug": topic}]}


def deps(tmp_path, papers, **over):
    calls = {"saved": None, "judge": 0}

    def save_day(all_papers, selected, date_str):
        calls["saved"] = (len(all_papers), [p["id"] for p in selected], date_str)

    def fake_judge(shortlist, seed=""):
        calls["judge"] += 1
        last = shortlist[-1]["id"]  # a judge that disagrees with the scorer
        return {"winner": last, "wins": {last: len(shortlist) - 1}, "reason": "Clearer results.",
                "ranking": [last], "done": 1, "total": 1}

    d = {
        "recent_featured": lambda n: {"old"},
        "fetch_all_papers": lambda: [dict(p) for p in papers],
        "fetch_hf_papers_for_date": lambda d: [],
        "classify_papers": lambda ps: ps,
        "judge_enabled": lambda: True,
        "judge": fake_judge,
        "curate_papers": lambda s: s,
        "summarize_papers": lambda s: s,
        "save_day": save_day,
        "data_dir": str(tmp_path),
        "shortlist_size": 3,
        "score_novelty": lambda papers, date, data_dir=None: 0,
        "collect_signals": lambda papers, date, data_dir=None: {},
        "extract_claims": lambda papers: 0,
        "claims_size": 8,
    }
    d.update(over)
    return d, calls


def test_a_near_tie_goes_to_the_judge_and_its_pick_is_saved(tmp_path, monkeypatch):
    monkeypatch.delenv("PICK_FROM", raising=False)
    # 50, 45 and 40 upvotes score 17, 17 and 16: all within 3 points, so the judge breaks the tie
    papers = [_p("old", 99), _p("a", 50), _p("b", 45, "vision"), _p("c", 40, "robotics"), _p("d", 1)]
    d, calls = deps(tmp_path, papers)
    state = pipeline_graph.run_day("2026-11-06", d)
    assert state["status"] == "ok" and calls["judge"] == 1
    assert [p["id"] for p in state["shortlist"]] == ["a", "b", "c"]  # "old" was featured recently
    assert [p["id"] for p in state["tied"]] == ["a", "b", "c"]
    assert state["selected"][0]["id"] == "c" and state["selected"][0]["slot"] == "pick"
    assert state["selected"][0]["judge"]["reason"] == "Clearer results."
    assert state["selected"][0]["judge"]["tie_break"] is True
    assert calls["saved"] == (4, ["c", "a"], "2026-11-06")


def test_a_clear_leader_never_reaches_the_judge(tmp_path, monkeypatch):
    monkeypatch.delenv("PICK_FROM", raising=False)
    papers = [_p("a", 200), _p("b", 3, "vision"), _p("c", 1, "robotics")]
    d, calls = deps(tmp_path, papers)
    state = pipeline_graph.run_day("2026-11-06", d)
    assert calls["judge"] == 0 and state["selected"][0]["id"] == "a"
    assert "judge" not in state["selected"][0]


def test_evidence_feeds_the_score(tmp_path, monkeypatch):
    monkeypatch.delenv("PICK_FROM", raising=False)
    seen = {}

    def collect(papers, date, data_dir=None):
        seen["order"] = [p["id"] for p in papers]
        for p in papers:
            if p["id"] == "b":  # the less upvoted paper has a popular repo and a big HN thread
                p["signals"] = {"fetched": True, "repo": "x/y", "stars": 900, "stars_gain": 400,
                                "hn_points": 300, "h_index": None}
        return {}

    def claims(papers):
        seen["claims"] = [p["id"] for p in papers]
        return 0

    d, calls = deps(tmp_path, [_p("a", 60), _p("b", 20, "vision")], collect_signals=collect, extract_claims=claims)
    state = pipeline_graph.run_day("2026-11-06", d)
    assert seen["order"] == ["a", "b"]  # looked up best first
    assert seen["claims"][0] == "b"     # claims are read for the new order
    assert state["selected"][0]["id"] == "b"
    assert state["selected"][0]["evidence"]["stars"] == 900


def test_a_failing_evidence_source_does_not_stop_the_edition(tmp_path, monkeypatch):
    monkeypatch.delenv("PICK_FROM", raising=False)

    def boom(*a, **k):
        raise RuntimeError("service down")

    d, _ = deps(tmp_path, [_p("a", 50), _p("b", 5, "vision")], collect_signals=boom, score_novelty=boom,
                extract_claims=boom)
    state = pipeline_graph.run_day("2026-11-06", d)
    assert state["status"] == "ok" and state["selected"][0]["id"] == "a"


def test_without_the_judge_the_best_score_is_the_pick(tmp_path, monkeypatch):
    monkeypatch.delenv("PICK_FROM", raising=False)
    d, calls = deps(tmp_path, [_p("a", 50), _p("b", 30, "vision")], judge_enabled=lambda: False)
    state = pipeline_graph.run_day("2026-11-06", d)
    assert calls["judge"] == 0 and state["selected"][0]["id"] == "a"
    assert "judge" not in state["selected"][0]


def test_a_judge_with_no_verdict_keeps_the_scorers_pick(tmp_path, monkeypatch):
    monkeypatch.delenv("PICK_FROM", raising=False)
    d, _ = deps(tmp_path, [_p("a", 50), _p("b", 30, "vision")], judge=lambda shortlist, seed="": None)
    assert pipeline_graph.run_day("2026-11-06", d)["selected"][0]["id"] == "a"


def test_nothing_fetched_stops_before_saving(tmp_path):
    d, calls = deps(tmp_path, [])
    state = pipeline_graph.run_day("2026-11-06", d)
    assert state["status"] == "no_papers" and calls["saved"] is None


def test_failing_notes_still_save_the_edition(tmp_path, monkeypatch):
    monkeypatch.delenv("PICK_FROM", raising=False)

    def boom(selected):
        raise RuntimeError("Groq is down")
    d, calls = deps(tmp_path, [_p("a", 50), _p("b", 30, "vision")], curate_papers=boom, summarize_papers=boom,
                    judge_enabled=lambda: False)
    assert pipeline_graph.run_day("2026-11-06", d)["status"] == "ok"
    assert calls["saved"][1] == ["a", "b"]


def test_yesterday_mode_picks_from_the_saved_day_and_saves_today(tmp_path, monkeypatch):
    monkeypatch.setenv("PICK_FROM", "yesterday")
    os.makedirs(tmp_path / "daily")
    old = [{"id": "y1", "title": "Y1", "abstract": "Old.", "categories": ["llms"], "hf_upvotes": 80,
            "source": "HuggingFace"}, {"id": "y2", "title": "Y2", "abstract": "Old.", "categories": ["vision"],
                                       "hf_upvotes": 10, "source": "HuggingFace"}]
    (tmp_path / "daily" / "2026-11-05.json").write_text(json.dumps({"date": "2026-11-05", "featured": [], "papers": old}))
    d, calls = deps(tmp_path, [_p("t1", 5), _p("t2")], judge_enabled=lambda: False)
    state = pipeline_graph.run_day("2026-11-06", d)
    assert state["pool_source"] == "2026-11-05"
    assert [p["id"] for p in state["selected"]] == ["y1", "y2"]
    assert calls["saved"][0] == 2  # today's two papers are still saved for tomorrow
    assert all("score" in p for p in state["papers"])


def test_the_graph_has_the_documented_steps():
    graph = pipeline_graph.build_graph(deps("/tmp", [])[0])
    nodes = set(graph.get_graph().nodes)
    assert {"fetch", "classify", "choose_pool", "evidence", "shortlist", "judge", "pick", "notes", "save"} <= nodes
