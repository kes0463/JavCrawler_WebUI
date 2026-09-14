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

        def __init__(self, n: int):
            self._n = n

        def json(self):
            # 요청된 텍스트 개수만큼 임베딩을 돌려준다(배치 응답 형태와 동일하게).
            return {
                "data": [
                    {"index": i, "embedding": [0.1, 0.2]} for i in range(self._n)
                ]
            }

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
            inp = (json or {}).get("input")
            n = len(inp) if isinstance(inp, list) else 1
            return DummyResp(n)

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


def test_llamacpp_embeds_in_one_batch_request(monkeypatch):
    """캐시 안 된 여러 텍스트는 배치 크기 이내면 요청 1번으로 묶인다."""
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_MAX_INPUT_CHARS", "500")
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_LLAMACPP_BATCH_SIZE", "10")
    posted: list[dict] = []
    _patch_sync_http_client(monkeypatch, posted)
    monkeypatch.setattr(emb.cache_manager, "get_embedding", lambda *_: None)
    monkeypatch.setattr(emb.cache_manager, "set_embedding", lambda *_a, **_k: None)

    out = asyncio.run(emb.llamacpp_embed_texts(texts=["aaa", "bbb"], model="test-model"))
    assert len(out) == 2
    assert len(posted) == 1
    assert posted[0]["input"] == ["aaa", "bbb"]


def test_llamacpp_embeds_respects_batch_size_env(monkeypatch):
    """텍스트 수가 배치 크기를 넘으면 여러 번의 배치 요청으로 나뉜다."""
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_MAX_INPUT_CHARS", "500")
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_LLAMACPP_BATCH_SIZE", "3")
    posted: list[dict] = []
    _patch_sync_http_client(monkeypatch, posted)
    monkeypatch.setattr(emb.cache_manager, "get_embedding", lambda *_: None)
    monkeypatch.setattr(emb.cache_manager, "set_embedding", lambda *_a, **_k: None)

    texts = [f"t{i}" for i in range(7)]
    out = asyncio.run(emb.llamacpp_embed_texts(texts=texts, model="test-model"))
    assert len(out) == 7
    # 마지막 배치는 1개라 input이 리스트가 아니라 문자열 그대로 전송된다(기존 단건 포맷과 동일).
    sizes = [len(p["input"]) if isinstance(p["input"], list) else 1 for p in posted]
    assert sizes == [3, 3, 1]


def test_llamacpp_embeds_falls_back_per_item_on_batch_failure(monkeypatch):
    """배치 요청이 실패하면 그 배치만 항목별 순차 요청으로 폴백해 전부 채워진다."""
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_MAX_INPUT_CHARS", "500")
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_LLAMACPP_BATCH_SIZE", "10")
    monkeypatch.setattr(emb.cache_manager, "get_embedding", lambda *_: None)
    monkeypatch.setattr(emb.cache_manager, "set_embedding", lambda *_a, **_k: None)

    posted: list[dict] = []

    class DummyResp:
        status_code = 200

        def __init__(self, n: int):
            self._n = n

        def json(self):
            return {"data": [{"index": i, "embedding": [0.1, 0.2]} for i in range(self._n)]}

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
            inp = (json or {}).get("input")
            if isinstance(inp, list):
                raise RuntimeError("simulated batch failure")
            return DummyResp(1)

    monkeypatch.setattr(emb.httpx, "Client", DummyClient)

    out = asyncio.run(emb.llamacpp_embed_texts(texts=["aaa", "bbb"], model="test-model"))
    assert len(out) == 2
    assert all(out)
    # 1번의 배치 시도(실패) + 2번의 개별 폴백
    assert len(posted) == 3
    assert isinstance(posted[0]["input"], list)
    assert all(isinstance(p["input"], str) for p in posted[1:])


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
