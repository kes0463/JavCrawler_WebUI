from __future__ import annotations

import asyncio
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from javstory.config.app_config import story_analysis_enabled_from_env
from javstory.services.harvest_execution_service import HarvestEntry, resolve_sku, run_one_sync


@dataclass
class HarvestQueueItem:
    id: str
    target: str
    product_code: Optional[str] = None
    status: str = "pending"
    progress: int = 0
    message: str = ""
    kind: str = "code"
    is_path: bool = False
    force_rebuild: bool = False
    staged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "target": self.target,
            "product_code": self.product_code,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "kind": self.kind,
            "is_path": self.is_path,
            "force_rebuild": self.force_rebuild,
            "staged": self.staged,
        }

    def to_entry(self) -> HarvestEntry:
        return HarvestEntry(
            target=self.target,
            is_path=self.is_path,
            product_code=self.product_code,
            force_rebuild=self.force_rebuild,
        )


BroadcastFn = Callable[[dict[str, Any]], Any]

_QUEUE_PERSIST_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cache" / "harvest_queue.json"


def _harvest_concurrency() -> int:
    raw = (os.environ.get("JAVSTORY_HARVEST_CONCURRENCY", "") or "").strip()
    try:
        n = int(raw) if raw else 1
    except ValueError:
        n = 1
    return max(1, min(5, n))


