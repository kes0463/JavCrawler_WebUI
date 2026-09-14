"""Library hybrid/keyword search service helpers."""

from __future__ import annotations

from types import SimpleNamespace

from javstory.services.library_service import LibraryService


def test_looks_like_natural_language():
    assert LibraryService._looks_like_natural_language("비 오는 날 실외") is True
    assert LibraryService._looks_like_natural_language("마사지받는장면") is True
    assert LibraryService._looks_like_natural_language("간호사") is True
    assert LibraryService._looks_like_natural_language("메이드") is True
    assert LibraryService._looks_like_natural_language("비서") is True
    assert LibraryService._looks_like_natural_language("office") is True
    assert LibraryService._looks_like_natural_language("DLDSS-493") is False
    assert LibraryService._looks_like_natural_language("ssis-001") is False
    assert LibraryService._looks_like_natural_language("") is False


def test_should_union_keyword():
    assert LibraryService._should_union_keyword("DLDSS-493") is True
    assert LibraryService._should_union_keyword("미카미") is True
    assert LibraryService._should_union_keyword("office") is False
    assert LibraryService._should_union_keyword("비 오는 날") is False
    assert LibraryService._should_union_keyword("마사지받는장면") is False
    assert LibraryService._should_union_keyword("간호사") is False


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
    svc = LibraryService()
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_ENABLED", "1")

    class FakeSearch:
        last_embedding_diag = {
            "status": "ok",
            "scored_n": 2,
            "returned_n": 2,
            "embedding_n": 2,
            "bm25_n": 0,
            "union_n": 2,
        }

        def __init__(self, *a, **k):
            pass

        def search_embedding_union_bm25(self, query, **kwargs):
            return [
                {"id": "BBB-002", "title": "B", "score": 0.9, "source": "embedding"},
                {"id": "AAA-001", "title": "A", "score": 0.8, "source": "embedding"},
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
        def __init__(self, *, codes_only=False):
            self._codes_only = codes_only

        def filter(self, *a, **k):
            return self

        def outerjoin(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def all(self):
            if self._codes_only:
                return [(r.product_code,) for r in rows]
            return rows

    class FakeSession:
        def query(self, *entities, **k):
            from javstory.harvest.database import JAVMetadata

            codes_only = len(entities) == 1 and entities[0] is JAVMetadata.product_code
            return FakeQuery(codes_only=codes_only)

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

    out = svc.search_items(q="비 오는 날", mode="hybrid", page=1, per_page=40, sort="similarity")
    assert out["mode"] == "hybrid"
    assert out["embedding_channel_used"] is True
    assert [r.product_code for r in out["items"]] == ["BBB-002", "AAA-001"]
    assert out["hit_meta"]["BBB-002"]["score"] == 0.9
    assert out["hit_meta"]["BBB-002"]["source"] == "embedding"


def test_search_items_hybrid_falls_back_to_keyword(monkeypatch):
    svc = LibraryService()
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_ENABLED", "1")

    class FakeSearch:
        last_embedding_diag = {
            "status": "ok",
            "scored_n": 3,
            "returned_n": 0,
            "embedding_n": 0,
            "bm25_n": 0,
            "union_n": 0,
        }

        def __init__(self, *a, **k):
            pass

        def search_embedding_union_bm25(self, query, **kwargs):
            return []

    monkeypatch.setattr(
        "javstory.search.library_search.HybridLibrarySearch",
        FakeSearch,
    )

    def fake_list(**kwargs):
        return {
            "total": 1,
            "page": 1,
            "per_page": 40,
            "items": [SimpleNamespace(product_code="KW-001", title_ko="키워드")],
        }

    monkeypatch.setattr(svc, "list_items", fake_list)

    rows = [SimpleNamespace(product_code="KW-001", title_ko="키워드")]

    class FakeQuery:
        def __init__(self, *, codes_only=False):
            self._codes_only = codes_only

        def filter(self, *a, **k):
            return self

        def outerjoin(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def all(self):
            if self._codes_only:
                return [(r.product_code,) for r in rows]
            return rows

    class FakeSession:
        def query(self, *entities, **k):
            from javstory.harvest.database import JAVMetadata

            codes_only = len(entities) == 1 and entities[0] is JAVMetadata.product_code
            return FakeQuery(codes_only=codes_only)

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

    out = svc.search_items(q="비 오는 날", mode="hybrid", page=1, per_page=40, sort="similarity")
    assert out["mode"] == "hybrid"
    assert out["embedding_channel_used"] is False
    assert out["hit_meta"]["KW-001"]["source"] == "keyword"
    assert "키워드 검색으로 대체" in (out["search_message"] or "")
    assert out["search_message_kind"] == "low_similarity"
    assert [r.product_code for r in out["items"]] == ["KW-001"]


def test_search_items_hybrid_product_code_unions_keyword_first(monkeypatch):
    svc = LibraryService()
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_ENABLED", "1")

    class FakeSearch:
        last_embedding_diag = {
            "status": "ok",
            "scored_n": 1,
            "returned_n": 1,
            "embedding_n": 1,
            "bm25_n": 0,
            "union_n": 1,
        }

        def __init__(self, *a, **k):
            pass

        def search_embedding_union_bm25(self, query, **kwargs):
            return [
                {"id": "OTH-999", "title": "다른", "score": 0.7, "source": "embedding"},
            ]

    monkeypatch.setattr(
        "javstory.search.library_search.HybridLibrarySearch",
        FakeSearch,
    )

    def fake_list(**kwargs):
        return {
            "total": 1,
            "page": 1,
            "per_page": 40,
            "items": [SimpleNamespace(product_code="DLDSS-493", title_ko="정확")],
        }

    monkeypatch.setattr(svc, "list_items", fake_list)

    rows = [
        SimpleNamespace(product_code="DLDSS-493", title_ko="정확"),
        SimpleNamespace(product_code="OTH-999", title_ko="다른"),
    ]

    class FakeQuery:
        def __init__(self, *, codes_only=False):
            self._codes_only = codes_only

        def filter(self, *a, **k):
            return self

        def outerjoin(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def all(self):
            if self._codes_only:
                return [(r.product_code,) for r in rows]
            return rows

    class FakeSession:
        def query(self, *entities, **k):
            from javstory.harvest.database import JAVMetadata

            codes_only = len(entities) == 1 and entities[0] is JAVMetadata.product_code
            return FakeQuery(codes_only=codes_only)

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

    out = svc.search_items(q="DLDSS-493", mode="hybrid", page=1, per_page=40, sort="similarity")
    assert out["mode"] == "hybrid"
    assert out["embedding_channel_used"] is True
    assert [r.product_code for r in out["items"]] == ["DLDSS-493", "OTH-999"]
    assert out["hit_meta"]["DLDSS-493"]["source"] == "keyword"
    assert out["hit_meta"]["OTH-999"]["source"] == "embedding"


def test_search_items_auto_short_concept_uses_hybrid(monkeypatch):
    svc = LibraryService()
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_ENABLED", "1")
    called = {"hybrid": False, "list": False}

    class FakeSearch:
        last_embedding_diag = {
            "status": "ok",
            "scored_n": 1,
            "returned_n": 1,
            "embedding_n": 1,
            "bm25_n": 0,
            "union_n": 1,
        }

        def __init__(self, *a, **k):
            pass

        def search_embedding_union_bm25(self, query, **kwargs):
            called["hybrid"] = True
            return [
                {"id": "NRS-001", "title": "간호사", "score": 0.7, "source": "embedding"},
            ]

    monkeypatch.setattr(
        "javstory.search.library_search.HybridLibrarySearch",
        FakeSearch,
    )

    def fake_list(**kwargs):
        called["list"] = True
        return {"total": 0, "page": 1, "per_page": 40, "items": []}

    monkeypatch.setattr(svc, "list_items", fake_list)

    rows = [SimpleNamespace(product_code="NRS-001", title_ko="간호사")]

    class FakeQuery:
        def __init__(self, *, codes_only=False):
            self._codes_only = codes_only

        def filter(self, *a, **k):
            return self

        def outerjoin(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def all(self):
            if self._codes_only:
                return [(r.product_code,) for r in rows]
            return rows

    class FakeSession:
        def query(self, *entities, **k):
            from javstory.harvest.database import JAVMetadata

            codes_only = len(entities) == 1 and entities[0] is JAVMetadata.product_code
            return FakeQuery(codes_only=codes_only)

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

    out = svc.search_items(q="간호사", mode="auto", page=1, per_page=40, sort="similarity")
    assert called["hybrid"] is True
    assert called["list"] is False
    assert out["mode"] == "hybrid"
    assert out["embedding_channel_used"] is True
    assert [r.product_code for r in out["items"]] == ["NRS-001"]


def test_search_items_connection_error_kind(monkeypatch):
    svc = LibraryService()
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_ENABLED", "1")

    class FakeSearch:
        last_embedding_diag = {
            "status": "query_failed",
            "error": "ConnectError: refused",
            "backend": "llamacpp",
            "scored_n": 0,
            "embedding_n": 0,
            "union_n": 0,
        }

        def __init__(self, *a, **k):
            pass

        def search_embedding_union_bm25(self, query, **kwargs):
            return []

    monkeypatch.setattr(
        "javstory.search.library_search.HybridLibrarySearch",
        FakeSearch,
    )
    monkeypatch.setattr(
        svc,
        "list_items",
        lambda **kwargs: {"total": 0, "page": 1, "per_page": 40, "items": []},
    )

    out = svc.search_items(q="비 오는 날", mode="hybrid", page=1, per_page=40, sort="similarity")
    assert out["mode"] == "hybrid"
    assert out["total"] == 0
    assert out["search_message_kind"] == "connection_error"
    assert "연결할 수 없습니다" in (out["search_message"] or "")
