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
    n = lab_logos.refresh({"Tiny Lab": "/avatars/tiny.png", "Nobody": ""}, today=date(2026, 1, 5), logo_dir=str(tmp_path))
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
