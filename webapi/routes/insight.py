from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from javstory.services.insight_service import InsightService
from webapi.schemas import (
    InsightCollectionResponse,
    InsightOverviewResponse,
    InsightPersonaCardResponse,
    InsightRecommendResponse,
    InsightTrendsResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)
_insight = InsightService()

_ws_clients: list[WebSocket] = []
_ws_lock = asyncio.Lock()
_refresh_running = False


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


@router.get("/overview", response_model=InsightOverviewResponse)
def insight_overview(force: bool = Query(False, description="캐시 무시 재조회")):
    data = _insight.fetch_overview(force_refresh=force)
    return InsightOverviewResponse(**data)


@router.get("/trends", response_model=InsightTrendsResponse)
def insight_trends():
    data = _insight.fetch_trends()
    return InsightTrendsResponse(**data)


@router.get("/recommend", response_model=InsightRecommendResponse)
def insight_recommend(force: bool = Query(False, description="추천 캐시 무시 재조회")):
    data = _insight.fetch_recommend(force_refresh=force)
    return InsightRecommendResponse(**data)


@router.get("/collection", response_model=InsightCollectionResponse)
def insight_collection(force: bool = Query(False)):
    data = _insight.fetch_collection(force_refresh=force)
    return InsightCollectionResponse(**data)


@router.get("/persona-card", response_model=InsightPersonaCardResponse)
async def insight_persona_card(force: bool = Query(False, description="LLM 재합성 강제")):
    from javstory.analytics.persona_card import get_persona_card

    data = await asyncio.to_thread(get_persona_card, cache_only=not force)
    return InsightPersonaCardResponse(**data)


@router.post("/refresh")
async def insight_refresh():
    """단계별 진행률을 /ws로 브로드캐스트하며 백그라운드에서 새로고침 실행."""
    global _refresh_running
    if _refresh_running:
        return {"started": False, "already_running": True}
    _refresh_running = True
    asyncio.create_task(_run_refresh_job())
    return {"started": True}


async def _run_refresh_job() -> None:
    global _refresh_running
    from javstory.analytics.persona_card import get_persona_card

    _insight.invalidate_recommend_cache()
    await _broadcast({"type": "progress", "phase": "start", "progress": 0})
    try:
        await asyncio.to_thread(_insight.fetch_phase, "core", force_refresh=True)
        await _broadcast({"type": "progress", "phase": "core", "progress": 10})

        await asyncio.to_thread(get_persona_card, force_refresh=True)
        await _broadcast({"type": "progress", "phase": "persona_card", "progress": 30})

        await asyncio.to_thread(_insight.fetch_phase, "trends", force_refresh=True)
        await _broadcast({"type": "progress", "phase": "trends", "progress": 60})

        await asyncio.to_thread(_insight.fetch_phase, "recommend", force_refresh=True)
        await _broadcast({"type": "progress", "phase": "recommend", "progress": 80})

        await asyncio.to_thread(_insight.fetch_phase, "collection", force_refresh=True)
        await _broadcast({"type": "progress", "phase": "collection", "progress": 95})

        await _broadcast({"type": "refresh_complete", "progress": 100})
    except Exception as e:
        logger.exception("Insight 새로고침 실패")
        await _broadcast({"type": "refresh_error", "message": str(e)})
    finally:
        # 새로고침마다 llama-server를 껐다 켜면 모델을 매번 처음부터 재로딩하게 돼
        # (대형 모델은 수십 초~분 단위) 느려진다 — 이제 서버를 켜둔 채로 두고
        # 기존 유휴 타임아웃(기본 5분)이 알아서 정리하게 한다.
        _refresh_running = False


@router.websocket("/ws")
async def insight_ws(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)
    try:
        await ws.send_text(
            json.dumps({"type": "state", "refreshing": _refresh_running}, ensure_ascii=False)
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
