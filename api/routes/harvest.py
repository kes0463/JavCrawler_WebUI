"""Live Harvest API — mount only when JAVSTORY_ALLOW_FROZEN_API=1 (see api/main.py)."""

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

# asyncio.Lock: 모든 route handler를 async로 선언하면 이벤트 루프 단일 스레드에서
# 실행되므로 명시적 Lock 없이도 안전하지만, _broadcast는 스레드에서
# run_coroutine_threadsafe로 진입할 수 있어 리스트 복사본 순회를 사용한다.
_ws_lock = asyncio.Lock()

# _run_harvest_sync(스레드)에서 _broadcast를 스케줄링하기 위해 이벤트 루프를 저장한다.
_main_loop: asyncio.AbstractEventLoop | None = None


@router.on_event("startup")
async def _on_startup() -> None:
    global _main_loop
    _main_loop = asyncio.get_running_loop()


async def _broadcast(event: dict[str, Any]) -> None:
    async with _ws_lock:
        dead = []
        for ws in list(_ws_clients):  # 복사본 순회 — 수정 충돌 방지
            try:
                await ws.send_text(json.dumps(event, ensure_ascii=False))
            except Exception:
                dead.append(ws)
        for ws in dead:
            try:
                _ws_clients.remove(ws)
            except ValueError:
                pass


def _update_item(item_id: str, **kwargs: Any) -> HarvestItem | None:
    for item in _queue:
        if item.id == item_id:
            for k, v in kwargs.items():
                setattr(item, k, v)
            return item
    return None


# ── 실제 수집 실행 (스레드) ──────────────────────────────────────────

def _run_harvest_sync(item: HarvestItem, main_loop: asyncio.AbstractEventLoop) -> None:
    """ThreadPoolExecutor 안에서 동기 크롤링 실행."""
    import sys
    from pathlib import Path
    import asyncio as _asyncio

    _ROOT = Path(__file__).resolve().parent.parent.parent
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))

    from javstory.harvest.coordinator import run_crawler_for_video_path

    # 이 스레드 전용 이벤트 루프 — main_loop와 별개
    loop = _asyncio.new_event_loop()
    _asyncio.set_event_loop(loop)

    def _progress_cb(sku: str, msg: str, pct: int) -> None:
        # main_loop에 브로드캐스트 코루틴을 안전하게 스케줄링
        _asyncio.run_coroutine_threadsafe(
            _broadcast({"type": "progress", "id": item.id, "sku": sku, "message": msg, "progress": pct}),
            main_loop,
        )

    try:
        loop.run_until_complete(
            run_crawler_for_video_path(
                item.target,
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

    # 순회 중 외부에서 _queue가 교체될 수 있으므로 스냅샷으로 순회
    for item in list(_queue):
        if item.status != "pending":
            continue

        _update_item(item.id, status="running", progress=0, message="수집 시작...")
        await _broadcast({"type": "item_started", "id": item.id})

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(_executor, _run_harvest_sync, item, loop)
            _update_item(item.id, status="done", progress=100, message="완료")
            await _broadcast({"type": "item_done", "id": item.id})
        except Exception as e:
            _update_item(item.id, status="error", message=str(e))
            await _broadcast({"type": "item_error", "id": item.id, "message": str(e)})

    _running = False
    await _broadcast({"type": "queue_finished"})


# ── 엔드포인트 ──────────────────────────────────────────────────────
# 모든 route handler를 async로 선언 — 이벤트 루프에서 실행되므로
# _queue 접근 시 _run_queue 코루틴과 경쟁 조건이 발생하지 않는다.

@router.get("/queue", response_model=HarvestQueueResponse)
async def get_queue():
    return HarvestQueueResponse(items=list(_queue), running=_running)


@router.post("/add", response_model=HarvestQueueResponse)
async def add_to_queue(body: AddHarvestRequest):
    # body.codes는 스키마 validator에서 이미 strip·upper·형식 검증 완료
    for code in body.codes:
        if any(i.target == code for i in _queue):
            continue
        _queue.append(HarvestItem(
            id=str(uuid.uuid4()),
            target=code,
            product_code=code,
        ))
    return HarvestQueueResponse(items=list(_queue), running=_running)


@router.delete("/queue/{item_id}")
async def remove_from_queue(item_id: str):
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
    global _running
    if _running:
        raise HTTPException(400, "이미 실행 중입니다")
    pending = [i for i in _queue if i.status == "pending"]
    if not pending:
        raise HTTPException(400, "대기 중인 항목이 없습니다")
    # _running 플래그를 즉시 설정해 중복 시작 방지 (create_task 전에)
    _running = True
    asyncio.create_task(_run_queue())
    return {"ok": True, "queued": len(pending)}


@router.post("/clear")
async def clear_queue():
    global _queue
    if _running:
        raise HTTPException(400, "실행 중에는 초기화할 수 없습니다")
    _queue = []
    return {"ok": True}


@router.websocket("/ws")
async def harvest_ws(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)
    try:
        await ws.send_text(json.dumps({
            "type": "state",
            "running": _running,
            "items": [i.model_dump() for i in _queue],
        }, ensure_ascii=False))
        while True:
            await ws.receive_text()  # ping 수신 (연결 유지)
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        # 정상/비정상 종료 모두 클라이언트 제거 보장
        try:
            _ws_clients.remove(ws)
        except ValueError:
            pass
