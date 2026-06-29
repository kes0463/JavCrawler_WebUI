"""WebAPI library PATCH route smoke test."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from webapi.routes import library as library_mod


@pytest.fixture
def library_client(monkeypatch):

    class FakeSvc:
        def get_by_code(self, code):
            if code.upper() != "TST-001":
                return None
            return type(
                "Row",
                (),
                {
                    "id": 1,
                    "product_code": "TST-001",
                    "title_ko": "테스트",
                    "title_ja": "テスト",
                    "actors_ko": "배우",
                    "actors_ja": None,
                    "genres_ko": "장르",
                    "genres_ja": None,
                    "maker_ko": "제작",
                    "cover_image_local_path": None,
                    "thumb_image_local_path": None,
                    "release_date": "2024-01-01",
                    "folder_path": None,
                    "is_hardcoded": False,
                    "is_mopa": False,
                    "analysis_status": "MANUAL",
                    "metadata_manual": True,
                    "updated_at": None,
                    "favorite_score": 0,
                    "synopsis_ko": "요약",
                    "synopsis_ja": None,
                    "synopsis_en": None,
                    "title_en": None,
                    "title_zh_cn": None,
                    "actors_romaji": None,
                    "actors_en": None,
                    "actors_zh_cn": None,
                    "genres_en": None,
                    "maker_ja": None,
                    "maker_en": None,
                    "cover_image_url": None,
                    "created_at": None,
                },
            )()

        def scene_count_for(self, _code):
            return 0

        def scene_counts_for(self, codes, _flags_map=None):
            return {c: 0 for c in codes}

        def list_items(self, **_kwargs):
            return {"total": 0, "page": 1, "per_page": 40, "items": []}

        def grok_scenes_for(self, _code):
            return []

        def canonical_scenes_for(self, _code):
            return []

        def canonical_summary_for(self, _code):
            return ""

        def media_flags_for(self, _row, _cache=None):
            return {
                "has_subtitle": False,
                "has_hardcoded_subtitle": False,
                "has_mosaic_removed": False,
                "has_preview": False,
                "preview_media": None,
            }

        def snapshot_count_for(self, _code):
            return 0

        def load_file_flags_for(self, _codes):
            return {}

        def update_item(self, code, data):
            row = self.get_by_code(code)
            if not row:
                return None
            for k, v in data.items():
                setattr(row, k, v)
            return row

    monkeypatch.setattr(library_mod, "_library", FakeSvc())
    app = FastAPI()
    app.include_router(library_mod.router, prefix="/api/library")
    return TestClient(app)


def test_patch_library_item(library_client):
    r = library_client.patch(
        "/api/library/TST-001",
        json={"title_ko": "수정 제목", "actors_ko": "새배우"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["title_ko"] == "수정 제목"
    assert body["actors_ko"] == "새배우"
    assert body["metadata_manual"] is True


def test_patch_library_item_not_found(library_client):
    r = library_client.patch("/api/library/NOPE-999", json={"title_ko": "x"})
    assert r.status_code == 404


def test_list_library_uses_batch_scene_counts(library_client, monkeypatch):
    row = SimpleNamespace(
        id=1,
        product_code="TST-002",
        title_ko="t",
        title_ja=None,
        actors_ko=None,
        actors_ja=None,
        genres_ko=None,
        maker_ko=None,
        cover_image_local_path=None,
        release_date=None,
        folder_path=None,
        is_hardcoded=False,
        is_mopa=False,
        analysis_status=None,
        metadata_manual=False,
        updated_at=None,
        favorite_score=0,
    )
    batch_calls: list[list[str]] = []

    class BatchSvc:
        def list_items(self, **_kwargs):
            return {"total": 1, "page": 1, "per_page": 40, "items": [row]}

        def load_file_flags_for(self, codes):
            return {c: {"has_story": 0} for c in codes}

        def scene_counts_for(self, codes, flags_map=None):
            batch_calls.append(list(codes))
            return {c: 0 for c in codes}

        def media_flags_for(self, _row, _cache=None):
            return {
                "has_subtitle": False,
                "has_hardcoded_subtitle": False,
                "has_mosaic_removed": False,
                "has_preview": False,
                "preview_media": None,
            }

    monkeypatch.setattr(library_mod, "_library", BatchSvc())
    r = library_client.get("/api/library?per_page=40")
    assert r.status_code == 200
    assert batch_calls == [["TST-002"]]
    assert r.json()["items"][0]["scene_count"] == 0
