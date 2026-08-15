from __future__ import annotations

import time

from javstory.library.embeddings import web_status as ws


def test_embeddings_settings_snapshot_is_fast(monkeypatch, tmp_path):
    monkeypatch.setattr(ws, "embeddings_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(ws, "embeddings_gguf_scan_dir", lambda: str(tmp_path))
    monkeypatch.setattr(ws, "list_embeddings_gguf_options", lambda: [])
    monkeypatch.setattr(ws, "embeddings_backfill_running", lambda: False)
    monkeypatch.setattr(ws, "embeddings_ollama_model_from_env", lambda: "test-model")
    monkeypatch.setattr(ws, "embeddings_enabled_from_env", lambda: True)

    class DummyDb:
        def query(self, *_args, **_kwargs):
            return self

        def count(self):
            return 10_000

    class DummyCtx:
        def __enter__(self):
            return DummyDb()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(ws, "get_db_session_ctx", lambda: DummyCtx())
    ws.invalidate_embeddings_coverage_cache()

    (tmp_path / "ABC-123__test-model.json").write_text("{}", encoding="utf-8")

    t0 = time.perf_counter()
    snap = ws.embeddings_settings_snapshot()
    elapsed = time.perf_counter() - t0

    assert snap["library_total"] == 10_000
    assert snap["embedded_count"] == 1
    assert snap["missing_count"] == 9_999
    assert elapsed < 0.5
