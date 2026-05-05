"""
OpenRouter 등 API 호출 공통: 지수 백오프 + 지터, 429/타임아웃 재시도.
`correction_chunk`·`ko_translation_chunk`에서 공유 (순환 import 방지).
"""
from __future__ import annotations

import asyncio
import random
import re
from typing import Any, Callable, Dict, List

from javstory.transcription.stt_types import STTCancelled

RetryLog = Callable[[str], None]

def _parse_retry_after_seconds(msg: str) -> float | None:
    """429 메시지 내 retryDelay(초)를 최대한 보수적으로 파싱."""
    s = (msg or "")
    m = re.search(r"retryDelay['\"]\s*:\s*['\"](?P<sec>\d+)s", s)
    if m:
        try:
            return float(m.group("sec"))
        except Exception:
            return None
    m2 = re.search(r"Please retry in\s+(?P<sec>[0-9]+(?:\.[0-9]+)?)s", s)
    if m2:
        try:
            return float(m2.group("sec"))
        except Exception:
            return None
    return None


def is_free_tier_daily_quota_exceeded(msg: str) -> bool:
    """Gemini FreeTier 일 quota 초과(20/day 등) 여부."""
    s = (msg or "")
    return "GenerateRequestsPerDayPerProjectPerModel-FreeTier" in s or "requests, limit: 20" in s


def retryable_api_error(e: BaseException) -> bool:
    msg = str(e).lower()
    if "429" in msg or "rate" in msg or "limit" in msg or "timeout" in msg:
        return True
    try:
        import openai

        if isinstance(e, openai.RateLimitError):
            return True
        sc = getattr(e, "status_code", None)
        if sc == 429:
            return True
    except Exception:
        pass
    return isinstance(e, (asyncio.TimeoutError, TimeoutError))


async def route_with_backoff(
    router: Any,
    messages: List[Dict[str, str]],
    tier: Dict[str, Any],
    *,
    log: RetryLog,
    json_mode: bool = False,
    max_attempts: int = 6,
) -> str:
    last: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return await router.route(messages, tier_override=tier, json_mode=json_mode)
        except STTCancelled:
            raise
        except Exception as e:
            last = e
            if attempt >= max_attempts - 1 or not retryable_api_error(e):
                raise
            # Gemini 429는 RetryInfo/retryDelay를 존중(불필요한 실패/쿼터 소모 방지)
            msg = str(e)
            retry_after = _parse_retry_after_seconds(msg)
            if retry_after is not None:
                wait = min(180.0, max(1.0, float(retry_after)) + random.uniform(0, 1.0))
            else:
                wait = min(180.0, (2**attempt) * 2.0 + random.uniform(0, 2.0))
            log(
                f"API 재시도 {attempt + 1}/{max_attempts} ({e!s:.120}) sleep {wait:.1f}s"
            )
            await asyncio.sleep(wait)
    assert last is not None
    raise last
