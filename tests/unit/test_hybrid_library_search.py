from __future__ import annotations


def test_hybrid_library_search_uses_rrf_weights():
    from javstory.search.library_search import HybridLibrarySearch, _SearchResult

    search = HybridLibrarySearch(weights=(0.3, 0.5, 0.2))
    fused = search._fuse_results(
        [
            [_SearchResult("A", "A title", "bm25"), _SearchResult("B", "B title", "bm25")],
            [_SearchResult("B", "B title", "embedding"), _SearchResult("A", "A title", "embedding")],
            [_SearchResult("C", "C title", "metadata")],
        ],
        (0.3, 0.5, 0.2),
    )

    assert fused[0][0].id == "B"
    assert fused[0][0].source == "bm25+embedding"
    assert fused[0][1] > fused[-1][1]


def test_hybrid_library_search_reads_weights_from_env(monkeypatch):
    from javstory.search.library_search import HybridLibrarySearch

    monkeypatch.setenv("JAVSTORY_HYBRID_SEARCH_WEIGHTS", "1,2,1")
    search = HybridLibrarySearch()

    assert search.weights == (0.25, 0.5, 0.25)


def test_hybrid_library_search_with_fusion_uses_all_rankers(monkeypatch):
    from javstory.search.library_search import HybridLibrarySearch, _LibraryDoc, _SearchResult

    docs = [
        _LibraryDoc("AAA-111", "마사지 작품", "마사지 긴장감", "마사지 배우"),
        _LibraryDoc("BBB-222", "배우 추천작", "다른 텍스트", "인기 배우"),
    ]
    search = HybridLibrarySearch(weights=(0.3, 0.5, 0.2))
    monkeypatch.setattr(search, "_load_docs", lambda: docs)
    monkeypatch.setattr(
        search,
        "_search_embedding",
        lambda query, docs, top_k: [_SearchResult("BBB-222", "배우 추천작", "embedding", 0.9)],
    )

    results = search.search_with_fusion("마사지 배우")

    assert results
    assert set(results[0]) == {"id", "title", "score", "source"}
    assert len(results) <= search.top_k


def test_hybrid_library_search_returns_configured_top_k(monkeypatch):
    from javstory.search.library_search import HybridLibrarySearch, _LibraryDoc, _SearchResult

    docs = [_LibraryDoc(f"TST-{idx:03d}", f"테스트 {idx}", "마사지", "배우") for idx in range(8)]
    search = HybridLibrarySearch(weights=(1.0, 0.0, 0.0), top_k=8)
    monkeypatch.setattr(search, "_load_docs", lambda: docs)
    monkeypatch.setattr(
        search,
        "_search_bm25",
        lambda query, docs, top_k: [
            _SearchResult(f"TST-{idx:03d}", f"테스트 {idx}", "bm25", 1.0)
            for idx in range(8)
        ],
    )
    monkeypatch.setattr(search, "_search_embedding", lambda query, docs, top_k: [])
    monkeypatch.setattr(search, "_search_metadata", lambda query, docs, top_k: [])

    results = search.search_with_fusion("마사지")

    assert len(results) == 8


def test_hybrid_library_search_skips_zero_weight_rankers(monkeypatch):
    from javstory.search.library_search import HybridLibrarySearch, _LibraryDoc

    docs = [_LibraryDoc("AAA-111", "마사지 작품", "마사지 긴장감", "마사지 배우")]
    search = HybridLibrarySearch(weights=(1.0, 0.0, 0.0), top_k=5)
    monkeypatch.setattr(search, "_load_docs", lambda: docs)
    monkeypatch.setattr(
        search,
        "_search_embedding",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("embedding ranker should be skipped")),
    )
    monkeypatch.setattr(
        search,
        "_search_metadata",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("metadata ranker should be skipped")),
    )

    results = search.search_with_fusion("마사지")

    assert results
    assert results[0]["id"] == "AAA-111"


def test_hybrid_results_adapter_matches_persona_schema():
    from javstory.persona.erotic_persona_engine import _adapt_hybrid_search_results

    adapted = _adapt_hybrid_search_results(
        "마사지 추천",
        [{"id": "TST-001", "title": "테스트 작품", "score": 0.012, "source": "bm25+metadata"}],
        product_codes=[],
        fallback_seed_codes=["HBAD-509"],
    )

    assert adapted["query"] == "마사지 추천"
    assert adapted["fallback_seed_codes"] == ["HBAD-509"]
    assert adapted["results"][0]["product_code"] == "TST-001"
    assert adapted["results"][0]["title_ko"] == "테스트 작품"
    assert adapted["results"][0]["hybrid_source"] == "bm25+metadata"
