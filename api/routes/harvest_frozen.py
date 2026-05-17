"""Harvest API stubs — always 410 when legacy API is disabled."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket

from api._freeze import FROZEN_DETAIL, frozen_http_exception

router = APIRouter()


def _frozen():
    raise frozen_http_exception()


@router.get("/queue")
async def get_queue():
    _frozen()


@router.post("/add")
async def add_to_queue():
    _frozen()


@router.delete("/queue/{item_id}")
async def remove_from_queue(item_id: str):
    _frozen()


@router.post("/start")
async def start_harvest():
    _frozen()


@router.post("/clear")
async def clear_queue():
    _frozen()


@router.websocket("/ws")
async def harvest_ws(ws: WebSocket):
    await ws.accept()
    await ws.send_json({"type": "frozen", **FROZEN_DETAIL})
    await ws.close(code=1008, reason="API frozen")
