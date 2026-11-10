"""
tests/test_trend_story.py
Unit tests for trend_story.py: the opening sentence and the five story charts.
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import trend_story as ts

MONTHS = [f"{y}-{m:02d}" for y, m in [(2025, 11), (2025, 12)] + [(2026, i) for i in range(1, 11)]]
NAMES = {"reasoning-agents": "Reasoning & Agents", "llms": "LLMs", "computer-vision": "Vision"}


def _per(rise, base=None):
    """Topic counts per month: 'reasoning-agents' follows rise (in %), llms stays at base, vision fills the rest."""
    base = base or [24] * len(MONTHS)
    return {m: Counter({"reasoning-agents": rise[i], "llms": base[i], "computer-vision": 100 - rise[i] - base[i]})
            for i, m in enumerate(MONTHS)}


def _tech(id_, name, status, growth, share=0.05, line=None):
    return {"id": id_, "name": name, "status": status, "growth": growth, "share": share,
            "share_before": share / growth if growth else 0, "line": line or [share] * len(MONTHS)}


def test_topic_shift_finds_the_rising_topic_and_the_biggest_one():
    d = ts.topic_shift(_per([6, 8, 9, 10, 12, 13, 14, 14, 18, 17, 17, 18]), MONTHS, NAMES)
    assert d["rise"] == "reasoning-agents" and d["base"] == "computer-vision"
    assert d["growth"] > 2
    svg = ts.topic_shift_chart(d)
    assert 'class="ts-rise"' in svg and "6% in Nov 2025" in svg and 'class="col"' in svg
    assert "<table" in ts.topic_shift_table(d)


def test_topic_shift_needs_real_growth():
    assert ts.topic_shift(_per([10] * 12), MONTHS, NAMES) is None


def test_a_month_that_has_just_started_is_left_out():
    totals = Counter({m: 800 for m in MONTHS})
    totals[MONTHS[-1]] = 90
    assert ts.full_months(MONTHS, totals) == MONTHS[:-1]
    totals[MONTHS[-1]] = 700
    assert ts.full_months(MONTHS, totals) == MONTHS


def test_momentum_groups_by_status_with_text_labels():
    stats = [_tech("world-models", "World models", "breakout", 1.87), _tech("rag", "Retrieval (RAG)", "cooling", 0.76),
             _tech("moe", "Mixture of experts", "steady", 1.05), _tech("ssm", "SSM", "few", None)]
    html = ts.momentum_bars(stats)
    assert html.index("Breakout") < html.index("Steady") < html.index("Cooling")
    assert "+87%" in html and "−24%" in html and "SSM" not in html
    assert 'href="papers.html?q=World%20models&amp;m=1"' in html
    assert ts.momentum_bars([_tech("ssm", "SSM", "few", None)]) == ""


def test_research_vs_practice_matches_case_studies_by_keyword():
    cases = [{"title": "Our RAG pipeline", "summary": "retrieval-augmented answers", "tags": []}] * 12
    cases += [{"title": "Scaling the warehouse", "summary": "cheaper storage", "tags": ["Cost"]}] * 18
    stats = [_tech("rag", "Retrieval (RAG)", "cooling", 0.76, share=0.05),
             _tech("world-models", "World models", "breakout", 1.87, share=0.06)]
    d = ts.research_vs_practice(stats, cases)
    assert d["n"] == 30
    assert [r["name"] for r in d["practice"]] == ["Retrieval (RAG)"]
    assert [r["name"] for r in d["research"]] == ["World models"]
    html = ts.research_vs_practice_chart(d)
    assert "8×" in html and "papers only" in html
    assert ts.research_vs_practice(stats, cases[:10]) is None  # too few case studies


def test_off_peak_lists_cooling_technologies_well_below_their_best_month():
    line = [0.09, 0.138, 0.13, 0.12, 0.11, 0.1, 0.1, 0.09, 0.09, 0.09, 0.088, 0.088]
    stats = [_tech("diffusion", "Diffusion", "cooling", 0.8, line=line), _tech("rl", "RL", "rising", 1.3)]
    rows = ts.off_peak(stats, MONTHS, Counter({m: 800 for m in MONTHS}))
    assert [r["name"] for r in rows] == ["Diffusion"]
    assert rows[0]["peak_month"] == "2025-12" and round(rows[0]["drop"], 2) == 0.36
    assert "peak 13.8%, Dec" in ts.off_peak_chart(rows)


def test_words_show_before_and_now():
    words = [{"word": "verifiable", "now": 0.12, "before": 0.014, "ratio": 8.6}]
    html = ts.words_chart(words)
    assert "1.4% before" in html and "12.0% now" in html and "8.6×" in html


def test_opening_is_written_from_the_numbers():
    shift = ts.topic_shift(_per([6, 8, 9, 10, 12, 13, 14, 14, 18, 17, 17, 18]), MONTHS, NAMES)
    stats = [_tech("world-models", "World models", "breakout", 1.87), _tech("rag", "Retrieval (RAG)", "cooling", 0.76)]
    head, lede, nums = ts.opening(shift, stats, None, ("2026-10", 0.44))
    assert "agent research" in head
    assert "World models nearly doubled its share in 90 days." in lede and "Retrieval (RAG) is cooling" in lede
    assert [n[0] for n in nums] == ["3×", "+87%", "−24%", "44%"]


def test_name_list_reads_like_a_sentence():
    assert ts.name_list(["Tool use", "Retrieval (RAG)", "AI agents"]) == "tool use, retrieval and AI agents"
    assert ts.name_list(["Tool use", "Safety and jailbreaks", "Retrieval (RAG)"]) == "tool use, safety and jailbreaks, and retrieval"


def test_card_has_a_table_behind_show_as_a_table():
    html = ts.card("01", "Label", "Title", "Sub", "3×", "stat", "up", "<svg></svg>", "note", "<table></table>")
    assert "Show as a table" in html and "tone-up" in html and "<b>01</b>" in html
