"""
scorer.py
Scores every candidate paper and picks the day's two papers.

Each point comes from evidence about the paper, not from the words in its abstract:
  community   Hugging Face upvotes, on a log scale so each doubling of upvotes adds the same points
  listed      the paper made Hugging Face's hand-picked Daily Papers list
  code        code is released (Hugging Face's repo field, or a code link in the abstract)
  lab         the lab is known from direct evidence (labs.py): a known lab, or any named one
  topics      the paper spans two or more research topics

Words like "novel" or "we propose" are left out: nearly every abstract uses them,
so they only added noise. The two picks also come from different topics when possible.
scripts/backtest_picker.py measures the picker against later upvotes.
"""

import math
import re
from typing import Optional

import labs

# Points per signal. Released code or a known lab is worth about one doubling of upvotes.
COMMUNITY_PER_DOUBLING = 8   # points for each doubling of upvotes (plus one)
COMMUNITY_CAP = 64           # reached at about 255 upvotes
LISTED_POINTS = 8
CODE_POINTS = 8
KNOWN_LAB_POINTS = 6
NAMED_LAB_POINTS = 3
MULTI_TOPIC_POINTS = 2

# A paper needs this many Hugging Face upvotes to fill the "Trending" slot
MIN_TRENDING_UPVOTES = 5

SURVEY_TITLE_PATTERNS = [
    r"\bsurvey\b", r"\breview\b", r"\boverview\b", r"\btutorial\b",
    r"\bposition paper\b",
]
SURVEY_ABSTRACT_PATTERNS = [
    r"\bliterature review\b", r"\bsystematic review\b", r"\bsystematic survey\b",
    r"\bcomprehensive survey\b", r"\bcomprehensive review\b", r"\bposition paper\b",
]

_CODE_LINK = re.compile(r"https?://(?:www\.)?(?:github\.com|gitlab\.com)/[\w.\-]+/[\w.\-]+", re.I)


def topics(paper: dict) -> list[str]:
    """The paper's topic slugs. Categories arrive as classifier dicts or as bare slugs."""
    return [c["slug"] if isinstance(c, dict) else c for c in paper.get("categories") or []]


def main_topic(paper: dict) -> str:
    """The paper's first topic, or '' when it only has the catch-all "other-ml"."""
    first = (topics(paper) or [""])[0]
    return "" if first == "other-ml" else first


def has_code(paper: dict) -> bool:
    """Released code, from Hugging Face's repo field, a code link already found, or the abstract."""
    for key in ("github_repo", "code_url"):
        if str(paper.get(key) or "").startswith("https://"):
            return True
    return bool(_CODE_LINK.search(paper.get("abstract") or ""))


def lab_of(paper: dict) -> str:
    """The lab that wrote the paper, from direct evidence only, or ''."""
    return paper.get("org") or labs.detect(paper) or ""


def is_survey(paper: dict) -> bool:
    title = (paper.get("title") or "").lower()
    abstract = (paper.get("abstract") or "").lower()
    return (any(re.search(p, title) for p in SURVEY_TITLE_PATTERNS)
            or any(re.search(p, abstract) for p in SURVEY_ABSTRACT_PATTERNS))


def community_points(upvotes) -> float:
    """8 points per doubling of upvotes: 1 -> 8, 7 -> 24, 31 -> 40, 127 -> 56, 255+ -> 64."""
    n = max(0, int(upvotes or 0))
    return min(COMMUNITY_CAP, COMMUNITY_PER_DOUBLING * math.log2(1 + n))


