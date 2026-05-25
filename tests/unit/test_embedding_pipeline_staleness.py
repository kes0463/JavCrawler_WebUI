from __future__ import annotations

import asyncio
import os


def test_embedding_cache_skips_when_story_context_not_newer(tmp_path, monkeypatch):
    from javstory.library.canonical.schema import LibraryCanonical
    from javstory.library.embeddings import pipeline

    embed_path = tmp_path / "embeddings" / "ABC-123__test-model.json"
    story_path = tmp_path / "story" / "ABC-123_grok.json"
    embed_path.parent.mkdir(parents=True)
    story_path.parent.mkdir(parents=True)
    embed_path.write_text("{}", encoding="utf-8")
    story_path.write_text("{}", encoding="utf-8")
    os.utime(story_path, (1000, 1000))
    os.utime(embed_path, (2000, 2000))

    calls = {"embed": 0}
    monkeypatch.setattr(pipeline, "embeddings_cache_path", lambda *_args, **_kwargs: embed_path)
    monkeypatch.setattr(pipeline, "story_context_cache_path_grok", lambda _code: story_path)
    monkeypatch.setattr(pipeline, "load_canonical_for_product", lambda _code: LibraryCanonical(product_code="ABC-123"))

    async def fake_embed_texts(*_args, **_kwargs):
        calls["embed"] += 1
        return [[0.1]]

    monkeypatch.setattr(pipeline, "ollama_embed_texts", fake_embed_texts)

    out = asyncio.run(
        pipeline.build_and_store_embeddings_for_product("ABC-123", model="test-model")
    )

    assert out == embed_path
    assert calls["embed"] == 0


def test_embedding_cache_regenerates_when_story_context_newer(tmp_path, monkeypatch):
    from javstory.library.canonical.schema import LibraryCanonical
    from javstory.library.embeddings import pipeline

    embed_path = tmp_path / "embeddings" / "ABC-123__test-model.json"
    story_path = tmp_path / "story" / "ABC-123_grok.json"
    embed_path.parent.mkdir(parents=True)
    story_path.parent.mkdir(parents=True)
    embed_path.write_text("{}", encoding="utf-8")
    story_path.write_text("{}", encoding="utf-8")
    os.utime(embed_path, (1000, 1000))
    os.utime(story_path, (2000, 2000))

    logs: list[str] = []
    calls = {"embed": 0}
    state = LibraryCanonical(product_code="ABC-123", title_ko="테스트 작품")
    monkeypatch.setattr(pipeline, "embeddings_cache_path", lambda *_args, **_kwargs: embed_path)
    monkeypatch.setattr(pipeline, "story_context_cache_path_grok", lambda _code: story_path)
    monkeypatch.setattr(pipeline, "load_canonical_for_product", lambda _code: state)
    monkeypatch.setattr(
        pipeline,
        "build_embedding_documents",
        lambda *_args, **_kwargs: [{"doc_id": "d1", "kind": "meta", "text": "hello", "meta": {}}],
    )

    async def fake_ensure_model(*_args, **_kwargs):
        return None

    async def fake_embed_texts(*_args, **_kwargs):
        calls["embed"] += 1
        return [[0.1, 0.2]]

    monkeypatch.setattr(pipeline, "ollama_ensure_model", fake_ensure_model)
    monkeypatch.setattr(pipeline, "ollama_embed_texts", fake_embed_texts)

    out = asyncio.run(
        pipeline.build_and_store_embeddings_for_product(
            "ABC-123",
            model="test-model",
            logger_func=logs.append,
        )
    )

    assert out == embed_path
    assert calls["embed"] == 1
    assert any("스토리 컨텍스트" in line for line in logs)
