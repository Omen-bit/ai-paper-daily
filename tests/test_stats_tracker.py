"""
tests/test_stats_tracker.py
Unit tests for stats_tracker.py reconciliation and error recovery.
"""
import sys
import os
import json
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from stats_tracker import load_stats, reconcile_from_disk, _reconcile_totals


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
