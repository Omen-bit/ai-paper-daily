"""
tests/test_paper_store.py
Unit tests for paper_store.py structured JSON records.
"""
import sys
import os
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from paper_store import to_record, save_day, recent_featured, rebuild_index


def _paper(pid, score=10.0, **extra):
    paper = {
        "id": pid,
        "title": f"Paper {pid}",
        "authors": ["A", "B", "C", "D", "E", "F"],
        "abstract": "We propose a method.",
        "url": f"https://arxiv.org/abs/{pid}",
        "pdf_url": f"https://arxiv.org/pdf/{pid}",
        "submitted": "2026-10-30",
        "submitted_dt": datetime(2026, 10, 30, tzinfo=timezone.utc),
        "arxiv_categories": ["cs.LG"],
        "source": "arXiv",
        "hf_upvotes": 0,
        "categories": [{"emoji": "x", "name": "LLMs", "slug": "llms", "score": 3}],
        "score": score,
        "badges": [("⭐", "Top Pick")],
    }
    paper.update(extra)
    return paper


def test_to_record_is_json_safe_and_flattened():
    rec = to_record(_paper("2610.00001"), "2026-10-31", featured=True)
    json.dumps(rec)  # no datetime left behind
    assert "submitted_dt" not in rec
    assert rec["categories"] == ["llms"]
    assert rec["badges"] == ["Top Pick"]
    assert len(rec["authors"]) == 6  # full author list kept
    assert rec["featured"] is True
    assert rec["summary"] is None


def test_to_record_keeps_summary():
    p = _paper("2610.00001", why_it_matters="It is fast.", summary_source="groq")
    rec = to_record(p, "2026-10-31", featured=True)
    assert rec["summary"] == {"text": "It is fast.", "source": "groq"}


def test_save_day_orders_featured_first_then_score(tmp_path):
    papers = [_paper("a", 5), _paper("b", 50), _paper("c", 20)]
    selected = [dict(papers[2], why_it_matters="Good.", summary_source="groq")]
    save_day(papers, selected, "2026-10-31", data_dir=str(tmp_path))

    day = json.loads((tmp_path / "daily" / "2026-10-31.json").read_text(encoding="utf-8"))
    assert day["featured"] == ["c"]
    assert [p["id"] for p in day["papers"]] == ["c", "b", "a"]
    assert day["papers"][0]["summary"]["text"] == "Good."

    latest = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert latest["date"] == "2026-10-31"


def test_recent_featured_reads_the_last_editions(tmp_path):
    assert recent_featured(data_dir=str(tmp_path)) == set()
    for i, day in enumerate(["2026-10-29", "2026-10-30", "2026-10-31"]):
        p = {"id": f"2610.{i}", "title": "T", "abstract": "A", "categories": ["llms"], "score": 1.0}
        save_day([p], [p], day, data_dir=str(tmp_path))
    assert recent_featured(days=2, data_dir=str(tmp_path)) == {"2610.2", "2610.1"}
    assert recent_featured(data_dir=str(tmp_path)) == {"2610.0", "2610.1", "2610.2"}


def test_index_counts_unique_papers_newest_first(tmp_path):
    save_day([_paper("a"), _paper("b")], [_paper("a")], "2026-10-30", data_dir=str(tmp_path))
    save_day([_paper("b"), _paper("c")], [_paper("c")], "2026-10-31", data_dir=str(tmp_path))
    index = rebuild_index(str(tmp_path))
    assert [d["date"] for d in index["days"]] == ["2026-10-31", "2026-10-30"]
    assert index["total_papers"] == 3  # "b" appears on both days
