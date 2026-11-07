"""tests/test_lab_logos.py: official lab logos from Hugging Face and Wikidata."""
import io
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PIL import Image

import lab_logos
import site_builder
import pytest


@pytest.fixture(autouse=True)
def _no_id_lookups(monkeypatch):
    """Tests never reach ROR or Wikidata for ids unless they ask to."""
    monkeypatch.setattr(lab_logos, "identify", lambda names: "")


def _png(w, h, colour=(118, 185, 0, 255)):
    img = Image.new("RGBA", (w + 20, h + 20), (0, 0, 0, 0))
    img.paste(Image.new("RGBA", (w, h), colour), (10, 10))
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def test_square_png_trims_and_fits():
    img = Image.open(io.BytesIO(lab_logos.to_square_png(_png(300, 100)))).convert("RGBA")
    assert img.size == (lab_logos.SIZE, lab_logos.SIZE)
    box = img.getchannel("A").getbbox()
    assert box[2] - box[0] == lab_logos.SIZE  # the logo fills the width once its empty edge is trimmed


def test_wikidata_exact_name_and_organization_only(monkeypatch):
    results = {"search": [
        {"id": "Q89", "label": "apple", "description": "fruit of the apple tree"},
        {"id": "Q312", "label": "Apple Inc.", "match": {"text": "Apple"}, "description": "American multinational technology company"},
    ]}
    monkeypatch.setattr(lab_logos, "_get_json", lambda url, params=None: results)
    assert lab_logos.wikidata_entity(["Apple"]) == "Q312"
    monkeypatch.setattr(lab_logos, "_get_json", lambda url, params=None: {"search": [
        {"id": "Q1", "label": "Applet", "description": "software company"}]})
    assert lab_logos.wikidata_entity(["Apple"]) == ""


def test_most_square_image_wins(monkeypatch):
    sizes = {"Wide.svg": ("https://x/wide.png", 4.0), "Seal.svg": ("https://x/seal.png", 1.0)}
    monkeypatch.setattr(lab_logos, "commons_thumb", lambda f, width=128: sizes[f])
    assert lab_logos.pick_wikidata([("P154", "Wide.svg"), ("P158", "Seal.svg")]) == ("https://x/seal.png", "P158")


def test_refresh_prefers_hugging_face_avatar_and_saves(tmp_path, monkeypatch):
    monkeypatch.setattr(lab_logos, "_download", lambda url: _png(80, 80))
    monkeypatch.setattr(lab_logos, "wikidata_entity", lambda names: "")
    monkeypatch.setattr(lab_logos, "ror_lookup", lambda names: ("", ""))
    n = lab_logos.refresh({"Tiny Lab": "https://cdn-avatars.huggingface.co/v1/production/uploads/a/tiny.png", "Nobody": ""}, today=date(2026, 1, 5), logo_dir=str(tmp_path))
    assert n == 2
    idx = json.load(open(tmp_path / "index.json"))
    assert idx["Tiny Lab"]["file"] == "tiny-lab.png" and idx["Tiny Lab"]["source"] == "Hugging Face"
    assert "file" not in idx["Nobody"]
    assert lab_logos.index(str(tmp_path / "index.json")) == {"Tiny Lab": "tiny-lab.png"}
    # Found logos are kept; missing ones wait a month before another try
    assert lab_logos.refresh({"Tiny Lab": "", "Nobody": ""}, today=date(2026, 1, 20), logo_dir=str(tmp_path)) == 0
    assert lab_logos.hf_avatar_url("/avatars/x.png") == "https://huggingface.co/avatars/x.png"


def test_site_uses_official_logo(monkeypatch):
    monkeypatch.setattr(site_builder, "LOGOS", {"NVIDIA": "nvidia.png"})
    rec = {"id": "1", "title": "T", "authors": ["A"], "abstract": "x", "categories": ["llms"], "first_seen": "2026-01-02"}
    assert site_builder.compact(rec, {"org": "NVIDIA"})["oi"] == "nvidia.png"
    html = site_builder.build_paper(rec, links={"org": "NVIDIA"})
    assert '<img src="../assets/logos/nvidia.png"' in html and "has-img" in html


def test_generated_hugging_face_avatars_are_not_logos():
    assert lab_logos.is_uploaded_avatar("https://cdn-avatars.huggingface.co/v1/production/uploads/6/x.png")
    assert not lab_logos.is_uploaded_avatar("/avatars/0f3c2a.svg")
    assert not lab_logos.is_uploaded_avatar("https://huggingface.co/avatars/0f3c2a.svg")
    assert not lab_logos.is_uploaded_avatar("")


