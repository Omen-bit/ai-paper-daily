"""
groq_summarizer.py
Generates "Why it matters" one-liner summaries using Groq API.
Falls back through multiple models if one is unavailable.
"""

import os
import time
import httpx
from typing import Optional

# Groq model fallback chain — ordered by preference.
# Groq adds/removes models frequently; this list provides resilience.
GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama3-70b-8192",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
    "llama3-8b-8192",
    "llama-3.1-8b-instant",
]

SYSTEM_PROMPT = """You are a concise science communicator helping researchers quickly understand why a paper matters.
Given a paper title and abstract, write a SINGLE sentence (max 30 words) explaining:
- What problem it solves OR what it enables
- Why it is significant to the AI/ML community
Be direct, specific, and avoid jargon. Do NOT start with "This paper". Output ONLY the sentence."""

_groq_client = None


def _get_client():
    """Lazy-initialize Groq client with a clean httpx client to avoid proxies conflict."""
    global _groq_client
    if _groq_client is None:
        try:
            from groq import Groq
            api_key = os.environ.get("GROQ_API_KEY", "")
            if not api_key:
                raise ValueError("GROQ_API_KEY environment variable not set")
            # Pass our own httpx.Client to bypass groq's internal client
            # which passes `proxies` — removed in httpx>=0.28.0
            _groq_client = Groq(api_key=api_key, http_client=httpx.Client())
        except ImportError:
            raise ImportError("groq package not installed. Run: pip install groq")
    return _groq_client


def _call_groq(model: str, title: str, abstract: str) -> Optional[str]:
    """Attempt to call Groq API with a specific model."""
    client = _get_client()

    # Truncate abstract to keep within token limits
    abstract_truncated = abstract[:800]

    user_message = f"""Title: {title}

Abstract: {abstract_truncated}

Why it matters (one sentence, max 30 words):"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_tokens=80,
            temperature=0.3,
        )
        result = response.choices[0].message.content.strip()

        # Sanity check — must be a reasonable sentence
        if result and len(result) > 10 and len(result) < 400:
            return result
        return None

    except Exception as e:
        error_str = str(e).lower()
        if "model" in error_str and ("not found" in error_str or "decommissioned" in error_str or "does not exist" in error_str):
            print(f"  ⚠️ Model {model} unavailable, trying next...")
            return None
        elif "rate limit" in error_str or "429" in error_str:
            print(f"  ⏳ Rate limited on {model}, waiting 3s...")
            time.sleep(3)
            return None
        else:
            print(f"  ❌ Groq error with {model}: {e}")
            return None


def _heuristic_summary(paper: dict) -> str:
    """
    Fallback heuristic summary when Groq is unavailable.
    Extracts key info from abstract keywords.
    """
    title = paper.get("title", "")
    abstract = paper.get("abstract", "")

    # Try to extract the first concrete result or contribution from abstract
    sentences = abstract.split(". ")
    for sentence in sentences[1:4]:  # Skip first sentence (usually context)
        words = sentence.split()
        if len(words) >= 8 and any(w in sentence.lower() for w in [
            "propose", "present", "introduce", "achieve", "outperform",
            "improve", "demonstrate", "show", "enable", "reduce", "increase"
        ]):
            summary = sentence.strip()
            if not summary.endswith("."):
                summary += "."
            return summary[:200]

    # Final fallback: first abstract sentence
    first = sentences[0].strip()
    return (first[:197] + "...") if len(first) > 200 else first


def get_summary(paper: dict) -> str:
    """
    Generate a "Why it matters" summary for a paper.
    Tries Groq models in order, falls back to heuristic if all fail.
    """
    title = paper.get("title", "")
    abstract = paper.get("abstract", "")

    # Check if Groq API key is available
    if not os.environ.get("GROQ_API_KEY"):
        print("  ℹ️  GROQ_API_KEY not set, using heuristic summary")
        return _heuristic_summary(paper)

    print(f"  🤖 Generating summary for: {title[:60]}...")

    for model in GROQ_MODELS:
        result = _call_groq(model, title, abstract)
        if result:
            print(f"  ✅ Summary generated with {model}")
            return result
        time.sleep(0.5)  # Small delay between model attempts

    # All Groq models failed — fall back to heuristic
    print("  ⚠️ All Groq models failed, using heuristic fallback")
    return _heuristic_summary(paper)


def summarize_papers(papers: list[dict]) -> list[dict]:
    """Add 'why_it_matters' field to each paper."""
    print("\n💬 Generating 'Why it matters' summaries...")
    for i, paper in enumerate(papers, 1):
        print(f"\n[{i}/{len(papers)}]")
        paper["why_it_matters"] = get_summary(paper)
    return papers
