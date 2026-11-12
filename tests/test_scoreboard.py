"""
tests/test_scoreboard.py
The scoreboard: outcomes, percentiles, metrics and the ablation rankers.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import scoreboard


def _r(i, score=0, upvotes=0, parts=None, repo=""):
    return {"id": f"p{i:03d}", "title": f"Paper {i}", "abstract": "We study models." + (f" {repo}" if repo else ""),
            "score": score, "hf_upvotes": upvotes, "score_parts": parts, "categories": []}


def test_percentiles_share_ties():
    assert scoreboard.percentiles({"a": 0, "b": 0, "c": 5}) == {"a": 0.25, "b": 0.25, "c": 1.0}


def test_metrics_reward_a_ranker_that_matches_the_outcome():
    target = {f"p{i}": i for i in range(30)}
    perfect = sorted(target, key=lambda k: -target[k])
    worst = list(reversed(perfect))
    good, bad = scoreboard.day_metrics(perfect, target), scoreboard.day_metrics(worst, target)
    assert good == {"hit": True, "p10": 1.0, "spearman": 1.0}
    assert bad["hit"] is False and bad["p10"] == 0.0 and bad["spearman"] == -1.0


def test_outcomes_use_links_then_github_and_skip_fresh_entries():
    days = [{"date": "2026-10-01", "records": [_r(1, repo="https://github.com/a/b"), _r(2, repo="https://github.com/c/d"),
                                              _r(3)]}]
    calls = []
    cache = {"p003": {"citations": 9, "stars": 0, "as_of": "2026-11-10"}}
    out = scoreboard.fetch_outcomes(days, cache, links={"p001": {"stars": 50}},
                                    cite_fn=lambda ids: calls.append(ids) or {i: 4 for i in ids},
                                    star_fn=lambda repo: {"stars": 7}, today="2026-11-12")
    assert calls == [["p001", "p002"]]  # p003 was refreshed 2 days ago
    assert out["p001"] == {"citations": 4, "stars": 50, "as_of": "2026-11-12"}
    assert out["p002"]["stars"] == 7 and out["p003"]["citations"] == 9


def test_papers_without_code_count_as_zero_stars():
    days = [{"date": "2026-10-01", "records": [_r(1)]}]
    out = scoreboard.fetch_outcomes(days, {}, {}, cite_fn=lambda ids: {}, today="2026-11-12")
    assert out["p001"]["stars"] == 0


def test_evaluate_runs_rankers_ablations_and_random():
    records = [_r(i, score=i, upvotes=30 - i, parts={"stars": i, "upvotes": 30 - i}) for i in range(30)]
    outcomes = {r["id"]: {"citations": int(r["id"][1:]), "stars": int(r["id"][1:])} for r in records}
    days = [{"date": "2026-10-01", "records": records}]
    res = scoreboard.evaluate(days, outcomes, {"live": scoreboard.rank_live, "hf-upvotes": scoreboard.rank_upvotes},
                              scoreboard.ABLATIONS)
    assert res["live"]["spearman"] == 1.0 and res["hf-upvotes"]["spearman"] == -1.0
    assert res["live minus builder evidence"]["spearman"] == -1.0  # stars carried the ranking
    assert res["random"]["hit"] == round(10 / 30, 3)


def test_main_writes_an_empty_board_when_no_day_is_old_enough(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(scoreboard, "CACHE_PATH", str(tmp_path / "c.json"))
    out = tmp_path / "board.json"
    assert scoreboard.main(["--out", str(out), "--offline"]) == 0
    board = json.load(open(out))
    assert board["days"] == 0 and board["rankers"] == {}
