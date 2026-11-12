"""
tests/test_case_categories.py
Case study categories: the narrower agent topics, categories the classifier proposes (cleaned,
merged and shown only with enough write-ups), their colours, and the scrolling chip row.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import case_pages
import case_studies as cs
from case_sources import TOPICS, category_norm, clean_category, match_category, split_agents

STYLE = os.path.join(os.path.dirname(__file__), "..", "src", "site_assets", "style.css")
APP = os.path.join(os.path.dirname(__file__), "..", "src", "site_assets", "app.js")


def _post(n, problem="agents", **extra):
    post = {"url": f"https://eng.example.com/{n}", "company": "Netflix", "title": f"Post {n}",
            "published": f"2026-10-{10 + n % 18:02d}", "problem": problem, "summary": "What the team did."}
    post.update(extra)
    return post


def test_agent_posts_move_to_the_narrower_agent_topics():
    assert split_agents({"title": "Replit Agent 4: building apps from a prompt"}) == "coding"
    assert split_agents({"title": "Vercel Agent can now validate alerts before paging"}) == "ops"
    assert split_agents({"title": "Analyze your Stripe data directly with your agent"}) == "data"
    assert split_agents({"title": "Extending Fin as the most open Agent platform"}) == "support"
    assert split_agents({"title": "Run agents on Vercel Sandbox"}) == "platforms"
    assert split_agents({"title": "Agents that plan trips"}) == "agents"
    # The title decides before the text does
    assert split_agents({"title": "Agent memory you own", "summary": "for coding agents"}) == "platforms"
    for key in ("coding", "data", "ops", "support", "platforms"):
        assert key in TOPICS


def test_recategorize_splits_old_agents_posts_once_and_leaves_groq_choices():
    old = _post(1, title="AI agents that migrate our codebase")
    moved = cs.recategorize(old)
    assert moved["problem"] == "coding" and moved["cat"] == cs.CAT_VERSION
    # A post Groq filed under agents with today's prompt stays there
    chosen = _post(2, title="AI agents that migrate our codebase", cat=cs.CAT_VERSION)
    assert cs.recategorize(chosen)["problem"] == "agents"
    # Other topics are not touched
    assert cs.recategorize(_post(3, "rag", title="Coding search"))["problem"] == "rag"


def test_proposed_names_are_cleaned_and_merged():
    assert clean_category("voice AGENTS") == "Voice agents"
    assert clean_category("LLM routing") == "LLM routing"
    assert clean_category("a way too long category name") == ""
    assert clean_category("ab") == ""
    assert category_norm("Voice-Agents") == category_norm("voice agent") == "voice agent"
    # A name that restates a topic joins that topic
    assert match_category("AI Agents") == ("agents", "")
    assert match_category("Coding Agent") == ("coding", "")
    assert match_category("Recommender systems") == ("recs", "")
    assert match_category("Text-to-SQL") == ("data", "")
    assert match_category("Other") == (None, "")
    # A new name keeps the spelling first saved
    assert match_category("voice agent", {"voice agent": "Voice agents"}) == ("", "Voice agents")
    assert match_category("Document processing") == ("", "Document processing")


def test_groq_may_propose_a_new_category():
    reply = ('{"kind": "build", "topic": "llm", "new_topic": "document processing", "issue": "Forms took days.", '
             '"summary": "An LLM reads the forms."}')
    out = cs.parse_reply(reply)
    assert out["topic"] == "llm" and out["category"] == "Document processing"
    # A "new" name that is really a topic becomes that topic
    out = cs.parse_reply('{"kind": "build", "topic": "agents", "new_topic": "Coding agents", "issue": "x", "summary": "y"}')
    assert out["topic"] == "coding" and "category" not in out
    out = cs.parse_reply('{"kind": "build", "topic": "rag", "new_topic": "", "issue": "x", "summary": "y"}')
    assert "category" not in out


def test_new_posts_keep_the_proposed_category(monkeypatch):
    existing = [_post(1, "llm", category="Voice agents", cat=cs.CAT_VERSION, v=cs.VERSION, issue="x")]
    monkeypatch.setattr(cs, "groq_sort", lambda post: {"keep": True, "topic": "llm", "category": "voice agent",
                                                        "summary": "s", "issue": "i", "tags": []})
    fetched = [dict(url="https://a.example/9", company="Uber", title="A voice agent for drivers",
                    published="2026-11-01", text="")]
    posts, _ = cs.update(existing, fetched, "2026-11-07")
    new = next(p for p in posts if p["url"] == "https://a.example/9")
    assert new["category"] == "Voice agents" and new["problem"] == "llm" and new["cat"] == cs.CAT_VERSION


def test_keyword_sorting_splits_agents_without_groq():
    fetched = [dict(url="https://a.example/1", company="Uber", title="An AI agent that triages incidents for on-call",
                    published="2026-11-01", text="")]
    posts, counts = cs.update([], fetched, "2026-11-07", use_groq=False)
    assert counts["rules"] == 1 and posts[0]["problem"] == "ops"


def test_recategorize_saved_is_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "groq_sort", lambda post: (_ for _ in ()).throw(AssertionError("no Groq calls")))
    path = str(tmp_path / "cases.json")
    cs.save([_post(1, title="Vibe coding a storefront"), _post(2, "rag")], path, rejected={"https://x"}, waiting=3,
            last_fetch="2026-11-09")
    counts = cs.recategorize_saved(path)
    assert counts == {"coding": 1, "rag": 1}
    saved = json.load(open(path, encoding="utf-8"))
    assert saved["last_fetch"] == "2026-11-09" and saved["rejected"] == ["https://x"] and saved["waiting"] == 3


def test_proposed_categories_need_three_write_ups_for_a_chip():
    posts = [_post(i, "llm", category="voice agent" if i == 1 else "Voice agents") for i in range(3)]
    posts += [_post(10 + i, "vision", category="Document processing") for i in range(2)]
    cleaned = case_pages._clean(posts)
    assert {p["problem"] for p in cleaned} == {"voice-agents", "vision"}
    assert "voice-agents" in case_pages.CUSTOM and case_pages.problem_name("voice-agents") == "Voice agents"
    chips = case_pages.filters(cleaned, cleaned)
    assert "Voice agents <span>3</span>" in chips and "Document processing" not in chips
    assert 'href="voice-agents.html"' in chips


def test_proposed_categories_get_a_stable_palette_colour():
    case_pages._clean([_post(i, "llm", category="Voice agents") for i in range(3)])
    first = case_pages.color("voice-agents")
    assert re.fullmatch(r"var\(--l-x[0-7]\)", first)
    case_pages._clean([_post(i, "llm", category="Voice agents") for i in range(4)])
    assert case_pages.color("voice-agents") == first
    assert case_pages.color("coding") == "var(--l-coding)"
    css = open(STYLE, encoding="utf-8").read()
    for key in list(TOPICS) + [f"x{i}" for i in range(case_pages.PALETTE)]:
        assert css.count(f"--l-{key}:") >= 2, key  # a light and a dark value


def test_topic_pages_are_written_for_new_topics(tmp_path):
    posts = [_post(i, "coding") for i in range(2)] + [_post(10 + i, "llm", category="Voice agents") for i in range(3)]
    written = {}
    paths = case_pages.build_all(posts, {}, lambda title, body, **kw: body,
                                 lambda path, text: written.__setitem__(path, text), str(tmp_path))
    assert "case-studies/coding-agents.html" in paths and "case-studies/voice-agents.html" in paths
    page = written[os.path.join(str(tmp_path), "case-studies", "voice-agents.html")]
    assert "<h1>Voice agents</h1>" in page and 'aria-current="page"' in page


def test_chip_row_has_arrows_fades_and_room_at_the_end():
    row = case_pages.chip_row(['<a href="index.html">All</a>'])
    assert "data-cs-chipbar" in row and "data-cs-chips" in row
    assert row.count('tabindex="-1"') == 2 and "data-cs-chip-prev hidden" in row and "data-cs-chip-next hidden" in row
    css = open(STYLE, encoding="utf-8").read()
    assert ".cs-chipbar[data-right]" in css and ".cs-chipbar[data-left]" in css
    assert "scroll-padding-inline" in css and ".cs-chips a:last-child { margin-right: 12px; }" in css
    assert re.search(r"prefers-reduced-motion: reduce\) \{ \.cs-chipbar", css)
    js = open(APP, encoding="utf-8").read()
    assert "[data-cs-chipbar]" in js and "focusin" in js and "prefers-reduced-motion" in js


def test_site_shows_the_last_twelve_months_of_write_ups():
    import case_pages
    posts = [{"url": "a", "published": "2026-11-01"}, {"url": "b", "published": "2025-11-02"},
             {"url": "c", "published": "2025-10-31"}, {"url": "d"}]
    kept = [p["url"] for p in case_pages.recent(posts)]
    assert kept == ["a", "b", "d"]  # measured from the newest post; undated posts stay
    assert case_pages.recent([]) == []
