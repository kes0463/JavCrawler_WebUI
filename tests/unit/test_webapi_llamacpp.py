"""webapi llama.cpp 모델 선택/상태 라우트 테스트."""

from __future__ import annotations

import pytest


@pytest.fixture
def llamacpp_client(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from webapi.main import app

    return TestClient(app)


def test_llamacpp_models_lists_all_presets(llamacpp_client):
    res = llamacpp_client.get("/api/llamacpp/models")
    assert res.status_code == 200
    body = res.json()
    ids = {m["id"] for m in body["models"]}
    assert "qwen3-14b" in ids
    assert "gemma-4-e4b" in ids
    assert "insight_active_preset_id" in body
    assert "persona_chat_active_preset_id" in body


def test_llamacpp_status_returns_snapshot(monkeypatch, llamacpp_client):
    from webapi.routes import llamacpp as llamacpp_mod

    monkeypatch.setattr(
        llamacpp_mod,
        "llamacpp_server_status",
        lambda: {
            "state": "stopped",
            "active_preset_id": None,
            "active_label": None,
            "base_url": "http://127.0.0.1:8081",
            "active_requests": 0,
            "persona_chat_managed": True,
        },
    )
    res = llamacpp_client.get("/api/llamacpp/status")
    assert res.status_code == 200
    assert res.json()["state"] == "stopped"


def test_llamacpp_select_rejects_unknown_preset(llamacpp_client):
    res = llamacpp_client.post(
        "/api/llamacpp/select", json={"feature": "insight", "preset_id": "no-such-model"}
    )
    assert res.status_code == 400


def test_llamacpp_select_is_idempotent_when_already_active(monkeypatch, llamacpp_client):
    from webapi.routes import llamacpp as llamacpp_mod

    monkeypatch.setattr(llamacpp_mod, "set_env_runtime_value", lambda *a, **kw: None)
    monkeypatch.setattr(
        llamacpp_mod,
        "llamacpp_server_status",
        lambda: {
            "state": "ready",
            "active_preset_id": "qwen3-14b",
            "active_label": "Qwen3-14B (Dense)",
            "base_url": "http://127.0.0.1:8081",
            "active_requests": 0,
            "persona_chat_managed": True,
        },
    )

    spawn_calls: list[str] = []
    monkeypatch.setattr(
        llamacpp_mod,
        "ensure_llamacpp_server_ready",
        lambda *a, **kw: spawn_calls.append("spawned"),
    )

    res = llamacpp_client.post(
        "/api/llamacpp/select", json={"feature": "insight", "preset_id": "qwen3-14b"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body == {"accepted": True, "already_active": True}
    assert spawn_calls == []


def test_llamacpp_select_kicks_off_spawn_when_different_model(monkeypatch, llamacpp_client):
    import threading

    from webapi.routes import llamacpp as llamacpp_mod

    monkeypatch.setattr(llamacpp_mod, "set_env_runtime_value", lambda *a, **kw: None)
    monkeypatch.setattr(
        llamacpp_mod,
        "llamacpp_server_status",
        lambda: {
            "state": "ready",
            "active_preset_id": "gemma-4-e4b",
            "active_label": "Gemma-4-E4B",
            "base_url": "http://127.0.0.1:8081",
            "active_requests": 0,
            "persona_chat_managed": True,
        },
    )

    spawned = threading.Event()
    monkeypatch.setattr(
        llamacpp_mod,
        "ensure_llamacpp_server_ready",
        lambda *a, **kw: spawned.set(),
    )

    res = llamacpp_client.post(
        "/api/llamacpp/select", json={"feature": "insight", "preset_id": "qwen3-14b"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body == {"accepted": True, "already_active": False}
    assert spawned.wait(timeout=2.0)
