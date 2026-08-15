"""webapi embeddings GGUF options route tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def gguf_options_client(monkeypatch, tmp_path: Path):
    gguf = tmp_path / "e5-mistral-7b-instruct-Q4_K_M.gguf"
    gguf.write_bytes(b"x")

    def fake_snapshot():
        return {
            "gguf_scan_dir": str(tmp_path),
            "gguf_options": [
                {"id": "", "label": "(자동 탐색)", "gguf_path": "", "gguf_env": ""},
                {
                    "id": "abc",
                    "label": gguf.name,
                    "gguf_path": str(gguf),
                    "gguf_env": "",
                },
            ],
        }

    from webapi.routes import settings as settings_mod

    monkeypatch.setattr(
        "javstory.library.embeddings.web_status.embeddings_gguf_options_snapshot",
        fake_snapshot,
    )
    app = FastAPI()
    app.include_router(settings_mod.router, prefix="/api/settings")
    return TestClient(app)


def test_embeddings_gguf_options_route(gguf_options_client: TestClient) -> None:
    r = gguf_options_client.get("/api/settings/embeddings/gguf-options")
    assert r.status_code == 200
    body = r.json()
    assert body["gguf_scan_dir"]
    assert len(body["gguf_options"]) >= 2
