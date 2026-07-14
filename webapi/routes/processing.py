from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from javstory.services.processing_queue_service import processing_queue
from webapi.schemas import (
    AddProcessingProductsRequest,
    AddProcessingRequest,
    ProcessingFolderRequest,
    ProcessingKindRequest,
    ProcessingQueueItem,
    ProcessingQueueResponse,
    ProcessingQueueSection,
)

router = APIRouter()

_ws_clients: list[WebSocket] = []
_ws_lock = asyncio.Lock()


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
    snap = processing_queue.snapshot()
    await _broadcast({"type": "state", **snap})


def bind_processing_broadcast(loop: asyncio.AbstractEventLoop) -> None:
    processing_queue.set_main_loop(loop)
    processing_queue.set_broadcast(_broadcast)
    processing_queue.load_persisted()


def _queue_response(snap: dict[str, Any]) -> ProcessingQueueResponse:
    return ProcessingQueueResponse(
        stt=ProcessingQueueSection(
            items=[ProcessingQueueItem(**i) for i in snap["stt"]["items"]],
            running=snap["stt"]["running"],
        ),
        subtitle=ProcessingQueueSection(
            items=[ProcessingQueueItem(**i) for i in snap["subtitle"]["items"]],
            running=snap["subtitle"]["running"],
        ),
        planned=snap.get("planned"),
        warnings=snap.get("warnings"),
        folder_path=snap.get("folder_path"),
    )


@router.get("/queue", response_model=ProcessingQueueResponse)
async def get_queue():
    return _queue_response(processing_queue.snapshot())


@router.post("/add", response_model=ProcessingQueueResponse)
async def add_to_queue(body: AddProcessingRequest):
    try:
        snap = processing_queue.add_paths(body.kind, body.paths)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    await _broadcast_state()
    return _queue_response(snap)


@router.post("/products", response_model=ProcessingQueueResponse)
async def add_products(body: AddProcessingProductsRequest):
    try:
        snap = processing_queue.add_products(body.kind, body.product_codes)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    await _broadcast_state()
    return _queue_response(snap)


@router.post("/folder", response_model=ProcessingQueueResponse)
async def add_folder(body: ProcessingFolderRequest):
    try:
        snap = processing_queue.add_folder(body.kind, body.folder_path)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    await _broadcast_state()
    return _queue_response(snap)


@router.delete("/item/{kind}/{item_id}")
async def remove_item(kind: str, item_id: str):
    if kind not in ("stt", "subtitle"):
        raise HTTPException(400, "kind must be stt or subtitle")
    try:
        processing_queue.remove_item(kind, item_id)
    except KeyError:
        raise HTTPException(404, "항목을 찾을 수 없습니다") from None
    except RuntimeError:
        raise HTTPException(400, "실행 중인 항목은 삭제할 수 없습니다. 취소 API를 사용하세요.") from None
    await _broadcast_state()
    return {"ok": True}


@router.post("/start")
async def start_queue(body: ProcessingKindRequest):
    try:
        queued = await processing_queue.start(body.kind)
    except RuntimeError as e:
        msg = str(e)
        if msg == "already_running":
            raise HTTPException(400, "이미 실행 중입니다") from None
        raise HTTPException(400, "대기 중인 항목이 없습니다") from None
    await _broadcast_state()
    return {"ok": True, "queued": queued}


@router.post("/cancel")
async def cancel_queue(body: ProcessingKindRequest):
    try:
        await processing_queue.cancel(body.kind)
    except RuntimeError:
        raise HTTPException(400, "실행 중인 큐가 없습니다") from None
    return {"ok": True}


@router.post("/clear-finished")
async def clear_finished(body: ProcessingKindRequest):
    removed = processing_queue.clear_finished(body.kind)
    processing_queue.persist_queue()
    await _broadcast_state()
    return {"ok": True, "removed": removed}


@router.post("/clear")
async def clear_queue(body: ProcessingKindRequest):
    try:
        removed = await processing_queue.clear_queue(body.kind)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    await _broadcast_state()
    return {"ok": True, "removed": removed}


@router.websocket("/ws")
async def processing_ws(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)
    try:
        snap = processing_queue.snapshot()
        await ws.send_text(json.dumps({"type": "state", **snap}, ensure_ascii=False))
        while True:
            await ws.receive_text()
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        try:
            _ws_clients.remove(ws)
        except ValueError:
            pass
