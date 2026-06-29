"""Unit tests for harvest_queue_service."""

from __future__ import annotations

import asyncio

import pytest

from javstory.services.harvest_queue_service import HarvestQueueService


@pytest.fixture
def queue_svc():
    svc = HarvestQueueService()
    events: list[dict] = []

    async def capture(ev: dict):
        events.append(ev)

    svc.set_broadcast(capture)
    loop = asyncio.new_event_loop()
    svc.set_main_loop(loop)
    svc._executor.shutdown(wait=False)
    svc._executor = __import__("concurrent.futures").futures.ThreadPoolExecutor(max_workers=1)
    yield svc, events
    loop.close()


def test_add_codes_and_snapshot(queue_svc, monkeypatch):
    svc, _ = queue_svc
    monkeypatch.setattr("javstory.harvest.database.assert_db_writable", lambda *_: None)

    snap = svc.add_codes(["STARS-001", "IPX-002"])
    assert len(snap["items"]) == 2
    assert snap["items"][0]["status"] == "pending"
    assert snap["grok_enabled"] is not None


def test_staged_not_started_by_default(queue_svc, monkeypatch):
    svc, _ = queue_svc
    monkeypatch.setattr("javstory.harvest.database.assert_db_writable", lambda *_: None)

    item = svc._new_item(
        target="D:\\video.mp4",
        product_code="STARS-001",
        kind="video_path",
        is_path=True,
        staged=True,
    )
    svc._queue.append(item)

    with pytest.raises(RuntimeError, match="empty"):
        asyncio.run(svc.start())


def test_process_item_done(queue_svc, monkeypatch):
    svc, events = queue_svc
    monkeypatch.setattr("javstory.harvest.database.assert_db_writable", lambda *_: None)
    monkeypatch.setattr(
        "javstory.services.harvest_queue_service.run_one_sync",
        lambda *_a, **_kw: {"ok": True, "message": "완료"},
    )

    async def noop_alert(_sku):
        return None

    monkeypatch.setattr(svc, "_maybe_harvest_alert", noop_alert)

    item = svc._new_item(target="STARS-001", product_code="STARS-001")
    svc._queue.append(item)
    asyncio.run(svc._process_item(item))

    assert item.status == "done"
    assert item.progress == 100
    done_events = [e for e in events if e.get("type") == "item_done"]
    assert done_events
    assert done_events[0].get("message") == "완료"
    assert done_events[0].get("progress") == 100


def test_clear_finished(queue_svc, monkeypatch):
    svc, _ = queue_svc
    monkeypatch.setattr("javstory.harvest.database.assert_db_writable", lambda *_: None)

    done = svc._new_item(target="A", product_code="A")
    done.status = "done"
    pending = svc._new_item(target="B", product_code="B")
    svc._queue = [done, pending]

    removed = svc.clear_finished()
    assert removed == 1
    assert len(svc._queue) == 1
    assert svc._queue[0].target == "B"


def test_set_grok_enabled(queue_svc):
    svc, _ = queue_svc
    svc.set_grok_enabled(False)
    assert svc.grok_enabled is False


def test_recrawl_replaces_done_item(queue_svc, monkeypatch):
    svc, _ = queue_svc
    monkeypatch.setattr("javstory.harvest.database.assert_db_writable", lambda *_: None)

    done = svc._new_item(target="STARS-001", product_code="STARS-001")
    done.status = "done"
    svc._queue = [done]

    snap = svc.recrawl_codes(["STARS-001"], force=True)
    assert snap["planned"] == 1
    assert len(svc._queue) == 1
    assert svc._queue[0].status == "pending"
    assert svc._queue[0].force_rebuild is True


def test_recrawl_skips_invalid_code(queue_svc, monkeypatch):
    svc, _ = queue_svc
    monkeypatch.setattr("javstory.harvest.database.assert_db_writable", lambda *_: None)

    snap = svc.recrawl_codes(["B"], force=True)
    assert snap["planned"] == 0
    assert snap.get("recrawl_running", 0) == 0
