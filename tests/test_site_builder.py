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


def test_trending_slot_is_labelled(tmp_path):
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    a = _paper("2610.1", 9, slot="pick")
    b = _paper("2610.2", 3, slot="trending", hf_upvotes=42)
    save_day([a, b], [a, b], "2026-10-31", data_dir=data_dir)
    build_site(data_dir, site_dir)
    home = open(os.path.join(site_dir, "index.html"), encoding="utf-8").read()
    assert "Today’s pick" in home and "Trending" in home and "42 upvotes on Hugging Face" in home
    listing = json.load(open(os.path.join(site_dir, "data", "papers.json"), encoding="utf-8"))
    assert {p["i"]: p["f"] for p in listing} == {"2610.1": 1, "2610.2": 2}


def test_home_has_for_you_section_and_site_ids(tmp_path):
    from site_builder import RECOMMEND_URL
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    save_day([_paper("2610.1"), _paper("2610.2")], [_paper("2610.1")], "2026-10-31", data_dir=data_dir)
    build_site(data_dir, site_dir)
    home = open(os.path.join(site_dir, "index.html"), encoding="utf-8").read()
    assert "data-foryou" in home and f'data-url="{RECOMMEND_URL}"' in home
    assert RECOMMEND_URL.endswith("/functions/v1/recommend")
    ids = json.load(open(os.path.join(site_dir, "data", "ids.json"), encoding="utf-8"))
    assert ids == ["2610.1", "2610.2"]


def test_scout_page_has_describe_only_form(tmp_path):
    from site_builder import SCOUT_URL
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    save_day([_paper("2610.1")], [_paper("2610.1")], "2026-10-31", data_dir=data_dir)
    build_site(data_dir, site_dir)
    page = open(os.path.join(site_dir, "scout.html"), encoding="utf-8").read()
    assert f'data-url="{SCOUT_URL}"' in page and SCOUT_URL.endswith("/functions/v1/scout")
    assert '<label class="field-label" for="desc">Describe your project</label>' in page
    assert "no code" in page and 'maxlength="1000"' in page
    assert 'href="scout.html"' in open(os.path.join(site_dir, "index.html"), encoding="utf-8").read()


def test_paper_page_has_ask_box(tmp_path):
    from site_builder import ASK_URL
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    save_day([_paper("2610.1")], [_paper("2610.1")], "2026-10-31", data_dir=data_dir)
    build_site(data_dir, site_dir)
    page = open(os.path.join(site_dir, "paper", "2610.1.html"), encoding="utf-8").read()
    assert f'data-url="{ASK_URL}"' in page and ASK_URL.endswith("/functions/v1/ask")
    assert 'for="ask-q"' in page and "data-ask-suggest" in page


def test_most_read_takes_second_slot_once_readers_are_enough(tmp_path):
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    export_dir = str(tmp_path / "export")
    a, b = _paper("2610.1", 9, slot="pick"), _paper("2610.2", 3, slot="trending", hf_upvotes=9)
    others = [_paper(f"2610.{n}", 1, title=f"Other {n}") for n in range(3, 7)]
    save_day([a, b] + others, [a, b], "2026-10-31", data_dir=data_dir)

    def most_read(views):
        os.makedirs(export_dir, exist_ok=True)
        with open(os.path.join(export_dir, "most_read.json"), "w", encoding="utf-8") as f:
            json.dump({"papers": [{"id": "2610.5", "views": views}, {"id": "2610.4", "views": 5},
                                  {"id": "2610.3", "views": 4}]}, f)

    most_read(8)  # too few readers: Trending stays
    build_site(data_dir, site_dir, export_dir)
    home = open(os.path.join(site_dir, "index.html"), encoding="utf-8").read()
    assert "Trending" in home and "Most read this week" in home and "8 readers" in home

    most_read(25)
    build_site(data_dir, site_dir, export_dir)
    home = open(os.path.join(site_dir, "index.html"), encoding="utf-8").read()
    assert ">Most read<" in home and "25 readers this week" in home
    assert 'data-picks="2610.1 2610.5"' in home
    page = open(os.path.join(site_dir, "paper", "2610.1.html"), encoding="utf-8").read()
    assert 'data-feedback="2610.1"' in page and 'data-vote="useful"' in page


