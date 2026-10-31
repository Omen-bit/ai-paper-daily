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


def test_related_papers_prefer_shared_words_and_topics():
    from site_builder import related_papers
    papers = {
        "a": {"id": "a", "title": "Sparse attention for long documents", "abstract": "", "categories": ["llms"]},
        "b": {"id": "b", "title": "Long documents with sparse attention kernels", "abstract": "", "categories": ["llms"]},
        "c": {"id": "c", "title": "Robot grasping from images", "abstract": "", "categories": ["computer-vision"]},
    }
    rel = related_papers(papers)
    assert rel["a"] == ["b"]
    assert "c" not in rel["a"]


def test_paper_page_has_reader_tools_and_bibtex(tmp_path):
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    papers = [_paper("2610.1", 9), _paper("2610.2", 3)]
    save_day(papers, [papers[0]], "2026-10-31", data_dir=data_dir)
    build_site(data_dir, site_dir)
    html = open(os.path.join(site_dir, "paper", "2610.1.html"), encoding="utf-8").read()
    for marker in ["data-save", "data-share", "data-copy-bibtex", "archivePrefix = {arXiv}", 'rel="next"']:
        assert marker in html, marker
    assert os.path.exists(os.path.join(site_dir, "saved.html"))


def test_curator_notes_show_on_paper_page_and_card(tmp_path):
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    notes = {"tldr": "Short <take>.", "whats_new": "New bit.", "key_result": None,
             "why_it_matters": "Matters.", "build_ideas": ["Build one.", "Build two."],
             "difficulty": "advanced", "difficulty_reason": "Needs many GPUs."}
    paper = _paper("2610.7", 5, why_it_matters="Matters.", summary_source="groq:m",
                   curator=notes, code_url="https://github.com/a/b")
    save_day([paper], [paper], "2026-10-31", data_dir=data_dir)
    build_site(data_dir, site_dir)
    page = open(os.path.join(site_dir, "paper", "2610.7.html"), encoding="utf-8").read()
    assert "Curator's notes" in page
    assert "Short &lt;take&gt;." in page
    assert "Key result" not in page  # empty fields are left out
    assert "Build two." in page and "Advanced" in page
    assert 'href="https://github.com/a/b"' in page
    home = open(os.path.join(site_dir, "index.html"), encoding="utf-8").read()
    assert "In short" in home and "Code available" in home


def test_papers_page_offers_search_by_meaning(tmp_path):
    from site_builder import SEARCH_URL
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    save_day([_paper("2610.9")], [_paper("2610.9")], "2026-10-31", data_dir=data_dir)
    build_site(data_dir, site_dir)
    page = open(os.path.join(site_dir, "papers.html"), encoding="utf-8").read()
    assert 'id="meaning"' in page
    assert f'data-search-url="{SEARCH_URL}"' in page
    assert SEARCH_URL.startswith("https://") and SEARCH_URL.endswith("/functions/v1/search")


def test_paper_page_has_check_question_and_next_pick(tmp_path):
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    notes = {"tldr": "Short take here.", "whats_new": "New bit.", "why_it_matters": "Matters.",
             "build_ideas": ["Build one.", "Build two."], "difficulty": "beginner",
             "check_question": "What is <traded> for speed?", "check_answer": "Memory."}
    a = _paper("2610.1", 9, curator=notes)
    b = _paper("2610.2", 8)
    save_day([a, b], [a, b], "2026-10-31", data_dir=data_dir)
    build_site(data_dir, site_dir)
    page = open(os.path.join(site_dir, "paper", "2610.1.html"), encoding="utf-8").read()
    assert "What is &lt;traded&gt; for speed?" in page
    assert "data-check-answer" in page
    assert "data-done" in page and "paper/2610.2.html" in page.replace("../", "paper/")
