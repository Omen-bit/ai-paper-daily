"""
tests/test_resilience.py
The daily edition and the site build keep going when one piece of data is bad.
"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import site_builder
import paper_store
from paper_store import save_day
from site_builder import build_site


def _paper(pid, **extra):
    paper = {"id": pid, "title": f"Paper {pid}", "authors": ["A"], "abstract": "Abs.",
             "submitted": "2026-10-30", "categories": ["llms"], "score": 1.0, "badges": []}
    paper.update(extra)
    return paper


def test_a_damaged_day_file_is_skipped_not_fatal(tmp_path):
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    save_day([_paper("2610.1")], [_paper("2610.1")], "2026-10-31", data_dir=data_dir)
    with open(os.path.join(data_dir, "daily", "2026-10-30.json"), "w", encoding="utf-8") as f:
        f.write('{"date": "2026-10-30", "papers": [')  # cut off mid-write

    assert build_site(data_dir, site_dir) == 1
    assert os.path.exists(os.path.join(site_dir, "paper", "2610.1.html"))
    # Saving the next day still works, and the index ignores the damaged file
    save_day([_paper("2611.1")], [_paper("2611.1")], "2026-11-01", data_dir=data_dir)
    index = json.load(open(os.path.join(data_dir, "index.json"), encoding="utf-8"))
    assert [d["date"] for d in index["days"]] == ["2026-11-01", "2026-10-31"]


def test_one_bad_paper_record_does_not_stop_the_other_pages(tmp_path, monkeypatch):
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    save_day([_paper("2610.1"), _paper("2610.2")], [_paper("2610.1")], "2026-10-31", data_dir=data_dir)
    real = site_builder.build_paper

    def flaky(rec, *args, **kwargs):
        if rec["id"] == "2610.2":
            raise KeyError("authors")
        return real(rec, *args, **kwargs)
    monkeypatch.setattr(site_builder, "build_paper", flaky)

    build_site(data_dir, site_dir)
    assert os.path.exists(os.path.join(site_dir, "paper", "2610.1.html"))
    assert not os.path.exists(os.path.join(site_dir, "paper", "2610.2.html"))
    assert os.path.exists(os.path.join(site_dir, "index.html"))


def test_share_image_failure_keeps_the_site(tmp_path, monkeypatch):
    data_dir, site_dir = str(tmp_path / "data"), str(tmp_path / "site")
    save_day([_paper("2610.1")], [_paper("2610.1")], "2026-10-31", data_dir=data_dir)
    def boom(*a, **k):
        raise OSError("font missing")
    monkeypatch.setattr(site_builder.discovery, "build_share_images", boom)
    build_site(data_dir, site_dir)
    html = open(os.path.join(site_dir, "paper", "2610.1.html"), encoding="utf-8").read()
    assert "og/site.png" in html  # falls back to the site-wide preview


def test_damaged_history_means_no_repeat_filter_not_a_crash(tmp_path):
    with open(tmp_path / "index.json", "w", encoding="utf-8") as f:
        f.write("not json")
    assert paper_store.recent_featured(7, data_dir=str(tmp_path)) == set()