class HarvestQueueService:
    def __init__(self) -> None:
        self._queue: list[HarvestQueueItem] = []
        self._running = False
        self._grok_enabled = story_analysis_enabled_from_env()
        self._executor = ThreadPoolExecutor(max_workers=_harvest_concurrency())
        self._broadcast: Optional[BroadcastFn] = None
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self._cancel_ids: set[str] = set()
        self._active_count = 0
        self._run_lock = asyncio.Lock()

    def set_broadcast(self, fn: BroadcastFn) -> None:
        self._broadcast = fn

    def set_main_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._main_loop = loop

    @property
    def running(self) -> bool:
        return self._running

    @property
    def grok_enabled(self) -> bool:
        return self._grok_enabled

    def set_grok_enabled(self, enabled: bool) -> None:
        self._grok_enabled = bool(enabled)

    def snapshot(self) -> dict[str, Any]:
        return {
            "items": [i.to_dict() for i in self._queue],
            "running": self._running,
            "grok_enabled": self._grok_enabled,
        }

    def _new_item(
        self,
        *,
        target: str,
        product_code: str | None,
        kind: str = "code",
        is_path: bool = False,
        force_rebuild: bool = False,
        staged: bool = False,
        message: str = "",
    ) -> HarvestQueueItem:
        msg = message or ("큐 대기" if staged else "대기 중...")
        return HarvestQueueItem(
            id=str(uuid.uuid4()),
            target=target,
            product_code=product_code,
            kind=kind,
            is_path=is_path,
            force_rebuild=force_rebuild,
            staged=staged,
            message=msg,
        )

    def add_codes(
        self,
        codes: list[str],
        *,
        auto_start: bool = False,
        force_rebuild: bool = False,
    ) -> dict[str, Any]:
        from javstory.harvest.database import assert_db_writable
        from javstory.utils.product_code import is_plausible_harvest_code

        assert_db_writable("harvest queue")
        added = 0
        for code in codes:
            c = code.strip().upper()
            if not c or not is_plausible_harvest_code(c):
                continue
            if any(
                self._same_product_code(i, c)
                and i.status in ("pending", "running")
                and not i.staged
                for i in self._queue
            ):
                continue
            self._queue.append(
                self._new_item(
                    target=c,
                    product_code=c,
                    kind="code",
                    force_rebuild=force_rebuild,
                )
            )
            added += 1
        if added:
            self.persist_queue()
        snap = self.snapshot()
        snap["planned"] = added
        return snap

    def _same_product_code(self, item: HarvestQueueItem, code: str) -> bool:
        pc = (item.product_code or item.target or "").strip().upper()
        return pc == code.strip().upper()

    def recrawl_codes(self, codes: list[str], *, force: bool = True) -> dict[str, Any]:
        """라이브러리 재크롤 — 완료·오류 항목은 교체하고 force_rebuild로 다시 수집."""
        from javstory.harvest.database import assert_db_writable
        from javstory.utils.product_code import is_plausible_harvest_code

        assert_db_writable("harvest queue")
        added = 0
        already_running = 0
        for code in codes:
            c = code.strip().upper()
            if not c or not is_plausible_harvest_code(c):
                continue
            running = next(
                (i for i in self._queue if self._same_product_code(i, c) and i.status == "running"),
                None,
            )
            if running:
                if force:
                    running.force_rebuild = True
                already_running += 1
                continue
            self._queue = [
                i for i in self._queue
                if not (self._same_product_code(i, c) and i.status != "running")
            ]
            self._queue.append(
                self._new_item(
                    target=c,
                    product_code=c,
                    kind="code",
                    force_rebuild=force,
                    message="재크롤 대기",
                )
            )
            added += 1
        if added or already_running:
            self.persist_queue()
        snap = self.snapshot()
        snap["planned"] = added
        snap["recrawl_running"] = already_running
        return snap

    def _validate_folder(self, path: str) -> Path:
        p = Path(path.strip()).expanduser().resolve()
        if not p.is_dir():
            raise ValueError(f"폴더가 아닙니다: {p}")
        return p

    def queue_folder(self, path: str) -> dict[str, Any]:
        from javstory.harvest.database import assert_db_writable
        from javstory.harvest.folder_harvest import plan_single_folder

        assert_db_writable("harvest queue")
        folder = self._validate_folder(path)
        jobs, warnings = plan_single_folder(folder)
        return self._append_planned(jobs, warnings, folder_path=str(folder))

    def queue_parent_folder(self, path: str) -> dict[str, Any]:
        from javstory.harvest.database import assert_db_writable
        from javstory.harvest.folder_harvest import plan_parent_folder

        assert_db_writable("harvest queue")
        folder = self._validate_folder(path)
        jobs, warnings = plan_parent_folder(folder)
        return self._append_planned(jobs, warnings, folder_path=str(folder))

    def queue_folders(self, paths: list[str]) -> dict[str, Any]:
        from javstory.harvest.database import assert_db_writable
        from javstory.harvest.folder_harvest import plan_folder_paths

        assert_db_writable("harvest queue")
        folders: list[Path] = []
        for raw in paths:
            p = str(raw or "").strip()
            if not p:
                continue
            folders.append(self._validate_folder(p))
        if not folders:
            raise ValueError("유효한 폴더 경로가 없습니다")
        jobs, warnings = plan_folder_paths(folders)
        label = folders[0].name if len(folders) == 1 else f"{len(folders)}개 폴더"
        return self._append_planned(jobs, warnings, folder_path=label)

    def _append_planned(self, jobs, warnings, *, folder_path: str) -> dict[str, Any]:
        added = 0
        for job in jobs:
            key = (job.crawl_target, job.product_code)
            if any(i.target == key[0] and i.product_code == key[1] for i in self._queue):
                continue
            self._queue.append(
                self._new_item(
                    target=job.crawl_target,
                    product_code=job.product_code,
                    kind="video_path" if job.is_media_path else "code",
                    is_path=job.is_media_path,
                    staged=True,
                )
            )
            added += 1
        snap = self.snapshot()
        snap["planned"] = added
        snap["warnings"] = warnings
        snap["folder_path"] = folder_path
        if self._main_loop and self._broadcast:
            asyncio.run_coroutine_threadsafe(
                self._emit(
                    {
                        "type": "folder_planned",
                        "path": folder_path,
                        "count": added,
                        "warnings": warnings,
                    }
                ),
                self._main_loop,
            )
        self.persist_queue()
        return snap

    async def start_staged(self) -> int:
        for item in self._queue:
            if item.staged and item.status == "pending":
                item.staged = False
                item.message = "대기 중..."
        return await self.start()

    def remove(self, item_id: str, *, cancel_running: bool = False) -> HarvestQueueItem:
        item = next((i for i in self._queue if i.id == item_id), None)
        if not item:
            raise KeyError(item_id)
        if item.status == "running":
            if not cancel_running:
                raise RuntimeError("running")
            self._cancel_ids.add(item_id)
        self._queue = [i for i in self._queue if i.id != item_id]
        self.persist_queue()
        return item

    async def cancel(self, item_id: str) -> None:
        item = next((i for i in self._queue if i.id == item_id), None)
        if not item:
            raise KeyError(item_id)
        if item.status != "running":
            raise RuntimeError("not_running")
        self._cancel_ids.add(item_id)

    def clear(self) -> None:
        if self._running:
            raise RuntimeError("running")
        self._queue = []

    def clear_finished(self) -> int:
        before = len(self._queue)
        self._queue = [i for i in self._queue if i.status not in ("done", "error")]
        removed = before - len(self._queue)
        if removed:
            self.persist_queue()
        return removed

    def persist_queue(self) -> None:
        try:
            _QUEUE_PERSIST_PATH.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "grok_enabled": self._grok_enabled,
                "items": [i.to_dict() for i in self._queue if i.status in ("pending", "running") or i.staged],
            }
            _QUEUE_PERSIST_PATH.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def load_persisted(self) -> None:
        if self._running or self._queue:
            return
        try:
            if not _QUEUE_PERSIST_PATH.is_file():
                return
            from javstory.utils.product_code import is_plausible_harvest_code

            raw = json.loads(_QUEUE_PERSIST_PATH.read_text(encoding="utf-8"))
            self._grok_enabled = bool(raw.get("grok_enabled", self._grok_enabled))
            loaded = 0
            for d in raw.get("items") or []:
                if d.get("status") == "running":
                    d = {**d, "status": "pending", "progress": 0, "message": "대기 중..."}
                is_path = bool(d.get("is_path"))
                kind = d.get("kind", "code")
                pc = (d.get("product_code") or d.get("target") or "").strip().upper()
                if kind == "code" and not is_path and not is_plausible_harvest_code(pc):
                    continue
                self._queue.append(
                    HarvestQueueItem(**{k: d[k] for k in d if k in HarvestQueueItem.__dataclass_fields__})
                )
                loaded += 1
            if loaded != len(raw.get("items") or []):
                self.persist_queue()
        except Exception:
            pass

    async def start(self) -> int:
        if self._running:
            raise RuntimeError("already_running")
        pending = [i for i in self._queue if i.status == "pending" and not i.staged]
        if not pending:
            raise RuntimeError("empty")
        self._running = True
        await self._emit({"type": "queue_started"})
        asyncio.create_task(self._run_queue())
        return len(pending)

    async def ensure_running(self) -> int:
        """대기 항목이 있으면 큐 실행. 이미 돌고 있으면 새 항목은 루프에서 이어서 처리."""
        pending = [i for i in self._queue if i.status == "pending" and not i.staged]
        if not pending:
            raise RuntimeError("empty")
        if self._running:
            return len(pending)
        return await self.start()

    async def _run_queue(self) -> None:
        async with self._run_lock:
            try:
                while True:
                    pending = [
                        i for i in self._queue
                        if i.status == "pending" and not i.staged
                    ]
                    if not pending:
                        break
                    sem = asyncio.Semaphore(_harvest_concurrency())

                    async def _run_one(item: HarvestQueueItem) -> None:
                        async with sem:
                            await self._process_item(item)

                    await asyncio.gather(
                        *[_run_one(i) for i in pending],
                        return_exceptions=True,
                    )
                    self.persist_queue()
            finally:
                self._running = False
                self.persist_queue()
                await self._emit({"type": "queue_finished"})

    async def _process_item(self, item: HarvestQueueItem) -> None:
        if item.status != "pending" or item.staged:
            return
        item.status = "running"
        item.progress = 0
        item.message = "수집 시작..."
        sku = item.product_code or resolve_sku(item.to_entry())
        await self._emit({"type": "item_started", "id": item.id})

        def progress_cb(_sku: str, msg: str, pct: int) -> None:
            item.progress = pct
            item.message = msg
            if self._main_loop and self._broadcast:
                asyncio.run_coroutine_threadsafe(
                    self._emit(
                        {
                            "type": "progress",
                            "id": item.id,
                            "sku": _sku,
                            "message": msg,
                            "progress": pct,
                        }
                    ),
                    self._main_loop,
                )

        def log_cb(level: str, text: str) -> None:
            if self._main_loop and self._broadcast:
                ts = datetime.now().strftime("%H:%M:%S")
                asyncio.run_coroutine_threadsafe(
                    self._emit({"type": "log", "level": level, "text": text, "ts": ts}),
                    self._main_loop,
                )

        def should_cancel() -> bool:
            return item.id in self._cancel_ids

        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                self._executor,
                lambda: run_one_sync(
                    item.to_entry(),
                    grok_enabled=self._grok_enabled,
                    on_progress=progress_cb,
                    on_log=log_cb,
                    should_cancel=should_cancel,
                ),
            )
            if should_cancel():
                item.status = "error"
                item.message = "취소됨"
                self._cancel_ids.discard(item.id)
                await self._emit({"type": "item_cancelled", "id": item.id})
                self._queue = [i for i in self._queue if i.id != item.id]
                return
            if result.get("ok"):
                item.status = "done"
                item.progress = 100
                item.message = result.get("message") or "완료"
                await self._emit(
                    {
                        "type": "item_done",
                        "id": item.id,
                        "message": item.message,
                        "progress": 100,
                    }
                )
                await self._maybe_harvest_alert(sku)
                self.persist_queue()
            else:
                item.status = "error"
                item.message = result.get("message") or "실패"
                await self._emit(
                    {"type": "item_error", "id": item.id, "message": item.message}
                )
        except Exception as e:
            item.status = "error"
            item.message = str(e)
            await self._emit(
                {"type": "item_error", "id": item.id, "message": str(e)}
            )
        finally:
            self._cancel_ids.discard(item.id)

    async def _maybe_harvest_alert(self, sku: str) -> None:
        try:
            from javstory.analytics.harvest_alert import evaluate_harvest_taste_alert

            msg = evaluate_harvest_taste_alert(sku)
            if msg:
                await self._emit({"type": "harvest_alert", "product_code": sku, "message": msg})
        except Exception:
            pass

    async def _emit(self, event: dict[str, Any]) -> None:
        if self._broadcast:
            result = self._broadcast(event)
            if asyncio.iscoroutine(result):
                await result


harvest_queue = HarvestQueueService()
