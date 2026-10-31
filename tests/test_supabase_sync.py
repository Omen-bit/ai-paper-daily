"""
tests/test_supabase_sync.py
Unit tests for supabase_sync.py. A fake session stands in for Supabase.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import supabase_sync as sync
from paper_store import save_day


class FakeResponse:
    def __init__(self, status=201, body=None):
        self.status_code, self._body, self.text = status, body or {}, ""

    def json(self):
        return self._body


class FakeSession:
    """Records calls; the embed endpoint reports 25 pending, then 5, then 0."""
    def __init__(self, upload_status=201):
        self.calls, self.upload_status = [], upload_status
        self.embed_replies = [{"embedded": 20, "remaining": 5}, {"embedded": 5, "remaining": 0}]

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append((url, json, headers))
        if "/functions/v1/embed" in url:
            return FakeResponse(200, self.embed_replies.pop(0))
        return FakeResponse(self.upload_status)


def _paper(pid, **extra):
    p = {"id": pid, "title": f"T{pid}", "authors": ["A"], "abstract": "Abs.", "submitted": "2026-10-30",
         "categories": ["llms"], "score": 1.0, "badges": []}
    p.update(extra)
    return p


def _env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co/")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_abc")
    monkeypatch.setenv("SYNC_SECRET", "s3cret")


def test_skips_quietly_without_settings(monkeypatch, tmp_path):
    for k in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "SYNC_SECRET"):
        monkeypatch.delenv(k, raising=False)
    session = FakeSession()
    assert sync.sync(data_dir=str(tmp_path), session=session) == 0
    assert session.calls == []


def test_daily_sync_uploads_newest_day_then_embeds(monkeypatch, tmp_path):
    _env(monkeypatch)
    data = str(tmp_path)
    save_day([_paper("a")], [_paper("a")], "2026-10-30", data_dir=data)
    save_day([_paper("b", code_url="https://github.com/x/y"), _paper("c")], [_paper("b")], "2026-10-31", data_dir=data)
    session = FakeSession()
    assert sync.sync(data_dir=data, session=session) == 2

    url, rows, headers = session.calls[0]
    assert url == "https://x.supabase.co/rest/v1/papers?on_conflict=id"
    assert sorted(r["id"] for r in rows) == ["b", "c"]
    assert headers["apikey"] == "sb_secret_abc" and "Authorization" not in headers
    assert "merge-duplicates" in headers["Prefer"]
    row_b = next(r for r in rows if r["id"] == "b")
    assert row_b["featured"] is True and row_b["first_seen"] == "2026-10-31"
    # Two embed calls, both carrying the sync secret
    embed_calls = [c for c in session.calls if "/functions/v1/embed" in c[0]]
    assert len(embed_calls) == 2
    assert embed_calls[0][2]["x-sync-secret"] == "s3cret"


def test_all_flag_uploads_every_paper(monkeypatch, tmp_path):
    _env(monkeypatch)
    data = str(tmp_path)
    save_day([_paper("a")], [_paper("a")], "2026-10-30", data_dir=data)
    save_day([_paper("b")], [_paper("b")], "2026-10-31", data_dir=data)
    session = FakeSession()
    assert sync.sync(everything=True, data_dir=data, session=session) == 2


def test_legacy_jwt_key_also_sends_authorization():
    assert sync._headers("eyJabc")["Authorization"] == "Bearer eyJabc"


def test_main_never_fails_the_run(monkeypatch, tmp_path):
    _env(monkeypatch)
    monkeypatch.setattr(sync, "DATA_DIR", str(tmp_path))
    save_day([_paper("a")], [_paper("a")], "2026-10-31", data_dir=str(tmp_path))
    monkeypatch.setattr(sync, "sync", lambda everything=False: (_ for _ in ()).throw(RuntimeError("down")))
    assert sync.main() == 0


def test_backfill_keeps_existing_rows_and_survives_bad_days():
    from datetime import date
    cfg = {"url": "https://x.supabase.co", "key": "sb_secret_abc", "secret": "s"}

    def fetch(day):
        if day == "2026-10-29":
            raise RuntimeError("HF down")
        return [_paper("p" + day[-2:], abstract="We train an LLM. Code: https://github.com/a/b.")]

    session = FakeSession()
    total = sync.backfill_hf(cfg, 3, session, fetch=fetch, today=date(2026, 10, 31), sleep=lambda s: None)
    assert total == 2  # 28th and 30th; the 29th failed and was skipped
    url, rows, headers = session.calls[0]
    assert "ignore-duplicates" in headers["Prefer"]
    assert [r["first_seen"] for r in rows] == ["2026-10-28", "2026-10-30"]
    assert rows[0]["featured"] is False and rows[0]["code_url"] == "https://github.com/a/b"
    assert rows[0]["categories"]  # classified into our topics


def test_embed_retries_with_smaller_batches_after_cpu_limit():
    cfg = {"url": "https://x.supabase.co", "key": "k", "secret": "s"}
    replies = [FakeResponse(546), FakeResponse(200, {"embedded": 4, "remaining": 0})]

    class Session:
        limits = []

        def post(self, url, json=None, headers=None, timeout=None):
            self.limits.append(json["limit"])
            return replies.pop(0)

    session = Session()
    assert sync.embed_pending(cfg, session, sleep=lambda s: None) == 4
    assert session.limits == [8, 4]


def test_embed_stops_at_once_when_function_is_missing():
    import pytest
    cfg = {"url": "https://x.supabase.co", "key": "k", "secret": "s"}

    class Session:
        def post(self, *a, **k):
            return FakeResponse(404)

    with pytest.raises(RuntimeError):
        sync.embed_pending(cfg, Session(), sleep=lambda s: None)
