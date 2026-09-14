"""Embedding ANN / vector-index unit tests."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def emb_cache(tmp_path: Path, monkeypatch):
    cache = tmp_path / "embeddings"
    cache.mkdir()
    monkeypatch.setattr(
        "javstory.library.embeddings.store.embeddings_cache_dir",
        lambda: cache,
    )
    monkeypatch.setattr(
        "javstory.library.embeddings.ann_index.embeddings_cache_dir",
        lambda: cache,
    )
    # 모듈 메모리 인덱스 초기
    import javstory.library.embeddings.ann_index as ann

    monkeypatch.setattr(ann, "_MEMORY", {})
    monkeypatch.setattr(ann, "_DIRTY", set())
    monkeypatch.setenv("JAVSTORY_EMBEDDING_ANN_ENABLED", "1")
    return cache


def _write_payload(cache: Path, code: str, model: str, docs: list[dict]) -> Path:
    path = cache / f"{code}__{model}.json"
    payload = {
        "product_code": code,
        "model": model,
        "docs": docs,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_build_and_search_ann_max_cosine(emb_cache: Path):
    from javstory.library.embeddings.ann_index import (
        build_embedding_ann_index,
        search_ann_max_cosine,
    )

    model = "test-embed"
    _write_payload(
        emb_cache,
        "AAA-001",
        model,
        [
            {"kind": "meta_canonical", "text": "사무실 OL", "embedding": [1.0, 0.0, 0.0]},
            {"kind": "grok_story", "text": "비 오는 날", "embedding": [0.2, 0.8, 0.0]},
        ],
    )
    _write_payload(
        emb_cache,
        "BBB-002",
        model,
        [
            {"kind": "meta_canonical", "text": "온천", "embedding": [0.0, 1.0, 0.0]},
        ],
    )

    index = build_embedding_ann_index(model, force=True)
    assert index is not None
    assert index.product_count == 2
    assert index.doc_count == 3

    # 쿼리가 [1,0,0]이면 AAA의 meta 문서가 최고
    hits, texts = search_ann_max_cosine([1.0, 0.0, 0.0], model=model)
    assert hits[0][0] == "AAA-001"
    assert hits[0][1] == pytest.approx(1.0, abs=1e-5)
    assert "사무실" in texts["AAA-001"]
    assert "온천" in texts["BBB-002"]


def test_build_ann_skips_source_signature_on_clean_cache(emb_cache: Path, monkeypatch):
    from javstory.library.embeddings import ann_index as ann

    model = "test-embed"
    _write_payload(
        emb_cache,
        "AAA-001",
        model,
        [{"kind": "meta", "text": "a", "embedding": [1.0, 0.0]}],
    )
    assert ann.build_embedding_ann_index(model, force=True) is not None

    calls = {"n": 0}
    orig = ann._source_signature

    def counted(m):
        calls["n"] += 1
        return orig(m)

    monkeypatch.setattr(ann, "_source_signature", counted)
    again = ann.build_embedding_ann_index(model, force=False)
    assert again is not None
    assert calls["n"] == 0
    fetched = ann.get_embedding_ann_index(model)
    assert fetched is not None
    assert calls["n"] == 0


def test_ann_invalidate_forces_rebuild(emb_cache: Path):
    from javstory.library.embeddings import ann_index as ann

    model = "test-embed"
    _write_payload(
        emb_cache,
        "AAA-001",
        model,
        [{"kind": "meta", "text": "a", "embedding": [1.0, 0.0]}],
    )
    assert ann.build_embedding_ann_index(model, force=True) is not None
    assert ann.get_embedding_ann_index(model).product_count == 1

    _write_payload(
        emb_cache,
        "BBB-002",
        model,
        [{"kind": "meta", "text": "b", "embedding": [0.0, 1.0]}],
    )
    ann.invalidate_embedding_ann_index(model)
    rebuilt = ann.get_embedding_ann_index(model)
    assert rebuilt is not None
    assert rebuilt.product_count == 2


def test_write_embeddings_json_invalidates_ann(emb_cache: Path, monkeypatch):
    from javstory.library.embeddings import ann_index as ann
    from javstory.library.embeddings.store import write_embeddings_json

    model = "test-embed"
    _write_payload(
        emb_cache,
        "AAA-001",
        model,
        [{"kind": "meta", "text": "a", "embedding": [1.0, 0.0]}],
    )
    ann.build_embedding_ann_index(model, force=True)
    assert model.replace("/", "_")  # touch
    key = ann._model_key(model)
    assert key in ann._MEMORY or ann.get_embedding_ann_index(model) is not None

    write_embeddings_json(
        emb_cache / f"CCC-003__{model}.json",
        {
            "product_code": "CCC-003",
            "model": model,
            "docs": [{"kind": "meta", "text": "c", "embedding": [0.0, 1.0]}],
        },
    )
    assert key in ann._DIRTY or key not in ann._MEMORY


def test_search_embedding_uses_ann(monkeypatch, emb_cache: Path):
    from javstory.search.library_search import HybridLibrarySearch, _LibraryDoc, _SearchResult

    model = "test-embed"
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_ENABLED", "1")
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_MODEL", model)
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_OLLAMA_MODEL", model)

    from javstory.library.embeddings.ann_index import build_embedding_ann_index

    _write_payload(
        emb_cache,
        "AAA-001",
        model,
        [{"kind": "meta", "text": "사무실", "embedding": [1.0, 0.0, 0.0]}],
    )
    _write_payload(
        emb_cache,
        "BBB-002",
        model,
        [{"kind": "meta", "text": "온천", "embedding": [0.0, 1.0, 0.0]}],
    )
    build_embedding_ann_index(model, force=True)

    search = HybridLibrarySearch()
    docs = [
        _LibraryDoc("AAA-001", "A", "a", "a"),
        _LibraryDoc("BBB-002", "B", "b", "b"),
    ]
    monkeypatch.setattr(search, "_load_docs", lambda: docs)

    async def fake_embed(texts, model=None, **kwargs):
        return [[1.0, 0.0, 0.0]]

    monkeypatch.setattr(
        "javstory.search.library_search.embed_texts",
        fake_embed,
    )
    monkeypatch.setattr(
        "javstory.search.library_search.format_search_query_for_embedding",
        lambda q, model=None: q,
    )
    monkeypatch.setattr(
        "javstory.search.library_search.expand_query_concepts",
        lambda q: [],
    )

    # 선형 스캔이 호출되면 실패시키기
    monkeypatch.setattr(
        "javstory.search.library_search._iter_embedding_payloads",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should use ANN")),
    )

    results = search._search_embedding("사무실", docs, top_k=None)
    assert search.last_embedding_diag.get("ann_used") is True
    assert results[0].id == "AAA-001"
    assert results[0].raw_score == pytest.approx(1.0, abs=1e-5)


def test_ann_disabled_falls_back(monkeypatch, emb_cache: Path):
    from javstory.search.library_search import HybridLibrarySearch, _LibraryDoc

    monkeypatch.setenv("JAVSTORY_EMBEDDING_ANN_ENABLED", "0")
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_ENABLED", "1")
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_MODEL", "test-embed")

    search = HybridLibrarySearch()
    docs = [_LibraryDoc("AAA-001", "A", "a", "a")]
    monkeypatch.setattr(search, "_load_docs", lambda: docs)

    async def fake_embed(texts, model=None, **kwargs):
        return [[1.0, 0.0]]

    monkeypatch.setattr("javstory.search.library_search.embed_texts", fake_embed)
    monkeypatch.setattr(
        "javstory.search.library_search.format_search_query_for_embedding",
        lambda q, model=None: q,
    )
    monkeypatch.setattr(
        "javstory.search.library_search.expand_query_concepts",
        lambda q: [],
    )
    monkeypatch.setattr(
        "javstory.search.library_search._iter_embedding_payloads",
        lambda **kwargs: iter(
            [
                (
                    Path("x"),
                    {
                        "product_code": "AAA-001",
                        "model": "test-embed",
                        "docs": [{"embedding": [1.0, 0.0], "text": "a"}],
                    },
                )
            ]
        ),
    )
    monkeypatch.setattr(
        "javstory.search.library_search.max_doc_cosine",
        lambda q, payload: 0.91,
    )
    monkeypatch.setattr(
        "javstory.search.library_search.payload_doc_text_blob",
        lambda payload: "a",
    )

    results = search._search_embedding("q", docs, top_k=None)
    assert search.last_embedding_diag.get("ann_used") is False
    assert results and results[0].id == "AAA-001"
