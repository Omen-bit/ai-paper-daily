"""
scorer.py
Heuristic-based paper scoring and badge assignment.
Scores papers and selects the top N for daily digest.
"""

import re
from typing import Optional


# Known top-tier institutions for bonus scoring
TOP_INSTITUTIONS = [
    "google", "deepmind", "google deepmind", "openai", "meta ai", "fair",
    "microsoft research", "anthropic", "stanford", "mit", "cmu", "carnegie mellon",
    "berkeley", "uc berkeley", "oxford", "cambridge", "eth zurich", "epfl",
    "toronto", "mila", "hugging face", "nvidia", "apple", "amazon",
    "tsinghua", "peking university", "chinese university", "ntu", "nus",
    "kaist", "samsung", "lg ai", "sony", "adobe", "salesforce research"
]

# Keywords that signal novelty or significance
NOVELTY_KEYWORDS = [
    "novel", "new", "first", "state-of-the-art", "state of the art", "sota",
    "outperform", "surpass", "exceed", "breakthrough", "superior", "improved",
    "advances", "propose", "introducing", "we present", "we introduce",
    "we propose", "significant", "substantially"
]

SURVEY_KEYWORDS = [
    "survey", "review", "overview", "benchmark", "comprehensive study",
    "systematic", "literature review", "tutorial", "position paper"
]

EFFICIENCY_KEYWORDS = [
    "efficient", "faster", "lightweight", "compress", "distill", "prune",
    "reduce cost", "inference speed", "fewer parameters", "low-resource"
]


def _normalize(text: str) -> str:
    return text.lower()


def _detect_institutions(authors_str: str) -> list[str]:
    """Detect known top-tier institutions from author affiliations string."""
    normalized = _normalize(authors_str)
    found = []
    for inst in TOP_INSTITUTIONS:
        if inst in normalized:
            found.append(inst.title())
    return found


def score_paper(paper: dict) -> dict:
    """
    Score a paper and assign badges.
    Returns the paper with 'score' and 'badges' fields added.
    """
    score = 0
    badges = []

    title_lower = _normalize(paper.get("title", ""))
    abstract_lower = _normalize(paper.get("abstract", ""))
    full_text = f"{title_lower} {abstract_lower}"
    authors = paper.get("authors", [])

    # --- Signal 1: HuggingFace upvotes (community signal) ---
    hf_upvotes = paper.get("hf_upvotes", 0)
    if hf_upvotes >= 50:
        score += 20
    elif hf_upvotes >= 20:
        score += 12
    elif hf_upvotes >= 5:
        score += 6
    elif hf_upvotes > 0:
        score += 3

    # If paper is from HF trending, it's community-validated
    if "HuggingFace" in paper.get("source", ""):
        score += 10
        badges.append(("🔥", "Trending on HF"))

    # --- Signal 2: Novelty keywords in title ---
    novelty_count = sum(1 for kw in NOVELTY_KEYWORDS if kw in title_lower)
    score += novelty_count * 4

    # --- Signal 3: Novelty keywords in abstract ---
    abstract_novelty = sum(1 for kw in NOVELTY_KEYWORDS if kw in abstract_lower)
    score += min(abstract_novelty * 1, 8)  # cap at 8

    # --- Signal 4: Source from HF (already handled above) ---

    # --- Signal 5: Author count (collaboration signal) ---
    num_authors = len(authors)
    if num_authors >= 8:
        score += 5  # Large collaboration
    elif num_authors >= 4:
        score += 3

    # --- Signal 6: Cross-category paper (interdisciplinary) ---
    categories = paper.get("categories", [])
    if len(categories) >= 3:
        score += 4
        badges.append(("🔀", "Interdisciplinary"))
    elif len(categories) == 2:
        score += 2

    # --- Signal 7: Survey/review bonus ---
    if any(kw in full_text for kw in SURVEY_KEYWORDS):
        score += 6
        badges.append(("📖", "Survey / Review"))

    # --- Signal 8: Efficiency / resource-saving angle ---
    if any(kw in full_text for kw in EFFICIENCY_KEYWORDS):
        score += 3

    # --- Signal 9: Abstract quality (length as proxy for detail) ---
    abstract_words = len(abstract_lower.split())
    if abstract_words >= 150:
        score += 3
    elif abstract_words >= 100:
        score += 1

    # --- Assign qualitative badges ---
    if novelty_count >= 2 or abstract_novelty >= 3:
        badges.append(("💡", "Novel Method"))

    # Assign final composite badges (only top 3 badges)
    paper["score"] = score
    paper["badges"] = badges[:3]
    return paper


def score_and_rank_papers(papers: list[dict], top_n: int = 2) -> list[dict]:
    """
    Score all papers, rank them, and return the top N.
    Also marks the #1 paper as ⭐ Top Pick.
    """
    if not papers:
        return []

    # Score all papers
    scored = [score_paper(p) for p in papers]

    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)

    # Mark top pick
    if scored:
        scored[0]["badges"] = [("⭐", "Top Pick")] + scored[0]["badges"]
        scored[0]["badges"] = scored[0]["badges"][:4]  # limit badges

    selected = scored[:top_n]

    print(f"\n🏆 Top {top_n} papers selected:")
    for i, p in enumerate(selected, 1):
        badge_str = " ".join([b[0] for b in p["badges"]])
        print(f"  {i}. [{p['score']} pts] {badge_str} {p['title'][:70]}...")

    return selected


def format_badges(badges: list[tuple[str, str]]) -> str:
    """Format badges as inline markdown spans."""
    if not badges:
        return ""
    parts = []
    for emoji, label in badges:
        parts.append(f"`{emoji} {label}`")
    return " ".join(parts)


def format_authors(authors: list[str], max_shown: int = 5) -> str:
    """Format author list, truncating if too long."""
    if not authors:
        return "*Unknown Authors*"
    if len(authors) <= max_shown:
        return ", ".join(authors)
    shown = ", ".join(authors[:max_shown])
    remaining = len(authors) - max_shown
    return f"{shown} *+{remaining} more*"
