"""Library hybrid/keyword search service helpers."""

from __future__ import annotations

from javstory.services.library_service import LibraryService


def test_looks_like_natural_language():
    assert LibraryService._looks_like_natural_language("비 오는 날 실외") is True
    assert LibraryService._looks_like_natural_language("마사지받는장면") is True
    assert LibraryService._looks_like_natural_language("DLDSS-493") is False
    assert LibraryService._looks_like_natural_language("ssis-001") is False
    assert LibraryService._looks_like_natural_language("") is False


def test_search_items_keyword_path(monkeypatch):
    svc = LibraryService()
    called = {}

    def fake_list(**kwargs):
        called.update(kwargs)
        return {"total": 0, "page": 1, "per_page": 40, "items": []}

    monkeypatch.setattr(svc, "list_items", fake_list)
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_ENABLED", "0")

    out = svc.search_items(q="DLDSS-493", mode="auto", page=1, per_page=40)
    assert out["mode"] == "keyword"
    assert called.get("q") == "DLDSS-493"
    assert out["embedding_channel_used"] is False


def test_search_items_hybrid_hydrates_order(monkeypatch):
    from types import SimpleNamespace

    svc = LibraryService()
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_ENABLED", "0")

    class FakeSearch:
        def __init__(self, *a, **k):
            pass

        def search_with_fusion(self, query):
            return [
                {"id": "BBB-002", "title": "B", "score": 0.9, "source": "bm25"},
                {"id": "AAA-001", "title": "A", "score": 0.8, "source": "bm25+metadata"},
            ]

    monkeypatch.setattr(
        "javstory.search.library_search.HybridLibrarySearch",
        FakeSearch,
    )

    rows = [
        SimpleNamespace(product_code="AAA-001", title_ko="A"),
        SimpleNamespace(product_code="BBB-002", title_ko="B"),
    ]

    class FakeQuery:
        def filter(self, *a, **k):
            return self

        def outerjoin(self, *a, **k):
            return self

        def all(self):
            return rows

    class FakeSession:
        def query(self, *a, **k):
            return FakeQuery()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        "javstory.services.library_service.get_db_session_ctx",
        lambda: FakeSession(),
    )
    monkeypatch.setattr(
        "javstory.services.library_service.apply_genre_filters",
        lambda query, genres, mode="and": query,
    )
    monkeypatch.setattr(
        "javstory.services.library_service._default_list_filter",
        lambda: True,
    )

    out = svc.search_items(q="비 오는 날", mode="hybrid", page=1, per_page=40)
    assert out["mode"] == "hybrid"
    assert [r.product_code for r in out["items"]] == ["BBB-002", "AAA-001"]
    assert out["hit_meta"]["BBB-002"]["score"] == 0.9
