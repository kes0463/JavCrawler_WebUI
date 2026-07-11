"""자막 번역 시 Grok 캐시 미스·크레딧 실패 건너뛰기."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from javstory.llm.engine import AllTiersExhaustedError
from javstory.translation import subtitle_pipeline_orchestrator as orch_mod


def test_load_grok_cache_async_continues_when_grok_fetch_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    logs: list[str] = []

    async def _fake_ensure(**kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        orch_mod,
        "ensure_grok_story_cache_for_translation",
        _fake_ensure,
    )

    async def _run() -> tuple[dict | None, str]:
        return await orch_mod._load_grok_cache_async("ABW-001", None, logs.append)

    grok, hints = asyncio.run(_run())
    assert grok is None
    assert hints == ""
    assert any("DB 배경만으로 번역 계속" in m for m in logs)


def test_run_story_grok_skips_on_credit_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    from javstory.translation import story_grok_module as grok_mod

    logs: list[str] = []
    router = MagicMock()
    router.route = AsyncMock(
        side_effect=AllTiersExhaustedError(
            "fail",
            last_error="402 insufficient credits",
        )
    )
    router.close = AsyncMock()

    monkeypatch.setattr(grok_mod, "_resolve_openrouter_api_key", lambda: "test-key")
    monkeypatch.setattr(grok_mod, "MultiTierRouter", lambda **kw: router)
    monkeypatch.setattr(grok_mod, "parse_grok_story_json", lambda raw: {"product_code": "ABW-001"})
    monkeypatch.setattr(
        grok_mod,
        "story_context_cache_path_grok",
        lambda pc: grok_mod.Path("/nonexistent/ABW-001_grok.json"),
    )
    monkeypatch.setattr(grok_mod, "_legacy_model_suffix_cache_exists", lambda pc: False)

    async def _run() -> None:
        await grok_mod.run_story_grok_after_harvest_async(
            product_code="ABW-001",
            logger_func=logs.append,
        )

    asyncio.run(_run())
    assert any("크레딧 부족" in m and "번역은 Grok 없이" in m for m in logs)
