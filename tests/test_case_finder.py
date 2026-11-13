"""
tests/test_case_finder.py
The Case studies finder: the main page's chips, sections and search index (case_pages.py), and the
keyword search in assets/case-finder.js, run under Node when it is installed.
"""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import case_pages

FINDER_JS = os.path.join(os.path.dirname(__file__), "..", "src", "site_assets", "case-finder.js")


def _post(n, problem="rag", score=None, published="2026-11-01", **extra):
    post = {"url": f"https://eng.example.com/{n}", "company": "Netflix", "title": f"Post {n}", "published": published,
            "problem": problem, "summary": "What they built.", "issue": "What hurt."}
    if score is not None:
        post.update(build_score=score, techniques=["rag"], industry="media",
                    build_details={k: i < score for i, k in enumerate(case_pages.BUILD_DETAILS)})
    post.update(extra)
    return post


def _build(tmp_path, posts):
    written = {}
    case_pages.build_all(posts, {}, lambda title, body, **kw: body,
                         lambda path, text: written.__setitem__(path, text), str(tmp_path), asset_v="abc123")
    return written[os.path.join(str(tmp_path), "case-studies", "index.html")]


def _index(page):
    return json.loads(page.split('id="cf-index">', 1)[1].split("</script>", 1)[0])


def test_the_page_has_the_search_box_try_chips_and_filters(tmp_path):
    page = _build(tmp_path, [_post(1, score=4), _post(2, "agents")])
    assert "<h1>How companies build AI</h1>" in page and "Every card opens the original post." in page
    assert 'placeholder="Describe your problem, e.g. HR policy chatbot with role-based access"' in page
    assert '<button class="cf-go" type="submit">Find write-ups</button>' in page
    for example in case_pages.TRY:
        assert f'data-cf-try="{case_pages.esc(example)}"' in page
    assert "data-cf-tech" in page and "RAG (1)" in page and "Media (1)" in page and "data-cf-co" in page
    assert 'data-cf-first checked' in page
    assert '<script src="../assets/case-finder.js?v=abc123" defer></script>' in page


def test_technique_and_industry_menus_wait_for_tagged_posts(tmp_path):
    page = _build(tmp_path, [_post(1), _post(2)])
    assert "data-cf-tech" not in page and "data-cf-ind" not in page and "data-cf-co" in page


def test_category_chips_and_sections_are_ordered_by_count(tmp_path):
    posts = [_post(i, "agents") for i in range(5)] + [_post(10 + i, "rag") for i in range(2)] + [_post(20, "evals")]
    page = _build(tmp_path, posts)
    chips = re.findall(r'data-cf-topic="(\w+)" aria-pressed="false"><i aria-hidden="true"></i>([^<]+) <span>(\d+)</span>', page)
    assert chips == [("agents", "Agents", "5"), ("rag", "RAG and search", "2"), ("evals", "Evaluation", "1")]
    sections = re.findall(r'<section class="cs-sec cf-sec" id="([\w-]+)"', page)
    assert sections == ["agents", "rag", "evaluation"]
    assert "AI that takes actions with tools, not just answers." in page
    assert "How teams test whether answers are right." in page
    assert page.count("Posts with real build details first.") == 3
    assert 'data-cf-see="agents">See all 5' in page
    agents = page.split('id="agents"', 1)[1].split("</section>", 1)[0]
    assert agents.count("data-cs-item") == case_pages.PER_SECTION


def test_sections_put_the_most_build_details_first(tmp_path):
    posts = [_post(1, score=1, published="2026-11-09"), _post(2, published="2026-11-10"),
             _post(3, score=5, published="2026-10-01"), _post(4, score=3, published="2026-11-02")]
    page = _build(tmp_path, posts)
    rag = page.split('id="rag"', 1)[1].split("</section>", 1)[0]
    assert re.findall(r'href="https://eng.example.com/(\d)"', rag) == ["3", "4", "1"]  # untagged (2) counts as 0, so it sinks
    assert [p["u"][-1] for p in _index(page)["posts"]] == ["3", "4", "1", "2"]


def test_build_details_pill_is_green_amber_or_hidden():
    hi = case_pages.post_card(_post(1, score=5))
    assert 'class="cs-bd cs-bd-hi"' in hi and "✓ Build details 5/5" in hi
    assert 'title="Describes: architecture, stack, evaluation, failure modes, numbers"' in hi
    mid = case_pages.post_card(_post(2, score=2))
    assert 'class="cs-bd cs-bd-mid"' in mid and "Build details 2/5" in mid
    for low in (_post(3, score=1), _post(4, score=0), _post(5)):
        assert "cs-bd" not in case_pages.post_card(low)
    assert '<span class="cs-topic">RAG and search</span>' in hi  # the topic pill stays
    assert 'href="https://eng.example.com/1" rel="noopener" target="_blank"' in hi  # opens the original post


