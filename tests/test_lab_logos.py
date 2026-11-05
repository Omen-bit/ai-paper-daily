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
    monkeypatch.setattr(lab_logos, "find_logo", lambda lab, aliases, avatar="", owners=(): seen.append(owners) or (b"", ""))
    lab_logos.refresh({"Lab": {"avatar": "", "github": ["lab-org"]}}, today=date(2026, 1, 2), logo_dir=str(tmp_path))
    assert seen == [["lab-org"]]
