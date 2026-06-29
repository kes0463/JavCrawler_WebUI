from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from javstory.services.favorites_harvest_service import resolve_favorite_codes, run_favorites_batch
from javstory.services.harvest_queue_service import harvest_queue
from webapi.schemas import (
    AddHarvestRequest,
    FavoritesHarvestRequest,
    FolderHarvestBatchRequest,
    FolderHarvestRequest,
    HarvestItem,
    HarvestQueueResponse,
    HarvestSettingsRequest,
    PickFoldersResponse,
    RecrawlRequest,
)

router = APIRouter()

_ws_clients: list[WebSocket] = []
_ws_lock = asyncio.Lock()
_favorites_running = False


async def _broadcast(event: dict[str, Any]) -> None:
    async with _ws_lock:
        dead: list[WebSocket] = []
        for ws in list(_ws_clients):
            try:
                await ws.send_text(json.dumps(event, ensure_ascii=False))
            except Exception:
                dead.append(ws)
        for ws in dead:
            try:
                _ws_clients.remove(ws)
            except ValueError:
                pass


async def _broadcast_state() -> None:
    snap = harvest_queue.snapshot()
    await _broadcast(
        {
            "type": "state",
            "running": snap["running"],
            "items": snap["items"],
            "grok_enabled": snap.get("grok_enabled", False),
        }
    )


def bind_harvest_broadcast(loop: asyncio.AbstractEventLoop) -> None:
    harvest_queue.set_main_loop(loop)
    harvest_queue.set_broadcast(_broadcast)
    harvest_queue.load_persisted()


def _queue_response(snap: dict[str, Any]) -> HarvestQueueResponse:
    return HarvestQueueResponse(
        items=[HarvestItem(**i) for i in snap["items"]],
        running=snap["running"],
        grok_enabled=snap.get("grok_enabled", False),
        planned=snap.get("planned"),
        warnings=snap.get("warnings"),
        folder_path=snap.get("folder_path"),
    )


@router.get("/queue", response_model=HarvestQueueResponse)
async def get_queue():
    return _queue_response(harvest_queue.snapshot())


@router.post("/add", response_model=HarvestQueueResponse)
async def add_to_queue(body: AddHarvestRequest):
    harvest_queue.add_codes(body.codes)
    if body.auto_start:
        try:
            await harvest_queue.start()
        except RuntimeError:
            pass
    await _broadcast_state()
    return _queue_response(harvest_queue.snapshot())


@router.post("/recrawl", response_model=HarvestQueueResponse)
async def recrawl_products(body: RecrawlRequest):
    snap = harvest_queue.recrawl_codes(body.codes, force=body.force)
    added = int(snap.get("planned") or 0)
    running = int(snap.get("recrawl_running") or 0)
    if added == 0 and running == 0:
        raise HTTPException(
            400,
            "재크롤 큐에 추가되지 않았습니다. 품번 형식을 확인하세요.",
        )
    try:
        await harvest_queue.ensure_running()
    except RuntimeError:
        pass
    await _broadcast_state()
    return _queue_response(harvest_queue.snapshot())


@router.post("/queue-folder", response_model=HarvestQueueResponse)
async def queue_folder(body: FolderHarvestRequest):
    try:
        snap = harvest_queue.queue_folder(body.path)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    await _broadcast_state()
    return _queue_response(snap)


@router.post("/queue-parent-folder", response_model=HarvestQueueResponse)
async def queue_parent_folder(body: FolderHarvestRequest):
    try:
        snap = harvest_queue.queue_parent_folder(body.path)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    await _broadcast_state()
    return _queue_response(snap)


@router.post("/queue-folders", response_model=HarvestQueueResponse)
async def queue_folders(body: FolderHarvestBatchRequest):
    try:
        snap = harvest_queue.queue_folders(body.paths)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    await _broadcast_state()
    return _queue_response(snap)


@router.post("/pick-folders", response_model=PickFoldersResponse)
async def pick_folders():
    loop = asyncio.get_running_loop()
    try:
        paths = await loop.run_in_executor(None, _pick_folders_sync)
    except Exception as e:
        raise HTTPException(500, f"폴더 선택 대화상자 오류: {e}") from None
    if not paths:
        return PickFoldersResponse(paths=[], cancelled=True)
    return PickFoldersResponse(paths=paths, cancelled=False)


def _pick_folders_sync() -> list[str]:
    from javstory.utils.native_folder_picker import pick_folders

    return pick_folders(title="Harvest 큐에 추가할 폴더 선택 (Ctrl+클릭 다중 선택)")


