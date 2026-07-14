"""로컬(llama.cpp) 번역 컨텍스트 절약·초과 감지."""

from __future__ import annotations

import asyncio
import json

import pytest

from javstory.llm.engine import AllTiersExhaustedError
from javstory.translation.ko_translation_chunk import (
    _compact_background_json_for_local,
    _default_chunk_durations,
    _story_hints_for_tier,
)
from javstory.translation.llm_backoff import is_context_size_exceeded, retryable_api_error


def test_is_context_size_exceeded_message() -> None:
    msg = (
        "Error code: 400 - {'error': {'code': 400, "
        "'message': 'request (2013 tokens) exceeds the available context size (1792 tokens)', "
        "'type': 'exceed_context_size_error', 'n_prompt_tokens': 2013, 'n_ctx': 1792}}"
    )
    assert is_context_size_exceeded(msg)
    assert not retryable_api_error(Exception(msg))


def test_is_context_size_exceeded_via_all_tiers_last_error() -> None:
    detail = "request (2013 tokens) exceeds the available context size (1792 tokens)"
    err = AllTiersExhaustedError("모든 AI 티어가 실패", last_model="local", last_error=detail)
    assert is_context_size_exceeded(err)


def test_await_cancellable_raises_on_cancel() -> None:
    from javstory.transcription.stt_types import STTCancelled
    from javstory.translation.llm_backoff import await_cancellable

    cancelled = {"v": False}

    async def slow() -> str:
        await asyncio.sleep(5)
        return "done"

    async def _run() -> None:
        async def flip() -> None:
            await asyncio.sleep(0.05)
            cancelled["v"] = True

        asyncio.create_task(flip())
        with pytest.raises(STTCancelled):
            await await_cancellable(slow(), should_cancel=lambda: cancelled["v"], poll_sec=0.05)

    asyncio.run(_run())


def test_compact_background_truncates_synopsis() -> None:
    bg = json.dumps(
        {
            "product_code": "GVH-684",
            "synopsis_short": "가" * 500,
            "genres": "장르," * 80,
        },
        ensure_ascii=False,
    )
    out = json.loads(_compact_background_json_for_local(bg))
    assert out["product_code"] == "GVH-684"
    assert len(out["synopsis_short"]) <= 181


def test_story_hints_for_local_are_compact() -> None:
    grok = {
        "verification_ok": True,
        "product_code": "GVH-684",
        "actress": "A",
        "overall_summary": "요약 " * 100,
        "scenes": [
            {
                "scene_id": "S01",
                "scene_label": "목격",
                "scene_summary": "긴 본문 " * 50,
                "tone": "긴장",
            }
        ],
    }
    local = _story_hints_for_tier(
        {"provider": "llamacpp", "model": "Qwen2.5-14B"},
        story_context_hints="ignored-full",
        story_context_grok_json=grok,
    )
    cloud = _story_hints_for_tier(
        {"provider": "openrouter", "model": "x"},
        story_context_hints="클라우드 힌트 전문",
        story_context_grok_json=None,
    )
    assert "긴 본문" not in local
    assert "S01" in local
    assert "클라우드 힌트 전문" in cloud


def test_llamacpp_default_chunk_is_short() -> None:
    tgt, ov = _default_chunk_durations(
        {"provider": "llamacpp", "model": "Qwen2.5-14B-Instruct-Q5_K_M"}
    )
    assert tgt <= 12.0
    assert ov <= 4.0
