"""
groq_summarizer.py
Generates "Why it matters" one-liner summaries using Groq API.
Falls back through multiple models if one is unavailable.
Returns (text, source) tuples so callers know which path ran.
"""

import os
import re
import time
from typing import Optional

# Preferred model order. Dynamic filtering at startup removes retired models.
GROQ_MODELS_PREFERRED = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

# Model ids containing any of these are not general chat models (speech, safety
# classifiers, agentic systems) and are never used as a fallback.
_NON_CHAT_MODEL_MARKERS = ("whisper", "tts", "guard", "playai", "orpheus", "compound", "distil")

SYSTEM_PROMPT = (
    "You are a concise science communicator helping researchers quickly understand "
    "why a paper matters. Given a paper title and abstract, write a SINGLE sentence "
    "(max 30 words) explaining: what problem it solves OR what it enables, and why it "
    "is significant to the AI/ML community. Be direct, specific, and avoid jargon. "
    "Do NOT start with 'This paper'. Output ONLY the sentence, no preamble."
)

# Prefixes to strip from model output before validation
_STRIP_PREFIXES = [
    "here is the sentence:",
    "here's the sentence:",
    "why it matters:",
    "abstract highlight:",
    "sure, here",
    "certainly,",
]

_groq_client = None
_active_models: Optional[list] = None  # resolved at first call
_auth_failed = False


def _get_api_key() -> str:
    return os.environ.get("GROQ_API_KEY", "").strip()


def _get_client():
    """Return a cached Groq client, or raise if unavailable."""
    global _groq_client
    if _groq_client is None:
        from groq import Groq
        api_key = _get_api_key()
        if not api_key:
            raise ValueError("GROQ_API_KEY is not set or is empty")
        _groq_client = Groq(api_key=api_key)
    return _groq_client


def _resolve_active_models() -> list:
    """
    Call client.models.list() once and keep only models from GROQ_MODELS_PREFERRED
    that appear in the returned list. If every preferred model has been retired,
    fall back to whatever chat models the account can use, so a Groq deprecation
    never silently turns every summary into the heuristic.
    Falls back to the static chain if models.list() itself fails.
    """
    global _auth_failed
    try:
        client = _get_client()
        available = {m.id for m in client.models.list().data}
        resolved = [m for m in GROQ_MODELS_PREFERRED if m in available]
        if resolved:
            print(f"  [groq] Active model chain: {resolved}")
            return resolved
        fallback = sorted(
            m for m in available
            if not any(marker in m.lower() for marker in _NON_CHAT_MODEL_MARKERS)
        )
        if fallback:
            print(f"  [groq] Preferred models retired; falling back to available models: {fallback}")
            return fallback
        print("  [groq] None of the preferred models found; using static chain")
    except Exception as exc:
        error_str = str(exc)
        if _is_auth_error(error_str):
            print(f"  [groq] Auth error during models.list(): {error_str[:120]}")
            _auth_failed = True
            raise
        print(f"  [groq] models.list() failed ({exc}); using static chain")
    return list(GROQ_MODELS_PREFERRED)


def _is_auth_error(error_str: str) -> bool:
    lowered = error_str.lower()
    return any(token in lowered for token in ("401", "403", "invalid api key", "unauthorized"))


def _clean_output(text: str) -> str:
    """Strip surrounding quotes and known preamble prefixes."""
    text = text.strip().strip('"').strip("'")
    lower = text.lower()
    for prefix in _STRIP_PREFIXES:
        if lower.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    return text


def _is_valid_output(text: str, finish_reason: str) -> bool:
    if not text or len(text) < 10:
        return False
    if text.lower().startswith("this paper"):
        return False
    if finish_reason == "length":
        return False
    if len(text.split()) > 40:
        return False
    return True


def _truncate_abstract(abstract: str, max_chars: int = 1500) -> str:
    """
    Truncate abstract to at most max_chars characters, always on a sentence boundary.
    Never cuts mid-word.
    """
    if len(abstract) <= max_chars:
        return abstract
    # Walk backward from max_chars to find end of a sentence
    chunk = abstract[:max_chars]
    # Find the last sentence-ending punctuation followed by whitespace
    last_end = max(chunk.rfind(". "), chunk.rfind("! "), chunk.rfind("? "))
    if last_end > 0:
        return chunk[:last_end + 1]
    # No sentence boundary found: cut at last space
    last_space = chunk.rfind(" ")
    if last_space > 0:
        return chunk[:last_space]
    return chunk


