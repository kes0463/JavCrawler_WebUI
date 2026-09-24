from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from javstory.persona import chat_sessions
from javstory.persona.persona_chat import ENHANCED_PERSONA_MEMORY_PATH, PersonaChatService
from webapi.schemas import (
    PersonaChatMessageRequest,
    PersonaChatSessionDetail,
    PersonaChatSessionRenameRequest,
    PersonaChatSessionSummary,
    PersonaChatSessionsResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_service = PersonaChatService()
try:
    _service.enhanced_memory_store.load_from_json(str(ENHANCED_PERSONA_MEMORY_PATH))
except Exception as e:
    logger.warning("페르소나챗 메모리 로드 실패(무시하고 빈 메모리로 시작): %s", e)


async def _sse_gen(
    request: Request,
    session_id: str | None,
    message: str,
    history: list[dict[str, str]],
    product_code: str | None,
):
    agen = _service.stream_chat(message, history=history, product_code=product_code)
    full_text = ""
    reasoning = ""
    try:
        async for event in agen:
            if event.get("type") == "reasoning":
                reasoning += str(event.get("text") or "")
            elif event.get("type") == "done":
                full_text = str(event.get("text") or "")
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if await request.is_disconnected():
                await agen.aclose()
                return
    except Exception as e:
        logger.exception("페르소나챗 스트리밍 중 오류")
        err = {"type": "error", "message": str(e)}
        yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
    finally:
        if session_id and full_text:
            try:
                chat_sessions.append_turn(session_id, message, full_text, reasoning=reasoning)
            except Exception:
                logger.exception("페르소나챗 세션 저장 실패")
    yield "data: [DONE]\n\n"


@router.post("/message")
async def persona_chat_message(request: Request, body: PersonaChatMessageRequest):
    return StreamingResponse(
        _sse_gen(request, body.session_id, body.message, body.history, body.product_code),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions", response_model=PersonaChatSessionsResponse)
def persona_chat_list_sessions():
    return PersonaChatSessionsResponse(sessions=chat_sessions.list_sessions())


@router.post("/sessions", response_model=PersonaChatSessionDetail)
def persona_chat_create_session():
    return PersonaChatSessionDetail(**chat_sessions.create_session())


@router.get("/sessions/{session_id}", response_model=PersonaChatSessionDetail)
def persona_chat_get_session(session_id: str):
    session = chat_sessions.get_session(session_id)
    if session is None:
        raise HTTPException(404, "대화를 찾을 수 없습니다")
    return PersonaChatSessionDetail(**session)


@router.patch("/sessions/{session_id}", response_model=PersonaChatSessionSummary)
def persona_chat_rename_session(session_id: str, body: PersonaChatSessionRenameRequest):
    session = chat_sessions.rename_session(session_id, body.title)
    if session is None:
        raise HTTPException(404, "대화를 찾을 수 없습니다")
    return PersonaChatSessionSummary(**session)


@router.delete("/sessions/{session_id}")
def persona_chat_delete_session(session_id: str):
    if not chat_sessions.delete_session(session_id):
        raise HTTPException(404, "대화를 찾을 수 없습니다")
    return {"deleted": True}
