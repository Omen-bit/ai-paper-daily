"""
tests/test_run_evals.py
The eval case files and the scoring in scripts/run_evals.py. No network: a fake
session stands in for Supabase.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import run_evals


def test_the_case_files_are_well_formed():
    scout, ask = run_evals.load_cases("scout"), run_evals.load_cases("ask")
    assert len(scout) >= 20 and len(ask) >= 25
    for cases in (scout, ask):
        ids = [c["id"] for c in cases]
        assert len(ids) == len(set(ids))
    for c in scout:
        assert len(c["description"]) >= 40 and c["expected"]
        assert all(run_evals.ID.match(pid) for pid in c["expected"])
    for c in ask:
        assert run_evals.ID.match(c["paper"]) and c["question"].strip()
        assert isinstance(c["answerable"], bool)
        assert c["reference"].strip() or not c["answerable"]
    assert any(not c["answerable"] for c in ask)


def test_scout_scoring():
    case = {"id": "x", "expected": ["2611.00002", "2611.00009"]}
    reply = {"mode": "ai", "engine": "langgraph", "expanded": ["zero-shot tagging"],
             "plan": [{"id": "2611.00001", "fit": "strong"}, {"id": "2611.00002", "fit": "related"}],
             "coverage": [{"status": "covered"}, {"status": "missing"}, {"status": "partial"}]}
    row = run_evals.score_scout(case, reply)
    assert row["hit"] and row["first_rank"] == 2 and row["rr"] == 0.5
    assert not row["strong_hit"] and row["missing"] == 1 and row["needs"] == 3
    assert row["engine"] == "langgraph" and row["searched_again"] == ["zero-shot tagging"]
    assert not run_evals.score_scout(case, {"plan": []})["hit"]


def test_scout_summary_skips_errors():
    rows = [{"hit": True, "rr": 1.0, "strong_hit": True, "needs": 2, "missing": 0, "mode": "ai",
             "searched_again": ["x"], "seconds": 9.0},
            {"hit": False, "rr": 0.0, "strong_hit": False, "needs": 2, "missing": 1, "mode": "basic"},
            {"id": "z", "error": "500"}]
    s = run_evals.summarize_scout(rows)
    assert s["hit@10"] == 0.5 and s["mrr"] == 0.5 and s["errors"] == 1 and s["missing_needs"] == 0.25
    assert s["second_round"] == 0.5


def test_ask_scoring_uses_the_grader_only_when_it_should():
    graded = []

    def grade(case, answer):
        graded.append(case["id"])
        return "35.3%" in answer
    good = {"id": "a", "question": "q", "reference": "r", "answerable": True}
    assert run_evals.score_ask(good, {"answer": "It uses 35.3% of the FLOPs.", "quote": "35.3%"}, grade)["correct"]
    # An answerable question the paper "doesn't say" is wrong, without asking the grader
    row = run_evals.score_ask(good, {"answer": "The paper doesn't say.", "answerable": False}, grade)
    assert row["correct"] is False and row["declined"]
    tricky = {"id": "b", "question": "q", "reference": "Not stated.", "answerable": False}
    assert run_evals.score_ask(tricky, {"answer": "The abstract does not mention the GPU count."}, grade)["correct"]
    assert not run_evals.score_ask(tricky, {"answer": "It used 8 GPUs.", "quote": "8 GPUs"}, grade)["correct"]
    assert graded == ["a"]
    assert run_evals.score_ask(good, {"answer": "Something."})["correct"] is None  # no grader


def test_ask_summary():
    rows = [{"answerable": True, "correct": True, "quoted": True, "declined": False, "mode": "full"},
            {"answerable": True, "correct": None, "quoted": False, "declined": False, "mode": "abstract"},
            {"answerable": False, "correct": True, "quoted": False, "declined": True, "mode": "abstract"}]
    s = run_evals.summarize_ask(rows)
    assert s["graded"] == 2 and s["correct"] == 1.0 and s["quoted"] == 0.5
    assert s["declines_when_it_should"] == 1.0 and s["declines_when_it_shouldnt"] == 0.0


class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self._body = status, body
        self.content = json.dumps(body).encode()
        self.text = self.content.decode()

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, replies):
        self.replies, self.sent = list(replies), []

    def post(self, url, json=None, headers=None, timeout=None):
        self.sent.append((url, json, headers))
        return self.replies.pop(0)


def test_run_suite_sends_the_secret_and_keeps_going_after_an_error():
    cases = [{"id": "one", "description": "d" * 50, "expected": ["2611.00001"]},
             {"id": "two", "description": "e" * 50, "expected": ["2611.00002"]}]
    session = FakeSession([FakeResponse(429, {"error": "Slow down."}),
                           FakeResponse(200, {"plan": [{"id": "2611.00002", "fit": "strong"}], "coverage": []})])
    rows = run_evals.run_suite("scout", cases, "https://x.supabase.co", "s3cret", session=session,
                               sleep=lambda s: (_ for _ in ()).throw(AssertionError("no pacing with a secret")))
    assert "429" in rows[0]["error"] and rows[1]["hit"] and rows[1]["strong_hit"]
    url, body, headers = session.sent[0]
    assert url == "https://x.supabase.co/functions/v1/scout" and headers["x-sync-secret"] == "s3cret"
    assert body == {"description": "d" * 50}


def test_run_suite_paces_without_a_secret():
    cases = [{"id": f"p-{i}", "paper": "2611.00001", "question": "Why?", "reference": "r", "answerable": True}
             for i in range(3)]
    session = FakeSession([FakeResponse(200, {"answer": "Because.", "quote": "x"})] * 3)
    waits = []
    rows = run_evals.run_suite("ask", cases, "https://x", "", session=session, sleep=waits.append)
    assert waits == [run_evals.PACE_SECONDS["ask"]] * 2 and len(rows) == 3
    assert "x-sync-secret" not in session.sent[0][2]


def test_results_are_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(run_evals, "RESULTS_DIR", str(tmp_path))
    path = run_evals.save("scout", [{"id": "a"}], {"hit@10": 1.0}, "2026-11-06")
    assert os.path.basename(path) == "2026-11-06-scout.json"
    assert json.load(open(path))["summary"] == {"hit@10": 1.0}


def test_no_grader_without_a_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert run_evals.make_grader() is None
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    assert callable(run_evals.make_grader())
