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
    # 31 upvotes -> 40, on the HF list -> 8, code link in the abstract -> 8,
    # HF org Google DeepMind -> 6, two topics -> 2. Total 64.
    paper = _p("1", upvotes=31, topics=("llms", "reasoning-agents"),
               abstract="Code: https://github.com/google-deepmind/thing.", hf_org={"name": "google-deepmind"})
    scored = score_paper(paper)
    assert scored["score_parts"] == {"community": 40.0, "listed": 8, "code": 8, "lab": 6, "topics": 2}
    assert scored["score"] == 64
    labels = [label for _, label in scored["badges"]]
    assert labels == ["Trending on HF", "Code released", "Google DeepMind"]


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


def test_community_points_grow_by_doublings_and_are_capped():
    assert scorer.community_points(0) == 0
    assert scorer.community_points(1) == 8
    assert scorer.community_points(7) == 24
    assert scorer.community_points(10_000) == scorer.COMMUNITY_CAP
    assert scorer.community_points(None) == 0


def test_code_and_named_labs():
    assert scorer.has_code({"github_repo": "https://github.com/a/b"})
    assert scorer.has_code({"abstract": "See https://gitlab.com/team/repo for code."})
    assert not scorer.has_code({"abstract": "See https://github.com for details."})
    unknown = score_paper(_p("1", org="Some Small Lab"))
    assert unknown["score_parts"]["lab"] == scorer.NAMED_LAB_POINTS
    assert not any(label == "Some Small Lab" for _, label in unknown["badges"])


def test_code_is_worth_about_one_doubling_of_upvotes():
    with_code = score_paper(_p("1", upvotes=20, code_url="https://github.com/a/b"))
    double = score_paper(_p("2", upvotes=41))
    assert abs(with_code["score"] - double["score"]) <= 1


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
