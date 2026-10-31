"""
tests/test_tech_trends.py
Unit tests for tech_trends.py: growth figures, statuses and the four charts.
"""
import sys
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tech_trends as tt
from tech_trends import change, status_for, tech_stats


END = date(2026, 10, 30)
MONTHS = [f"{y}-{m:02d}" for y, m in [(2025, 11), (2025, 12)] + [(2026, i) for i in range(1, 11)]]


def _rows(days_ago_from, days_ago_to, n, tech, up=0, start_id=0):
    """n papers spread over a window of days before END, each tagged with tech."""
    out = []
    span = days_ago_to - days_ago_from
    for i in range(n):
        d = END - timedelta(days=days_ago_from + (i * span) // max(1, n))
        out.append({"id": f"2601.{start_id + i:05d}", "day": d.isoformat(), "title": f"Paper {start_id + i}",
                    "tech": list(tech), "code": i % 2 == 0, "up": up})
    return out


def _sample():
    rows = []
    rows += _rows(0, 89, 200, [], start_id=0)             # background, last 90 days
    rows += _rows(90, 179, 200, [], start_id=1000)        # background, the 90 days before
    rows += _rows(0, 89, 40, ["agents"], up=50, start_id=2000)   # 40 now, 10 before: breakout
    rows += _rows(90, 179, 10, ["agents"], start_id=3000)
    rows += _rows(0, 89, 20, ["rag"], start_id=4000)      # 20 now, 40 before: cooling
    rows += _rows(90, 179, 40, ["rag"], start_id=5000)
    rows += _rows(0, 89, 20, ["moe"], start_id=6000)      # no history at all: new
    rows += _rows(0, 89, 5, ["ssm"], start_id=7000)       # too few to rate
    rows += _rows(0, 89, 30, ["diffusion"], start_id=8000)  # same share: steady
    rows += _rows(90, 179, 30, ["diffusion"], start_id=9000)
    return rows


def _by_id(stats):
    return {s["id"]: s for s in stats}


def test_change_reads_as_a_plain_percentage():
    assert change(None) == "—"
    assert change(1.92) == "+92%"
    assert change(0.65) == "−35%"
    assert change(1.0) == "0%"


def test_status_needs_enough_papers_and_history():
    assert status_for(10, 3.0) == "few"
    assert status_for(30, None) == "new"
    assert status_for(30, 1.8) == "breakout"
    assert status_for(30, 1.3) == "rising"
    assert status_for(30, 1.0) == "steady"
    assert status_for(30, 0.7) == "cooling"


def test_stats_compare_shares_not_counts():
    s = _by_id(tech_stats(_sample(), MONTHS))
    assert s["agents"]["recent"] == 40 and s["agents"]["before"] == 10
    assert s["agents"]["status"] == "breakout"
    assert s["agents"]["growth"] > 1.8
    assert s["rag"]["status"] == "cooling"
    assert s["moe"]["status"] == "new" and s["moe"]["growth"] is None
    assert s["ssm"]["status"] == "few"
    assert s["diffusion"]["status"] == "steady"
    assert len(s["agents"]["counts"]) == len(MONTHS) and len(s["agents"]["line"]) == len(MONTHS)
    assert s["agents"]["top"] and all(p["up"] > 0 for p in s["agents"]["top"])
    assert s["rag"]["top"] == []  # no upvotes, nothing to show
    order = [x["status"] for x in tech_stats(_sample(), MONTHS)]
    assert order.index("breakout") < order.index("steady") < order.index("cooling") < order.index("few")


def test_empty_input_gives_nothing():
    assert tech_stats([], MONTHS) == []
    assert "empty-note" in tt.leaderboard([], MONTHS)
    assert tt.spotlight([], MONTHS) == "" and tt.momentum([]) == "" and tt.multiples([], MONTHS) == ""


def test_charts_render_with_status_text_not_colour_alone():
    stats = tech_stats(_sample(), MONTHS)
    board = tt.leaderboard(stats, MONTHS)
    assert "AI agents" in board and "Breakout" in board and "▲▲" in board
    assert "Not enough papers yet to rate:" in board and "State-space and linear attention" in board.split("tb-note")[1]
    spot = tt.spotlight(stats, MONTHS, on_site={"2601.02000"})
    assert "AI agents went from" in spot and 'class="sl-main"' in spot and "Show as a table" in spot
    assert 'href="paper/2601.02000.html"' in spot or "huggingface.co/papers/" in spot
    smalls = tt.multiples(stats, MONTHS)
    assert smalls.count('class="sm ') == 4  # agents, rag, moe, diffusion; not the "few" one


def test_momentum_map_needs_four_technologies_with_growth():
    stats = tech_stats(_sample(), MONTHS)
    assert tt.momentum(stats) == ""  # only three have a growth figure
    extra = _sample() + _rows(0, 89, 30, ["speech"], start_id=10000) + _rows(90, 179, 20, ["speech"], start_id=11000)
    mm = tt.momentum(tech_stats(extra, MONTHS))
    assert 'class="chart mm-chart"' in mm and 'class="dumbbell"' in mm
    assert mm.count('class="pt mm-pt') == 4
