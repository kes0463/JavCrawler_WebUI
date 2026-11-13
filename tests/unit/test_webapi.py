"""webapi smoke tests."""

from __future__ import annotations

import pytest


def test_webapi_import():
    from webapi.main import app

    assert app.title == "JAVSTORY WebAPI"


def test_webapi_health():
    from fastapi.testclient import TestClient
    from webapi.main import app

    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["api"] == "webapi"


def test_dashboard_summary_shape(monkeypatch):
    from fastapi.testclient import TestClient
    from webapi.main import app
    from javstory.services import dashboard_service

    class FakeDashboard:
        def summary(self):
            return {
                "library": {
                    "total": 10,
                    "with_metadata": 8,
                    "with_folder": 5,
                    "without_metadata": 2,
                },
                "watch": {
                    "total": 10,
                    "completed": 1,
                    "completion_rate": 0.1,
                    "avg_rating": 4.0,
                    "rated_count": 2,
                    "watched_count": 3,
                    "total_watch_hours": 1.5,
                },
                "pending_count": 2,
                "metadata_match_rate": 80.0,
            }

        def system_metrics(self):
            return {
                "gpu_name": "N/A",
                "gpu_usage_percent": 0,
                "gpu_total_gb": 0.0,
                "gpu_used_gb": 0.0,
                "cpu_percent": 10,
                "mem_percent": 50,
                "mem_used_gb": 8.0,
                "mem_total_gb": 16.0,
                "cpu_model": "Test CPU",
            }

    monkeypatch.setattr(dashboard_service, "DashboardService", FakeDashboard)
    import importlib
    import webapi.routes.dashboard as dash_mod

    importlib.reload(dash_mod)
    monkeypatch.setattr(dash_mod, "_dashboard", FakeDashboard())

    client = TestClient(app)
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["library"]["total"] == 10
    assert body["metadata_match_rate"] == 80.0


def test_foreign_origin_is_rejected_before_handler():
    from fastapi.testclient import TestClient
    from webapi.main import app

    client = TestClient(app)
    # 다른 사이트가 보낸 본문 없는 POST — 핸들러까지 가면 안 된다
    r = client.post("/api/playback/cache/clear", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert client.get("/health", headers={"Origin": "http://localhost:5173"}).status_code == 200
    assert client.get("/health").status_code == 200  # Origin 없는 요청(CLI 등)은 통과


def test_cover_upload_rejects_path_traversal_code(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import javstory.utils.image_handler as ih
    from webapi.main import app

    # 미디어 루트를 두 단계 아래에 둬서 `..\..\` 탈출이 tmp_path 안에 떨어지게 한다
    monkeypatch.setattr(ih, "E_MEDIA_ROOT", str(tmp_path / "a" / "media"))
    client = TestClient(app)
    r = client.post(
        "/api/library/..%5C..%5Cescaped/cover",
        files={"file": ("x.jpg", b"\xff\xd8\xff", "image/jpeg")},
    )
    assert r.status_code == 400
    assert not any(tmp_path.rglob("*.jpg"))
