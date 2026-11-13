"""
tests/test_today_page.py
Today in the Case studies style: the date eyebrow, "Picked today", the "Also new today" rows with a
line on why each matters and a labelled Save, and "How companies built it this week".
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import case_pages
import site_builder as sb


def _paper(pid, **extra):
    p = {"id": pid, "title": f"Paper {pid}", "authors": ["A", "B"], "submitted": "2026-11-10",
         "abstract": "We cut inference cost in half. Then we test it on ten tasks.", "categories": ["llms"]}
    p.update(extra)
    return p


def _case(n, added="2026-11-12", score=None, **extra):
    c = {"url": f"https://eng.example.com/{n}", "company": f"Co{n}", "title": f"Case {n}", "problem": "rag",
         "published": "2026-11-10", "added": added, "issue": f"Problem {n}.", "summary": "s", "slug": f"co{n}-case-{n}"}
    if score is not None:
        c["build_score"] = score
    c.update(extra)
    return c


def test_why_line_is_the_summary_or_the_first_sentence():
    assert sb.why_line(_paper("1")) == "We cut inference cost in half."
    assert sb.why_line(_paper("2", summary={"text": "Builders get cheaper models. More text."})) == "Builders get cheaper models."
    long = sb.why_line(_paper("3", abstract="word " * 80))
    assert len(long) <= 150 and long.endswith("…")
    assert sb.why_line({"title": "T"}) == ""


def test_home_rows_have_the_why_line_and_a_labelled_save():
    row = sb.home_row(_paper("2611.1"), 3)
    assert '<span class="row-why">We cut inference cost in half.</span>' in row
    assert 'data-label aria-pressed="false" aria-label="Save for later">+ <span>Save</span></button>' in row
    assert sb.MORE_FROM_TODAY == 5


def test_the_pick_date_says_picked_today_only_on_today():
    rec = _paper("2611.2", slot="pick")
    assert "<b>Picked today</b> · on arXiv 10 Nov" in sb.featured_card(rec, 1, "", today=True)
    assert "Published 10 Nov 2026" in sb.featured_card(rec, 1, "../", past=True)


def test_today_has_the_eyebrow_and_the_case_row():
    days = [{"date": "2026-11-13", "featured": ["2611.1"], "scanned": 900,
             "papers": [_paper("2611.1", slot="pick", featured=True)] + [_paper(f"2611.{i}") for i in range(2, 10)]}]
    papers = {p["id"]: p for p in days[0]["papers"]}
    row = case_pages.home_case_row([_case(i, score=i) for i in range(1, 6)], today="2026-11-13")
    html = sb.build_index(days, papers, [], [], row)
    assert '<p class="hero-eyebrow">Today · Fri 13 Nov 2026</p>' in html and 'class="home-today"' in html
    assert html.count('class="row"') == 5  # "Also new today" shows 5
    # after the picks and the newsletter box, before "Also new today"
    assert html.index('id="today"') < html.index('class="subscribe') < html.index("How companies built it this week") < html.index("Also new today")


def test_the_case_row_shows_the_three_most_detailed_new_cases():
    cases = [_case(1, score=1), _case(2, score=5), _case(3, score=3), _case(4, score=4),
             _case(5, published="2026-09-01", added="2026-11-12", score=5)]  # an old post found late: not new
    row = case_pages.home_case_row(cases, today="2026-11-13")
    assert [s for s in ("co2-case-2", "co4-case-4", "co3-case-3") if f'href="case-studies/{s}.html"' in row] == ["co2-case-2", "co4-case-4", "co3-case-3"]
    assert row.index("co2-case-2") < row.index("co4-case-4") < row.index("co3-case-3")
    assert "co1-case-1" not in row and "co5-case-5" not in row
    assert "See all 4 new case studies" in row and 'href="case-studies/index.html?new=1"' in row
    assert "Problem 2." in row and "Build details 5/5" in row


def test_the_case_row_hides_when_nothing_is_new():
    assert case_pages.home_case_row([_case(1, added="2026-10-01", published="2026-09-30")], today="2026-11-13") == ""
    assert case_pages.home_case_row([], today="2026-11-13") == ""
