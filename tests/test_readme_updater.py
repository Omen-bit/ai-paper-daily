"""
tests/test_readme_updater.py
Tests for readme_updater.py.
Verifies section replacement idempotence and missing marker error handling.
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from readme_updater import _replace_section, MARKERS


def test_replace_section_idempotence():
    sample_content = (
        "# Title\n\n"
        "<!-- TODAY_START -->\n"
        "Old today content\n"
        "<!-- TODAY_END -->\n\n"
        "<!-- ARCHIVE_START -->\n"
        "Old archive content\n"
        "<!-- ARCHIVE_END -->\n\n"
        "<!-- STATS_START -->\n"
        "Old stats content\n"
        "<!-- STATS_END -->\n"
    )

    new_today = "New today content row 1\nNew today content row 2"
    first_run = _replace_section(sample_content, "today", new_today)
    second_run = _replace_section(first_run, "today", new_today)

    assert first_run == second_run
    assert "<!-- TODAY_START -->\nNew today content row 1\nNew today content row 2\n<!-- TODAY_END -->" in first_run


def test_missing_start_marker_raises_error():
    content_missing_start = (
        "# Title\n\n"
        "Some body text without start marker\n"
        "<!-- TODAY_END -->\n"
    )

    with pytest.raises(SystemExit) as excinfo:
        _replace_section(content_missing_start, "today", "New Content")
    assert excinfo.value.code == 1


def test_missing_end_marker_raises_error():
    content_missing_end = (
        "# Title\n\n"
        "<!-- TODAY_START -->\n"
        "Some body text without end marker\n"
    )

    with pytest.raises(SystemExit) as excinfo:
        _replace_section(content_missing_end, "today", "New Content")
    assert excinfo.value.code == 1
