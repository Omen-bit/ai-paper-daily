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
    for marker in ["data-save", "data-share", "data-copy-bibtex", "archivePrefix = {arXiv}", 'data-out="pdf"']:
        assert marker in html, marker
    for gone in ['rel="next"', "data-focus", "data-pixbar", "data-progress"]:
        assert gone not in html, gone
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
    assert "Next pick" in page and "paper/2610.2.html" in page.replace("../", "paper/")


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
    assert "data-daily" not in home and "Topic pulse" not in home
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
    assert '<time datetime="2026-10-28">2026.10.28</time>' in page
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
    assert "has no good paper, it says so." in scout and "page-scout" in scout


def test_picks_show_when_the_paper_came_out(tmp_path):
    from site_builder import is_older
    assert is_older({"submitted": "2026-08-01", "first_seen": "2026-10-31"})
    assert not is_older({"submitted": "2026-10-20", "first_seen": "2026-10-31"})
    assert not is_older({"first_seen": "2026-10-31"})
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    picks = [_paper("2610.1"), _paper("2608.2", submitted="2026-08-01")]
    save_day(picks, picks, "2026-10-31", data_dir=data_dir)
    build_site(data_dir, site_dir, str(tmp_path / "export"))
    home = open(os.path.join(site_dir, "index.html"), encoding="utf-8").read()
    assert "Published 30 Oct 2026" in home and "Published 1 Aug 2026" in home
    assert home.count("Older paper, trending now") == 1
    old = open(os.path.join(site_dir, "paper", "2608.2.html"), encoding="utf-8").read()
    assert "Trending since" in old


def test_featured_cards_ask_if_the_paper_was_seen_before():
    from site_builder import featured_card, seen_check
    rec = {"id": "2610.00001", "title": "T", "abstract": "A.", "submitted": "2026-10-30", "slot": "pick"}
    html = featured_card(rec, 1, "")
    assert 'data-slot="pick"' in html and 'data-seen="2610.00001"' in html
    assert seen_check(dict(rec, slot="most-read")) == ""  # asked on the top pick only
    assert seen_check(dict(rec, slot=None)) == ""  # editions from before slots existed


def test_lead_sentence_takes_the_first_sentence_and_cuts_long_ones():
    from site_builder import lead_sentence
    assert lead_sentence("We build X. It is fast.") == "We build X."
    assert lead_sentence("Scores rose 2.5 points on GPT-4. Then more.") == "Scores rose 2.5 points on GPT-4."
    long = lead_sentence("word " * 80)
    assert len(long) <= 180 and long.endswith("…")
    assert lead_sentence("") == ""


def test_cards_carry_summary_and_signals():
    from site_builder import compact, archive_compact
    rec = {"id": "2610.1", "title": "T", "authors": ["A"], "abstract": "First. Second.", "submitted": "2026-10-30",
           "source": "arXiv", "hf_upvotes": 0, "featured": True, "slot": "pick", "code_url": "https://github.com/x",
           "curator": {"tldr": "Short.", "difficulty": "beginner"}}
    c = compact(rec)
    assert (c["m"], c["u"], c["k"], c["h"], c["l"], c["f"]) == ("Short.", 0, 1, 1, "b", 1)
    c2 = compact(dict(rec, curator=None, hf_upvotes=40, source="arXiv + HuggingFace"))
    assert c2["m"] == "First." and c2["u"] == 40 and "h" not in c2
    a = archive_compact({"id": "2601.2", "title": "T", "authors": [], "lead": "Lead.", "hf_upvotes": 7, "source": "HuggingFace"})
    assert (a["m"], a["u"], a["x"]) == ("Lead.", 7, 1)


def test_cards_know_when_a_paper_was_published_and_when_we_added_it():
    from site_builder import compact, archive_compact
    rec = {"id": "2611.1", "title": "T", "authors": ["A"], "abstract": "First.", "submitted": "2026-11-03",
           "first_seen": "2026-11-05", "arxiv_categories": ["cs.CL", "cs.LG"], "hf_upvotes": 3}
    c = compact(rec)
    assert (c["d"], c["w"], c["ac"]) == ("2026-11-03", "2026-11-05", "cs.CL")
    a = archive_compact({"id": "2601.2", "title": "T", "authors": [], "submitted": "2026-01-02", "first_seen": "2026-01-04"})
    assert (a["d"], a["w"]) == ("2026-01-02", "2026-01-04")


def test_paper_page_has_the_breakdown_and_asks_for_a_summary_only_without_notes(tmp_path):
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    a = _paper("2610.1", 9, curator={"tldr": "Short take."})
    b = _paper("2610.2", 3)
    save_day([a, b], [a], "2026-10-31", data_dir=data_dir)
    build_site(data_dir, site_dir)
    with_notes = open(os.path.join(site_dir, "paper", "2610.1.html"), encoding="utf-8").read()
    without = open(os.path.join(site_dir, "paper", "2610.2.html"), encoding="utf-8").read()
    assert 'data-breakdown="2610.1"' in with_notes and "data-summary" not in with_notes
    assert 'data-breakdown="2610.2"' in without and 'data-summary="1"' in without


def test_trends_tab_waits_for_enough_history(tmp_path):
    import site_builder
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    save_day([_paper("2610.1", 9)], [_paper("2610.1", 9)], "2026-10-31", data_dir=data_dir)
    build_site(data_dir, site_dir)
    home = open(os.path.join(site_dir, "index.html"), encoding="utf-8").read()
    assert 'href="trends.html"' not in home.split("</nav>")[0]
    assert os.path.exists(os.path.join(site_dir, "trends.html"))
    site_builder.SHOW_TRENDS = True


