"""
tests/test_case_suggestions.py
"Suggest a write-up": the daily checks (case_suggestions.py) with the page fetch, Groq and Supabase
stood in for, publishing approved rows, the credit rules, and the page parts (case_pages.py).
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import case_pages
import case_studies as cs
import case_suggestions as sg

TODAY = "2026-11-13"
PAGE = """<html><head><title>How we built a RAG assistant for support | Acme Engineering</title>
<meta property="og:site_name" content="Acme"></head><body><article>
<p>Our support team answers thousands of tickets, so we built an LLM assistant with retrieval over our help center.</p>
<p>We chunk articles, embed them, rerank the results and evaluate answers with an offline eval set every week.</p>
</article></body></html>"""
NOT_AI = """<html><head><title>Our new office in Berlin</title></head><body><article>
<p>We moved into a bright new office with plenty of room for the whole team and their dogs.</p></article></body></html>"""


def _finder(score):
    return {"techniques": ["rag", "evaluation-harness"], "industry": "saas", "build_score": score,
            "build_details": {"architecture": True, "stack": score > 1, "evaluation": score > 2,
                              "failure_modes": False, "numbers": score > 3}}


def _sorter(score=4, kind="build", calls=None):
    def sort(post):
        if calls is not None:
            calls.append(post["url"])
        return ({"keep": True, "topic": "rag", "issue": "Support answers were slow.", "summary": "A RAG assistant.",
                 "result": "", "tags": ["RAG"], "finder": _finder(score)}, kind)
    return sort


def _row(n, url=None, **extra):
    return {"id": n, "url": url or f"https://eng.acme.example/post-{n}", "note": "", "credit": "", "status": "new", **extra}


SAVED = [{"url": "https://eng.acme.example/old", "company": "Acme", "title": "An older post", "published": "2026-10-01",
          "problem": "rag", "summary": "x", "issue": "y", "tags": []}]


# ---------- the checks

def test_a_good_suggestion_is_checked_and_tagged_with_one_groq_call():
    calls = []
    out = sg.check(_row(1), SAVED, fetch=lambda url: (True, PAGE), sorter=_sorter(4, calls=calls), today=TODAY)
    assert calls == ["https://eng.acme.example/post-1"]
    assert out["status"] == "checked"
    assert out["checks"] == {"link_works": True, "about_ai": True, "not_on_site": True, "has_build_details": True,
                             "announcement": False, "kind": "build"}
    assert out["title"] == "How we built a RAG assistant for support" and out["company"] == "Acme"
    assert out["topic"] == "rag" and out["techniques"] == ["rag", "evaluation-harness"] and out["build_score"] == 4
    assert out["problem"] == "Support answers were slow." and out["solution"] == "A RAG assistant."
    assert out["card"]["url"] == "https://eng.acme.example/post-1" and out["card"]["sorted_by"] == "groq"


def test_free_checks_come_first_and_save_the_groq_call():
    calls = []
    sorter = _sorter(calls=calls)
    broken = sg.check(_row(1), SAVED, fetch=lambda url: (False, ""), sorter=sorter)
    assert broken["status"] == "checked" and broken["checks"]["link_works"] is False
    off_topic = sg.check(_row(2), SAVED, fetch=lambda url: (True, NOT_AI), sorter=sorter)
    assert off_topic["status"] == "checked" and off_topic["checks"]["about_ai"] is False
    blocked = sg.check(_row(3, "https://x.com/someone/status/1"), SAVED, fetch=lambda url: (True, PAGE), sorter=sorter)
    assert blocked["checks"]["link_works"] is False
    assert calls == []  # no Groq call for any of them


def test_posts_already_on_the_site_are_duplicates_without_a_fetch_or_groq():
    fetched, calls = [], []
    dup = sg.check(_row(1, "http://ENG.acme.example/old/?utm_source=x"), SAVED,
                   fetch=lambda url: fetched.append(url) or (True, PAGE), sorter=_sorter(calls=calls))
    assert dup["status"] == "duplicate" and dup["checks"]["not_on_site"] is False
    assert fetched == [] and calls == []
    same_title = sg.check(_row(2, "https://medium.com/acme/older-post-123"),
                          SAVED, fetch=lambda url: (True, PAGE.replace("How we built a RAG assistant for support", "An older post")),
                          sorter=_sorter(calls=calls))
    assert same_title["status"] == "duplicate" and calls == []


def test_light_details_and_announcements_are_flagged():
    light = sg.check(_row(1), SAVED, fetch=lambda url: (True, PAGE), sorter=_sorter(2))
    assert light["status"] == "checked" and light["checks"]["has_build_details"] is False and light["build_score"] == 2
    launch = sg.check(_row(2), SAVED, fetch=lambda url: (True, PAGE), sorter=_sorter(1, kind="launch"))
    assert launch["checks"]["announcement"] is True and launch["checks"]["kind"] == "launch"


def test_a_groq_failure_leaves_the_suggestion_for_the_next_run():
    out = sg.check(_row(1), SAVED, fetch=lambda url: (True, PAGE), sorter=lambda post: (None, ""))
    assert out["status"] == "new" and out["checks"]["groq"] == "failed"


# ---------- the run against Supabase (a stand-in session)

class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code, self._body, self.text = status, body if body is not None else [], ""

    def json(self):
        return self._body


class FakeSupabase:
    def __init__(self, rows):
        self.rows = rows
        self.patches = []

    def get(self, url, headers=None, params=None, timeout=None):
        status = params["status"].split(".", 1)[1]
        return FakeResponse(200, [r for r in self.rows if r["status"] == status])

    def patch(self, url, headers=None, params=None, json=None, timeout=None):
        row_id = int(params["id"].split(".", 1)[1])
        if row_id == 13:
            return FakeResponse(500)  # one row the database refuses
        self.patches.append((row_id, json))
        return FakeResponse(204)


CFG = {"url": "https://x.supabase.co", "key": "service"}


def _cases(tmp_path):
    path = str(tmp_path / "cases.json")
    cs.save(list(SAVED), path, rejected=["https://no.example/a"], last_fetch="2026-11-09")
    return path


def test_the_run_checks_at_most_twenty_and_one_failure_stops_nothing(tmp_path):
    path = _cases(tmp_path)
    db = FakeSupabase([_row(i) for i in range(1, 26)])
    calls = []
    counts = sg.run(path, CFG, db, fetch=lambda url: (True, PAGE), sorter=_sorter(calls=calls), today=TODAY)
    assert len(calls) == 20 and counts["groq"] == 20
    assert counts["checked"] == 19 and counts["failed"] == 1  # row 13 could not be saved; the rest went on
    assert {rid for rid, _ in db.patches} == set(range(1, 21)) - {13}
    assert all(p["status"] == "checked" for _, p in db.patches)


def test_approved_rows_are_published_with_their_credit(tmp_path):
    path = _cases(tmp_path)
    card = sg.check(_row(1), SAVED, fetch=lambda url: (True, PAGE), sorter=_sorter(4), today=TODAY)["card"]
    rows = [{**_row(1), "status": "approved", "card": card, "credit": "<b>Priya</b> K."},
            {**_row(2), "status": "approved", "card": {**card, "url": "https://eng.acme.example/post-2", "title": "Another"},
             "credit": ""},
            {**_row(3), "status": "rejected", "card": {**card, "url": "https://eng.acme.example/post-3", "title": "Nope"}},
            {**_row(4), "status": "duplicate", "card": {**card, "url": "https://eng.acme.example/post-4", "title": "Dup"}},
            {**_row(5), "status": "approved", "card": None}]
    counts = sg.run(path, CFG, FakeSupabase(rows), fetch=lambda url: (True, PAGE), sorter=_sorter(), today=TODAY)
    assert counts["published"] == 2
    saved = cs.load_all(path)
    by_url = {p["url"]: p for p in saved["posts"]}
    assert by_url["https://eng.acme.example/post-1"]["suggested_by"] == "bPriyab K."
    assert "suggested_by" not in by_url["https://eng.acme.example/post-2"]  # anonymous
    assert by_url["https://eng.acme.example/post-1"]["suggested"] is True
    assert by_url["https://eng.acme.example/post-1"]["build_score"] == 4
    assert "https://eng.acme.example/post-3" not in by_url and "https://eng.acme.example/post-4" not in by_url
    assert saved["last_fetch"] == "2026-11-09" and saved["rejected"] == ["https://no.example/a"]
    # The next run does not add them again
    again = sg.run(path, CFG, FakeSupabase(rows), fetch=lambda url: (True, PAGE), sorter=_sorter(), today=TODAY)
    assert again["published"] == 0


def test_without_supabase_keys_nothing_happens(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    assert sg.run(_cases(tmp_path))["published"] == 0


def test_a_missing_table_never_fails_the_daily_run(tmp_path):
    class Missing(FakeSupabase):
        def get(self, url, headers=None, params=None, timeout=None):
            return FakeResponse(404)
    assert sg.run(_cases(tmp_path), CFG, Missing([]))["checked"] == 0


# ---------- credit, and the page

def test_credit_is_plain_text_with_the_same_rule_as_the_function():
    assert sg.clean_credit("  @priya_k  ") == "@priya_k"
    assert sg.clean_credit("José Núñez-Ruiz") == "José Núñez-Ruiz"
    assert sg.clean_credit('<a href="https://evil">x</a>') == "a hrefhttpsevilxa"
    assert sg.clean_credit("y" * 80) == "y" * 40
    assert sg.clean_credit(None) == ""


def test_the_suggested_by_row_shows_only_with_a_credit():
    post = {"url": "https://eng.acme.example/a", "company": "Acme", "title": "T", "problem": "rag", "summary": "s"}
    assert "cs-by" not in case_pages.post_card(post)
    assert "cs-by" not in case_pages.post_card({**post, "suggested_by": "  <>  "})
    card = case_pages.post_card({**post, "suggested_by": "@priya <script>"})
    assert '<span class="cs-av" aria-hidden="true">P</span><span>Suggested by <b>@priya script</b></span>' in card
    assert card.index("cs-by") < card.index("cs-foot") and "<script>" not in card


def test_the_page_has_the_button_the_form_and_a_honeypot(tmp_path):
    written = {}
    post = {"url": "https://eng.acme.example/a", "company": "Acme", "title": "RAG at Acme", "problem": "rag",
            "summary": "s", "issue": "i", "published": "2026-11-01", "suggested_by": "Ana"}
    case_pages.build_all([post], {}, lambda title, body, **kw: body,
                         lambda path, text: written.__setitem__(path, text), str(tmp_path))
    page = written[os.path.join(str(tmp_path), "case-studies", "index.html")]
    assert 'data-sg-open aria-haspopup="dialog">+ Suggest a write-up</button>' in page
    assert '<dialog class="sg" data-sg aria-labelledby="sg-title">' in page and '<h2 id="sg-title">Suggest a write-up</h2>' in page
    for label in ('for="sg-url">Link to the post', 'for="sg-note">Why is it worth reading?', 'for="sg-credit">Credit me as'):
        assert label in page
    assert 'maxlength="280"' in page and 'maxlength="40"' in page
    assert 'class="sg-hp" aria-hidden="true"' in page and 'tabindex="-1" autocomplete="off" data-sg-hp' in page
    assert ">Cancel</button>" in page and ">Send suggestion</button>" in page
    assert "We review suggestions within a few days. Only links to public posts, please." in page
    assert 'data-endpoint="https://nmelkepelhwyhlfdznpf.supabase.co/functions/v1/suggest"' in page
    index = json.loads(page.split('id="cf-index">', 1)[1].split("</script>", 1)[0])
    assert index["posts"][0]["sb"] == "Ana"
    review = written[os.path.join(str(tmp_path), "case-studies", "review.html")]
    assert "suggest-admin" in review and "Only you can see this page" in review
    assert "ADMIN_TOKEN" in review and "sb_secret" not in review and "service_role" not in review
