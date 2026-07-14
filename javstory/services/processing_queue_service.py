from __future__ import annotations

import asyncio
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Literal, Optional

from javstory.library.video_ext import is_video_file
from javstory.services.processing_execution_service import run_stt_job, run_subtitle_job
from javstory.services.processing_paths import collect_videos_flat_folder, normalize_unique_paths
from javstory.utils.product_code import resolve_product_code_for_video

ProcessingKind = Literal["stt", "subtitle"]
KINDS: tuple[ProcessingKind, ...] = ("stt", "subtitle")

BroadcastFn = Callable[[dict[str, Any]], Any]

_QUEUE_PERSIST_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cache" / "processing_queue.json"


def _processing_concurrency() -> int:
    raw = (os.environ.get("JAVSTORY_PROCESSING_CONCURRENCY", "") or "").strip()
    try:
        n = int(raw) if raw else 1
    except ValueError:
        n = 1
    return max(1, min(2, n))


@dataclass
class ProcessingQueueItem:
    id: str
    target: str
    product_code: Optional[str] = None
    status: str = "pending"
    progress: int = 0
    message: str = "대기 중..."
    file_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "target": self.target,
            "product_code": self.product_code,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "file_name": self.file_name,
        }


class ProcessingQueueService:
    def __init__(self) -> None:
        self._queues: dict[ProcessingKind, list[ProcessingQueueItem]] = {
            "stt": [],
            "subtitle": [],
        }
        self._running: dict[ProcessingKind, bool] = {"stt": False, "subtitle": False}
        self._executor = ThreadPoolExecutor(max_workers=_processing_concurrency())
        self._broadcast: Optional[BroadcastFn] = None
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self._cancel_ids: set[str] = set()
        self._abort: dict[ProcessingKind, bool] = {"stt": False, "subtitle": False}
        self._run_locks: dict[ProcessingKind, asyncio.Lock] = {
            "stt": asyncio.Lock(),
            "subtitle": asyncio.Lock(),
        }

    def set_broadcast(self, fn: BroadcastFn) -> None:
        self._broadcast = fn

    def set_main_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._main_loop = loop

    def _queue(self, kind: ProcessingKind) -> list[ProcessingQueueItem]:
        return self._queues[kind]

    def snapshot(self) -> dict[str, Any]:
        return {
            "stt": {
                "items": [i.to_dict() for i in self._queues["stt"]],
                "running": self._running["stt"],
            },
            "subtitle": {
                "items": [i.to_dict() for i in self._queues["subtitle"]],
                "running": self._running["subtitle"],
            },
        }

    def _new_item(self, path: Path) -> ProcessingQueueItem:
        pc = resolve_product_code_for_video(path) or None
        return ProcessingQueueItem(
            id=str(uuid.uuid4()),
            target=str(path),
            product_code=pc,
            file_name=path.name,
            message="대기 중...",
        )

    def _is_duplicate(self, kind: ProcessingKind, path: Path) -> bool:
        key = str(path).lower()
        for item in self._queue(kind):
            if item.status not in ("pending", "running"):
                continue
            if str(Path(item.target).resolve()).lower() == key:
                return True
        return False

    def add_paths(self, kind: ProcessingKind, paths: list[str]) -> dict[str, Any]:
        if kind not in KINDS:
            raise ValueError(f"invalid kind: {kind}")
        normalized = normalize_unique_paths(paths)
        added = 0
        warnings: list[str] = []
        for path in normalized:
            if not path.is_file():
                warnings.append(f"파일 없음: {path}")
                continue
            if not is_video_file(path):
                warnings.append(f"동영상이 아님: {path.name}")
                continue
            if self._is_duplicate(kind, path):
                continue
            self._queue(kind).append(self._new_item(path))
            added += 1
        if added:
            self.persist_queue()
        snap = self.snapshot()
        snap["planned"] = added
        if warnings:
            snap["warnings"] = warnings
        return snap

    def add_folder(self, kind: ProcessingKind, folder_path: str) -> dict[str, Any]:
        folder = Path(folder_path.strip()).expanduser().resolve()
        if not folder.is_dir():
            raise ValueError(f"폴더가 아닙니다: {folder}")
        videos = collect_videos_flat_folder(folder)
        if not videos:
            raise ValueError(f"폴더에 동영상이 없습니다: {folder}")
        snap = self.add_paths(kind, [str(v) for v in videos])
        snap["folder_path"] = str(folder)
        return snap

    def add_products(self, kind: ProcessingKind, product_codes: list[str]) -> dict[str, Any]:
        if kind not in KINDS:
            raise ValueError(f"invalid kind: {kind}")
        from javstory.harvest.product_repository import resolve_video_paths_for_playback
        from javstory.services.library_service import LibraryService

        lib = LibraryService()
        paths: list[str] = []
        warnings: list[str] = []
        seen_codes: set[str] = set()
        for raw in product_codes:
            pc = (raw or "").strip().upper()
            if not pc or pc in seen_codes:
                continue
            seen_codes.add(pc)
            row = lib.get_by_code(pc)
            folder_path = (row.folder_path if row else None) or None
            vps = resolve_video_paths_for_playback(pc, folder_path)
            if not vps:
                warnings.append(f"{pc}: 동영상을 찾을 수 없습니다")
                continue
            paths.extend(str(v) for v in vps)
        if not paths:
            msg = warnings[0] if len(warnings) == 1 else "추가할 동영상이 없습니다"
            raise ValueError(msg)
        snap = self.add_paths(kind, paths)
        merged_warnings = list(warnings)
        if snap.get("warnings"):
            merged_warnings.extend(snap["warnings"])
        if merged_warnings:
            snap["warnings"] = merged_warnings
        return snap

    def remove_item(self, kind: ProcessingKind, item_id: str) -> ProcessingQueueItem:
        item = next((i for i in self._queue(kind) if i.id == item_id), None)
        if not item:
            raise KeyError(item_id)
        if item.status == "running":
            raise RuntimeError("running")
        self._queues[kind] = [i for i in self._queue(kind) if i.id != item_id]
        self.persist_queue()
        return item

    async def cancel(self, kind: ProcessingKind) -> None:
        """실행 중 큐를 중지한다. 항목은 삭제하지 않고 pending으로 되돌린다."""
        if not self._running[kind]:
            raise RuntimeError("not_running")
        self._abort[kind] = True
        cancelled_ids: list[str] = []
        for item in self._queue(kind):
            if item.status == "running":
                self._cancel_ids.add(item.id)
                cancelled_ids.append(item.id)
                # UI/목록 유지를 위해 즉시 pending 복원 (백그라운드 잡은 cancel로 종료)
                self._reset_item_to_pending(item)
        self.persist_queue()
        for item_id in cancelled_ids:
            await self._emit({"type": "item_cancelled", "kind": kind, "id": item_id})
        await self._emit({"type": "state", **self.snapshot()})

    def _reset_item_to_pending(self, item: ProcessingQueueItem) -> None:
        item.status = "pending"
        item.progress = 0
        item.message = "대기 중..."

    def clear_finished(self, kind: ProcessingKind) -> int:
        before = len(self._queue(kind))
        self._queues[kind] = [i for i in self._queue(kind) if i.status not in ("done", "error")]
        removed = before - len(self._queues[kind])
        if removed:
            self.persist_queue()
        return removed

    async def clear_queue(self, kind: ProcessingKind) -> int:
        """해당 kind 큐를 전부 비운다. 실행 중이면 중지도 요청한다."""
        if kind not in KINDS:
            raise ValueError(f"invalid kind: {kind}")
        items = list(self._queue(kind))
        removed = len(items)
        if not removed:
            return 0
        if self._running[kind]:
            self._abort[kind] = True
            for item in items:
                if item.status == "running":
                    self._cancel_ids.add(item.id)
        self._queues[kind] = []
        self.persist_queue()
        await self._emit({"type": "state", **self.snapshot()})
        return removed

    def persist_queue(self) -> None:
        try:
            _QUEUE_PERSIST_PATH.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "stt": [i.to_dict() for i in self._queues["stt"] if i.status in ("pending", "running")],
                "subtitle": [
                    i.to_dict() for i in self._queues["subtitle"] if i.status in ("pending", "running")
                ],
            }
            _QUEUE_PERSIST_PATH.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def load_persisted(self) -> None:
        if any(self._queues[k] for k in KINDS) or any(self._running.values()):
            return
        try:
            if not _QUEUE_PERSIST_PATH.is_file():
                return
            raw = json.loads(_QUEUE_PERSIST_PATH.read_text(encoding="utf-8"))
            for kind in KINDS:
                for d in raw.get(kind) or []:
                    if d.get("status") == "running":
                        d = {**d, "status": "pending", "progress": 0, "message": "대기 중..."}
                    fields = ProcessingQueueItem.__dataclass_fields__
                    self._queues[kind].append(
                        ProcessingQueueItem(**{k: d[k] for k in d if k in fields})
                    )
        except Exception:
            pass

    async def start(self, kind: ProcessingKind) -> int:
        if self._running[kind]:
            raise RuntimeError("already_running")
        pending = [i for i in self._queue(kind) if i.status == "pending"]
        if not pending:
            raise RuntimeError("empty")
        self._abort[kind] = False
        self._running[kind] = True
        await self._emit({"type": "queue_started", "kind": kind})
        asyncio.create_task(self._run_queue(kind))
        return len(pending)

    async def _run_queue(self, kind: ProcessingKind) -> None:
        lock = self._run_locks[kind]
        async with lock:
            try:
                while True:
                    if self._abort[kind]:
                        break
                    pending = [i for i in self._queue(kind) if i.status == "pending"]
                    if not pending:
                        break
                    for item in pending:
                        if self._abort[kind]:
                            break
                        await self._process_item(kind, item)
                        self.persist_queue()
            finally:
                self._running[kind] = False
                self._abort[kind] = False
                self.persist_queue()
                await self._emit({"type": "queue_finished", "kind": kind})
                await self._emit({"type": "state", **self.snapshot()})

    async def _process_item(self, kind: ProcessingKind, item: ProcessingQueueItem) -> None:
        if item.status != "pending":
            return
        item.status = "running"
        item.progress = 0
        item.message = "시작..."
        await self._emit({"type": "item_started", "kind": kind, "id": item.id})
        await self._emit({"type": "content_clear", "kind": kind, "id": item.id})

        def progress_cb(msg: str, pct: int) -> None:
            if item.id in self._cancel_ids:
                return
            if pct >= 0:
                item.progress = pct
            item.message = msg
            if self._main_loop and self._broadcast:
                asyncio.run_coroutine_threadsafe(
                    self._emit(
                        {
                            "type": "progress",
                            "kind": kind,
                            "id": item.id,
                            "message": msg,
                            "progress": item.progress if pct >= 0 else item.progress,
                        }
                    ),
                    self._main_loop,
                )

        def log_cb(level: str, text: str) -> None:
            if item.id in self._cancel_ids:
                return
            if self._main_loop and self._broadcast:
                ts = datetime.now().strftime("%H:%M:%S")
                asyncio.run_coroutine_threadsafe(
                    self._emit({"type": "log", "kind": kind, "level": level, "text": text, "ts": ts}),
                    self._main_loop,
                )

        def content_cb(payload: dict[str, object]) -> None:
            if item.id in self._cancel_ids:
                return
            if self._main_loop and self._broadcast:
                ts = datetime.now().strftime("%H:%M:%S")
                asyncio.run_coroutine_threadsafe(
                    self._emit(
                        {
                            "type": "content_line",
                            "kind": kind,
                            "id": item.id,
                            "ts": ts,
                            **payload,
                        }
                    ),
                    self._main_loop,
                )

        def should_cancel() -> bool:
            return item.id in self._cancel_ids

        loop = asyncio.get_running_loop()
        try:
            if kind == "stt":
                result = await loop.run_in_executor(
                    self._executor,
                    lambda: run_stt_job(
                        item.target,
                        on_progress=progress_cb,
                        on_log=log_cb,
                        on_content_line=content_cb,
                        should_cancel=should_cancel,
                    ),
                )
            else:
                pc = item.product_code or resolve_product_code_for_video(item.target)
                result = await loop.run_in_executor(
                    self._executor,
                    lambda: run_subtitle_job(
                        pc,
                        item.target,
                        on_progress=progress_cb,
                        on_log=log_cb,
                        on_content_line=content_cb,
                        should_cancel=should_cancel,
                    ),
                )

            still_queued = any(i.id == item.id for i in self._queue(kind))
            if not still_queued:
                self._cancel_ids.discard(item.id)
                return

            if should_cancel() or item.status == "pending":
                # 중지면 삭제하지 않고 대기 상태로 복원
                if item.status != "pending":
                    self._reset_item_to_pending(item)
                self._cancel_ids.discard(item.id)
                await self._emit({"type": "item_cancelled", "kind": kind, "id": item.id})
                await self._emit({"type": "state", **self.snapshot()})
                return

            if result.ok:
                item.status = "done"
                item.progress = 100
                item.message = result.message
                await self._emit(
                    {
                        "type": "item_done",
                        "kind": kind,
                        "id": item.id,
                        "message": item.message,
                        "progress": 100,
                    }
                )
            else:
                item.status = "error"
                item.message = result.message
                await self._emit(
                    {"type": "item_error", "kind": kind, "id": item.id, "message": item.message}
                )
        except Exception as e:
            if not any(i.id == item.id for i in self._queue(kind)):
                return
            item.status = "error"
            item.message = str(e)
            await self._emit(
                {"type": "item_error", "kind": kind, "id": item.id, "message": str(e)}
            )
        finally:
            self._cancel_ids.discard(item.id)

    async def _emit(self, event: dict[str, Any]) -> None:
        if self._broadcast:
            result = self._broadcast(event)
            if asyncio.iscoroutine(result):
                await result


processing_queue = ProcessingQueueService()
