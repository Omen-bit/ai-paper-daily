"""
scorer.py
Scores every candidate paper out of 100 from measured evidence and picks the day's two papers.

The score is four capped groups, so no single source can decide the pick on its own:

  Builder evidence (40)      code released 8, GitHub stars 16, stars gained since yesterday 10,
                             models / datasets / demos on Hugging Face 6
  Community attention (30)   Hugging Face upvotes 20, Hacker News points 10
  Author track record (15)   median author h-index on Semantic Scholar 10, known lab 5
  What the paper shows (15)  benchmark results it claims, each checked against the abstract 10,
                             novelty against the last 90 days of papers 5

Counts use a log scale, so each doubling adds the same points and one viral number
can't swamp the rest. The numbers come from signals.py (GitHub, Hugging Face,
Hacker News, Semantic Scholar), claims.py and novelty.py; every one is saved with the
paper and shown on its page ("Why this ranked"), and docs/methodology.md explains them.

A signal we could not look up (a service was down, or Semantic Scholar hasn't indexed
the paper yet) is "not known", not zero: it gets the median of the day's papers that
were looked up, and the page marks it as estimated. Papers that were never looked up
(the long tail of arXiv) score only on what the feeds say: code, upvotes, lab, novelty.

Words like "novel" or "we propose" are left out: nearly every abstract uses them.
The two picks also come from different topics when possible.
scripts/scoreboard.py checks the ranking against citations and stars 30 days later.
"""

import math
import re
import statistics
from typing import Optional

import labs

# (group key, label, [(signal key, max points)]). Group maxima add up to 100.
GROUPS = [
    ("builder", "Builder evidence", [("code", 8), ("stars", 16), ("stars_gain", 10), ("artifacts", 6)]),
    ("community", "Community attention", [("upvotes", 20), ("hn", 10)]),
    ("authors", "Author track record", [("h_index", 10), ("lab", 5)]),
    ("content", "What the paper shows", [("claims", 10), ("novelty", 5)]),
]
MAX_POINTS = {sig: pts for _, _, sigs in GROUPS for sig, pts in sigs}

# Points per doubling for the log-scaled counts
PER_DOUBLING = {"stars": 2.0, "stars_gain": 1.5, "upvotes": 3.0, "hn": 1.5, "h_index": 2.0}
CODE_POINTS = 8
KNOWN_LAB_POINTS = 5
NAMED_LAB_POINTS = 2.5
POINTS_PER_CLAIM = 4
ARTIFACT_POINTS = {"hf_models": 3, "hf_datasets": 2, "hf_spaces": 1}

# Signals that get the day's median when a lookup failed, and the evidence key each reads
ESTIMATED = {"stars_gain": "stars_gain", "hn": "hn_points", "h_index": "h_index"}

# A paper needs this many Hugging Face upvotes to fill the "Trending" slot
MIN_TRENDING_UPVOTES = 5
# The LLM judge only breaks ties: papers within this many points of the leader
TIE_MARGIN = 3

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


def log_points(signal: str, n) -> float:
    """Points for a count: PER_DOUBLING[signal] per doubling of (n + 1), capped at the signal's maximum."""
    if n is None:
        return 0.0
    return min(MAX_POINTS[signal], PER_DOUBLING[signal] * math.log2(1 + max(0, float(n))))


def community_points(upvotes) -> float:
    """Hugging Face upvotes: 3 points per doubling, up to 20 (reached at about 100 upvotes)."""
    return log_points("upvotes", int(upvotes or 0))


def day_medians(papers: list[dict]) -> dict:
    """The median of each estimable signal over the papers whose lookup worked."""
    out = {}
    looked = [p["signals"] for p in papers if (p.get("signals") or {}).get("fetched")]
    for key in ESTIMATED.values():
        if key == "stars_gain":
            vals = [s[key] for s in looked if s.get("repo") and s.get(key) is not None]
        else:
            vals = [s[key] for s in looked if s.get(key) is not None]
        if vals:
            out[key] = statistics.median(vals)
    return out


def novelty_ranks(papers: list[dict]) -> None:
    """Set paper["novelty_pct"]: the share of the day's papers that are less novel (0..1)."""
    scored = sorted((p for p in papers if p.get("novelty") is not None), key=lambda p: p["novelty"])
    n = len(scored)
    for i, p in enumerate(scored):
        p["novelty_pct"] = round(i / (n - 1), 3) if n > 1 else 0.5


