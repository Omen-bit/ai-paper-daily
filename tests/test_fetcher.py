"""
tests/test_fetcher.py
Unit tests for fetcher.py retry backoff, version stripping, deduplication, and failure handling.
"""
import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fetcher import _strip_version, _is_transient, _fetch_with_retry, fetch_all_papers


def test_strip_version():
    assert _strip_version("2301.00234v1") == "2301.00234"
    assert _strip_version("2301.00234v2") == "2301.00234"
    assert _strip_version("2301.00234v12") == "2301.00234"
    assert _strip_version("2301.00234") == "2301.00234"
    assert _strip_version("cs.AI/0001001v3") == "cs.AI/0001001"


def test_is_transient():
    assert _is_transient("Connection timeout after 15s") is True
    assert _is_transient("503 Service Unavailable") is True
    assert _is_transient("429 Too Many Requests") is True
    assert _is_transient("404 Not Found") is False
    assert _is_transient("Invalid format") is False


def test_fetch_with_retry_succeeds_on_second_attempt():
    attempts = 0

    def mock_fetch():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise Exception("503 Server Error")
        return {"feed": "ok"}

    with patch("time.sleep", return_value=None):
        result = _fetch_with_retry(mock_fetch, "test_source")
        assert result == {"feed": "ok"}
        assert attempts == 2


def test_fetch_with_retry_exhausts_retries():
    def mock_failing_fetch():
        raise Exception("500 Internal Error")

    with patch("time.sleep", return_value=None):
        result = _fetch_with_retry(mock_failing_fetch, "test_source")
        assert result is None


def test_fetch_all_papers_deduplication():
    arxiv_mock = [
        {"id": "2401.00001", "title": "Paper One", "authors": ["Alice"], "source": "arXiv"},
        {"id": "2401.00002", "title": "Paper Two", "authors": ["Bob"], "source": "arXiv"},
    ]
    hf_mock = [
        {"id": "2401.00001", "title": "Paper One", "authors": ["Alice"], "source": "HuggingFace", "hf_upvotes": 42},
        {"id": "2401.00003", "title": "Paper Three", "authors": ["Charlie"], "source": "HuggingFace", "hf_upvotes": 10},
    ]

    with patch("fetcher.fetch_arxiv_papers", return_value=arxiv_mock), \
         patch("fetcher.fetch_hf_papers", return_value=hf_mock):
        merged = fetch_all_papers(max_arxiv=10)
        assert len(merged) == 3
        p1 = next(p for p in merged if p["id"] == "2401.00001")
        assert p1["source"] == "arXiv + HuggingFace"
        assert p1["hf_upvotes"] == 42


def test_fetch_all_papers_exits_when_both_fail():
    with patch("fetcher.fetch_arxiv_papers", return_value=[]), \
         patch("fetcher.fetch_hf_papers", return_value=[]):
        with pytest.raises(SystemExit) as excinfo:
            fetch_all_papers(max_arxiv=10)
        assert excinfo.value.code == 1
