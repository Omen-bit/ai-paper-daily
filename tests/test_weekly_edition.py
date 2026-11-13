import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import weekly_edition as we  # noqa: E402

SUNDAY = date(2026, 11, 8)


def paper(pid, upvotes, first_seen, score=50, cats=("llms",)):
    return {"id": pid, "title": f"Paper {pid}: A Method", "authors": ["A", "B", "C", "D"],
            "abstract": f"We propose method {pid}. It improves results.", "hf_upvotes": upvotes, "score": score,
            "categories": list(cats), "first_seen": first_seen, "curator": {"tldr": f"{pid} does a thing."}}


def write_day(d, day, papers, featured=(), scanned=100):
    with open(os.path.join(d, f"{day}.json"), "w") as f:
        json.dump({"date": day, "scanned": scanned, "featured": list(featured), "papers": papers}, f)


def setup_week(tmp_path):
    daily = tmp_path / "daily"
    daily.mkdir()
    write_day(daily, "2026-11-02", [paper("a", 10, "2026-11-02"), paper("old", 999, "2026-10-30")], featured=["a"])
    # the same paper later in the week with more upvotes: the highest count wins
    write_day(daily, "2026-11-04", [paper("a", 80, "2026-11-02"), paper("b", 40, "2026-11-04", cats=("reasoning-agents",))])
    write_day(daily, "2026-11-08", [paper("c", 40, "2026-11-08", score=90), paper("d", 5, "2026-11-08")])
    # last week's file must be ignored
    write_day(daily, "2026-11-01", [paper("z", 500, "2026-11-01")])
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps({"posts": [
        {"company": "X", "title": "No result", "url": "https://x/1", "added": "2026-11-05", "published": "2026-11-05",
         "build_score": 2, "issue": "Search was slow."},
        {"company": "Y", "title": "With result", "url": "https://y/1", "added": "2026-11-03", "published": "2026-11-03",
         "result": "2x faster", "build_score": 4, "issue": "Agents kept guessing API parameters."},
        {"company": "Z", "title": "Last week", "url": "https://z/1", "added": "2026-11-01", "published": "2026-11-01"},
        # found this week, but published long ago (a new blog's back catalogue)
        {"company": "Q", "title": "Old post", "url": "https://q/1", "added": "2026-11-04", "published": "2025-06-01"},
    ]}))
    return str(daily), str(cases)


def test_week_bounds_and_id():
    assert we.week_bounds(SUNDAY) == (date(2026, 11, 2), date(2026, 11, 8))
    assert we.week_bounds(date(2026, 11, 4)) == (date(2026, 11, 2), date(2026, 11, 8))
    assert we.week_id(SUNDAY) == "2026-W45"


def test_collect_keeps_this_weeks_papers_with_their_best_upvotes(tmp_path):
    daily, cases = setup_week(tmp_path)
    week = we.collect(SUNDAY, daily, cases)
    assert set(week["papers"]) == {"a", "b", "c", "d"}  # "old" and "z" were new in an earlier week
    assert week["papers"]["a"]["hf_upvotes"] == 80
    assert week["numbers"] == {"scanned": 300, "new_papers": 4, "picks": 1, "cases": 2}
    assert week["topics"][0] == ("llms", 3)
    assert [c["company"] for c in week["cases"]] == ["Y", "X"]  # the most build details first; Q's old post is not new


def test_ranking_uses_upvotes_then_score(tmp_path):
    daily, cases = setup_week(tmp_path)
    week = we.collect(SUNDAY, daily, cases)
    assert [p["id"] for p in we.rank(week["papers"])] == ["a", "c", "b", "d"]
    stories = we.pick_stories(week, n=2)
    assert [s["id"] for s in stories] == ["a", "c"]
    assert stories[0]["picked_on"] == "2026-11-02" and stories[0]["authors"] == ["A", "B", "C"]


def test_refresh_only_raises_upvotes_and_survives_errors(tmp_path):
    papers = {"a": {"id": "a", "hf_upvotes": 10}, "b": {"id": "b", "hf_upvotes": 50}}

    def fetch(pid):
        if pid == "b":
            raise OSError("down")
        return 30
    assert we.refresh_upvotes(papers, fetch=fetch) == 1
    assert papers["a"]["hf_upvotes"] == 30 and papers["b"]["hf_upvotes"] == 50


def test_first_figure_url_resolves_relative_paths():
    page = '<html><base href="/html/2611.08449v1/"><figure id="F1"><img src="x1.png" alt=""></figure></html>'
    assert we.first_figure_url(page, "https://arxiv.org/html/2611.08449v1") == "https://arxiv.org/html/2611.08449v1/x1.png"
    no_base = '<figure><img class="ltx" src="figs/a.png"></figure>'
    assert we.first_figure_url(no_base, "https://arxiv.org/html/1v2") == "https://arxiv.org/html/1v2/figs/a.png"
    assert we.first_figure_url("<img src='logo.png'>", "https://arxiv.org/html/1") is None


