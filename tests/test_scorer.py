"""
tests/test_scorer.py
Tests for paper scoring and badge assignment.
Verifies that a known paper receives the expected score and badges.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from scorer import score_paper, score_and_rank_papers, format_badges, format_authors


def test_known_paper_scoring():
    # Known paper crafted with exact signals:
    # 1. hf_upvotes = 55 -> +20
    # 2. source = "HuggingFace" -> +10, badge ("🔥", "Trending on HF")
    # 3. title with novelty kw "novel", "sota" -> 2 * 4 = +8, novelty_count >= 2 -> ("💡", "Novel Method")
    # 4. abstract with novelty kw "propose" and "we propose" -> 2 * 1 = +2
    # 5. authors = 8 -> +5
    # 6. categories = 3 -> +4, badge ("🔀", "Interdisciplinary")
    # 7. survey kw "survey" -> +6, badge ("📖", "Survey / Review")
    # 8. efficiency kw "faster" -> +3
    # 9. abstract length >= 150 words -> +3
    # Total score: 20 + 10 + 8 + 2 + 5 + 4 + 6 + 3 + 3 = 61
    abstract_words = ["word"] * 150
    abstract = "We propose a faster survey of models. " + " ".join(abstract_words)

    paper = {
        "title": "A Novel SOTA Architecture for Deep Learning",
        "abstract": abstract,
        "authors": [f"Author {i}" for i in range(8)],
        "source": "HuggingFace",
        "hf_upvotes": 55,
        "categories": [
            {"slug": "generative-ai"},
            {"slug": "llms"},
            {"slug": "reasoning-agents"},
        ],
    }

    scored = score_paper(paper)
    assert scored["score"] == 61

    badge_labels = [label for _, label in scored["badges"]]
    assert "Trending on HF" in badge_labels
    assert "Interdisciplinary" in badge_labels


def test_top_pick_assignment():
    papers = [
        {
            "id": "1",
            "title": "A Low Score Paper",
            "abstract": "Simple text.",
            "authors": ["Alice"],
            "source": "arXiv",
            "categories": [],
        },
        {
            "id": "2",
            "title": "A Novel Breakthrough Architecture Outperforming SOTA",
            "abstract": "We introduce and propose a superior model.",
            "authors": ["Bob"] * 5,
            "source": "HuggingFace",
            "hf_upvotes": 30,
            "categories": [{"slug": "llms"}, {"slug": "reasoning-agents"}],
        },
    ]

    ranked = score_and_rank_papers(papers, top_n=2)
    assert len(ranked) == 2
    assert ranked[0]["id"] == "2"
    top_badge_emojis = [b[0] for b in ranked[0]["badges"]]
    assert "⭐" in top_badge_emojis


def test_format_badges_and_authors():
    badges = [("🔥", "Trending on HF"), ("⭐", "Top Pick")]
    formatted = format_badges(badges)
    assert "`🔥 Trending on HF`" in formatted
    assert "`⭐ Top Pick`" in formatted

    authors = ["Alice", "Bob", "Charlie", "David", "Eve", "Frank"]
    formatted_auth = format_authors(authors, max_shown=3)
    assert "Alice, Bob, Charlie" in formatted_auth
    assert "+3 more" in formatted_auth
