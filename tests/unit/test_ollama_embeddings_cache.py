from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_ollama_embed_text_uses_cache(monkeypatch):
    from javstory.llm import ollama_embeddings
    from javstory.utils.cache_manager import cache_manager

    cache_manager.reset()
    calls = {"count": 0}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"embedding": [0.1, 0.2, 0.3]}

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *_args, **_kwargs):
            calls["count"] += 1
            return DummyResponse()

    monkeypatch.setattr(ollama_embeddings.httpx, "AsyncClient", DummyClient)

    first = await ollama_embeddings.ollama_embed_text(text="hello", model="dummy")
    second = await ollama_embeddings.ollama_embed_text(text="hello", model="dummy")

    assert first == [0.1, 0.2, 0.3]
    assert second == first
    assert calls["count"] == 1
