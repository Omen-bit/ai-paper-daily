"""
tests/test_trends.py
Unit tests for trends.py: the numbers behind the Trends page and the topic pulse.
"""
import sys
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import trends


def _rows(spec):
    """spec: list of (day, [topics], has_code, title)."""
    return [{"id": str(i), "day": d, "cats": c, "code": code, "title": t} for i, (d, c, code, t) in enumerate(spec)]


def test_trend_rows_prefer_hugging_face_papers():
    archive = [{"id": str(i), "first_seen": "2026-10-01", "categories": ["llms"], "source": "HuggingFace"} for i in range(250)]
    archive += [{"id": f"x{i}", "first_seen": "2026-10-01", "categories": ["llms"], "source": "arXiv"} for i in range(500)]
    rows, source = trends.trend_rows(archive, {})
    assert len(rows) == 250 and "Hugging Face" in source
    rows, source = trends.trend_rows([], {"a": {"id": "a", "first_seen": "2026-10-01", "categories": []}})
    assert rows[0]["cats"] == ["other-ml"] and source == "papers on this site"


def test_shares_split_multi_topic_papers_and_add_up():
    rows = _rows([("2026-09-03", ["llms", "code-ai"], False, "A"), ("2026-09-04", ["llms"], True, "B"),
                  ("2026-10-01", ["code-ai"], True, "C")])
    months = trends.last_months(rows, 2)
    assert months == ["2026-09", "2026-10"]
    per = trends.topic_counts(rows, months)
    s = trends.shares(per["2026-09"])
    assert abs(s["llms"] - 0.75) < 1e-9 and abs(sum(s.values()) - 1) < 1e-9
    assert [round(v, 2) for _, v, _ in trends.code_share(rows, months)] == [0.5, 1.0]


def test_last_months_cross_the_year():
    rows = _rows([("2025-12-03", ["llms"], False, "B"), ("2026-02-10", ["llms"], False, "A")])
    assert trends.last_months(rows, 3) == ["2025-12", "2026-01", "2026-02"]


def test_last_months_skips_empty_months_before_the_history_starts():
    rows = _rows([("2026-02-10", ["llms"], False, "A")])
    assert trends.last_months(rows, 12) == ["2026-02"]


def test_weekly_pulse_hides_change_without_a_steady_baseline():
    end = date(2026, 10, 31)
    few = _rows([((end - timedelta(days=i)).isoformat(), ["llms"], False, "t") for i in range(10)])
    assert trends.weekly_pulse(few)[0]["delta"] is None  # tiny baseline: no "5100%"
    many = _rows([((end - timedelta(days=i % 35)).isoformat(), ["llms" if i % 4 else "code-ai"], False, "t")
                  for i in range(400)])
    pulse = trends.weekly_pulse(many)
    assert pulse[0]["topic"] == "llms" and pulse[0]["delta"] is not None and abs(pulse[0]["delta"]) < 0.2


def test_rising_words_find_new_terms():
    months = [f"2026-{m:02d}" for m in range(1, 13)]
    spec = []
    for i, m in enumerate(months):
        for k in range(30):
            word = "agentic" if (i >= 9 and k % 2) else "classic"
            spec.append((f"{m}-10", ["llms"], False, f"{word} planners for robots {k}"))
    words = trends.rising_words(_rows(spec), months)
    assert words and words[0]["word"] == "agentic" and words[0]["ratio"] > 5
    assert all(w["word"] != "classic" for w in words)


def test_charts_render_and_escape():
    rows = _rows([(f"2026-{m:02d}-0{d}", ["llms" if d % 2 else "code-ai"], d == 1, "T") for m in range(1, 13) for d in range(1, 8)])
    months = trends.last_months(rows, 12)
    per = trends.topic_counts(rows, months)
    names = {"llms": "LLMs <&>", "code-ai": "Code"}
    svg = trends.share_area(per, months, trends.top_topics(per), names)
    assert svg.startswith("<svg") and "LLMs &lt;&amp;&gt;" in svg and 'tabindex="0"' in svg
    assert "<table" in trends.share_table(per, months, ["llms"], names)
    assert "Busiest day" in trends.calendar(trends.daily_counts(rows), "2026-12-07")
    assert "code-line" in trends.code_chart(trends.code_share(rows, months))


def test_end_labels_never_overlap():
    from trends import spread_labels
    out = spread_labels([300, 302, 305, 100, 299], 18, 20, 310)
    ordered = sorted(out)
    assert all(b - a >= 18 - 1e-9 for a, b in zip(ordered, ordered[1:]))
    assert max(out) <= 310 and min(out) >= 20
    assert out[3] == 100  # labels with room stay where they are