def test_save_figure_skips_missing_pages(tmp_path):
    def get(url):
        raise OSError("404")
    assert we.save_figure("2611.0", str(tmp_path), get=get) is None


class Fake:
    """A stand-in for a Groq chain: returns the queued answers in order."""
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        return self.answers.pop(0)


GOOD_LEAD = {"headline": "One Model Handles Every Prompt", "dek": "A plain sentence about it.",
             "problem": "A problem.", "idea": "An idea.", "why": "Why it matters."}


def story(pid="a"):
    return {"id": pid, "title": f"Paper {pid}: A Method", "abstract": "We propose a method.", "tldr": "It does a thing."}


def test_write_story_accepts_checked_copy():
    copy = we.write_story(story(), True, Fake([GOOD_LEAD]), Fake([{"ok": True, "problems": []}]), pause=0)
    assert copy["headline"] == "One Model Handles Every Prompt" and copy["source"] == "groq" and copy["checked"]


def test_write_story_redrafts_then_falls_back():
    writer = Fake([GOOD_LEAD, GOOD_LEAD])
    checker = Fake([{"ok": False, "problems": ["invented a number"]}, {"ok": False, "problems": ["still wrong"]}])
    copy = we.write_story(story(), True, writer, checker, pause=0)
    assert writer.calls == 2 and copy["source"] == "fallback"
    assert copy["headline"] == "Paper a: A Method" and copy["dek"] == "It does a thing."


def test_clean_copy_rules():
    assert we.clean_copy({**GOOD_LEAD, "headline": "This paper shows a thing"}, True) is None
    assert we.clean_copy({**GOOD_LEAD, "why": ""}, True) is None  # the lead needs all three parts
    short = we.clean_copy(GOOD_LEAD, False)
    assert short and short["problem"] == "" and short["why"] == ""
    assert we.clean_copy({**GOOD_LEAD, "headline": " ".join(["word"] * 15)}, False) is None


def test_write_keeps_saved_copy_and_marks_ready(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    week = {"stories": [{**story("a"), "copy": {"headline": "Edited by hand", "dek": "x"}}, story("b")]}
    we.write(week)
    assert week["stories"][0]["copy"]["headline"] == "Edited by hand"
    assert week["stories"][1]["copy"]["source"] == "fallback"
    assert week["status"] == "ready"


def test_render_email(tmp_path):
    daily, cases = setup_week(tmp_path)
    week = we.collect(SUNDAY, daily, cases)
    week["stories"] = we.pick_stories(week, n=3)
    week["stories"][0]["figure"] = "fig-a.jpg"
    we.write(week)
    email = we.render(week)
    body = email["body"]
    assert email["subject"].startswith("The Weekly Express: ")
    assert "\n" not in body  # Buttondown reads the body as Markdown
    assert "assets/weekly-masthead.png" in body and "weekly/2026-W45/fig-a.jpg" in body
    assert "Paper of the week" in body and "How companies built it this week" in body and "More case studies" in body
    assert "Agents kept guessing API parameters." in body and "Build details 4/5" in body
    assert "4 new papers this week. You read none of them." in body
    assert "data:image" not in body  # images are hosted, never inlined
    assert len(body.encode()) < 60_000  # far below Gmail's 102 KB clipping


def test_replaces_daily_only_on_a_ready_sunday(tmp_path, monkeypatch):
    monkeypatch.delenv("WEEKLY_EMAIL", raising=False)
    weekly = str(tmp_path)
    assert not we.replaces_daily("2026-11-08", weekly)  # no week file yet
    we.save_week({"week": "2026-W45", "status": "collected"}, weekly)
    assert not we.replaces_daily("2026-11-08", weekly)
    we.save_week({"week": "2026-W45", "status": "ready"}, weekly)
    assert we.replaces_daily("2026-11-08", weekly)
    assert not we.replaces_daily("2026-11-07", weekly)  # Saturday
    monkeypatch.setenv("WEEKLY_EMAIL", "off")
    assert not we.replaces_daily("2026-11-08", weekly)


def test_prepare_end_to_end_without_network(tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    daily, cases = setup_week(tmp_path)
    weekly = str(tmp_path / "weekly")
    week = we.prepare(SUNDAY, figures=False, refresh=False, daily_dir=daily, weekly_dir=weekly, cases_path=cases)
    assert week["status"] == "ready" and week["papers"] == {}
    saved = we.load_week("2026-W45", weekly)
    assert [s["id"] for s in saved["stories"]] == ["a", "c", "b", "d"]
    # an edit to the saved file survives the next run
    saved["stories"][0]["copy"]["headline"] = "Edited"
    we.save_week(saved, weekly)
    again = we.prepare(SUNDAY, figures=False, refresh=False, daily_dir=daily, weekly_dir=weekly, cases_path=cases)
    assert again["stories"][0]["copy"]["headline"] == "Edited"


def test_main_topic_prefers_specific_topics():
    assert we.main_topic(["llms", "computer-vision"]) == "Vision"
    assert we.main_topic(["llms"]) == "LLMs"
    assert we.main_topic([]) == "Research"
