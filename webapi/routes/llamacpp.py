from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from javstory.config.secrets_manager import set_env_runtime_value
from javstory.llm.llamacpp_backend import (
    LLAMACPP_MODEL_PRESETS,
    ensure_llamacpp_server_ready,
    llamacpp_server_status,
)
from webapi.schemas import (
    LlamaCppModelOption,
    LlamaCppModelsResponse,
    LlamaCppSelectRequest,
    LlamaCppSelectResponse,
    LlamaCppStatusResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_FEATURE_ENV_KEY = {
    "insight": "JAVSTORY_PERSONA_CARD_PRESET",
    "persona_chat": "JAVSTORY_PERSONA_CHAT_MODEL",
}


@router.get("/models", response_model=LlamaCppModelsResponse)
def llamacpp_models():
    from javstory.analytics.persona_card import persona_card_model_from_env
    from javstory.persona.persona_chat import persona_chat_model_from_env

    options = [
        LlamaCppModelOption(id=pid, label=preset.label)
        for pid, preset in LLAMACPP_MODEL_PRESETS.items()
    ]
    return LlamaCppModelsResponse(
        models=options,
        insight_active_preset_id=persona_card_model_from_env(),
        persona_chat_active_preset_id=persona_chat_model_from_env(),
    )


@router.get("/status", response_model=LlamaCppStatusResponse)
async def llamacpp_status():
    status = await asyncio.to_thread(llamacpp_server_status)
    return LlamaCppStatusResponse(**status)


@router.post("/select", response_model=LlamaCppSelectResponse)
async def llamacpp_select(body: LlamaCppSelectRequest):
    if body.preset_id not in LLAMACPP_MODEL_PRESETS:
        raise HTTPException(400, f"알 수 없는 모델: {body.preset_id}")

    env_key = _FEATURE_ENV_KEY[body.feature]
    set_env_runtime_value(env_key, body.preset_id)

    status = await asyncio.to_thread(llamacpp_server_status)
    if status["state"] in ("ready", "busy") and status["active_preset_id"] == body.preset_id:
        return LlamaCppSelectResponse(accepted=True, already_active=True)

    def _spawn() -> None:
        try:
            ensure_llamacpp_server_ready(
                {"model": body.preset_id, "provider": "llamacpp"}, wait_sec=120.0
            )
        except Exception as e:
            logger.warning("llama.cpp 모델 전환 실패(%s): %s", body.preset_id, e)

    asyncio.create_task(asyncio.to_thread(_spawn))
    return LlamaCppSelectResponse(accepted=True, already_active=False)
