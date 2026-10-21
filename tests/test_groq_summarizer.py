"""
tests/test_groq_summarizer.py
Unit tests for groq_summarizer.py validation and heuristic functions.
No network calls are made (client is mocked where applicable).
"""
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from groq_summarizer import (
    _clean_output,
    _is_valid_output,
    _truncate_abstract,
    _heuristic_summary,
    get_summary,
)


def test_clean_output():
    assert _clean_output('"A quoted summary."') == "A quoted summary."
    assert _clean_output("'Single quoted summary.'") == "Single quoted summary."
    assert _clean_output("Here is the sentence: This method scales well.") == "This method scales well."
    assert _clean_output("Why it matters: It cuts memory consumption in half.") == "It cuts memory consumption in half."
    assert _clean_output("Sure, here is the text.") == "is the text."


def test_is_valid_output():
    # Valid output
    valid_text = "This approach introduces a modular runtime that reduces latency by 40%."
    assert _is_valid_output(valid_text, finish_reason="stop") is True

    # Rejects text starting with 'This paper'
    assert _is_valid_output("This paper presents a new benchmark.", "stop") is False
    assert _is_valid_output("this paper presents a new benchmark.", "stop") is False

    # Rejects finish_reason == 'length'
    assert _is_valid_output(valid_text, finish_reason="length") is False

    # Rejects output over 40 words
    long_text = " ".join(["word"] * 45)
    assert _is_valid_output(long_text, "stop") is False

    # Rejects too short output (< 10 chars)
    assert _is_valid_output("Short", "stop") is False


def test_truncate_abstract():
    # Short abstract unchanged
    short = "This is a short abstract of research."
    assert _truncate_abstract(short, max_chars=100) == short

    # Long abstract cut at sentence boundary
    s1 = "This is sentence one. "
    s2 = "This is sentence two. "
    s3 = "This is sentence three which exceeds the limit."
    combined = s1 + s2 + s3
    truncated = _truncate_abstract(combined, max_chars=len(s1) + len(s2) + 5)
    assert truncated == (s1 + s2).strip()

    # Abstract with no sentence boundary cuts at last space (not mid-word)
    no_period = "word1 word2 word3 word4 word5"
    cut = _truncate_abstract(no_period, max_chars=15)
    assert cut == "word1 word2"


def test_heuristic_summary():
    # Empty abstract
    assert _heuristic_summary("") == ""

    # Abstract with abbreviations: "et al.", "e.g.", "Fig."
    abstract = (
        "Smith et al. studied vision models e.g. ResNet and ViT in Fig. 1. "
        "We propose a novel attention mechanism that improves accuracy by ten percent. "
        "Further results confirm robustness across benchmarks."
    )
    summary = _heuristic_summary(abstract)
    assert "propose a novel attention mechanism" in summary
    assert not summary.startswith("Smith et al.")


def test_get_summary_with_mocked_client():
    paper = {
        "title": "Scaling Efficient Transformers",
        "abstract": "We present an architecture that reduces compute by half.",
    }

    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Reduces compute requirements by 50% for large-scale training."
    mock_choice.finish_reason = "stop"
    mock_client.chat.completions.create.return_value.choices = [mock_choice]
    mock_client.models.list.return_value.data = [MagicMock(id="llama-3.3-70b-versatile")]

    with patch("groq_summarizer._get_client", return_value=mock_client), \
         patch("groq_summarizer._get_api_key", return_value="dummy_key"):
        text, source = get_summary(paper)
        assert "Reduces compute" in text
        assert source.startswith("groq:")


def test_get_summary_fallback_on_client_error():
    paper = {
        "title": "Scaling Efficient Transformers",
        "abstract": "We present an architecture that reduces compute by half.",
    }

    with patch("groq_summarizer._get_client", side_effect=Exception("API error")), \
         patch("groq_summarizer._get_api_key", return_value="dummy_key"):
        text, source = get_summary(paper)
        assert source == "heuristic"
        assert len(text) > 0


def test_get_summary_auth_error_stops_chain():
    paper = {
        "title": "Scaling Efficient Transformers",
        "abstract": "We present an architecture that reduces compute by half.",
    }

    mock_client = MagicMock()
    mock_client.models.list.side_effect = Exception("401 Unauthorized: Invalid API Key")

    with patch("groq_summarizer._get_client", return_value=mock_client), \
         patch("groq_summarizer._get_api_key", return_value="bad_key"), \
         patch("groq_summarizer._active_models", None), \
         patch("groq_summarizer._auth_failed", False):
        text, source = get_summary(paper)
        assert source == "heuristic"
        assert len(text) > 0

