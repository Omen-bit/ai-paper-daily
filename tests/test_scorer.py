"""
tests/test_scorer.py
Tests for paper scoring, badges and the day's two picks.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import scorer
from scorer import score_paper, score_and_rank_papers, select_daily, format_badges, format_authors


def _p(pid, title="A study of models", upvotes=0, topics=("llms",), **extra):
    return {"id": pid, "title": title, "abstract": "We study models.", "authors": ["A"],
            "categories": [{"slug": t} for t in topics], "hf_upvotes": upvotes,
            "source": "HuggingFace" if upvotes else "arXiv", **extra}


def test_known_paper_scoring():
    # 31 upvotes -> 3 * log2(32) = 15, code link in the abstract -> 8,
    # HF org Google DeepMind (a known lab) -> 5. Nothing was looked up, so no other signals.
    paper = _p("1", upvotes=31, topics=("llms", "reasoning-agents"),
               abstract="Code: https://github.com/google-deepmind/thing.", hf_org={"name": "google-deepmind"})
    scored = score_paper(paper)
    assert scored["score_parts"] == {"code": 8, "upvotes": 15.0, "lab": 5}
    assert scored["score"] == 28
    assert scored["evidence"]["upvotes"] == 31 and scored["evidence"]["lab"] == "Google DeepMind"
    labels = [label for _, label in scored["badges"]]
    assert labels == ["Code released", "Trending on HF", "Google DeepMind"]


def test_the_groups_add_up_to_100():
    assert sum(scorer.MAX_POINTS.values()) == 100
    assert [g["max"] for g in scorer.group_points({})] == [40, 30, 15, 15]


def test_a_paper_with_every_signal_maxed_scores_100():
    sig = {"fetched": True, "repo": "a/b", "stars": 10**6, "stars_gain": 10**6, "hf_models": 2,
           "hf_datasets": 1, "hf_spaces": 1, "hn_points": 10**4, "h_index": 200}
    p = _p("1", upvotes=10**4, code_url="https://github.com/a/b", org="OpenAI", signals=sig,
           claims=[{}, {}, {}], novelty_pct=1.0)
    assert score_paper(p)["score"] == 100
    groups = {g["key"]: g["points"] for g in scorer.group_points(p["score_parts"])}
    assert groups == {"builder": 40, "community": 30, "authors": 15, "content": 15}


def test_github_and_hacker_news_can_beat_raw_upvotes():
    hyped = _p("hyped", upvotes=120)
    built = _p("built", upvotes=10, code_url="https://github.com/a/b",
               signals={"fetched": True, "repo": "a/b", "stars": 600, "stars_gain": 250, "hn_points": 150})
    ranked = scorer.score_all([hyped, built])
    assert [p["id"] for p in ranked] == ["built", "hyped"]
    assert ranked[0]["rank"] == 1 and ranked[0]["of"] == 2


def test_unknown_signals_get_the_days_median_and_are_marked():
    looked = [_p(str(i), signals={"fetched": True, "h_index": h, "hn_points": 0}) for i, h in enumerate([4, 10, 30])]
    missing = _p("m", signals={"fetched": True, "h_index": None, "hn_points": 0})
    never = _p("n")  # never looked up: no estimate
    scorer.score_all(looked + [missing, never])
    assert missing["evidence"]["h_index"] == 10 and missing["evidence"]["estimated"] == ["h_index"]
    assert missing["score_parts"]["h_index"] == looked[1]["score_parts"]["h_index"]
    assert "h_index" not in never["score_parts"] and "estimated" not in never["evidence"]


def test_a_known_zero_is_not_estimated():
    looked = [_p("a", signals={"fetched": True, "hn_points": 200}), _p("b", signals={"fetched": True, "hn_points": 0})]
    scorer.score_all(looked)
    assert "hn" not in looked[1]["score_parts"] and "estimated" not in looked[1]["evidence"]


def test_star_gain_is_only_estimated_for_papers_with_a_repo():
    with_repo = _p("a", signals={"fetched": True, "repo": "x/y", "stars": 50, "stars_gain": None})
    other = _p("b", signals={"fetched": True, "repo": "z/w", "stars": 90, "stars_gain": 40})
    no_repo = _p("c", signals={"fetched": True, "repo": None})
    scorer.score_all([with_repo, other, no_repo])
    assert with_repo["evidence"]["stars_gain"] == 40
    assert "stars_gain" not in no_repo["evidence"]


def test_claims_and_novelty_count_but_not_for_surveys():
    paper = _p("1", claims=[{"benchmark": "GSM8K"}, {"benchmark": "MATH"}], novelty_pct=0.5, novelty=0.7)
    assert score_paper(paper)["score_parts"] == {"claims": 8, "novelty": 2.5}
    survey = _p("2", title="A Survey of Agents", claims=[{"benchmark": "X"}], novelty_pct=1.0)
    assert score_paper(survey)["score"] == 0


def test_novelty_ranks_are_shares_of_the_day():
    papers = [_p("a", novelty=0.2), _p("b", novelty=0.9), _p("c", novelty=0.5), _p("d")]
    scorer.novelty_ranks(papers)
    assert [p.get("novelty_pct") for p in papers] == [0.0, 1.0, 0.5, None]


def test_tie_break_takes_only_the_close_leaders():
    ranked = [{"score": 60}, {"score": 58}, {"score": 57}, {"score": 50}]
    assert len(scorer.tied_with_leader(ranked)) == 3
    assert scorer.tied_with_leader([{"score": 60}, {"score": 40}]) == [{"score": 60}]


def test_buzzwords_and_padding_earn_nothing():
    plain = score_paper(_p("1"))
    hyped = score_paper(_p("2", title="A Novel SOTA Breakthrough",
                           abstract="We propose a novel, state-of-the-art, efficient method. " * 30,
                           authors=[f"Author {i}" for i in range(12)]))
    assert hyped["score"] == plain["score"] == 0


def test_surveys_keep_their_badge_but_get_no_points():
    survey = score_paper(_p("1", title="A Survey of Agents"))
    assert survey["score"] == 0
    assert ("📖", "Survey / Review") in survey["badges"]


def test_counts_grow_by_doublings_and_are_capped():
    assert scorer.community_points(0) == 0
    assert scorer.community_points(1) == 3
    assert scorer.community_points(7) == 9
    assert scorer.community_points(10_000) == scorer.MAX_POINTS["upvotes"]
    assert scorer.community_points(None) == 0
    assert scorer.log_points("stars", 255) == 16
    assert scorer.log_points("stars", None) == 0


def test_code_and_named_labs():
    assert scorer.has_code({"github_repo": "https://github.com/a/b"})
    assert scorer.has_code({"abstract": "See https://gitlab.com/team/repo for code."})
    assert not scorer.has_code({"abstract": "See https://github.com for details."})
    unknown = score_paper(_p("1", org="Some Small Lab"))
    assert unknown["score_parts"]["lab"] == scorer.NAMED_LAB_POINTS
    assert not any(label == "Some Small Lab" for _, label in unknown["badges"])


def test_top_pick_assignment():
    papers = [_p("1", "A low score paper"), _p("2", "A popular paper", upvotes=30, topics=("llms", "vision"))]
    ranked = score_and_rank_papers(papers, top_n=2)
    assert [p["id"] for p in ranked] == ["2", "1"]
    assert ranked[0]["badges"][0] == ("⭐", "Top Pick")


def test_format_badges_and_authors():
    formatted = format_badges([("🔥", "Trending on HF"), ("⭐", "Top Pick")])
    assert "`🔥 Trending on HF`" in formatted
    assert "`⭐ Top Pick`" in formatted
    formatted_auth = format_authors(["Alice", "Bob", "Charlie", "David", "Eve", "Frank"], max_shown=3)
    assert "Alice, Bob, Charlie" in formatted_auth
    assert "+3 more" in formatted_auth


def test_select_daily_picks_best_then_trending():
    papers = [_p("1"), _p("2", upvotes=40, topics=("vision",)), _p("3", upvotes=8, topics=("robotics",))]
    chosen = select_daily(papers)
    assert [(p["id"], p["slot"]) for p in chosen] == [("2", "pick"), ("3", "trending")]


def test_trending_comes_from_another_topic_when_it_can():
    papers = [_p("1", upvotes=90), _p("2", upvotes=60), _p("3", upvotes=10, topics=("vision",))]
    chosen = select_daily(papers)
    assert [(p["id"], p["slot"]) for p in chosen] == [("1", "pick"), ("3", "trending")]
    assert chosen[1]["badges"][0] == ("🔥", "Trending")


def test_same_topic_is_allowed_when_nothing_else_has_upvotes():
    papers = [_p("1", upvotes=90), _p("2", upvotes=60), _p("3", topics=("vision",))]
    chosen = select_daily(papers)
    assert [(p["id"], p["slot"]) for p in chosen] == [("1", "pick"), ("2", "trending")]


def test_other_ml_never_blocks_a_paper():
    papers = [_p("1", upvotes=90, topics=("other-ml",)), _p("2", upvotes=60, topics=("other-ml",))]
    assert [p["id"] for p in select_daily(papers)] == ["1", "2"]


def test_ties_are_broken_the_same_way_every_time():
    a, b = _p("b", upvotes=20), _p("a", upvotes=20)
    assert select_daily([dict(a), dict(b)])[0]["id"] == select_daily([dict(b), dict(a)])[0]["id"] == "a"


def test_select_daily_falls_back_to_runner_up_without_upvotes():
    chosen = select_daily([_p("1"), _p("2", topics=("vision",))])
    assert [p["slot"] for p in chosen] == ["pick", "runner-up"]
    assert select_daily([]) == []
    assert [p["slot"] for p in select_daily([_p("1")])] == ["pick"]


def test_select_daily_can_be_told_which_paper_to_pick():
    papers = [_p("1", upvotes=90), _p("2", upvotes=10, topics=("vision",)), _p("3", upvotes=40, topics=("robotics",))]
    chosen = select_daily(papers, prefer="2")
    assert [(p["id"], p["slot"]) for p in chosen] == [("2", "pick"), ("1", "trending")]
    assert select_daily([_p("1", upvotes=9)], prefer="missing")[0]["id"] == "1"
