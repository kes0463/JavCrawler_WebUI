"""ProcessingQueueService unit tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from javstory.services.processing_execution_service import SttJobResult, SubtitleJobResult
from javstory.services.processing_queue_service import ProcessingQueueService


@pytest.fixture
def svc() -> ProcessingQueueService:
    return ProcessingQueueService()


@pytest.fixture
def video_file(tmp_path: Path) -> Path:
    p = tmp_path / "ABF-364 sample.mp4"
    p.write_bytes(b"\x00" * 64)
    return p


def test_add_paths_dedupes_and_extracts_product_code(
    svc: ProcessingQueueService,
    video_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "javstory.services.processing_queue_service.is_video_file",
        lambda p: str(p).endswith(".mp4"),
    )
    snap = svc.add_paths("stt", [str(video_file), str(video_file)])
    assert snap["planned"] == 1
    assert len(svc.snapshot()["stt"]["items"]) == 1
    item = svc.snapshot()["stt"]["items"][0]
    assert item["file_name"] == video_file.name
    assert item["product_code"] == "ABF-364"


def test_add_folder_collects_videos(
    svc: ProcessingQueueService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    v1 = tmp_path / "a.mp4"
    v2 = tmp_path / "b.mkv"
    v1.write_bytes(b"x")
    v2.write_bytes(b"x")
    (tmp_path / "note.txt").write_text("skip")

    monkeypatch.setattr(
        "javstory.services.processing_queue_service.collect_videos_flat_folder",
        lambda folder: [v1, v2] if folder == tmp_path else [],
    )
    monkeypatch.setattr(
        "javstory.services.processing_queue_service.is_video_file",
        lambda p: True,
    )

    snap = svc.add_folder("subtitle", str(tmp_path))
    assert snap["planned"] == 2
    assert len(svc.snapshot()["subtitle"]["items"]) == 2


def test_remove_pending_item(svc: ProcessingQueueService, video_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "javstory.services.processing_queue_service.is_video_file",
        lambda p: True,
    )
    svc.add_paths("stt", [str(video_file)])
    item_id = svc.snapshot()["stt"]["items"][0]["id"]
    svc.remove_item("stt", item_id)
    assert svc.snapshot()["stt"]["items"] == []


def test_clear_finished(svc: ProcessingQueueService, video_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "javstory.services.processing_queue_service.is_video_file",
        lambda p: True,
    )
    svc.add_paths("stt", [str(video_file)])
    svc._queues["stt"][0].status = "done"
    removed = svc.clear_finished("stt")
    assert removed == 1
    assert svc.snapshot()["stt"]["items"] == []


def test_clear_queue_removes_all(
    svc: ProcessingQueueService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "javstory.services.processing_queue_service.is_video_file",
        lambda p: True,
    )
    v1 = tmp_path / "A.mp4"
    v2 = tmp_path / "B.mp4"
    v1.write_bytes(b"x")
    v2.write_bytes(b"x")
    svc.add_paths("stt", [str(v1), str(v2)])
    svc._queues["stt"][0].status = "done"

    async def _run() -> None:
        async def _broadcast(_event: dict) -> None:
            pass

        svc.set_broadcast(_broadcast)
        removed = await svc.clear_queue("stt")
        assert removed == 2
        assert svc.snapshot()["stt"]["items"] == []

    asyncio.run(_run())


def test_start_runs_stt_job(
    svc: ProcessingQueueService,
    video_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "javstory.services.processing_queue_service.is_video_file",
        lambda p: True,
    )

    events: list[dict] = []

    async def _run() -> None:
        async def _broadcast(event: dict) -> None:
            events.append(event)

        svc.set_broadcast(_broadcast)
        svc.set_main_loop(asyncio.get_running_loop())

        monkeypatch.setattr(
            "javstory.services.processing_queue_service.run_stt_job",
            lambda *_a, **_k: SttJobResult(True, "ok", str(video_file.with_suffix(".ja.srt"))),
        )

        svc.add_paths("stt", [str(video_file)])
        queued = await svc.start("stt")
        assert queued == 1

        for _ in range(50):
            if not svc._running["stt"]:
                break
            await asyncio.sleep(0.05)

        snap = svc.snapshot()
        assert snap["stt"]["items"][0]["status"] == "done"
        assert any(e.get("type") == "item_done" for e in events)

    asyncio.run(_run())


def test_cancel_keeps_items_as_pending(
    svc: ProcessingQueueService,
    video_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "javstory.services.processing_queue_service.is_video_file",
        lambda p: True,
    )

    async def _run() -> None:
        async def _broadcast(_event: dict) -> None:
            pass

        svc.set_broadcast(_broadcast)
        svc.set_main_loop(asyncio.get_running_loop())

        def slow_stt(*_a, should_cancel=None, **_k):
            import time

            for _ in range(100):
                if should_cancel and should_cancel():
                    return SttJobResult(False, "취소됨")
                time.sleep(0.02)
            return SttJobResult(True, "done")

        monkeypatch.setattr("javstory.services.processing_queue_service.run_stt_job", slow_stt)

        svc.add_paths("stt", [str(video_file)])
        await svc.start("stt")
        await asyncio.sleep(0.05)
        await svc.cancel("stt")

        for _ in range(80):
            if not svc._running["stt"]:
                break
            await asyncio.sleep(0.05)

        items = svc.snapshot()["stt"]["items"]
        assert len(items) == 1
        assert items[0]["status"] == "pending"

    asyncio.run(_run())


def test_cancel_stops_queue_but_keeps_remaining(
    svc: ProcessingQueueService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "javstory.services.processing_queue_service.is_video_file",
        lambda p: True,
    )
    v1 = tmp_path / "ABF-001 a.mp4"
    v2 = tmp_path / "ABF-002 b.mp4"
    v1.write_bytes(b"\x00" * 64)
    v2.write_bytes(b"\x00" * 64)
    started: list[str] = []

    async def _run() -> None:
        async def _broadcast(_event: dict) -> None:
            pass

        svc.set_broadcast(_broadcast)
        svc.set_main_loop(asyncio.get_running_loop())

        def slow_stt(path, should_cancel=None, **_k):
            import time

            started.append(str(path))
            for _ in range(200):
                if should_cancel and should_cancel():
                    return SttJobResult(False, "취소됨")
                time.sleep(0.02)
            return SttJobResult(True, "done")

        monkeypatch.setattr("javstory.services.processing_queue_service.run_stt_job", slow_stt)

        svc.add_paths("stt", [str(v1), str(v2)])
        await svc.start("stt")
        await asyncio.sleep(0.08)
        await svc.cancel("stt")

        for _ in range(100):
            if not svc._running["stt"]:
                break
            await asyncio.sleep(0.05)

        items = svc.snapshot()["stt"]["items"]
        assert len(items) == 2
        assert all(i["status"] == "pending" for i in items)
        assert len(started) == 1

    asyncio.run(_run())


def test_remove_pending_while_running(
    svc: ProcessingQueueService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "javstory.services.processing_queue_service.is_video_file",
        lambda p: True,
    )
    v1 = tmp_path / "A.mp4"
    v2 = tmp_path / "B.mp4"
    v1.write_bytes(b"x")
    v2.write_bytes(b"x")

    async def _run() -> None:
        async def _broadcast(_event: dict) -> None:
            pass

        svc.set_broadcast(_broadcast)
        svc.set_main_loop(asyncio.get_running_loop())

        def slow_stt(*_a, should_cancel=None, **_k):
            import time

            for _ in range(80):
                if should_cancel and should_cancel():
                    return SttJobResult(False, "취소됨")
                time.sleep(0.02)
            return SttJobResult(True, "done")

        monkeypatch.setattr("javstory.services.processing_queue_service.run_stt_job", slow_stt)
        svc.add_paths("stt", [str(v1), str(v2)])
        await svc.start("stt")
        await asyncio.sleep(0.05)

        pending_id = next(i.id for i in svc._queues["stt"] if i.status == "pending")
        svc.remove_item("stt", pending_id)
        assert len(svc.snapshot()["stt"]["items"]) == 1

        await svc.cancel("stt")
        for _ in range(80):
            if not svc._running["stt"]:
                break
            await asyncio.sleep(0.05)

    asyncio.run(_run())


def test_subtitle_job_failure(
    svc: ProcessingQueueService,
    video_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "javstory.services.processing_queue_service.is_video_file",
        lambda p: True,
    )

    async def _run() -> None:
        async def _broadcast(_event: dict) -> None:
            pass

        svc.set_broadcast(_broadcast)
        svc.set_main_loop(asyncio.get_running_loop())
        monkeypatch.setattr(
            "javstory.services.processing_queue_service.run_subtitle_job",
            lambda *_a, **_k: SubtitleJobResult(False, "JA 자막 없음"),
        )

        svc.add_paths("subtitle", [str(video_file)])
        await svc.start("subtitle")

        for _ in range(50):
            if not svc._running["subtitle"]:
                break
            await asyncio.sleep(0.05)

        assert svc.snapshot()["subtitle"]["items"][0]["status"] == "error"

    asyncio.run(_run())


def test_add_products_resolves_videos(
    svc: ProcessingQueueService,
    video_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    v2 = video_file.parent / "ABF-364 part2.mp4"
    v2.write_bytes(b"\x00" * 64)

    class _Row:
        folder_path = str(video_file.parent)

    class _Lib:
        def get_by_code(self, pc: str):
            return _Row() if pc == "ABF-364" else None

    def _resolve(pc: str, folder_path: str | None):
        if pc == "ABF-364":
            return [video_file, v2]
        return []

    monkeypatch.setattr("javstory.services.library_service.LibraryService", _Lib)
    monkeypatch.setattr(
        "javstory.harvest.product_repository.resolve_video_paths_for_playback",
        _resolve,
    )
    monkeypatch.setattr(
        "javstory.services.processing_queue_service.is_video_file",
        lambda p: str(p).endswith(".mp4"),
    )

    snap = svc.add_products("stt", ["ABF-364"])
    assert snap["planned"] == 2
    assert len(svc.snapshot()["stt"]["items"]) == 2


def test_add_products_multiple_codes(
    svc: ProcessingQueueService,
    video_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    v2 = video_file.parent / "STARS-001.mp4"
    v2.write_bytes(b"\x00" * 64)

    class _Row:
        def __init__(self, folder: str):
            self.folder_path = folder

    rows = {
        "ABF-364": _Row(str(video_file.parent)),
        "STARS-001": _Row(str(video_file.parent)),
    }

    class _Lib:
        def get_by_code(self, pc: str):
            return rows.get(pc)

    def _resolve(pc: str, folder_path: str | None):
        if pc == "ABF-364":
            return [video_file]
        if pc == "STARS-001":
            return [v2]
        return []

    monkeypatch.setattr("javstory.services.library_service.LibraryService", _Lib)
    monkeypatch.setattr(
        "javstory.harvest.product_repository.resolve_video_paths_for_playback",
        _resolve,
    )
    monkeypatch.setattr(
        "javstory.services.processing_queue_service.is_video_file",
        lambda p: str(p).endswith(".mp4"),
    )

    snap = svc.add_products("subtitle", ["ABF-364", "STARS-001"])
    assert snap["planned"] == 2


def test_add_products_warns_missing_videos(
    svc: ProcessingQueueService,
    video_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Row:
        folder_path = str(video_file.parent)

    class _Lib:
        def get_by_code(self, pc: str):
            return _Row() if pc == "ABF-364" else None

    def _resolve(pc: str, folder_path: str | None):
        if pc == "ABF-364":
            return [video_file]
        return []

    monkeypatch.setattr("javstory.services.library_service.LibraryService", _Lib)
    monkeypatch.setattr(
        "javstory.harvest.product_repository.resolve_video_paths_for_playback",
        _resolve,
    )
    monkeypatch.setattr(
        "javstory.services.processing_queue_service.is_video_file",
        lambda p: str(p).endswith(".mp4"),
    )

    snap = svc.add_products("stt", ["ABF-364", "MISSING-999"])
    assert snap["planned"] == 1
    assert any("MISSING-999" in w for w in (snap.get("warnings") or []))


def test_add_products_raises_when_no_videos(
    svc: ProcessingQueueService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Lib:
        def get_by_code(self, _pc: str):
            return None

    monkeypatch.setattr("javstory.services.library_service.LibraryService", _Lib)
    monkeypatch.setattr(
        "javstory.harvest.product_repository.resolve_video_paths_for_playback",
        lambda *_a, **_k: [],
    )

    with pytest.raises(ValueError, match="동영상을 찾을 수 없습니다"):
        svc.add_products("stt", ["NOPE-001"])
