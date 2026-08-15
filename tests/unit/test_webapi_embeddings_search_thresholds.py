"""Embeddings search threshold settings (API + env helpers)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_embedding_search_thresholds_from_env_defaults(monkeypatch):
    from javstory.search.library_search import embedding_search_thresholds_from_env

    monkeypatch.delenv("JAVSTORY_EMBEDDING_SEARCH_MIN_SCORE", raising=False)
    monkeypatch.delenv("JAVSTORY_EMBEDDING_SEARCH_RELATIVE_RATIO", raising=False)
    monkeypatch.delenv("JAVSTORY_EMBEDDING_SEARCH_MAX_GAP", raising=False)

    snap = embedding_search_thresholds_from_env()
    assert snap["search_min_score"] == 0.36
    assert snap["search_relative_ratio"] == 0.84
    assert snap["search_max_gap"] == 0.1


def test_embedding_search_thresholds_from_env_custom(monkeypatch):
    from javstory.search.library_search import embedding_search_thresholds_from_env

    monkeypatch.setenv("JAVSTORY_EMBEDDING_SEARCH_MIN_SCORE", "0.42")
    monkeypatch.setenv("JAVSTORY_EMBEDDING_SEARCH_RELATIVE_RATIO", "0.9")
    monkeypatch.setenv("JAVSTORY_EMBEDDING_SEARCH_MAX_GAP", "0.15")

    snap = embedding_search_thresholds_from_env()
    assert snap["search_min_score"] == 0.42
    assert snap["search_relative_ratio"] == 0.9
    assert snap["search_max_gap"] == 0.15


def test_embeddings_settings_snapshot_includes_search_thresholds(monkeypatch):
    from javstory.library.embeddings import web_status

    monkeypatch.setenv("JAVSTORY_EMBEDDING_SEARCH_MIN_SCORE", "0.4")
    monkeypatch.setenv("JAVSTORY_EMBEDDING_SEARCH_RELATIVE_RATIO", "0.8")
    monkeypatch.setenv("JAVSTORY_EMBEDDING_SEARCH_MAX_GAP", "0.12")
    monkeypatch.setattr(web_status, "_library_total_cached", lambda: 0)
    monkeypatch.setattr(
        web_status,
        "_coverage_stats",
        lambda **kwargs: {
            "embedded_count": 0,
            "missing_count": 0,
            "pending_count": 0,
            "coverage_pct": 0.0,
        },
    )
    monkeypatch.setattr(web_status, "embeddings_backfill_running", lambda: False)
    monkeypatch.setattr(
        "javstory.library.embeddings.pipeline.embeddings_enabled_from_env",
        lambda: False,
    )
    monkeypatch.setattr(
        "javstory.library.embeddings.pipeline.embeddings_backend_from_env",
        lambda: "llamacpp",
    )
    monkeypatch.setattr(
        "javstory.library.embeddings.pipeline.embeddings_ollama_model_from_env",
        lambda: "nomic-embed-text",
    )
    monkeypatch.setattr(web_status, "list_embeddings_gguf_options", lambda: [])
    monkeypatch.setattr(web_status, "embeddings_gguf_scan_dir", lambda: "")

    snap = web_status.embeddings_settings_snapshot()
    assert snap["search_min_score"] == 0.4
    assert snap["search_relative_ratio"] == 0.8
    assert snap["search_max_gap"] == 0.12


def test_patch_embeddings_search_thresholds(monkeypatch):
    from webapi.routes import settings as settings_mod

    stored: dict[str, str] = {}
    cleared = {"n": 0}

    def fake_set(key: str, value: str):
        stored[key] = value

    monkeypatch.setattr(
        "javstory.config.secrets_manager.set_env_runtime_value",
        fake_set,
    )
    monkeypatch.setattr(
        "javstory.search.library_search.clear_embed_search_cache",
        lambda: cleared.__setitem__("n", cleared["n"] + 1),
    )
    monkeypatch.setattr(
        "javstory.library.embeddings.web_status.invalidate_embeddings_coverage_cache",
        lambda: None,
    )
    monkeypatch.setattr(
        "javstory.library.embeddings.web_status.embeddings_settings_snapshot",
        lambda: {
            "enabled": True,
            "backend": "llamacpp",
            "model": "nomic-embed-text",
            "gguf_path": "",
            "gguf_scan_dir": "",
            "gguf_options": [],
            "embedded_count": 0,
            "library_total": 0,
            "missing_count": 0,
            "pending_count": 0,
            "backfill_running": False,
            "coverage_pct": 0.0,
            "search_min_score": 0.3,
            "search_relative_ratio": 0.75,
            "search_max_gap": 0.2,
        },
    )

    app = FastAPI()
    app.include_router(settings_mod.router, prefix="/api/settings")
    client = TestClient(app)

    r = client.patch(
        "/api/settings/embeddings",
        json={
            "search_min_score": 0.3,
            "search_relative_ratio": 0.75,
            "search_max_gap": 0.2,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["search_min_score"] == 0.3
    assert stored["JAVSTORY_EMBEDDING_SEARCH_MIN_SCORE"] == "0.3000"
    assert stored["JAVSTORY_EMBEDDING_SEARCH_RELATIVE_RATIO"] == "0.7500"
    assert stored["JAVSTORY_EMBEDDING_SEARCH_MAX_GAP"] == "0.2000"
    assert cleared["n"] == 1


def test_patch_embeddings_search_thresholds_reject_out_of_range():
    from webapi.routes import settings as settings_mod

    app = FastAPI()
    app.include_router(settings_mod.router, prefix="/api/settings")
    client = TestClient(app)

    r = client.patch("/api/settings/embeddings", json={"search_min_score": 1.5})
    assert r.status_code == 422
