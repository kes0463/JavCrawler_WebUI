"""metadata_edit 및 library update 단위 테스트."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from javstory.library.metadata_edit import (
    HARVEST_FAILED_TITLE_MARKER,
    apply_library_metadata_fields,
    harvest_merge_empty_only,
    is_metadata_manual_protected,
    mark_metadata_as_manual,
)


def test_apply_library_metadata_fields_sets_legacy_columns() -> None:
    row = SimpleNamespace(
        title_ko=None,
        title=None,
        title_ja=None,
        original_title=None,
        synopsis_ko=None,
        synopsis=None,
        actors_ko=None,
        actors=None,
        genres_ko=None,
        genres=None,
        maker_ko=None,
        maker=None,
    )
    apply_library_metadata_fields(
        row,
        {
            "title_ko": "한국 제목",
            "title_ja": "日本語",
            "synopsis_ko": "요약",
            "actors_ko": "배우A",
            "genres_ko": "장르A",
            "maker_ko": "제작사",
        },
    )
    assert row.title_ko == "한국 제목"
    assert row.title == "한국 제목"
    assert row.title_ja == "日本語"
    assert row.original_title == "日本語"
    assert row.synopsis == "요약"
    assert row.actors == "배우A"
    assert row.genres == "장르A"
    assert row.maker == "제작사"


def test_mark_metadata_as_manual_clears_failed_placeholder() -> None:
    row = SimpleNamespace(
        metadata_manual=False,
        analysis_status="FAILED_CRAWL",
        product_code="ABC-123",
        title_ko=f"[ABC-123] {HARVEST_FAILED_TITLE_MARKER}",
        title=f"[ABC-123] {HARVEST_FAILED_TITLE_MARKER}",
        title_ja="日本語タイトル",
    )
    mark_metadata_as_manual(row)
    assert row.metadata_manual is True
    assert row.analysis_status == "MANUAL"
    assert row.title_ko is None
    assert row.title is None


def test_is_metadata_manual_protected() -> None:
    assert is_metadata_manual_protected(None) is False
    assert is_metadata_manual_protected(SimpleNamespace(metadata_manual=False)) is False
    assert is_metadata_manual_protected(SimpleNamespace(metadata_manual=True)) is True


def test_harvest_merge_empty_only() -> None:
    manual = SimpleNamespace(metadata_manual=True)
    assert harvest_merge_empty_only(manual, force_rebuild=True) is True
    assert harvest_merge_empty_only(manual, force_rebuild=False) is True
    assert harvest_merge_empty_only(None, force_rebuild=True) is False
    assert harvest_merge_empty_only(None, force_rebuild=False) is True


def test_upsert_preserves_manual_fields_on_force_rebuild_empty() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from javstory.harvest.database import Base, JAVMetadata, upsert_jav_metadata

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(
        JAVMetadata(
            product_code="TST-001",
            metadata_manual=True,
            actors_ko="수동 배우",
            actors_ja="手動女優",
            title_ko="수동 제목",
        )
    )
    session.commit()

    upsert_jav_metadata(
        session,
        "TST-001",
        merge_empty_only=False,
        actors_ko="",
        actors_ja="",
        actors_romaji="",
        title_ko="",
        title_ja="",
    )
    session.commit()
    row = session.query(JAVMetadata).filter_by(product_code="TST-001").one()
    assert row.actors_ko == "수동 배우"
    assert row.actors_ja == "手動女優"
    assert row.title_ko == "수동 제목"


def test_coordinator_preserves_manual_metadata_on_crawl_fail(monkeypatch) -> None:
    from javstory.harvest import coordinator

    class FakeRow:
        metadata_manual = True
        folder_path = "/tmp/fake"
        title_ja = "ja"
        synopsis_ja = "syn"
        cover_image_url = "http://example.com/c.jpg"
        title_ko = "수동 제목"
        synopsis_ko = "수동 요약"
        analysis_status = "MANUAL"
        maker_ja = ""
        actors_ja = ""
        genres_ja = ""
        release_date = ""
        original_title = ""
        favorite_score = 0
        favorite_sources = None

    class FakeSession:
        def query(self, _model):
            return self

        def filter_by(self, **kwargs):
            return self

        def first(self):
            return FakeRow()

    class FakeCtx:
        def __enter__(self):
            return FakeSession()

        def __exit__(self, *args):
            return False

    upsert_called = {"count": 0}

    def fake_upsert(*args, **kwargs):
        upsert_called["count"] += 1
        return SimpleNamespace()

    class FakeCrawler:
        async def fetch_metadata_smart(self, code):
            return None

    monkeypatch.setattr(coordinator, "get_db_session_ctx", lambda: FakeCtx())
    monkeypatch.setattr(coordinator, "upsert_jav_metadata", fake_upsert)
    monkeypatch.setattr(coordinator, "commit_with_retry", lambda _s: None)
    monkeypatch.setattr(coordinator, "HybridJavCrawler", lambda: FakeCrawler())
    monkeypatch.setattr(coordinator, "ActressResolver", lambda: SimpleNamespace(resolve_names=lambda x: {"ja": [], "ko": [], "romaji": []}))
    monkeypatch.setattr(coordinator, "MetadataAssetsHandler", lambda: SimpleNamespace())
    monkeypatch.setattr(coordinator, "MetadataTranslator", lambda **kwargs: SimpleNamespace())

    async def _run():
        return await coordinator.run_crawler_for_video_path(
            "ABC-123",
            force_rebuild_story_context=True,
        )

    result = asyncio.run(_run())
    assert result.get("manual_metadata_preserved") is True
    assert upsert_called["count"] == 0


def test_coordinator_preserves_manual_actors_on_successful_empty_crawl(monkeypatch) -> None:
    from javstory.harvest import coordinator

    class FakeRow:
        metadata_manual = True
        folder_path = "/tmp/fake"
        title_ja = "ja"
        synopsis_ja = "syn"
        cover_image_url = "http://example.com/c.jpg"
        title_ko = "수동 제목"
        synopsis_ko = "수동 요약"
        analysis_status = "MANUAL"
        maker_ja = ""
        actors_ja = "手動女優"
        actors_ko = "수동 배우"
        genres_ja = ""
        release_date = ""
        original_title = ""
        favorite_score = 0
        favorite_sources = None

    class FakeSession:
        def query(self, _model):
            return self

        def filter_by(self, **kwargs):
            return self

        def first(self):
            return FakeRow()

    class FakeCtx:
        def __enter__(self):
            return FakeSession()

        def __exit__(self, *args):
            return False

    captured: dict = {}

    def fake_upsert(session, product_code, merge_empty_only=False, **kwargs):
        captured["merge_empty_only"] = merge_empty_only
        captured["actors_ko"] = kwargs.get("actors_ko")
        return SimpleNamespace(id=1)

    class FakeCrawler:
        async def fetch_metadata_smart(self, code):
            return {
                "title": "크롤 제목",
                "synopsis": "크롤 시놉",
                "actors": [],
                "genres": [],
                "maker": "",
                "cover_url": "http://example.com/new.jpg",
            }

    class FakeResolver:
        def resolve_names(self, names):
            return {"ja": [], "ko": [], "romaji": [], "zh_cn": [], "zh_tw": []}

    class FakeTranslator:
        async def translate_metadata_batch(self, *args, **kwargs):
            return {
                "title_ko": "번역 제목",
                "synopsis_ko": "번역 시놉",
                "title_ja": "ja",
                "synopsis_ja": "syn",
            }

    class FakeAssets:
        async def download_cover_image(self, *args, **kwargs):
            return None

    monkeypatch.setattr(coordinator, "get_db_session_ctx", lambda: FakeCtx())
    monkeypatch.setattr(coordinator, "upsert_jav_metadata", fake_upsert)
    monkeypatch.setattr(coordinator, "commit_with_retry", lambda _s: None)
    monkeypatch.setattr(coordinator, "HybridJavCrawler", lambda: FakeCrawler())
    monkeypatch.setattr(coordinator, "ActressResolver", lambda: FakeResolver())
    monkeypatch.setattr(coordinator, "MetadataAssetsHandler", lambda: FakeAssets())
    monkeypatch.setattr(coordinator, "MetadataTranslator", lambda **kwargs: FakeTranslator())
    monkeypatch.setattr(
        coordinator,
        "_resolve_genres",
        lambda g: {"ja": [], "ko": [], "en": [], "zh_cn": [], "zh_tw": []},
    )
    monkeypatch.setattr(
        coordinator,
        "_resolve_maker",
        lambda m: {"ja": "", "ko": "", "en": "", "zh_cn": "", "zh_tw": ""},
    )
    monkeypatch.setattr(
        "javstory.utils.actress_resolver.dedupe_crawled_actor_names",
        lambda _s, names: names,
    )
    monkeypatch.setattr(coordinator, "_harvest_should_run_story_context", lambda *a, **k: False)
    monkeypatch.setattr(
        "javstory.harvest.product_repository.sync_product_from_metadata_row",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "javstory.utils.actress_profile.sync_actress_works_for_product",
        lambda *a, **k: 0,
    )

    async def _run():
        return await coordinator.run_crawler_for_video_path(
            "TST-001",
            force_rebuild_story_context=True,
            skip_media=True,
        )

    result = asyncio.run(_run())
    assert "error" not in result
    assert captured.get("merge_empty_only") is True
    assert captured.get("actors_ko") == ""
