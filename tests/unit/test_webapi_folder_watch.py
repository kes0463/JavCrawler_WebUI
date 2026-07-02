"""webapi folder-watch route tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def folder_watch_client(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from javstory.folder_watch import inbox as inbox_mod
    from javstory.folder_watch import paused as paused_mod
    from javstory.folder_watch.service import FolderWatchBackgroundService
    from webapi.routes import folder_watch as fw_mod

    monkeypatch.setattr(inbox_mod, "_INBOX_PATH", tmp_path / "inbox.json")
    monkeypatch.setattr(paused_mod, "_PAUSED_FILE", tmp_path / "paused.json")
    paused_mod.invalidate_cache()

    svc = FolderWatchBackgroundService()
    monkeypatch.setattr(fw_mod, "_svc", svc)

    app = FastAPI()
    app.include_router(fw_mod.router, prefix="/api/folder-watch")
    return TestClient(app), svc


def test_inbox_pause_resume_flow(folder_watch_client) -> None:
    client, svc = folder_watch_client
    from javstory.folder_watch.inbox import upsert_inbox_item

    upsert_inbox_item("TST-001", r"D:\old", [r"E:\new"])
    svc.notify_change()

    res = client.get("/api/folder-watch/inbox")
    assert res.status_code == 200
    body = res.json()
    assert body["revision"] >= 1
    assert len(body["items"]) == 1
    assert body["items"][0]["product_code"] == "TST-001"
    assert body["items"][0]["monitoring_paused"] is False

    res = client.post("/api/folder-watch/pause/TST-001")
    assert res.status_code == 200
    assert res.json()["items"][0]["monitoring_paused"] is True

    res = client.post("/api/folder-watch/resume/TST-001")
    assert res.status_code == 200
    assert res.json()["items"][0]["monitoring_paused"] is False


def test_inbox_remove_and_clear(folder_watch_client) -> None:
    client, svc = folder_watch_client
    from javstory.folder_watch.inbox import upsert_inbox_item

    upsert_inbox_item("A-001", "/a", [])
    upsert_inbox_item("B-002", "/b", [])
    svc.notify_change()

    res = client.delete("/api/folder-watch/inbox/A-001")
    assert res.status_code == 200
    assert len(res.json()["items"]) == 1

    res = client.post("/api/folder-watch/inbox/clear")
    assert res.status_code == 200
    assert res.json()["items"] == []


def test_candidates_refresh_updates_inbox(folder_watch_client, monkeypatch) -> None:
    client, _svc = folder_watch_client
    from javstory.folder_watch.inbox import upsert_inbox_item

    upsert_inbox_item("SRC-001", r"D:\old", [])
    monkeypatch.setattr(
        "webapi.routes.folder_watch.search_folder_candidates",
        lambda *_a, **_k: [r"E:\SRC-001"],
    )

    res = client.post(
        "/api/folder-watch/candidates/refresh",
        json={"product_code": "SRC-001", "old_path": r"D:\old"},
    )
    assert res.status_code == 200
    item = res.json()["items"][0]
    assert item["candidates"] == [r"E:\SRC-001"]
