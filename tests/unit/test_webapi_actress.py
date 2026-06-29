"""WebAPI actress routes smoke tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def actress_client(monkeypatch):
    from webapi.main import app

    class FakeSvc:
        def list_actresses(self, **kwargs):
            items = [{"id": 1, "name_ko": "테스트", "name_ja": "テスト", "work_count": 3}]
            return {"total": 1, "page": 1, "per_page": 48, "items": items}

        def get_profile(self, actress_id):
            if actress_id != 1:
                return None
            return {
                "id": 1,
                "name_ko": "테스트",
                "name_ja": "テスト",
                "name_en": "",
                "romaji": "",
                "profile_image_url": "",
                "genres": "",
                "user_score": 0,
                "profile_text": "",
                "birth_date": "",
                "height": 0,
                "bust": 0,
                "waist": 0,
                "hip": 0,
                "cup_size": "",
                "debut_date": "",
                "debut_date_raw": "",
                "agency": "",
                "is_favorite": False,
                "favorite_intensity": 0,
                "memo": "",
                "work_count": 3,
                "aliases": [],
                "gallery_images": [],
                "library_refresh_pcs": [],
            }

        def get_works_bundle(self, actress_id):
            return {"works": [], "genres": []}

        def resolve_id_by_name(self, name):
            return 1 if name == "테스트" else None

    monkeypatch.setattr("webapi.routes.actress._svc", FakeSvc())
    return TestClient(app)


def test_list_actresses(actress_client):
    r = actress_client.get("/api/actresses")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["name_ko"] == "테스트"


def test_get_actress_profile(actress_client):
    r = actress_client.get("/api/actresses/1")
    assert r.status_code == 200
    assert r.json()["id"] == 1


def test_resolve_actress(actress_client):
    r = actress_client.get("/api/actresses/resolve", params={"name": "테스트"})
    assert r.status_code == 200
    assert r.json()["actress_id"] == 1