@router.post("/start-staged")
async def start_staged():
    try:
        queued = await harvest_queue.start_staged()
    except RuntimeError as e:
        msg = str(e)
        if msg == "already_running":
            raise HTTPException(400, "이미 실행 중입니다") from None
        raise HTTPException(400, "대기 중인 항목이 없습니다") from None
    await _broadcast_state()
    return {"ok": True, "queued": queued}


@router.delete("/queue/{item_id}")
async def remove_from_queue(item_id: str):
    try:
        harvest_queue.remove(item_id)
    except KeyError:
        raise HTTPException(404, "항목을 찾을 수 없습니다") from None
    except RuntimeError:
        raise HTTPException(400, "실행 중인 항목은 삭제할 수 없습니다. 취소 API를 사용하세요.") from None
    harvest_queue.persist_queue()
    await _broadcast_state()
    return {"ok": True}


@router.post("/cancel/{item_id}")
async def cancel_item(item_id: str):
    try:
        await harvest_queue.cancel(item_id)
    except KeyError:
        raise HTTPException(404, "항목을 찾을 수 없습니다") from None
    except RuntimeError:
        raise HTTPException(400, "실행 중인 항목만 취소할 수 있습니다") from None
    return {"ok": True}


@router.post("/start")
async def start_harvest():
    try:
        queued = await harvest_queue.start()
    except RuntimeError as e:
        msg = str(e)
        if msg == "already_running":
            raise HTTPException(400, "이미 실행 중입니다") from None
        raise HTTPException(400, "대기 중인 항목이 없습니다") from None
    await _broadcast_state()
    return {"ok": True, "queued": queued}


@router.post("/clear-finished")
async def clear_finished():
    removed = harvest_queue.clear_finished()
    harvest_queue.persist_queue()
    await _broadcast_state()
    return {"ok": True, "removed": removed}


@router.post("/clear")
async def clear_queue():
    try:
        harvest_queue.clear()
    except RuntimeError:
        raise HTTPException(400, "실행 중에는 초기화할 수 없습니다") from None
    harvest_queue.persist_queue()
    await _broadcast_state()
    return {"ok": True}


@router.patch("/settings", response_model=HarvestQueueResponse)
async def patch_settings(body: HarvestSettingsRequest):
    harvest_queue.set_grok_enabled(body.grok_enabled)
    await _broadcast_state()
    return _queue_response(harvest_queue.snapshot())


@router.post("/favorites")
async def harvest_favorites(body: FavoritesHarvestRequest):
    global _favorites_running
    if _favorites_running:
        raise HTTPException(400, "좋아요 수집이 이미 실행 중입니다")
    mode = (body.mode or "selected").strip().lower()
    if mode not in ("selected", "all", "missing"):
        raise HTTPException(400, "mode must be selected, all, or missing")
    try:
        codes = resolve_favorite_codes(mode, body.codes)
    except Exception as e:
        raise HTTPException(400, str(e)) from None
    if not codes:
        raise HTTPException(400, "처리할 품번이 없습니다")
    _favorites_running = True
    asyncio.create_task(_run_favorites_job(codes, mode))
    return {"ok": True, "queued": len(codes), "mode": mode}


async def _run_favorites_job(codes: list[str], mode: str) -> None:
    global _favorites_running
    loop = asyncio.get_running_loop()
    await _broadcast(
        {"type": "favorites_started", "mode": mode, "total": len(codes)}
    )

    def on_progress(cur: int, total: int, sku: str, status: str, pct: int, msg: str) -> None:
        asyncio.run_coroutine_threadsafe(
            _broadcast(
                {
                    "type": "favorites_progress",
                    "current": cur,
                    "total": total,
                    "product_code": sku,
                    "status": status,
                    "progress": pct,
                    "message": msg,
                }
            ),
            loop,
        )

    try:
        result = await loop.run_in_executor(
            None,
            lambda: run_favorites_batch(codes, on_progress=on_progress),
        )
        await _broadcast({"type": "favorites_finished", **result})
    except Exception as e:
        await _broadcast({"type": "favorites_error", "message": str(e)})
    finally:
        _favorites_running = False


@router.websocket("/ws")
async def harvest_ws(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)
    try:
        snap = harvest_queue.snapshot()
        await ws.send_text(
            json.dumps(
                {
                    "type": "state",
                    "running": snap["running"],
                    "items": snap["items"],
                    "grok_enabled": snap.get("grok_enabled", False),
                },
                ensure_ascii=False,
            )
        )
        while True:
            await ws.receive_text()
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        try:
            _ws_clients.remove(ws)
        except ValueError:
            pass