def test_the_index_carries_what_the_cards_and_search_need(tmp_path):
    post = _post(1, score=4, tags=["Reranking"], result="2x faster", techniques=["rag", "made-up"], industry="nowhere")
    index = case_pages.search_index(case_pages._clean([post]))
    row = index["posts"][0]
    assert row == {"u": "https://eng.example.com/1", "c": "Netflix", "t": "Post 1", "p": "rag", "d": "2026-11-01",
                   "i": "What hurt.", "s": "What they built.", "r": "2x faster", "g": ["Reranking"], "x": ["rag"],
                   "n": "", "b": 4, "bd": ["architecture", "stack", "evaluation", "failure_modes"]}
    assert index["topics"]["rag"] == ["RAG and search", "var(--l-rag)"]
    assert index["labels"]["x"]["classical-ml"] == "Classical ML"
    assert index["brands"]["Netflix"][0].startswith("<svg") and index["brands"]["Netflix"][2].startswith("#")
    assert "</" not in case_pages.index_json([_post(9, title="</script><b>")])


def test_an_empty_list_shows_the_empty_note(tmp_path):
    page = _build(tmp_path, [])
    assert "No write-ups yet." in page and "cf-index" not in page


# ---------- the search itself, in Node

NODE = shutil.which("node")


def _node(script: str):
    code = f"const F = require({json.dumps(os.path.abspath(FINDER_JS))});\n{script}"
    out = subprocess.run([NODE, "-e", code], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


INDEX = {
    "topics": {"rag": ["RAG and search", ""], "support": ["Customer support", ""], "cost": ["Cost and speed", ""]},
    "labels": {"x": {"rag": "RAG"}, "n": {"saas": "SaaS"}},
    "posts": [
        {"u": "a", "c": "Acme", "t": "An HR policy assistant for employees", "p": "rag", "d": "2026-10-01",
         "i": "Staff could not find answers in HR policies.", "s": "A bot answers with role-based access to documents.",
         "r": "", "g": ["RAG"], "x": ["rag"], "n": "saas", "b": 2},
        {"u": "b", "c": "Shop", "t": "Support chatbot with human handoff", "p": "support", "d": "2026-11-01",
         "i": "Agents were swamped.", "s": "A chatbot that escalates to a person.", "r": "", "g": [], "x": [], "n": "", "b": 5},
        {"u": "c", "c": "Fast", "t": "Cutting LLM costs with caching", "p": "cost", "d": "2026-11-05",
         "i": "Model bills grew.", "s": "Semantic caching and smaller models.", "r": "40% cheaper", "g": [], "x": [], "n": "", "b": 0},
    ],
}


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_words_are_stemmed_stopworded_and_mapped_to_synonyms():
    out = _node("""console.log(JSON.stringify({
      stems: ["policies", "chatbots", "testing", "costs", "access", "evaluated"].map(F.stem),
      keys: F.terms("HR policy chatbot with role-based access, e.g. for the bots!").map(t => t.key),
      syn: ["assistant", "bot", "retrieval", "evaluation", "agentic", "cheaper", "latency", "models"].map(F.key)
    }));""")
    assert out["stems"] == ["policy", "chatbot", "test", "cost", "access", "evaluat"]
    assert out["keys"] == ["hr", "policy", "chatbot", "access"]  # role is access; with, based, e.g., for, the dropped
    assert out["syn"] == ["chatbot", "chatbot", "rag", "eval", "agent", "cost", "cost", "llm"]


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_search_finds_the_closest_write_ups_and_puts_build_details_first():
    out = _node(f"""const index = {json.dumps(INDEX)};
      const show = (q, o) => F.search(index, q, o).map(h => [h.post.u, h.hits]);
      console.log(JSON.stringify({{
        hr: show("HR policy chatbot with role-based access"),
        handoff: show("Support chatbot with handoff"),
        relevance: show("chatbot", {{detailFirst: false}}),
        cost: show("Cut LLM costs"),
        none: show("quantum blockchain"),
        all: show("").map(r => r[0])
      }}));""")
    assert out["hr"][0][0] == "a" and set(out["hr"][0][1]) >= {"hr", "policy", "chatbot"}
    assert [u for u, _ in out["hr"]] == ["a"]  # a 4-word search needs 2 words in common
    assert out["handoff"][0] == ["b", ["support", "chatbot", "handoff"]]
    assert [u for u, _ in out["relevance"]][:2] == ["b", "a"]
    assert out["cost"][0][0] == "c"
    assert out["none"] == []
    assert out["all"] == ["b", "a", "c"]  # no words: every write-up, most build details first
