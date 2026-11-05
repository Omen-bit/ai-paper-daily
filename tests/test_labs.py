"""tests/test_labs.py: finding the lab or company behind a paper."""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import labs
import paper_links
import site_builder
from paper_store import to_record


def test_hf_org_known_and_unknown():
    assert labs.from_hf_org({"name": "google", "fullname": "Google"}) == "Google"
    assert labs.from_hf_org({"name": "deepseek-ai", "fullname": "DeepSeek"}) == "DeepSeek"
    assert labs.from_hf_org({"name": "Qwen", "fullname": "Qwen"}) == "Alibaba Qwen"
    # A lab we don't list is still shown under its own name
    assert labs.from_hf_org({"name": "tiny-lab", "fullname": "Tiny Robotics Lab"}) == "Tiny Robotics Lab"
    assert labs.from_hf_org(None) == ""


def test_code_owner_only_for_known_accounts():
    assert labs.from_code_url("https://github.com/google-deepmind/foo") == "Google DeepMind"
    assert labs.from_code_url("https://github.com/facebookresearch/bar") == "Meta"
    assert labs.from_code_url("https://github.com/someone/bar") == ""
    assert labs.from_code_url("") == ""


def test_text_needs_whole_names():
    assert labs.from_text("Work done during an internship at Google DeepMind.") == "Google DeepMind"
    assert labs.from_text("Accepted at NeurIPS 2025. Work done at Meta FAIR") == "Meta"
    assert labs.from_text("12 pages, code under the MIT license") == ""
    assert labs.from_text("a fair comparison, 8 figures") == ""
    assert labs.from_text("Meta-learning for tables, 10 pages") == ""
    assert labs.from_text("Accepted to ICLR 2026") == ""


def test_institutions_most_common_wins():
    names = ["Tsinghua University", "Tsinghua University", "Google (United States)"]
    assert labs.from_institutions(names) == "Tsinghua University"
    assert labs.from_institutions(["Microsoft Research (United Kingdom)"]) == "Microsoft"
    assert labs.from_institutions(["Google (United States)", "Unknown Uni"]) == "Google"
    work = {"authorships": [{"institutions": [{"display_name": "Stanford University"}]}, {"institutions": []}]}
    assert labs.openalex_institutions(work) == ["Stanford University"]


def test_record_keeps_lab():
    paper = {"id": "2601.00001", "title": "T", "abstract": "A",
             "hf_org": {"name": "nvidia", "fullname": "NVIDIA"}}
    assert to_record(paper, "2026-01-02", False)["org"] == "NVIDIA"
    assert to_record({"id": "2601.00002", "title": "T"}, "2026-01-02", False)["org"] is None


def test_refresh_orgs_hf_then_openalex(monkeypatch):
    papers = {"a": {"id": "a", "first_seen": "2026-01-02"},
              "b": {"id": "b", "first_seen": "2026-01-01"},
              "c": {"id": "c", "first_seen": "2026-01-01", "org": "OpenAI"}}
    monkeypatch.setattr(paper_links, "hf_paper_org", lambda pid: "Hugging Face" if pid == "a" else "")
    monkeypatch.setattr(paper_links, "openalex_org", lambda pid: "EPFL")
    links = {"b": {"stars": 3}}
    n = paper_links.refresh_orgs(papers, links, today=date(2026, 1, 5))
    assert n == 2
    assert links["a"]["org"] == "Hugging Face"
    assert links["b"] == {"stars": 3, "org": "EPFL", "org_checked": "2026-01-05"}
    assert "c" not in links
    # Found ones are not looked up again
    assert paper_links.refresh_orgs(papers, links, today=date(2026, 1, 20)) == 0


def test_refresh_orgs_failure_retries_next_run(monkeypatch):
    def down(pid):
        raise RuntimeError("offline")
    monkeypatch.setattr(paper_links, "hf_paper_org", down)
    monkeypatch.setattr(paper_links, "openalex_org", down)
    links = {}
    paper_links.refresh_orgs({"a": {"id": "a"}}, links, today=date(2026, 1, 5))
    # The code-owner step still ran, so the paper counts as checked; nothing was invented
    assert "org" not in links["a"]


def test_lab_on_card_and_page():
    rec = {"id": "2601.00003", "title": "A paper", "authors": ["Ada", "Bo"], "abstract": "We do things.",
           "categories": ["nlp"], "first_seen": "2026-01-02", "submitted": "2026-01-01"}
    assert "o" not in site_builder.compact(rec)
    card = site_builder.compact(rec, {"org": "Google DeepMind"})
    assert (card["o"], card["ol"], card["oc"]) == ("Google DeepMind", "deepmind", "4285F4")
    assert site_builder.compact(rec, {"org": "Hugging Face"})["oc"] == "FFD21E/1a1a1a"
    html = site_builder.build_paper(rec, links={"org": "Google DeepMind"})
    assert '<b class="org-name">Google DeepMind</b>' in html and "labs.svg" in html and "#lab-deepmind" in html
    html = site_builder.build_paper(rec, links={"org": "Tsinghua University"})
    assert ">TU</span>" in html and "--lab:#660874" in html
    assert ">Tiny</span>" in site_builder.build_paper(rec, links={"org": "Tiny"})
    assert 'class="org-name"' not in site_builder.build_paper(rec)


def test_every_logo_is_in_the_sprite():
    sprite = open(os.path.join(os.path.dirname(__file__), "..", "src", "site_assets", "labs.svg"), encoding="utf-8").read()
    for name, (logo, colour) in labs.BRANDS.items():
        assert len(colour) == 6, name
        if logo:
            assert f'id="lab-{logo}"' in sprite, name
    assert set(labs.BRANDS) >= set(labs.LABS)


def test_initials():
    assert [labs.initials(n) for n in ("OpenAI", "MIT", "Tsinghua University", "Salesforce")] == ["OA", "MIT", "TU", "S"]
