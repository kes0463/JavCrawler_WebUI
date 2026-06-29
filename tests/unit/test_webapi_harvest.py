"""webapi harvest route tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def harvest_client(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from webapi.main import app
    from javstory.services import harvest_queue_service

    class FakeQueue:
        def __init__(self):
            self._items = []
            self._running = False
            self._grok = False

        def snapshot(self):
            return {
                "items": self._items,
                "running": self._running,
                "grok_enabled": self._grok,
            }

        def add_codes(self, codes, *, auto_start=False, force_rebuild=False):
            for c in codes:
                self._items.append(
                    {
                        "id": f"id-{c}",
                        "target": c,
                        "product_code": c,
                        "status": "pending",
                        "progress": 0,
                        "message": "대기",
                        "kind": "code",
                        "is_path": False,
                        "force_rebuild": force_rebuild,
                        "staged": False,
                    }
                )
            return self.snapshot()

        async def start(self):
            self._running = True
            return len(self._items)

        def set_grok_enabled(self, v):
            self._grok = v

        def clear_finished(self):
            before = len(self._items)
            self._items = [i for i in self._items if i["status"] not in ("done", "error")]
            return before - len(self._items)

        def recrawl_codes(self, codes, *, force=True):
            added = 0
            running = 0
            for c in codes:
                cu = c.strip().upper()
                if any(i["product_code"] == cu and i["status"] == "running" for i in self._items):
                    running += 1
                    continue
                self._items = [
                    i for i in self._items
                    if not (i["product_code"] == cu and i["status"] != "running")
                ]
                self._items.append(
                    {
                        "id": f"id-{cu}",
                        "target": cu,
                        "product_code": cu,
                        "status": "pending",
                        "progress": 0,
                        "message": "재크롤",
                        "kind": "code",
                        "is_path": False,
                        "force_rebuild": force,
                        "staged": False,
                    }
                )
                added += 1
            snap = self.snapshot()
            snap["planned"] = added
            snap["recrawl_running"] = running
            return snap

        async def ensure_running(self):
            if not self._running:
                self._running = True
            return len(self._items)

        def persist_queue(self):
            pass

        def load_persisted(self):
            pass

    fake = FakeQueue()
    monkeypatch.setattr(harvest_queue_service, "harvest_queue", fake)
    import importlib
    import webapi.routes.harvest as harvest_mod

    importlib.reload(harvest_mod)
    monkeypatch.setattr(harvest_mod, "harvest_queue", fake)

    return TestClient(app), fake


def test_harvest_queue_get(harvest_client):
    client, fake = harvest_client
    fake.add_codes(["STARS-001"])
    r = client.get("/api/harvest/queue")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1
    assert body["grok_enabled"] is False


def test_harvest_add_auto_start(harvest_client):
    client, fake = harvest_client
    r = client.post("/api/harvest/add", json={"codes": ["IPX-001"], "auto_start": True})
    assert r.status_code == 200
    assert fake._running is True


def test_harvest_settings_patch(harvest_client):
    client, _ = harvest_client
    r = client.patch("/api/harvest/settings", json={"grok_enabled": False})
    assert r.status_code == 200
    assert r.json()["grok_enabled"] is False


def test_harvest_clear_finished(harvest_client):
    client, fake = harvest_client
    fake._items.append(
        {
            "id": "x",
            "target": "A",
            "product_code": "A",
            "status": "done",
            "progress": 100,
            "message": "",
            "kind": "code",
            "is_path": False,
            "force_rebuild": False,
            "staged": False,
        }
    )
    r = client.post("/api/harvest/clear-finished")
    assert r.status_code == 200
    assert r.json()["removed"] == 1


def test_harvest_recrawl(harvest_client):
    client, fake = harvest_client
    fake._items.append(
        {
            "id": "old",
            "target": "STARS-001",
            "product_code": "STARS-001",
            "status": "done",
            "progress": 100,
            "message": "",
            "kind": "code",
            "is_path": False,
            "force_rebuild": False,
            "staged": False,
        }
    )
    r = client.post("/api/harvest/recrawl", json={"codes": ["STARS-001"], "force": True})
    assert r.status_code == 200
    body = r.json()
    assert body["running"] is True
    assert any(i["product_code"] == "STARS-001" and i["status"] == "pending" for i in body["items"])
    assert body["items"][0]["force_rebuild"] is True
