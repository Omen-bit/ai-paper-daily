"""
tests/test_paper_reading_tools.py
"Copy for LLM", "View as Markdown" and the sticky "On this page" bar on paper pages.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import site_builder
from paper_store import save_day
from site_builder import build_site, build_paper, paper_markdown

REC = {
    "id": "2611.00001", "title": "A  Small\nTest Paper", "authors": ["Ada Lovelace", "Alan Turing"],
    "abstract": "We study tests. Our method cuts errors by 42.5% on average.",
    "url": "https://arxiv.org/abs/2611.00001", "pdf_url": "https://arxiv.org/pdf/2611.00001",
    "published": "2026-11-01", "hf_upvotes": 12, "categories": ["reasoning"],
    "curator": {"tldr": "It makes tests better.", "whats_new": "A new idea.", "key_result": "42.5% fewer errors.",
                "build_ideas": ["Build a checker.", "Build a dashboard."], "difficulty": "beginner",
                "check_question": "What does it cut?", "check_answer": "Errors."},
}


def test_markdown_has_the_notes_numbers_and_links():
    md = paper_markdown(REC)
    assert md.startswith("# A Small Test Paper\n")
    assert "**Authors:** Ada Lovelace, Alan Turing" in md
    assert "[PDF](https://arxiv.org/pdf/2611.00001)" in md
    assert f"[This page]({site_builder.SITE_URL}paper/2611.00001.html)" in md
    assert "**TL;DR:** It makes tests better." in md
    assert "- **Key result:** 42.5% fewer errors." in md
    assert "## Key numbers" in md and "**42.5%**" in md
    assert "1. Build a checker.\n2. Build a dashboard." in md
    assert "**Answer:** Errors." in md
    assert "<" not in md


def test_markdown_without_notes_still_reads_well():
    md = paper_markdown({k: v for k, v in REC.items() if k != "curator"})
    assert "## Abstract" in md and "## What you could build" not in md and "TL;DR" not in md


def test_page_has_the_buttons_and_the_contents_bar():
    html = build_paper(REC)
    assert 'data-md-copy data-md="2611.00001.md"' in html
    assert 'href="2611.00001.md" data-md-view' in html
    assert 'class="rd-toc"' not in html  # the details column holds no contents list, so it fits one screen
    for sec in ("minute", "numbers", "abstract", "build", "ask-sec"):
        assert f'id="{sec}"' in html
    assert 'href="#fits"' not in html


def test_build_writes_a_markdown_file_next_to_each_paper(tmp_path):
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    save_day([REC], [REC], "2026-11-01", data_dir=data_dir)
    build_site(data_dir, site_dir)
    path = os.path.join(site_dir, "paper", "2611.00001.md")
    assert os.path.exists(path)
    assert open(path, encoding="utf-8").read().startswith("# A Small Test Paper")


def test_contents_bar_lists_only_sections_on_the_page():
    html = build_paper(REC)
    if 'id="try"' not in html:
        assert 'href="#try"' not in html
    assert 'href="#fits"' not in html
