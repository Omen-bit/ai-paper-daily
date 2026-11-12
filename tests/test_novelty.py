"""
tests/test_novelty.py
Novelty: TF-IDF distance from the papers of the last 90 days.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import novelty

FILLER = ["retrieval", "robotics", "diffusion", "speech", "graphs", "tabular", "protein", "weather",
          "compiler", "music", "finance", "chemistry", "traffic", "legal", "medical", "satellite"]


def _past(n=80):
    out = []
    for i in range(n):
        a, b = FILLER[i % len(FILLER)], FILLER[(i * 7 + 3) % len(FILLER)]
        out.append({"id": f"p{i}", "title": f"{a} {b} study {i}",
                    "abstract": f"We apply {a} techniques to {b} problems with benchmark{i} evaluation."})
    out.append({"id": "twin", "title": "Sparse mixture routing for long context transformers",
                "abstract": "Sparse mixture routing lets long context transformers scale with gating experts."})
    return out


def test_a_near_copy_is_less_novel_than_a_new_idea():
    papers = [{"id": "copy", "title": "Sparse mixture routing for long context transformers",
               "abstract": "Sparse mixture routing lets long context transformers scale with gating experts."},
              {"id": "fresh", "title": "Origami folding planners for soft grippers",
               "abstract": "Origami folding planners give soft grippers crease-aware dexterity."}]
    assert novelty.score(papers, "2026-11-12", past=_past()) == 2
    assert papers[0]["novelty"] < 0.2 and papers[0]["closest"] == "twin"
    assert papers[1]["novelty"] > 0.8


def test_too_little_history_skips_novelty():
    papers = [{"id": "x", "title": "t", "abstract": "a"}]
    assert novelty.score(papers, "2026-11-12", past=_past(10)) == 0
    assert "novelty" not in papers[0]


def test_a_paper_is_never_compared_with_itself():
    past = _past()
    papers = [dict(past[-1])]
    novelty.score(papers, "2026-11-12", past=past)
    assert papers[0]["closest"] != "twin"


def test_history_reads_the_last_90_days(tmp_path):
    os.makedirs(tmp_path / "daily")
    for d, pid in [("2026-11-11", "recent"), ("2026-07-01", "old"), ("2026-11-12", "today")]:
        json.dump({"date": d, "papers": [{"id": pid, "title": "t", "abstract": "a b c"}]},
                  open(tmp_path / "daily" / f"{d}.json", "w"))
    assert [r["id"] for r in novelty.history("2026-11-12", str(tmp_path))] == ["recent"]
