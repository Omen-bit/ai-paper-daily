"""
tests/test_paper_links.py
Unit tests for paper_links.py. No network calls: requests are mocked.
"""
import os
import sys
from datetime import date
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import paper_links


def test_due_checks_new_papers_weekly_and_old_ones_once():
    today = date(2026, 11, 5)
    assert paper_links.due(None, "2026-11-03", today)
    assert not paper_links.due({"checked": "2026-11-02"}, "2026-11-01", today)
    assert paper_links.due({"checked": "2026-10-28"}, "2026-10-20", today)
    assert not paper_links.due({"checked": "2026-08-01"}, "2026-07-01", today)  # too old to recheck


def test_refresh_saves_models_stars_and_lineage():
    papers = {"2611.1": {"id": "2611.1", "featured": True, "first_seen": "2026-11-05", "submitted": "2026-11-04",
                         "code_url": "https://github.com/org/repo"},
              "2611.2": {"id": "2611.2", "first_seen": "2026-11-05"}}

    def fake_get(url, headers=None):
        if "huggingface.co" in url:
            return {"models": [{"id": "a/m1", "likes": 1}, {"id": "a/m2", "likes": 9}], "datasets": [], "spaces": []}
        if "api.github.com/repos/org/repo" in url:
            return {"stargazers_count": 321}
        if "semanticscholar" in url:
            return {"citationCount": 1, "references": [{"title": "Old", "year": 2020, "citationCount": 5, "externalIds": {"ArXiv": "2001.1"}},
                                                       {"title": "Older", "year": 2019, "citationCount": 50, "externalIds": {}}],
                    "citations": [{"title": "Newer", "year": 2026, "citationCount": 0, "externalIds": {}}]}
        raise AssertionError(url)

    links = {}
    with patch.object(paper_links, "_get", side_effect=fake_get):
        n = paper_links.refresh(papers, links, today=date(2026, 11, 5), max_lookups=1, pause=0)
    assert n == 1 and list(links) == ["2611.1"]  # the pick goes first, and the cap holds
    entry = links["2611.1"]
    assert entry["checked"] == "2026-11-05" and entry["stars"] == 321
    assert entry["hf"]["models"]["n"] == 2 and entry["hf"]["models"]["top"][0]["id"] == "a/m2"
    assert [r["title"] for r in entry["s2"]["refs"]] == ["Older", "Old"]
    assert entry["s2"]["cites"][0]["title"] == "Newer"


def test_refresh_keeps_old_data_when_a_service_fails():
    papers = {"2611.1": {"id": "2611.1", "first_seen": "2026-11-05"}}
    links = {"2611.1": {"checked": "2026-10-01", "hf": {"models": {"n": 1, "top": []}}}}

    def failing(url, headers=None):
        raise RuntimeError("down")

    with patch.object(paper_links, "_get", side_effect=failing):
        paper_links.refresh(papers, links, today=date(2026, 11, 5), pause=0)
    assert links["2611.1"]["hf"]["models"]["n"] == 1
    assert links["2611.1"]["checked"] == "2026-11-05"