def score_paper(paper: dict) -> dict:
    """
    Score a paper and assign badges. Adds 'score' (a whole number), 'score_parts'
    (points per signal, for debugging and the backtest) and 'badges' to the paper.
    """
    parts = {}
    badges = []

    parts["community"] = round(community_points(paper.get("hf_upvotes")), 1)

    if "HuggingFace" in (paper.get("source") or ""):
        parts["listed"] = LISTED_POINTS
        badges.append(("🔥", "Trending on HF"))

    if has_code(paper):
        parts["code"] = CODE_POINTS
        badges.append(("💻", "Code released"))

    lab = lab_of(paper)
    if lab:
        known = bool(labs.canonical(lab)) or lab in labs.BRANDS
        parts["lab"] = KNOWN_LAB_POINTS if known else NAMED_LAB_POINTS
        if known:
            badges.append(("🏛️", lab))

    if len(topics(paper)) >= 2:
        parts["topics"] = MULTI_TOPIC_POINTS
        badges.append(("🔀", "Interdisciplinary"))

    # Surveys keep their badge but get no points: the picks are meant to be new work
    if is_survey(paper):
        badges.append(("📖", "Survey / Review"))

    paper["score"] = round(sum(parts.values()))
    paper["score_parts"] = parts
    paper["badges"] = badges[:3]
    return paper


def score_and_rank_papers(papers: list[dict], top_n: int = 2) -> list[dict]:
    """
    Score all papers, rank them, and return the top N.
    Also marks the #1 paper as ⭐ Top Pick.
    """
    if not papers:
        return []
    scored = sorted((score_paper(p) for p in papers), key=_rank_key)
    scored[0]["badges"] = ([("⭐", "Top Pick")] + scored[0]["badges"])[:4]
    selected = scored[:top_n]
    print(f"\n🏆 Top {top_n} papers selected:")
    for i, p in enumerate(selected, 1):
        badge_str = " ".join([b[0] for b in p["badges"]])
        print(f"  {i}. [{p['score']} pts] {badge_str} {p['title'][:70]}...")
    return selected


def _rank_key(p: dict):
    """Best first: score, then upvotes, then id so the order never depends on input order."""
    return (-p["score"], -(p.get("hf_upvotes") or 0), p.get("id") or "")


def _other_topic(paper: dict, pick: dict) -> bool:
    """True when the two papers' main topics differ (or either has none)."""
    a, b = main_topic(paper), main_topic(pick)
    return not a or not b or a != b


def select_daily(papers: list[dict], prefer: Optional[str] = None) -> list[dict]:
    """
    Pick the day's two papers, each for a different reason:
      1. "pick": the best paper by score, or the paper with id `prefer` when it is
         among them (the LLM judge's choice from the shortlist, see judge.py).
      2. "trending": the most upvoted of the rest, from a different topic than the pick
         when one has enough upvotes. When nothing has enough upvotes, the best-scored
         paper from another topic ("runner-up").
    Each selected paper gets a "slot" key saying which one it is.
    """
    if not papers:
        return []
    ranked = sorted((score_paper(p) for p in papers), key=_rank_key)
    if prefer:
        chosen = next((i for i, p in enumerate(ranked) if p.get("id") == prefer), 0)
        ranked.insert(0, ranked.pop(chosen))
    top = ranked[0]
    top["badges"] = ([("⭐", "Top Pick")] + top["badges"])[:4]
    top["slot"] = "pick"
    rest = ranked[1:]
    if not rest:
        return [top]

    def hottest(pool):
        return max(pool, key=lambda p: (p.get("hf_upvotes") or 0, p["score"])) if pool else None

    varied = [p for p in rest if _other_topic(p, top)]
    hot = hottest([p for p in varied if (p.get("hf_upvotes") or 0) >= MIN_TRENDING_UPVOTES]) \
        or hottest([p for p in rest if (p.get("hf_upvotes") or 0) >= MIN_TRENDING_UPVOTES])
    if hot:
        hot["slot"] = "trending"
        hot["badges"] = [("🔥", "Trending")] + [b for b in hot["badges"] if b[1] != "Trending on HF"][:3]
    else:
        hot = (varied or rest)[0]
        hot["slot"] = "runner-up"
    print(f"  [pick] Today's pick: {top['title'][:60]} ({top['score']} pts {top['score_parts']})")
    print(f"  [pick] {hot['slot'].capitalize()}: {hot['title'][:60]} ({hot.get('hf_upvotes') or 0} upvotes)")
    return [top, hot]


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
