"""
tests/test_fetcher.py
Unit tests for fetcher.py retry backoff, version stripping, deduplication, and failure handling.
"""
import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fetcher import (
    _strip_version, _is_transient, _fetch_with_retry, fetch_all_papers,
    _fill_missing_arxiv_categories,
)


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
         patch("fetcher.fetch_hf_papers", return_value=hf_mock), \
         patch("fetcher._fill_missing_arxiv_categories"):
        merged = fetch_all_papers(max_arxiv=10)
        assert len(merged) == 3
        p1 = next(p for p in merged if p["id"] == "2401.00001")
        assert p1["source"] == "arXiv + HuggingFace"
        assert p1["hf_upvotes"] == 42


def test_fetch_all_papers_returns_empty_when_both_fail():
    # main.py writes a "no papers today" placeholder when this returns an empty list
    with patch("fetcher.fetch_arxiv_papers", return_value=[]), \
         patch("fetcher.fetch_hf_papers", return_value=[]):
        assert fetch_all_papers(max_arxiv=10) == []


def test_fill_missing_arxiv_categories():
    papers = [
        {"id": "2401.00001", "arxiv_categories": []},
        {"id": "2401.00002", "arxiv_categories": ["cs.CL"]},
    ]
    entry = MagicMock()
    entry.id = "http://arxiv.org/abs/2401.00001v2"
    entry.tags = [MagicMock(term="cs.CV"), MagicMock(term="cs.LG")]
    feed = MagicMock(entries=[entry])

    with patch("fetcher._fetch_with_retry", return_value=feed) as fetch:
        _fill_missing_arxiv_categories(papers)

    # Only the paper without categories is looked up
    assert fetch.call_count == 1
    assert papers[0]["arxiv_categories"] == ["cs.CV", "cs.LG"]
    assert papers[1]["arxiv_categories"] == ["cs.CL"]


def test_fill_missing_arxiv_categories_survives_failed_lookup():
    papers = [{"id": "2401.00001", "arxiv_categories": []}]
    with patch("fetcher._fetch_with_retry", return_value=None):
        _fill_missing_arxiv_categories(papers)
    assert papers[0]["arxiv_categories"] == []
