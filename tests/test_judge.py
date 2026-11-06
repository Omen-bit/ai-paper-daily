"""
tests/test_judge.py
Tests for judge.py, the pairwise LLM judge. A fake model stands in for Groq.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from langchain_core.runnables import RunnableLambda

import judge
from judge import Verdict


def _p(pid, title=None):
    return {"id": pid, "title": title or f"Paper {pid}", "abstract": f"Abstract of {pid}."}


def fake_llm(prefer_order, fail_every=0):
    """A model that prefers papers earlier in prefer_order, and fails every nth call."""
    calls = {"n": 0}

    def answer(messages):
        calls["n"] += 1
        if fail_every and calls["n"] % fail_every == 0:
            raise RuntimeError("429 rate limited")
        text = messages[-1].content
        a = text.split("Paper A\nTitle: ")[1].split("\n")[0]
        b = text.split("Paper B\nTitle: ")[1].split("\n")[0]
        return Verdict(winner="A" if prefer_order.index(a) < prefer_order.index(b) else "B",
                       reason=f"{min(a, b, key=prefer_order.index)} has stronger results.")
    return RunnableLambda(answer), calls


def test_the_paper_that_wins_most_pairs_is_the_pick():
    shortlist = [_p("1"), _p("2"), _p("3"), _p("4")]
    llm, calls = fake_llm(["Paper 3", "Paper 1", "Paper 4", "Paper 2"])
    verdict = judge.judge(shortlist, llm=llm, seed="2026-11-06")
    assert calls["n"] == 6  # every pair once
    assert verdict["winner"] == "3" and verdict["ranking"] == ["3", "1", "4", "2"]
    assert verdict["wins"] == {"3": 3, "1": 2, "4": 1, "2": 0}
    assert "Paper 3" in verdict["reason"]


def test_sides_are_shuffled_but_repeatable():
    shortlist = [_p(str(i)) for i in range(6)]
    first = [(r["a"], r["b"]) for r in judge.compare_all(shortlist, fake_llm([f"Paper {i}" for i in range(6)])[0], "d1")]
    again = [(r["a"], r["b"]) for r in judge.compare_all(shortlist, fake_llm([f"Paper {i}" for i in range(6)])[0], "d1")]
    assert first == again and len(first) == 15
    # Not every pair keeps the scorer's order on side A
    assert any(int(a) > int(b) for a, b in first)


def test_a_few_failures_still_give_a_verdict_but_many_do_not():
    shortlist = [_p(str(i)) for i in range(5)]  # 10 pairs
    order = [f"Paper {i}" for i in range(5)]
    assert judge.judge(shortlist, llm=fake_llm(order, fail_every=5)[0])["winner"] == "0"  # 2 of 10 fail
    assert judge.judge(shortlist, llm=fake_llm(order, fail_every=2)[0]) is None  # half fail


def test_ties_keep_the_scorers_order():
    shortlist = [_p("a"), _p("b"), _p("c")]
    rows = [{"a": "a", "b": "b", "winner": "b", "reason": ""},
            {"a": "b", "b": "c", "winner": "c", "reason": ""},
            {"a": "c", "b": "a", "winner": "a", "reason": ""}]
    assert judge.tally(shortlist, rows)["ranking"] == ["a", "b", "c"]


def test_a_broken_model_means_no_verdict():
    def boom(_):
        raise ValueError("bad key")
    assert judge.judge([_p("1"), _p("2")], llm=RunnableLambda(boom)) is None
    assert judge.judge([_p("1")], llm=RunnableLambda(boom)) is None


def test_enabled_needs_a_key_and_respects_the_switch(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("PICK_JUDGE", raising=False)
    assert not judge.enabled()
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    assert judge.enabled()
    monkeypatch.setenv("PICK_JUDGE", "off")
    assert not judge.enabled()


def test_the_prompt_shows_code_and_trims_long_abstracts():
    a = dict(_p("1"), abstract="x " * 2000, code_url="https://github.com/a/b")
    text = judge.pair_prompt(a, _p("2"))
    assert "Code released: yes" in text and "Code released: not stated" in text
    assert len(text) < 2 * judge.ABSTRACT_CHARS + 400


def test_make_llm_builds_a_fallback_chain(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("GROQ_MODELS", "openai/gpt-oss-120b,openai/gpt-oss-20b")
    assert type(judge.make_llm()).__name__ == "RunnableWithFallbacks"
    monkeypatch.setenv("GROQ_MODELS", "openai/gpt-oss-120b")
    assert type(judge.make_llm()).__name__ != "RunnableWithFallbacks"