def test_old_entries_are_checked_again(tmp_path, monkeypatch):
    (tmp_path / "old-lab.png").write_bytes(_png(10, 10))
    (tmp_path / "index.json").write_text(json.dumps({"Old Lab": {"file": "old-lab.png", "checked": "2026-01-01"}}))
    monkeypatch.setattr(lab_logos, "wikidata_entity", lambda names: "")
    monkeypatch.setattr(lab_logos, "ror_lookup", lambda names: ("", ""))
    assert lab_logos.refresh({"Old Lab": "/avatars/abc.svg"}, today=date(2026, 1, 2), logo_dir=str(tmp_path)) == 1
    assert not (tmp_path / "old-lab.png").exists()
    assert lab_logos.index(str(tmp_path / "index.json")) == {}


def test_ror_exact_name_gives_wikidata_and_site(monkeypatch):
    data = {"items": [
        {"names": [{"value": "Korea University"}], "external_ids": [{"type": "wikidata", "preferred": "Q1"}]},
        {"names": [{"value": "Korea Advanced Institute of Science and Technology"}, {"value": "KAIST"}],
         "external_ids": [{"type": "wikidata", "all": ["Q30"], "preferred": None}],
         "links": [{"type": "website", "value": "https://www.kaist.ac.kr"}]},
    ]}
    monkeypatch.setattr(lab_logos, "_get_json", lambda url, params=None: data)
    assert lab_logos.ror_lookup(["KAIST"]) == ("Q30", "https://www.kaist.ac.kr")
    assert lab_logos.ror_lookup(["Nowhere Lab"]) == ("", "")


def test_site_icons_best_first():
    html = ('<link rel="icon" href="/fav-32.png" sizes="32x32"><link rel="icon" href="/logo.svg">'
            '<link rel="apple-touch-icon" href="/touch.png" sizes="180x180"><link rel="icon" href="/fav-192.png" sizes="192x192">')
    urls = lab_logos.site_icon_urls("https://lab.example/en/", html)
    assert urls[:3] == ["https://lab.example/touch.png", "https://lab.example/fav-192.png", "https://lab.example/fav-32.png"]
    assert "https://lab.example/logo.svg" not in urls and urls[-1] == "https://lab.example/favicon.ico"


def test_github_org_must_carry_the_lab_name(monkeypatch):
    class R:
        def __init__(self, data): self.status_code, self._d = 200, data
        def json(self): return self._d
    users = {"someone": {"type": "User", "login": "someone", "avatar_url": "https://a/1"},
             "acme-ai": {"type": "Organization", "login": "acme-ai", "name": "Acme AI", "avatar_url": "https://a/2?v=4"}}
    monkeypatch.setattr(lab_logos.requests, "get", lambda url, **kw: R(users[url.rsplit("/", 1)[1]]))
    assert lab_logos.github_avatar(["someone", "acme-ai"], ["Acme AI"]) == "https://a/2?v=4&s=128"
    assert lab_logos.github_avatar(["someone"], ["Someone"]) == ""


def test_find_logo_falls_through_sources(monkeypatch):
    calls = []
    monkeypatch.setattr(lab_logos, "ror_lookup", lambda names: ("", "https://lab.example"))
    monkeypatch.setattr(lab_logos, "wikidata_entity", lambda names: calls.append("wd") or "")
    monkeypatch.setattr(lab_logos, "github_avatar", lambda owners, names: calls.append("gh") or "")
    monkeypatch.setattr(lab_logos, "website_icon", lambda site: b"PNG")
    assert lab_logos.find_logo("Lab", [], "/avatars/x.svg", ["lab"]) == (b"PNG", "website https://lab.example")
    assert calls == ["wd", "gh"]


