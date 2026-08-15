from __future__ import annotations

import asyncio

import httpx
import pytest

from javstory.llm import llamacpp_embeddings as emb


@pytest.fixture(autouse=True)
def _reset_embed_semaphore():
    emb._embed_http_sem = None
    yield
    emb._embed_http_sem = None


def _patch_sync_http_client(monkeypatch, posted: list[dict]):
    class DummyResp:
        status_code = 200

        def json(self):
            return {"data": [{"index": 0, "embedding": [0.1, 0.2]}]}

        def raise_for_status(self):
            return None

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json=None):
            posted.append(json or {})
            return DummyResp()

    monkeypatch.setattr(emb.httpx, "Client", DummyClient)


def test_embedding_max_input_chars_default(monkeypatch):
    monkeypatch.delenv("JAVSTORY_EMBEDDINGS_MAX_INPUT_CHARS", raising=False)
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_LLAMACPP_CTX", "2048")
    assert emb.embedding_max_input_chars() == 2048 - 128


def test_embedding_max_input_chars_env_override(monkeypatch):
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_MAX_INPUT_CHARS", "4096")
    assert emb.embedding_max_input_chars() == 4096


def test_truncate_embedding_input(monkeypatch):
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_MAX_INPUT_CHARS", "500")
    assert emb.truncate_embedding_input("x" * 600) == "x" * 500
    assert emb.truncate_embedding_input("short") == "short"
    assert emb.truncate_embedding_input("  padded  ") == "padded"


def test_is_context_exceed_error_matches_500_body():
    resp = httpx.Response(
        500,
        json={"error": {"message": "Context size has been exceeded.", "type": "server_error"}},
        request=httpx.Request("POST", "http://127.0.0.1:8082/v1/embeddings"),
    )
    exc = httpx.HTTPStatusError("boom", request=resp.request, response=resp)
    assert emb._is_context_exceed_error(exc)
    assert emb._is_server_overload_error(exc)


def test_llamacpp_embeds_sequentially_not_batch(monkeypatch):
    """여러 텍스트는 batch가 아니라 항목별 POST."""
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_MAX_INPUT_CHARS", "500")
    posted: list[dict] = []
    _patch_sync_http_client(monkeypatch, posted)
    monkeypatch.setattr(emb.cache_manager, "get_embedding", lambda *_: None)
    monkeypatch.setattr(emb.cache_manager, "set_embedding", lambda *_a, **_k: None)

    out = asyncio.run(emb.llamacpp_embed_texts(texts=["aaa", "bbb"], model="test-model"))
    assert len(out) == 2
    assert len(posted) == 2
    assert all(isinstance(p.get("input"), str) for p in posted)


def test_llamacpp_embed_truncates_long_text(monkeypatch):
    """긴 입력은 truncate 후 API 호출 — 400 ctx 초과 방지."""
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_MAX_INPUT_CHARS", "500")
    posted: list[dict] = []
    _patch_sync_http_client(monkeypatch, posted)
    monkeypatch.setattr(emb.cache_manager, "get_embedding", lambda *_: None)
    monkeypatch.setattr(emb.cache_manager, "set_embedding", lambda *_a, **_k: None)

    long_text = "가" * 5000
    out = asyncio.run(emb.llamacpp_embed_texts(texts=[long_text], model="test-model"))
    assert len(out) == 1
    assert len(out[0]) == 2
    assert len(posted[0]["input"]) == 500