def score_paper(paper: dict, medians: Optional[dict] = None) -> dict:
    """
    Score a paper out of 100 and assign badges. Adds 'score' (a whole number),
    'score_parts' (points per signal), 'evidence' (the raw numbers behind them,
    shown on the paper's page) and 'badges' to the paper.
    """
    medians = medians or {}
    sig = paper.get("signals") or {}
    looked_up = bool(sig.get("fetched"))
    parts, evidence, estimated, badges = {}, {}, [], []

    def value(signal: str, key: str):
        v = sig.get(key)
        if v is None and looked_up and signal in ESTIMATED and key in medians:
            if signal == "stars_gain" and not sig.get("repo"):
                return None
            estimated.append(signal)
            return medians[key]
        return v

    # Builder evidence
    code = has_code(paper)
    if code:
        parts["code"] = CODE_POINTS
        badges.append(("💻", "Code released"))
    evidence["code"] = code
    if sig.get("stars") is not None:
        evidence["stars"] = sig["stars"]
        parts["stars"] = log_points("stars", sig["stars"])
    gain = value("stars_gain", "stars_gain")
    if gain is not None:
        evidence["stars_gain"] = gain
        parts["stars_gain"] = log_points("stars_gain", gain)
    arts = {k: int(sig.get(k) or 0) for k in ARTIFACT_POINTS}
    if any(arts.values()):
        evidence.update({k: v for k, v in arts.items() if v})
        parts["artifacts"] = min(MAX_POINTS["artifacts"], sum(ARTIFACT_POINTS[k] for k, v in arts.items() if v))

    # Community attention
    upvotes = int(paper.get("hf_upvotes") or 0)
    evidence["upvotes"] = upvotes
    parts["upvotes"] = community_points(upvotes)
    if "HuggingFace" in (paper.get("source") or ""):
        badges.append(("🔥", "Trending on HF"))
    hn = value("hn", "hn_points")
    if hn is not None:
        evidence["hn_points"] = hn
        if sig.get("hn_url"):
            evidence["hn_url"] = sig["hn_url"]
        parts["hn"] = log_points("hn", hn)

    # Author track record
    h = value("h_index", "h_index")
    if h is not None:
        evidence["h_index"] = h
        parts["h_index"] = log_points("h_index", h)
    lab = lab_of(paper)
    if lab:
        known = bool(labs.canonical(lab)) or lab in labs.BRANDS
        parts["lab"] = KNOWN_LAB_POINTS if known else NAMED_LAB_POINTS
        evidence["lab"] = lab
        if known:
            badges.append(("🏛️", lab))

    # What the paper shows
    claims = paper.get("claims") or []
    if claims:
        evidence["claims"] = len(claims)
        parts["claims"] = min(MAX_POINTS["claims"], POINTS_PER_CLAIM * len(claims))
    if paper.get("novelty_pct") is not None:
        evidence["novelty"] = paper.get("novelty")
        evidence["novelty_pct"] = paper["novelty_pct"]
        parts["novelty"] = round(MAX_POINTS["novelty"] * paper["novelty_pct"], 1)

    if len(topics(paper)) >= 2:
        badges.append(("🔀", "Interdisciplinary"))
    # Surveys keep their badge but are not meant to be the pick: they lose their claims and novelty points
    if is_survey(paper):
        badges.append(("📖", "Survey / Review"))
        parts.pop("claims", None)
        parts.pop("novelty", None)

    parts = {k: round(v, 1) for k, v in parts.items() if v}
    if estimated:
        evidence["estimated"] = sorted(set(estimated))
    paper["score"] = round(sum(parts.values()))
    paper["score_parts"] = parts
    paper["evidence"] = evidence
    paper["badges"] = badges[:3]
    return paper


def group_points(parts: dict) -> list[dict]:
    """The score by group, for the page: [{key, label, points, max}], in GROUPS order."""
    out = []
    for key, label, sigs in GROUPS:
        out.append({"key": key, "label": label,
                    "points": round(sum(parts.get(s, 0) for s, _ in sigs), 1),
                    "max": sum(m for _, m in sigs)})
    return out


def score_all(papers: list[dict]) -> list[dict]:
    """Score every paper against the day's medians and novelty ranks; best first, with 'rank' and 'of' set."""
    medians = day_medians(papers)
    novelty_ranks(papers)
    ranked = sorted((score_paper(p, medians) for p in papers), key=_rank_key)
    for i, p in enumerate(ranked, 1):
        p["rank"], p["of"] = i, len(ranked)
    return ranked


def tied_with_leader(ranked: list[dict], margin: int = TIE_MARGIN, most: int = 4) -> list[dict]:
    """The leader and the papers within `margin` points of it, for the LLM tie-break (at most `most`)."""
    if not ranked:
        return []
    top = ranked[0]["score"]
    return [p for p in ranked if p["score"] >= top - margin][:most]


def score_and_rank_papers(papers: list[dict], top_n: int = 2) -> list[dict]:
    """
    Score all papers, rank them, and return the top N.
    Also marks the #1 paper as ⭐ Top Pick.
    """
    if not papers:
        return []
    scored = score_all(papers)
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
         among them (the LLM judge's tie-break between near-equal leaders, see judge.py).
      2. "trending": the most upvoted of the rest, from a different topic than the pick
         when one has enough upvotes. When nothing has enough upvotes, the best-scored
         paper from another topic ("runner-up").
    Each selected paper gets a "slot" key saying which one it is.
    """
    if not papers:
        return []
    ranked = score_all(papers)
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
