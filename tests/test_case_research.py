"""
tests/test_case_research.py
"Research behind this" on case study cards: case_research.py matches each case to a paper on the
site with BM25 and strict checks (no LLM), and the cards show it only when there is a match.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import case_pages
import case_research as cr

FILLER = [
    ("Protein folding with geometric deep learning", "We predict protein structures from sequences using geometric networks."),
    ("A survey of reinforcement learning for robotics", "We review policy learning for manipulation and locomotion."),
    ("Climate downscaling with neural operators", "Neural operators map coarse climate fields to fine resolution grids."),
    ("Image segmentation for medical scans", "A segmentation network outlines organs in medical CT scans."),
    ("Theory of overparameterized networks", "We prove generalization bounds for wide neural networks."),
    ("Music generation with transformers", "A transformer composes piano music from symbolic notes."),
    ("Graph neural networks for chemistry", "Message passing networks predict molecule properties."),
    ("Federated learning under privacy constraints", "Clients train a shared network without sharing raw data."),
    ("Causal discovery from observational data", "We recover causal graphs from samples without interventions."),
    ("Speech recognition for low-resource languages", "An acoustic network transcribes languages with little data."),
    ("Weather nowcasting with radar", "Short-term rain prediction from radar frames."),
    ("Adversarial robustness of vision networks", "Small perturbations fool image classifiers."),
    ("Autonomous driving perception", "Lidar and camera fusion for detecting cars and pedestrians."),
    ("Mathematical reasoning benchmarks", "A benchmark of olympiad problems for language models."),
    ("Sparse attention for long documents", "Attention over long inputs with block sparse patterns."),
    ("Table question answering", "Answering questions over spreadsheets with semantic parsing."),
    ("Neural rendering of 3D scenes", "Radiance fields render novel views of scenes."),
    ("Anomaly detection in industrial sensors", "Detecting faults in factory sensor streams."),
    ("Curriculum learning for small models", "Ordering training examples from easy to hard."),
    ("Evaluation of chatbots with human raters", "Human raters compare chatbot answers side by side."),
    ("Multilingual translation at scale", "One translation network for two hundred languages."),
    ("Energy use of datacenter training", "Measuring power draw of large training runs."),
    ("Ocean current forecasting", "Forecasting surface currents from satellite data."),
    ("Legal document classification", "Classifying court rulings by area of law."),
    ("Self-supervised video representations", "Learning video features without labels."),
]
TARGETS = {
    "2611.00001": ("Faster speculative decoding with tree-structured draft models",
                   "Speculative decoding speeds up LLM inference: a small draft model proposes tokens that the target "
                   "model verifies in parallel. Our tree drafts raise acceptance rates and cut latency by 2.5x."),
    "2611.00002": ("Two-tower retrieval with hard negatives for large-scale recommendation",
                   "Two-tower models embed users and items for candidate retrieval in recommender systems. Hard negative "
                   "sampling improves recall of the item tower for feed recommendation."),
}


def _library():
    papers = {f"2610.{i:05d}": {"id": f"2610.{i:05d}", "title": t, "abstract": a, "categories": ["other-ml"]}
              for i, (t, a) in enumerate(FILLER)}
    for pid, (t, a) in TARGETS.items():
        papers[pid] = {"id": pid, "title": t, "abstract": a, "categories": ["efficient-ai"]}
    return papers


SPEC = {"url": "https://eng.example.com/spec", "company": "Acme", "title": "Speculative decoding cut our LLM latency in half",
        "issue": "Chat answers were slow for users.", "published": "2026-11-01", "problem": "cost",
        "summary": "A small draft model proposes tokens and the big model verifies them in parallel, so inference is faster.",
        "tags": ["Speculative decoding", "Latency"], "techniques": ["distillation"]}
RECS = {"url": "https://eng.example.com/recs", "company": "Acme", "title": "Two-tower retrieval for the home feed",
        "issue": "The feed showed stale items.", "published": "2026-11-02", "problem": "recs",
        "summary": "User and item towers embed candidates; hard negatives improved recall for feed recommendation.",
        "tags": ["Two-tower", "Embeddings"], "techniques": ["embeddings", "classical-ml"]}
OFFICE = {"url": "https://eng.example.com/office", "company": "Acme", "title": "What we learned moving to a new office",
          "issue": "The team was spread across two floors.", "published": "2026-11-03", "problem": "llm",
          "summary": "We planned seating and meeting rooms together.", "tags": [], "techniques": []}


def test_the_matcher_finds_the_paper_behind_a_case():
    index = cr.PaperIndex(_library())
    spec = cr.match(SPEC, index, labels=case_pages.TECH_LABELS)
    assert spec and spec[0]["id"] == "2611.00001" and spec[0]["url"] == "../paper/2611.00001.html"
    assert "decod" in spec[0]["shared"] and spec[0]["score"] >= cr.MIN_SCORE
    recs = cr.match(RECS, index, labels=case_pages.TECH_LABELS)
    assert recs and recs[0]["id"] == "2611.00002"


def test_unrelated_text_gets_no_paper():
    index = cr.PaperIndex(_library())
    assert cr.match(OFFICE, index) == []
    # A technical case with no paper on its technique on the site gets none either
    rag = {**OFFICE, "title": "RAG over our help center with hybrid search", "tags": ["RAG", "Reranking"],
           "summary": "Chunked help articles are embedded and reranked before the LLM answers."}
    assert cr.match(rag, index) == []


def test_the_score_threshold_is_respected():
    index = cr.PaperIndex(_library())
    best = cr.match(SPEC, index)[0]["score"]
    assert cr.match(SPEC, index, min_score=best + 0.01) == []


def test_a_paper_must_share_a_technique_named_by_the_case():
    index = cr.PaperIndex(_library())
    # Same words in the solution, but the case's title and tags name no technique
    vague = {**SPEC, "title": "Making chat faster", "tags": ["Latency"], "techniques": []}
    assert cr.match(vague, index) == []


def test_a_foundational_paper_only_when_it_has_a_page_here():
    papers = _library()
    rag = {**OFFICE, "title": "Answering from our docs", "tags": [], "techniques": ["rag"]}
    assert cr.match(rag, cr.PaperIndex(papers)) == []
    papers["2005.11401"] = {"id": "2005.11401", "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
                            "abstract": "Combining parametric and non-parametric memory.", "categories": []}
    found = cr.match(rag, cr.PaperIndex(papers))
    assert found[0]["id"] == "2005.11401" and found[0]["foundational"] is True


def test_cards_show_the_block_only_when_there_is_a_match(tmp_path):
    written = {}
    case_pages.build_all([SPEC, OFFICE], _library(), lambda title, body, **kw: body,
                         lambda path, text: written.__setitem__(path, text), str(tmp_path))
    page = written[os.path.join(str(tmp_path), "case-studies", "index.html")]
    spec_card = page.split('href="https://eng.example.com/spec"', 1)[1].split("</div></div></li>", 1)[0]
    office_card = page.split('href="https://eng.example.com/office"', 1)[1].split("</div></div></li>", 1)[0]
    assert "Research behind this, on AI Papers Daily" in spec_card and 'href="../paper/2611.00001.html"' in spec_card
    assert "cs-rel" not in office_card
    # The tags come first, then the paper, then the "Read on" footer
    assert spec_card.index("cs-tags") < spec_card.index("cs-rel") < spec_card.index("cs-foot")
    index = json.loads(page.split('id="cf-index">', 1)[1].split("</script>", 1)[0])
    rows = {r["u"]: r for r in index["posts"]}
    assert rows["https://eng.example.com/spec"]["rp"][0] == "2611.00001"
    assert "rp" not in rows["https://eng.example.com/office"]


def test_research_block_markup():
    block = case_pages.research_block(("2611.00001", "A <b>title</b>"))
    assert block.startswith('<a class="cs-rel" href="../paper/2611.00001.html">') and "A &lt;b&gt;title" in block
    assert case_pages.research_block(None) == ""


NODE = shutil.which("node")


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_words_are_handled_like_the_browser_search():
    js = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "site_assets", "case-finder.js"))
    words = ["policies", "chatbots", "testing", "reranking", "embeddings", "evaluated", "costs", "agentic", "classes"]
    code = (f"const F = require({json.dumps(js)}); console.log(JSON.stringify({{stop: F.STOP, groups: F.GROUPS, "
            f"keys: {json.dumps(words)}.map(F.key)}}));")
    out = json.loads(subprocess.run([NODE, "-e", code], capture_output=True, text=True, timeout=60, check=True).stdout)
    assert set(out["stop"]) == cr.STOP
    assert out["groups"] == cr.GROUPS
    assert out["keys"] == [cr.key(w) for w in words]
