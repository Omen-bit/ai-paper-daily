"""
tests/test_claims.py
Benchmark claims: only claims quoted word for word from the abstract survive.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import claims

ABSTRACT = ("We introduce Foo, a small reasoning model. On GSM8K, Foo reaches 91.2% accuracy, "
            "beating larger baselines. It also improves MATH by 4.5 points over the base model.")


def test_verified_claims_need_the_exact_quote_and_number():
    good = {"task": "math", "benchmark": "GSM8K", "metric": "accuracy", "result": "91.2%",
            "quote": "On GSM8K, Foo reaches 91.2% accuracy, beating larger baselines."}
    assert claims.verify(good, ABSTRACT)
    assert claims.verify({**good, "quote": good["quote"].upper()}, ABSTRACT)  # case and spacing don't matter
    assert not claims.verify({**good, "result": "93.0%"}, ABSTRACT)              # number not in the quote
    assert not claims.verify({**good, "quote": "On GSM8K, Foo reaches 95% accuracy."}, ABSTRACT)  # made up
    assert not claims.verify({**good, "benchmark": "HumanEval"}, ABSTRACT)      # benchmark not in the abstract
    assert not claims.verify({**good, "result": "high"}, ABSTRACT)              # no number


def test_checked_drops_duplicates_and_inventions():
    raw = [{"benchmark": "GSM8K", "result": "91.2%", "quote": "On GSM8K, Foo reaches 91.2% accuracy"},
           {"benchmark": "GSM8K", "result": "91.2", "quote": "On GSM8K, Foo reaches 91.2% accuracy"},
           {"benchmark": "MATH", "result": "4.5 points", "quote": "It also improves MATH by 4.5 points over the base model."},
           {"benchmark": "ARC", "result": "70%", "quote": "On ARC, Foo reaches 70%."}]
    out = claims.checked(raw, ABSTRACT)
    assert [c["benchmark"] for c in out] == ["GSM8K", "MATH"]


class FakeLLM:
    def __init__(self):
        self.sent = 0

    def batch(self, inputs, config=None, return_exceptions=False):
        self.sent += len(inputs)
        return [{"claims": [{"task": "math", "benchmark": "GSM8K", "metric": "accuracy", "result": "91.2%",
                             "quote": "On GSM8K, Foo reaches 91.2% accuracy, beating larger baselines."},
                            {"task": "code", "benchmark": "HumanEval", "metric": "pass@1", "result": "80%",
                             "quote": "Foo reaches 80% on HumanEval."}]}
                for _ in inputs]


def test_extract_caches_by_id_and_never_sends_a_paper_twice(tmp_path):
    path = str(tmp_path / "claims.json")
    llm = FakeLLM()
    papers = [{"id": "1", "abstract": ABSTRACT}]
    assert claims.extract(papers, llm=llm, path=path, today="2026-11-12") == 1
    assert [c["benchmark"] for c in papers[0]["claims"]] == ["GSM8K"]
    saved = json.load(open(path))
    assert saved["1"]["proposed"] == 2 and len(saved["1"]["claims"]) == 1
    again = [{"id": "1", "abstract": ABSTRACT}]
    assert claims.extract(again, llm=llm, path=path) == 0
    assert llm.sent == 1 and again[0]["claims"][0]["result"] == "91.2%"


def test_without_a_key_only_the_cache_is_used(tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    path = str(tmp_path / "claims.json")
    papers = [{"id": "1", "abstract": ABSTRACT}]
    assert claims.extract(papers, path=path) == 0
    assert "claims" not in papers[0]


def test_a_failed_answer_is_retried_another_day(tmp_path):
    class Broken:
        def batch(self, inputs, config=None, return_exceptions=False):
            return [RuntimeError("429")]

    path = str(tmp_path / "claims.json")
    papers = [{"id": "1", "abstract": ABSTRACT}]
    claims.extract(papers, llm=Broken(), path=path)
    assert claims.load(path) == {}
