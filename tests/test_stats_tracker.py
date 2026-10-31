"""
tests/test_stats_tracker.py
Unit tests for stats_tracker.py reconciliation and error recovery.
"""
import sys
import os
import json
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from stats_tracker import (
    load_stats, reconcile_from_disk, _reconcile_totals, update_stats, _parse_digest_file,
)


def test_reconcile_totals():
    stats = {
        "digests": [
            {"date": "2026-10-20", "paper_count": 2},
            {"date": "2026-10-19", "paper_count": 2},
            {"date": "2026-10-18", "paper_count": 0},  # placeholder
        ]
    }
    reconciled = _reconcile_totals(stats)
    assert reconciled["total_digests"] == 2  # 2 non-placeholder editions
    assert reconciled["total_papers"] == 4
    assert reconciled["first_digest"] == "2026-10-18"
    assert reconciled["papers_by_date"]["2026-10-20"] == 2


def test_reconcile_from_disk_sync_anomaly():
    # Simulate an anomaly where stats.json has inflated numbers (6 papers, 3 editions)
    # but disk only has one digest file with 2 papers.
    anomalous_stats = {
        "total_papers": 6,
        "total_digests": 3,
        "digests": [
            {"date": "2026-10-20", "paper_count": 6, "top_category": "General"},
            {"date": "2026-10-19", "paper_count": 2, "top_category": "General"},  # phantom file
        ]
    }

    mock_disk_entries = [{"date": "2026-10-20", "is_placeholder": False}]

    with patch("stats_tracker.scan_digests_folder", return_value=mock_disk_entries):
        reconciled = reconcile_from_disk(anomalous_stats)
        # Phantom date 2026-10-19 removed because it does not exist on disk
        dates = [d["date"] for d in reconciled["digests"]]
        assert dates == ["2026-10-20"]
        assert reconciled["total_digests"] == 1


def test_load_stats_corrupted_json_recovery(tmp_path):
    # Test that corrupted stats.json (e.g. merge conflict markers) is handled gracefully
    corrupted_file = os.path.join(tmp_path, "stats.json")
    with open(corrupted_file, "w", encoding="utf-8") as f:
        f.write("<<<<<<< HEAD\ncorrupted json\n=======\n>>>>>>>\n")

    with patch("stats_tracker.STATS_FILE", corrupted_file), \
         patch("stats_tracker.scan_digests_folder", return_value=[]):
        recovered = load_stats()
        assert isinstance(recovered, dict)
        assert recovered["total_papers"] == 0
        assert recovered["total_digests"] == 0


def test_update_stats_idempotence(tmp_path):
    # Verify that running update_stats multiple times on the same date gives identical stats
    stats_file = os.path.join(tmp_path, "stats.json")
    papers = [
        {
            "id": "2610.00001",
            "title": "Novel Reasoning Architecture",
            "authors": ["Alice"],
            "categories": [{"slug": "reasoning-agents"}],
        },
        {
            "id": "2610.00002",
            "title": "Efficient Scaling Theory",
            "authors": ["Bob"],
            "categories": [{"slug": "ml-theory"}],
        },
    ]

    with patch("stats_tracker.STATS_FILE", stats_file), \
         patch("stats_tracker.DIGESTS_DIR", str(tmp_path)):
        # Run 1
        res1 = update_stats(papers, "2026-10-21")
        # Run 2 on same date
        res2 = update_stats(papers, "2026-10-21")
        # Run 3 on same date
        res3 = update_stats(papers, "2026-10-21")

        assert res1["total_papers"] == 2
        assert res2["total_papers"] == 2
        assert res3["total_papers"] == 2

        assert res1["total_digests"] == 1
        assert res2["total_digests"] == 1
        assert res3["total_digests"] == 1

        assert res3["papers_by_category"]["reasoning-agents"] == 1
        assert res3["papers_by_category"]["ml-theory"] == 1
        assert res3["top_authors"]["Alice"] == 1
        assert res3["top_authors"]["Bob"] == 1



def test_reconcile_keeps_full_stored_records():
    # Stored records carry fields the digest Markdown only partly shows.
    # Reconciling against the digest file must not throw them away.
    stored_paper = {
        "id": "2610.00001",
        "title": "Novel Reasoning Architecture",
        "authors": ["Alice", "Bob", "Carol", "Dan", "Eve", "Frank"],
        "categories": ["reasoning-agents"],
        "badges": [["⭐", "Top Pick"]],
        "url": "https://arxiv.org/abs/2610.00001",
        "pdf_url": "https://arxiv.org/pdf/2610.00001",
        "submitted": "2026-10-19",
    }
    parsed_paper = {
        "id": "2610.00001",
        "title": "Novel Reasoning Architecture",
        "authors": ["Alice", "Bob", "Carol", "Dan"],
        "categories": ["reasoning-agents"],
        "url": "https://arxiv.org/abs/2610.00001",
        "pdf_url": "https://arxiv.org/pdf/2610.00001",
        "submitted": "2026-10-19",
    }
    stats = {"digests": [{"date": "2026-10-20", "paper_count": 1, "papers": [dict(stored_paper)]}]}

    with patch("stats_tracker.scan_digests_folder", return_value=[{"date": "2026-10-20", "is_placeholder": False}]), \
         patch("stats_tracker._parse_digest_file", return_value=[parsed_paper]), \
         patch("stats_tracker.os.path.exists", return_value=True):
        reconciled = reconcile_from_disk(stats)

    paper = reconciled["digests"][0]["papers"][0]
    assert paper["authors"] == stored_paper["authors"]
    assert paper["badges"] == stored_paper["badges"]


def test_reconcile_repairs_missing_fields_from_digest():
    # Records damaged by the old reconcile (no date or PDF link) are filled from the digest file
    damaged = {"id": "2610.00001", "title": "Paper", "authors": ["Alice"], "categories": ["llms"]}
    parsed = {
        "id": "2610.00001", "title": "Paper", "authors": ["Alice"], "categories": ["llms"],
        "url": "https://arxiv.org/abs/2610.00001",
        "pdf_url": "https://arxiv.org/pdf/2610.00001",
        "submitted": "2026-10-18",
    }
    stats = {"digests": [{"date": "2026-10-20", "paper_count": 1, "papers": [damaged]}]}

    with patch("stats_tracker.scan_digests_folder", return_value=[{"date": "2026-10-20", "is_placeholder": False}]), \
         patch("stats_tracker._parse_digest_file", return_value=[parsed]), \
         patch("stats_tracker.os.path.exists", return_value=True):
        reconciled = reconcile_from_disk(stats)

    paper = reconciled["digests"][0]["papers"][0]
    assert paper["submitted"] == "2026-10-18"
    assert paper["pdf_url"] == "https://arxiv.org/pdf/2610.00001"


def test_parse_digest_file_reads_date_and_pdf(tmp_path):
    digest = tmp_path / "2026-10-20.md"
    digest.write_text(
        "# Digest\n\n"
        "### 1. [Some Paper Title](https://arxiv.org/abs/2610.00001)\n\n"
        "- 👥 **Authors:** Alice, Bob\n"
        "- 📅 **Date:** 2026-10-18 &nbsp;•&nbsp; 📡 **HuggingFace**\n"
        "\n---\n",
        encoding="utf-8",
    )
    papers = _parse_digest_file(str(digest))
    assert papers[0]["id"] == "2610.00001"
    assert papers[0]["submitted"] == "2026-10-18"
    assert papers[0]["pdf_url"] == "https://arxiv.org/pdf/2610.00001"
    assert papers[0]["authors"] == ["Alice", "Bob"]
