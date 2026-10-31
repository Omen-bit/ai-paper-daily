"""
curator.py
The Curator agent: one Groq call per featured paper that returns structured
reading notes as JSON (TL;DR, what's new, key result, build ideas, difficulty).

The notes are checked field by field. A paper whose notes fail the checks
keeps curator=None and still gets the usual "Why it matters" line from
groq_summarizer, so the daily run never breaks because of this step.

The code link never comes from the model, because it could make one up. It is
taken from Hugging Face's githubRepo field or from a link in the abstract.
"""
import json
import re
import time
from typing import Optional

import groq_summarizer as gs

DIFFICULTIES = ("beginner", "intermediate", "advanced")

# Upper word limits per field. Output over a limit is rejected, not trimmed,
# because a trimmed sentence reads as broken.
LIMITS = {
    "tldr": 30,
    "whats_new": 45,
    "key_result": 40,
    "why_it_matters": 40,
    "difficulty_reason": 25,
    "build_idea": 25,
}

SYSTEM_PROMPT = """You are the Curator for AI Papers Daily, a site for people who read AI papers and build projects from them.
Read the paper's title and abstract and return reading notes as one JSON object with exactly these keys:

"tldr": one plain sentence, at most 25 words, saying what the paper does.
"whats_new": one or two sentences, at most 40 words, on what is new compared with earlier work.
"key_result": the single most important result stated in the abstract, with its number if one is given, at most 35 words. Use null if the abstract states no result.
"why_it_matters": one sentence, at most 30 words, on why builders should care. Do not start with "This paper".
"build_ideas": a list of 2 or 3 concrete projects a developer could build with this work, each at most 20 words and starting with a verb.
"difficulty": one of "beginner", "intermediate", "advanced", for how hard it is to reproduce or use.
"difficulty_reason": one short phrase, at most 20 words, explaining the difficulty (for example the compute or background needed).

Rules: use only facts from the abstract and never invent numbers, datasets or links. Write in plain language and avoid hype words such as "groundbreaking" or "revolutionary". Return only the JSON object."""

_CODE_LINK = re.compile(r"https?://(?:www\.)?(?:github\.com|gitlab\.com|huggingface\.co)/[\w.\-/]+", re.I)


def find_code_url(paper: dict) -> Optional[str]:
    """Return a real code link for the paper, or None. Never asks the model."""
    repo = (paper.get("github_repo") or "").strip()
    if repo.startswith("https://"):
        return repo
    match = _CODE_LINK.search(paper.get("abstract") or "")
    if match:
        return match.group(0).rstrip(".,;)/")
    return None


def _sentence(value, limit: int) -> Optional[str]:
    """A non-empty string within the word limit, else None."""
    if not isinstance(value, str):
        return None
    text = " ".join(value.split()).strip().strip('"')
    if len(text) < 8 or len(text.split()) > limit:
        return None
    return text


def parse_notes(raw: str) -> Optional[dict]:
    """
    Turn the model's reply into clean notes, or None if it is unusable.
    Required: tldr, whats_new, why_it_matters, 2+ build ideas, a known difficulty.
    Optional: key_result and difficulty_reason (dropped when they fail checks).
    """
    if not raw:
        return None
    # Models sometimes wrap JSON in a code fence despite json mode
    text = raw.strip()
    fence = re.search(r"\{.*\}", text, re.S)
    if fence:
        text = fence.group(0)
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    notes = {
        "tldr": _sentence(data.get("tldr"), LIMITS["tldr"]),
        "whats_new": _sentence(data.get("whats_new"), LIMITS["whats_new"]),
        "key_result": _sentence(data.get("key_result"), LIMITS["key_result"]),
        "why_it_matters": _sentence(data.get("why_it_matters"), LIMITS["why_it_matters"]),
        "difficulty": str(data.get("difficulty", "")).strip().lower(),
        "difficulty_reason": _sentence(data.get("difficulty_reason"), LIMITS["difficulty_reason"]),
    }
    ideas = data.get("build_ideas")
    ideas = ideas if isinstance(ideas, list) else []
    notes["build_ideas"] = [i for i in (_sentence(x, LIMITS["build_idea"]) for x in ideas) if i][:3]

    if not (notes["tldr"] and notes["whats_new"] and notes["why_it_matters"]):
        return None
    if notes["why_it_matters"].lower().startswith("this paper"):
        return None
    if notes["difficulty"] not in DIFFICULTIES or len(notes["build_ideas"]) < 2:
        return None
    return notes


def _ask(model: str, title: str, abstract: str) -> Optional[str]:
    """One JSON-mode Groq call. Returns the raw reply or None."""
    client = gs._get_client()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Title: {title}\n\nAbstract: {gs._truncate_abstract(abstract, 2500)}"},
        ],
        response_format={"type": "json_object"},
        max_tokens=600,
        temperature=0.2,
    )
    choice = response.choices[0]
    if choice.finish_reason == "length":
        return None
    return choice.message.content


def curate(paper: dict) -> tuple[Optional[dict], str]:
    """Return (notes, source). notes is None when no model gave usable output."""
    if gs._auth_failed or not gs._get_api_key():
        return None, "none"
    if gs._active_models is None:
        try:
            gs._active_models = gs._resolve_active_models()
        except Exception as exc:
            print(f"  [curator] Groq unavailable: {str(exc)[:120]}")
            return None, "none"

    for model in gs._active_models:
        try:
            raw = _ask(model, paper.get("title", ""), paper.get("abstract", ""))
        except Exception as exc:
            error_str = str(exc)
            if gs._is_auth_error(error_str):
                gs._auth_failed = True
                print("  [curator] Auth error; stopping.")
                return None, "none"
            print(f"  [curator] {model} failed: {error_str[:120]}")
            time.sleep(1)
            continue
        notes = parse_notes(raw)
        if notes:
            return notes, f"groq:{model}"
        print(f"  [curator] {model} returned notes that failed the checks")
        time.sleep(0.5)
    return None, "none"


def curate_papers(papers: list[dict]) -> list[dict]:
    """
    Add 'curator' (notes or None) and 'code_url' to each paper.
    When the notes include why_it_matters, it also fills the paper's
    'why_it_matters' so groq_summarizer can skip that paper.
    """
    print("\n[curator] Writing reading notes for the top picks...")
    done = 0
    for paper in papers:
        paper["code_url"] = find_code_url(paper)
        notes, source = curate(paper)
        paper["curator"] = notes
        if notes:
            done += 1
            paper["curator_source"] = source
            paper["why_it_matters"] = notes["why_it_matters"]
            paper["summary_source"] = source
            print(f"  [curator] Notes for {paper.get('id')} from {source}")
    print(f"[curator] {done}/{len(papers)} papers got notes.")
    return papers
