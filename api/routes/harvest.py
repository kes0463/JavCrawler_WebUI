from __future__ import annotations

import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException

from api.schemas import HarvestItem, AddHarvestRequest, HarvestQueueResponse

router = APIRouter()

# ── 인메모리 큐 상태 ────────────────────────────────────────────────
_queue: list[HarvestItem] = []
_running = False
_executor = ThreadPoolExecutor(max_workers=1)
_ws_clients: list[WebSocket] = []


async def _broadcast(event: dict[str, Any]) -> None:
    dead = []
    for ws in _ws_clients:
        try:
            await ws.send_text(json.dumps(event, ensure_ascii=False))
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.remove(ws)


def _update_item(item_id: str, **kwargs: Any) -> HarvestItem | None:
    for item in _queue:
        if item.id == item_id:
            for k, v in kwargs.items():
                setattr(item, k, v)
            return item
    return None


# ── 실제 수집 실행 (스레드) ──────────────────────────────────────────

def _run_harvest_sync(item: HarvestItem) -> None:
    """ThreadPoolExecutor 안에서 동기 크롤링 실행."""
    import sys
    from pathlib import Path
    import asyncio

    _ROOT = Path(__file__).resolve().parent.parent.parent
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))

    from javstory.harvest.coordinator import run_crawler_for_video_path

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _progress_cb(sku: str, msg: str, pct: int) -> None:
        asyncio.run_coroutine_threadsafe(
            _broadcast({"type": "progress", "id": item.id, "sku": sku, "message": msg, "progress": pct}),
            asyncio.get_event_loop(),
        )

    try:
        loop.run_until_complete(
            run_crawler_for_video_path(
                target=item.target,
                is_path=False,
                product_code=item.product_code or item.target,
                progress_cb=_progress_cb,
            )
        )
    except Exception as e:
        raise RuntimeError(str(e)) from e
    finally:
        loop.close()


async def _run_queue() -> None:
    global _running
    _running = True
    await _broadcast({"type": "queue_started"})

    for item in _queue:
        if item.status != "pending":
            continue

        _update_item(item.id, status="running", progress=0, message="수집 시작...")
        await _broadcast({"type": "item_started", "id": item.id})

        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(_executor, _run_harvest_sync, item)
            _update_item(item.id, status="done", progress=100, message="완료")
            await _broadcast({"type": "item_done", "id": item.id})
        except Exception as e:
            _update_item(item.id, status="error", message=str(e))
            await _broadcast({"type": "item_error", "id": item.id, "message": str(e)})

    _running = False
    await _broadcast({"type": "queue_finished"})


# ── 엔드포인트 ──────────────────────────────────────────────────────

@router.get("/queue", response_model=HarvestQueueResponse)
def get_queue():
    return HarvestQueueResponse(items=list(_queue), running=_running)


@router.post("/add", response_model=HarvestQueueResponse)
def add_to_queue(body: AddHarvestRequest):
    for code in body.codes:
        code = code.strip().upper()
        if not code:
            continue
        if any(i.target == code for i in _queue):
            continue
        _queue.append(HarvestItem(
            id=str(uuid.uuid4()),
            target=code,
            product_code=code,
        ))
    return HarvestQueueResponse(items=list(_queue), running=_running)


@router.delete("/queue/{item_id}")
def remove_from_queue(item_id: str):
    global _queue
    item = next((i for i in _queue if i.id == item_id), None)
    if not item:
        raise HTTPException(404, "항목을 찾을 수 없습니다")
    if item.status == "running":
        raise HTTPException(400, "실행 중인 항목은 삭제할 수 없습니다")
    _queue = [i for i in _queue if i.id != item_id]
    return {"ok": True}


@router.post("/start")
async def start_harvest():
    if _running:
        raise HTTPException(400, "이미 실행 중입니다")
    pending = [i for i in _queue if i.status == "pending"]
    if not pending:
        raise HTTPException(400, "대기 중인 항목이 없습니다")
    asyncio.create_task(_run_queue())
    return {"ok": True, "queued": len(pending)}


@router.post("/clear")
def clear_queue():
    global _queue
    if _running:
        raise HTTPException(400, "실행 중에는 초기화할 수 없습니다")
    _queue = []
    return {"ok": True}


@router.websocket("/ws")
async def harvest_ws(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)
    # 현재 상태 즉시 전송
    await ws.send_text(json.dumps({
        "type": "state",
        "running": _running,
        "items": [i.model_dump() for i in _queue],
    }, ensure_ascii=False))
    try:
        while True:
            await ws.receive_text()  # ping 수신 (연결 유지)
    except WebSocketDisconnect:
        _ws_clients.remove(ws)
