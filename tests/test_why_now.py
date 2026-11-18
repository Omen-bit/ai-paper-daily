"""
tests/test_why_now.py
The "why it's here now" line on a top pick that came out on arXiv more than 3 days earlier.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import site_builder as sb
import why_now


def _pick(**extra):
    rec = {"id": "2611.1", "title": "Mobile AI Factory", "submitted": "2026-11-09", "slot": "pick",
           "featured": True, "source": "HuggingFace", "hf_upvotes": 19, "rank": 1, "of": 50,
           "abstract": "We build models. We test four phones.",
           "evidence": {"stars": 8, "stars_gain": 4, "hf_models": 4, "upvotes": 19, "estimated": ["stars_gain"]}}
    rec.update(extra)
    return rec


def test_a_recent_pick_needs_no_line():
    assert why_now.why_now(_pick(submitted="2026-11-15"), "2026-11-18") == ""
    assert why_now.why_now(_pick(submitted="2026-11-16"), "2026-11-18") == ""
    assert why_now.why_now(_pick(submitted=None), "2026-11-18") == ""


def test_an_older_pick_says_when_and_why():
    line = why_now.why_now(_pick(), "2026-11-18")
    assert line == ("From 9 Nov. Picked today because it made Hugging Face’s daily papers "
                    "with 19 upvotes and 4 models built on it.")
    past = why_now.why_now(_pick(), "2026-11-18", today=False)
    assert past.startswith("From 9 Nov. Picked on 18 Nov because")


def test_stars_this_week_lead_and_estimates_are_never_used():
    line = why_now.why_now(_pick(), "2026-11-18", stars_week=1200, span=6)
    assert line.startswith("From 9 Nov. Picked today because it gained 1,200 GitHub stars this week, and it made")
    # the scorer's stars_gain was estimated, so it is not a reason
    est = _pick(source="arXiv", evidence={"stars_gain": 500, "estimated": ["stars_gain"]})
    assert "stars" not in why_now.why_now(est, "2026-11-18")
    assert why_now.why_now(est, "2026-11-18").endswith("because it scored highest of the 50 papers we ranked that morning.")
    measured = _pick(source="arXiv", evidence={"stars": 900, "stars_gain": 300})
    assert "it gained 300 GitHub stars since yesterday" in why_now.why_now(measured, "2026-11-18")
    hn = _pick(source="arXiv", evidence={"hn_points": 240})
    assert "it reached 240 points on Hacker News" in why_now.why_now(hn, "2026-11-18")


def test_stars_this_week_come_from_the_snapshots(tmp_path):
    os.makedirs(tmp_path / "signals")
    for day, stars in (("2026-11-12", 100), ("2026-11-15", 400), ("2026-11-18", 1300)):
        with open(tmp_path / "signals" / f"{day}.json", "w") as f:
            json.dump({"papers": {"2611.1": {"stars": stars}}}, f)
    assert why_now.stars_this_week("2611.1", "2026-11-18", str(tmp_path)) == (1200, 6)
    assert why_now.stars_this_week("2611.1", "2026-11-12", str(tmp_path)) == (None, 0)
    assert why_now.stars_this_week("2611.9", "2026-11-18", str(tmp_path)) == (None, 0)


def test_the_top_pick_card_shows_the_line(tmp_path):
    rec = _pick()
    days = [{"date": "2026-11-18", "featured": ["2611.1"], "papers": [rec]}]
    html = sb.build_index(days, {"2611.1": rec}, [], [], "", str(tmp_path))
    assert ('<p class="pick-date pick-now"><b>From 9 Nov.</b> Picked today because it made Hugging Face’s '
            'daily papers with 19 upvotes and 4 models built on it.</p>') in html
    assert "Best new paper by our score" not in html
    day = sb.build_day(days[0], {"2611.1": rec}, str(tmp_path))
    assert "<b>From 9 Nov.</b> Picked on 18 Nov because" in day
    # the second slot and a fresh pick keep the usual date line
    fresh = _pick(submitted="2026-11-17")
    assert "pick-now" not in sb.build_index([dict(days[0], papers=[fresh])], {"2611.1": fresh}, [], [], "", str(tmp_path))
    assert "pick-now" not in sb.featured_card(dict(rec, slot="trending"), 2, "", today=True)


def test_for_you_and_your_projects_start_hidden():
    rec = _pick()
    html = sb.build_index([{"date": "2026-11-18", "featured": ["2611.1"], "papers": [rec]}], {"2611.1": rec}, [], [], "")
    assert "data-foryou " in html and "<section class=\"block\" data-watch " in html
    for marker in ("data-foryou ", "data-watch "):
        tag = html[html.index(marker):].split(">", 1)[0]
        assert tag.rstrip().endswith("hidden"), tag