def test_published_dates_and_database_archive(tmp_path):
    data_dir, site_dir, export_dir = str(tmp_path / "data"), str(tmp_path / "site"), str(tmp_path / "export")
    save_day([_paper("2610.1", submitted="2026-10-28")], [], "2026-10-31", data_dir=data_dir)
    os.makedirs(export_dir)
    with open(os.path.join(export_dir, "papers.json"), "w", encoding="utf-8") as f:
        json.dump({"papers": [
            {"id": "2610.1", "title": "Dup", "submitted": "2026-10-28"},
            {"id": "2503.7", "title": "Older", "authors": ["A", "B", "C", "D"], "categories": ["llms"],
             "submitted": "2025-03-04", "first_seen": "2025-03-05"}]}, f)
    build_site(data_dir, site_dir, export_dir)
    listing = json.load(open(os.path.join(site_dir, "data", "papers.json"), encoding="utf-8"))
    assert [(p["i"], p["d"], p.get("x", 0)) for p in listing] == [("2610.1", "2026-10-28", 0), ("2503.7", "2025-03-04", 1)]
    assert listing[1]["n"] == 4 and len(listing[1]["a"]) == 3
    page = open(os.path.join(site_dir, "paper", "2610.1.html"), encoding="utf-8").read()
    assert "<dt>Published</dt><dd>28 Oct 2026</dd>" in page
    assert not os.path.exists(os.path.join(site_dir, "paper", "2503.7.html"))


def test_trends_page_is_built_and_linked(tmp_path):
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    save_day([_paper("2610.1")], [], "2026-10-31", data_dir=data_dir)
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    rows = [{"id": f"25{i:05d}", "title": "T", "categories": ["llms"], "first_seen": f"2026-{m:02d}-10"}
            for i, m in enumerate([8] * 70 + [9] * 70 + [10] * 70)]
    (export_dir / "papers.json").write_text(json.dumps({"papers": rows}), encoding="utf-8")
    build_site(data_dir, site_dir, str(export_dir))
    page = open(os.path.join(site_dir, "trends.html"), encoding="utf-8").read()
    assert "<h1>Trends</h1>" in page and "Topic share, month by month" in page
    home = open(os.path.join(site_dir, "index.html"), encoding="utf-8").read()
    assert 'href="trends.html"' in home and 'href="archive.html"' not in home.split("</nav>")[0]
    archive = open(os.path.join(site_dir, "archive.html"), encoding="utf-8").read()
    assert 'class="tabs"' in archive


def test_trends_page_tracks_technologies(tmp_path):
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    save_day([_paper("2610.1")], [], "2026-10-31", data_dir=data_dir)
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    rows = []
    for m in range(4, 11):  # April to October, agents growing fast in the last three months
        for i in range(60):
            title = "AI Agents for Tasks" if (m >= 8 and i < 20) or (m < 8 and i < 5) else "A Study"
            rows.append({"id": f"26{m:02d}.{i:05d}", "title": title, "categories": ["llms"],
                         "first_seen": f"2026-{m:02d}-{1 + i % 28:02d}", "hf_upvotes": 3})
    (export_dir / "papers.json").write_text(json.dumps({"papers": rows}), encoding="utf-8")
    build_site(data_dir, site_dir, str(export_dir))
    page = open(os.path.join(site_dir, "trends.html"), encoding="utf-8").read()
    assert "Technologies to watch" in page and "AI agents" in page
    assert "Breakout of the season" in page and "Every technology, month by month" not in page
    assert page.index("Technologies to watch") < page.index("Topic share, month by month")
    assert "assets/style.css?v=" in page and "assets/app.js?v=" in page


def test_trends_page_waits_for_three_months_of_history(tmp_path):
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    papers = [_paper(f"2610.{i}", first_seen="2026-10-10") for i in range(40)]
    save_day(papers, [], "2026-10-31", data_dir=data_dir)
    build_site(data_dir, site_dir, str(tmp_path / "none"))
    page = open(os.path.join(site_dir, "trends.html"), encoding="utf-8").read()
    assert "three months" in page and "Topic share" not in page


def test_home_has_a_hidden_watched_projects_section(tmp_path):
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    save_day([_paper("2610.1")], [_paper("2610.1")], "2026-10-31", data_dir=data_dir)
    build_site(data_dir, site_dir, str(tmp_path / "none"))
    home = open(os.path.join(site_dir, "index.html"), encoding="utf-8").read()
    assert "data-watch " in home and "Your projects" in home and "/functions/v1/search" in home
    scout = open(os.path.join(site_dir, "scout.html"), encoding="utf-8").read()
    assert "If nothing fits, it says so." in scout
