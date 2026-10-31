"""
tests/test_site_builder.py
Unit tests for site_builder.py: merging daily records and building the static site.
"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from paper_store import save_day
from site_builder import merge_papers, build_site, load_days


def _paper(pid, score=1.0, **extra):
    paper = {"id": pid, "title": f"Paper <{pid}>", "authors": ["A", "B"], "abstract": "Abs.",
             "submitted": "2026-10-30", "categories": ["llms"], "score": score, "badges": []}
    paper.update(extra)
    return paper


def test_merge_keeps_featured_status_and_first_seen():
    days = [  # newest first, as load_days returns them
        {"date": "2026-10-31", "papers": [{"id": "a", "title": "A", "featured": False, "abstract": ""}]},
        {"date": "2026-10-30", "papers": [{"id": "a", "title": "A", "featured": True, "abstract": "Old",
                                           "summary": {"text": "Why", "source": "groq"}}]},
    ]
    merged = merge_papers(days)
    assert merged["a"]["featured"] is True
    assert merged["a"]["featured_on"] == "2026-10-30"
    assert merged["a"]["first_seen"] == "2026-10-30"
    assert merged["a"]["summary"]["text"] == "Why"
    assert merged["a"]["abstract"] == "Old"


def test_build_site_writes_pages_and_escapes_html(tmp_path):
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    papers = [_paper("2610.1", 9), _paper("2610.2", 3)]
    save_day(papers, [dict(papers[0], why_it_matters="Fast.", summary_source="groq")],
             "2026-10-31", data_dir=data_dir)

    assert build_site(data_dir, site_dir) == 2
    for rel in ["index.html", "papers.html", "archive.html", "day/2026-10-31.html",
                "paper/2610.1.html", "paper/2610.2.html", "assets/style.css", "assets/app.js", ".nojekyll"]:
        assert os.path.exists(os.path.join(site_dir, rel)), rel

    index = open(os.path.join(site_dir, "index.html"), encoding="utf-8").read()
    assert "Paper &lt;2610.1&gt;" in index  # titles are escaped
    assert "<2610.1>" not in index
    assert "Fast." in index

    listing = json.load(open(os.path.join(site_dir, "data", "papers.json"), encoding="utf-8"))
    assert [p["i"] for p in listing] == ["2610.1", "2610.2"]
    assert listing[0]["f"] == 1


def test_build_site_with_no_data(tmp_path):
    assert load_days(str(tmp_path / "missing")) == []
    assert build_site(str(tmp_path / "missing"), str(tmp_path / "site")) == 0
    assert os.path.exists(tmp_path / "site" / "index.html")