def test_refresh_accepts_github_hints(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(lab_logos, "find_logo", lambda lab, aliases, avatar="", owners=(), ids=None: seen.append(owners) or (b"", ""))
    lab_logos.refresh({"Lab": {"avatar": "", "github": ["lab-org"]}}, today=date(2026, 1, 2), logo_dir=str(tmp_path))
    assert seen == [["lab-org"]]


def test_network_failure_is_retried_next_run(tmp_path, monkeypatch):
    def down(*a, **k):
        raise lab_logos.requests.exceptions.ConnectionError("offline")
    for name in ("ror_lookup", "wikidata_entity"):
        monkeypatch.setattr(lab_logos, name, down)
    lab_logos.refresh({"Lab": ""}, today=date(2026, 1, 2), logo_dir=str(tmp_path))
    assert lab_logos.due(lab_logos.load_index(str(tmp_path / "index.json")).get("Lab"), date(2026, 1, 3))


def test_lobe_icons_come_first_for_listed_labs(monkeypatch):
    urls = []
    monkeypatch.setattr(lab_logos, "_download", lambda url: urls.append(url) or _png(40, 40))
    monkeypatch.setattr(lab_logos, "ror_lookup", lambda names: (_ for _ in ()).throw(AssertionError("not needed")))
    png, source = lab_logos.find_logo("OpenAI", [], "https://cdn-avatars.huggingface.co/v1/openai.png")
    assert source == "Lobe Icons" and png
    assert urls == [f"https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@{lab_logos.LOBE_VERSION}/light/openai.png"]


def test_labs_with_a_lobe_icon_or_a_site_icon_are_looked_at_again():
    today = date(2026, 11, 7)
    hf = {"file": "meta.png", "source": "Hugging Face", "v": 4, "checked": "2026-11-05"}
    assert lab_logos.due(hf, today, "Meta")
    assert not lab_logos.due(hf, today, "Some University")
    assert not lab_logos.due(dict(hf, v=6), today, "Meta")  # once is enough
    site = {"file": "x.png", "source": "website https://x.edu", "v": 4, "checked": "2026-11-05"}
    assert lab_logos.due(site, today, "X University")
    assert not lab_logos.due(dict(site, v=5), today, "X University")


def test_a_second_look_that_finds_nothing_keeps_the_old_logo(tmp_path, monkeypatch):
    (tmp_path / "x-university.png").write_bytes(_png(10, 10))
    old = {"file": "x-university.png", "source": "website https://x.edu", "v": 4, "checked": "2026-11-01"}
    (tmp_path / "index.json").write_text(json.dumps({"X University": old}))
    monkeypatch.setattr(lab_logos, "find_logo", lambda *a, **k: (b"", ""))
    lab_logos.refresh({"X University": ""}, today=date(2026, 11, 7), logo_dir=str(tmp_path))
    entry = lab_logos.load_index(str(tmp_path / "index.json"))["X University"]
    assert (tmp_path / "x-university.png").exists() and entry["file"] == "x-university.png"
    assert entry["v"] == lab_logos.VERSION and not lab_logos.due(entry, date(2026, 11, 8), "X University")


def test_ror_skips_an_acronym_when_a_full_name_is_known(monkeypatch):
    asked = []
    monkeypatch.setattr(lab_logos, "_get_json", lambda url, params=None: asked.append(params["query"]) or {})
    lab_logos.ror_lookup(["NUS", "national university of singapore"])
    assert asked == ["national university of singapore"]
    asked.clear()
    lab_logos.ror_lookup(["KAIST"])  # nothing longer to go by
    assert asked == ["KAIST"]


def test_commons_thumbnails_use_a_standard_width(monkeypatch):
    seen = {}
    monkeypatch.setattr(lab_logos, "_get_json", lambda url, params=None: seen.update(params) or {})
    lab_logos.commons_thumb("Logo.svg")
    assert seen["iiurlwidth"] in (20, 40, 60, 120, 250, 330, 500, 960)


def test_logo_dev_uses_the_download_api_not_the_cdn(monkeypatch):
    calls = []

    class R:
        def __init__(self, code, data=None): self.status_code, self._d = code, data
        def json(self): return self._d
    monkeypatch.setenv("LOGO_DEV_SECRET_KEY", "sk_test")
    monkeypatch.setattr(lab_logos.requests, "get",
                        lambda url, **kw: calls.append((url, kw)) or R(200, {"data": {"url": "https://dl.example/x.png"}}))
    monkeypatch.setattr(lab_logos, "_download", lambda url: calls.append((url, {})) or _png(40, 40))
    assert lab_logos.logo_dev("https://www.lab.example/")
    assert calls[0][0] == "https://api.logo.dev/v2/brands/logo"
    assert calls[0][1]["params"] == {"domain": "lab.example"}
    assert calls[0][1]["headers"]["Authorization"] == "Bearer sk_test"
    assert calls[1][0] == "https://dl.example/x.png" and not any("img.logo.dev" in u for u, _ in calls)
    monkeypatch.setattr(lab_logos.requests, "get", lambda url, **kw: R(202))
    assert lab_logos.logo_dev("https://lab.example") == b""
    monkeypatch.delenv("LOGO_DEV_SECRET_KEY")
    assert lab_logos.logo_dev("https://lab.example") == b""


def test_every_lobe_name_is_a_known_lab_or_alias():
    import labs
    assert set(lab_logos.LOBE) - set(labs.LABS) <= {"Sakana AI", "Perplexity", "Upstage", "Baichuan", "01.AI",
                                                    "Nous Research", "Yandex"}


def test_companies_match_lobe_icons_by_brand_name():
    assert lab_logos.lobe_file("Sakana AI") == "sakana-color"
    assert lab_logos.lobe_file("sakana-ai") == "sakana-color"
    assert lab_logos.lobe_file("Black Forest Labs") == "bfl"
    assert lab_logos.lobe_file("Google DeepMind") == "deepmind-color"  # named in LOBE
    assert lab_logos.lobe_file("Tencent") == ""  # its own avatar reads better
    assert lab_logos.lobe_file("Magic") == ""  # a common word, too likely to be someone else
    assert lab_logos.lobe_file("Meta University") == ""  # universities are never matched by name
    assert lab_logos.lobe_file("Some New Lab") == ""


def test_lab_ids_are_saved_and_backfilled(tmp_path, monkeypatch):
    (tmp_path / "old.png").write_bytes(_png(10, 10))
    (tmp_path / "index.json").write_text(json.dumps({
        "Old Lab": {"file": "old.png", "source": "Hugging Face", "v": 4, "checked": "2026-11-01"}}))
    monkeypatch.setattr(lab_logos, "identify", lambda names: {"Old Lab": "Q1", "New Lab": "Q2"}.get(names[0], ""))
    monkeypatch.setattr(lab_logos, "find_logo", lambda *a, **k: (b"PNG", "Hugging Face"))
    lab_logos.refresh({"New Lab": "", "Old Lab": ""}, today=date(2026, 11, 7), logo_dir=str(tmp_path))
    idx = lab_logos.load_index(str(tmp_path / "index.json"))
    assert idx["New Lab"]["qid"] == "Q2" and idx["Old Lab"]["qid"] == "Q1"
    assert idx["Old Lab"]["file"] == "old.png"  # only the id was looked up


def test_find_logo_reports_the_id_it_found(monkeypatch):
    monkeypatch.setattr(lab_logos, "ror_lookup", lambda names: ("Q30", ""))
    monkeypatch.setattr(lab_logos, "wikidata_images", lambda qid: [])
    monkeypatch.setattr(lab_logos, "wikidata_website", lambda qid: "")
    ids = {}
    assert lab_logos.find_logo("KAIST", [], ids=ids) == (b"", "")
    assert ids == {"qid": "Q30"}


def test_same_org_groups_names_sharing_an_id(tmp_path):
    (tmp_path / "index.json").write_text(json.dumps({
        "ucas": {"qid": "Q9"}, "University of Chinese Academy of Sciences": {"qid": "Q9"},
        "Chinese Academy of Sciences": {"qid": "Q8"}, "MMLab@NTU": {"qid": ""}}))
    assert lab_logos.same_org(str(tmp_path / "index.json")) == {
        "Q9": ["University of Chinese Academy of Sciences", "ucas"]}


def test_one_lab_under_two_names_is_shown_once(monkeypatch):
    groups = {"Q9": ["University of Chinese Academy of Sciences", "ucas"], "Q1": ["MIT", "mit-han-lab"],
              "Q5": ["Only Here", "No Papers"]}
    counts = {"University of Chinese Academy of Sciences": 2, "ucas": 5, "MIT": 1, "mit-han-lab": 9, "Only Here": 1}
    same = site_builder.same_lab_names(groups, counts)
    assert same == {"ucas": "University of Chinese Academy of Sciences",  # written out, though fewer papers
                    "mit-han-lab": "MIT"}  # a name the site already knows wins
    monkeypatch.setattr(site_builder, "SAME_LAB", same)
    assert site_builder.lab_of({"org": "mit-han-lab"}) == "MIT"
    assert site_builder.lab_of({"org": "Only Here"}) == "Only Here"