def _call_groq(model: str, title: str, abstract: str) -> tuple[Optional[str], str]:
    """
    Attempt one Groq call.
    Returns (summary_text, finish_reason) or (None, "") on failure.
    Retries once on 429, timeout, or 5xx.
    Returns (None, "auth_error") if an auth error is detected so callers stop looping.
    """
    try:
        client = _get_client()
    except Exception as exc:
        print(f"  [groq] Failed to get client ({exc})")
        return None, ""
    abstract_truncated = _truncate_abstract(abstract)

    user_message = (
        f"Title: {title}\n\n"
        f"Abstract: {abstract_truncated}\n\n"
        "Why it matters (one sentence, max 30 words):"
    )

    def _do_call():
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_tokens=80,
            temperature=0.3,
        )
        choice = response.choices[0]
        return choice.message.content.strip(), choice.finish_reason

    for attempt in range(2):
        try:
            raw_text, finish_reason = _do_call()
            return raw_text, finish_reason
        except Exception as exc:
            error_str = str(exc)
            if _is_auth_error(error_str):
                print(f"  [groq] Auth error: {error_str[:120]}")
                return None, "auth_error"
            if "429" in error_str or "rate limit" in error_str.lower():
                # Try to read retry-after from the error message
                wait = 3
                match = re.search(r"retry.after['\"]?\s*[:\s]+(\d+)", error_str.lower())
                if match:
                    wait = min(int(match.group(1)), 20)
                print(f"  [groq] Rate limited on {model}, waiting {wait}s...")
                time.sleep(wait)
                if attempt == 0:
                    continue
            elif any(code in error_str for code in ("timeout", "Timeout", "503", "502", "500")):
                if attempt == 0:
                    print(f"  [groq] Timeout/5xx on {model}, retrying once...")
                    time.sleep(1)
                    continue
            elif "model" in error_str.lower() and any(
                t in error_str.lower() for t in ("not found", "decommissioned", "does not exist")
            ):
                print(f"  [groq] Model {model} unavailable")
                return None, ""
            else:
                print(f"  [groq] Error with {model}: {error_str[:120]}")
            return None, ""
    return None, ""


def _heuristic_summary(abstract: str) -> str:
    """
    Extract one useful sentence from the abstract.
    Handles empty abstracts gracefully.
    Uses regex sentence splitting to avoid breaking on "et al.", "e.g.", "Fig.".
    """
    if not abstract:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", abstract)
    contribution_words = (
        "propose", "present", "introduce", "achieve", "outperform",
        "improve", "demonstrate", "show", "enable", "reduce", "increase", "develop"
    )
    for sentence in sentences[1:5]:
        words = sentence.split()
        if len(words) >= 8 and any(w in sentence.lower() for w in contribution_words):
            summary = sentence.strip()
            if not summary.endswith("."):
                summary += "."
            if len(summary) > 200:
                summary = summary[:197].rsplit(" ", 1)[0] + "..."
            return summary
    # Final fallback: first sentence
    first = sentences[0].strip()
    if len(first) > 200:
        return first[:197].rsplit(" ", 1)[0] + "..."
    return first


def get_summary(paper: dict) -> tuple[str, str]:
    """
    Generate a "Why it matters" summary for a paper.
    Returns (text, source) where source is "groq:<model>" or "heuristic".
    Tries active Groq models in order, falls back to heuristic if all fail.
    """
    global _active_models, _auth_failed

    title = paper.get("title", "")
    abstract = paper.get("abstract", "")

    if _auth_failed:
        return _heuristic_summary(abstract), "heuristic"

    api_key = _get_api_key()
    if not api_key:
        print("  [groq] GROQ_API_KEY not set; using heuristic")
        return _heuristic_summary(abstract), "heuristic"

    # Resolve active models once per process run
    if _active_models is None:
        try:
            _active_models = _resolve_active_models()
        except Exception as exc:
            if _auth_failed:
                print("  [groq] Stopping Groq pipeline due to auth error")
                return _heuristic_summary(abstract), "heuristic"
            print(f"  [groq] Could not initialise client: {exc}")
            return _heuristic_summary(abstract), "heuristic"

    print(f"  [groq] Generating summary for: {title[:60]}...")

    for model in _active_models:
        raw_text, finish_reason = _call_groq(model, title, abstract)

        if finish_reason == "auth_error":
            _auth_failed = True
            print("  [groq] Stopping model chain due to auth error.")
            break

        if raw_text is None:
            time.sleep(0.5)
            continue

        cleaned = _clean_output(raw_text)
        if _is_valid_output(cleaned, finish_reason):
            print(f"  [groq] Summary from {model}")
            return cleaned, f"groq:{model}"

        print(f"  [groq] Output from {model} failed validation (finish={finish_reason})")
        time.sleep(0.5)

    print("  [groq] All models failed or produced invalid output; using heuristic")
    return _heuristic_summary(abstract), "heuristic"


def summarize_papers(papers: list[dict]) -> list[dict]:
    """
    Add 'why_it_matters' and 'summary_source' fields to each paper.
    Prints a final summary line indicating how many came from Groq vs heuristic.
    """
    print("\n[groq] Generating 'Why it matters' summaries...")
    groq_count = 0
    heuristic_count = 0

    for i, paper in enumerate(papers, 1):
        print(f"\n[{i}/{len(papers)}]")
        if paper.get("why_it_matters") and str(paper.get("summary_source", "")).startswith("groq:"):
            # The Curator already wrote this line in its notes
            print(f"  [groq] Using the Curator's line for: {paper.get('title', '')[:60]}")
            groq_count += 1
            continue
        text, source = get_summary(paper)
        paper["why_it_matters"] = text
        paper["summary_source"] = source
        if source.startswith("groq:"):
            groq_count += 1
        else:
            heuristic_count += 1

    # Final summary line
    total = len(papers)
    print(
        f"\n[groq] Summary: {groq_count}/{total} from Groq, "
        f"{heuristic_count}/{total} from heuristic."
    )
    api_key = _get_api_key()
    if total and heuristic_count == total:
        if api_key:
            _warn(
                "Every summary used the heuristic fallback despite GROQ_API_KEY being set. "
                "Check key validity and Groq API status in the [groq] lines above."
            )
        else:
            _warn("GROQ_API_KEY is not set, so every summary used the heuristic fallback.")

    return papers


def _warn(message: str) -> None:
    """Print a warning; on GitHub Actions also raise a visible run annotation."""
    print(f"  WARNING: {message}")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::warning title=Groq summaries unavailable::{message}")