def test_tidy_tex_makes_abstract_maths_readable():
    from site_builder import tidy_tex
    assert tidy_tex(r"up to $38.6\times$ fewer and $\geq 90\%$") == "up to 38.6× fewer and ≥ 90%"
    assert tidy_tex("costs $5 and $6 per hour") == "costs $5 and $6 per hour"


def test_umami_script_only_when_a_website_id_is_set(tmp_path, monkeypatch):
    import site_builder
    site_dir = tmp_path / "site"
    build_site(str(tmp_path / "missing"), str(site_dir))
    assert "umami" not in (site_dir / "index.html").read_text(encoding="utf-8")

    monkeypatch.setattr(site_builder, "UMAMI_WEBSITE_ID", "0a1b2c3d-1111-2222-3333-444455556666")
    build_site(str(tmp_path / "missing"), str(site_dir))
    index = (site_dir / "index.html").read_text(encoding="utf-8")
    assert 'data-website-id="0a1b2c3d-1111-2222-3333-444455556666"' in index
    assert 'data-auto-track="false"' in index


def test_tidy_tex_handles_bold_numbers_and_arrows():
    from site_builder import tidy_tex
    text = r"by $\boldsymbol{300\times}$ ($\boldsymbol{1{,}200 \rightarrow 4}$ tokens)"
    assert tidy_tex(text) == "by 300× (1,200 → 4 tokens)"


def test_key_numbers_come_from_the_abstract_and_skip_names():
    from site_builder import key_numbers
    abstract = ("Agents need stable websites. We build a suite of 153 websites with 3,518 tasks. "
                "A Qwen3-8B agent trained on it cuts errors from 9.9% to 1.0% and runs 4.3x faster.")
    values = [n["value"] for n in key_numbers(abstract)]
    assert "9.9% → 1.0%" in values and "4.3×" in values
    assert "8B" not in values and "1.0%" not in values
    assert len(values) == 3
    for n in key_numbers(abstract):
        assert n["context"] and len(n["context"].split()) <= 18


def test_skim_labels_problem_method_and_result():
    from site_builder import skim_label
    assert skim_label("Large models are costly to serve.", 0) == "goal"
    assert skim_label("We propose FastServe, a scheduler for long prompts.", 1) == "method"
    assert skim_label("FastServe achieves 2x higher throughput than vLLM.", 3) == "result"
    assert skim_label("The scheduler has three parts.", 4) == ""


def test_paper_page_shows_links_lineage_and_terms(tmp_path):
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    notes = {"tldr": "It learns a latent action space from videos.", "whats_new": "New bit.", "why_it_matters": "Matters.",
             "build_ideas": ["Build one.", "Build two."], "difficulty": "advanced",
             "tldr_simple": "It learns how things move from videos.", "tldr_expert": "Diffusion features give a latent action space.",
             "terms": [{"term": "latent action space", "meaning": "Numbers that describe what moved between frames."}]}
    a = _paper("2610.1", 9, curator=notes, code_url="https://github.com/a/b")
    save_day([a], [a], "2026-10-31", data_dir=data_dir)
    links = {"2610.1": {"checked": "2026-10-31", "stars": 1234,
                        "hf": {"models": {"n": 2, "top": [{"id": "org/model-x", "likes": 5}]},
                               "datasets": {"n": 0, "top": []}, "spaces": {"n": 0, "top": []}},
                        "s2": {"found": True, "cited_by": 0, "refs": [{"title": "Older <work>", "year": 2024, "arxiv": "2401.1", "cites": 99}],
                               "cites": []}}}
    with open(os.path.join(data_dir, "links.json"), "w", encoding="utf-8") as f:
        json.dump(links, f)
    build_site(data_dir, site_dir)
    page = open(os.path.join(site_dir, "paper", "2610.1.html"), encoding="utf-8").read()
    assert "Where it fits" in page and "Older &lt;work&gt;" in page and "No papers cite it yet" in page
    assert "Try it" in page and "org/model-x" in page and "★ 1.2k" in page and "0 demos" not in page
    assert 'class="term"' in page and "Numbers that describe what moved" in page
    assert 'data-level="simple"' in page and 'data-level-text="expert"' in page


def test_try_it_only_shows_what_really_exists(tmp_path):
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    save_day([_paper("2610.1")], [_paper("2610.1")], "2026-10-31", data_dir=data_dir)
    links = {"2610.1": {"checked": "2026-10-31", "hf": {"models": {"n": 0, "top": []},
                                                        "datasets": {"n": 0, "top": []}, "spaces": {"n": 0, "top": []}}}}
    with open(os.path.join(data_dir, "links.json"), "w", encoding="utf-8") as f:
        json.dump(links, f)
    build_site(data_dir, site_dir)
    page = open(os.path.join(site_dir, "paper", "2610.1.html"), encoding="utf-8").read()
    assert "Try it" not in page and "on Hugging Face" not in page


def test_paper_page_without_links_leaves_those_parts_out(tmp_path):
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    save_day([_paper("2610.1")], [_paper("2610.1")], "2026-10-31", data_dir=data_dir)
    build_site(data_dir, site_dir)
    page = open(os.path.join(site_dir, "paper", "2610.1.html"), encoding="utf-8").read()
    assert "Where it fits" not in page and "Try it" not in page
    assert "data-breakdown" in page and "np-mbar" in page
