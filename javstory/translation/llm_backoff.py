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


def is_openrouter_credit_exhausted(exc_or_msg: BaseException | str) -> bool:
    """OpenRouter 402·크레딧 부족 메시지 여부 (재시도·Grok 스킵 판단용)."""
    if isinstance(exc_or_msg, BaseException):
        status = getattr(exc_or_msg, "status_code", None)
        if status == 402:
            return True
        body = getattr(exc_or_msg, "body", None)
        if body is not None and is_openrouter_credit_exhausted(str(body)):
            return True
        msg = str(exc_or_msg)
    else:
        msg = str(exc_or_msg or "")
    s = msg.lower()
    if "insufficient credit" in s:
        return True
    if "payment required" in s:
        return True
    if "402" in s and ("credit" in s or "payment" in s):
        return True
    if "more credits" in s and ("afford" in s or "openrouter" in s or "max_tokens" in s):
        return True
    return False


def is_context_size_exceeded(exc_or_msg: BaseException | str) -> bool:
    """llama.cpp 등: 프롬프트가 n_ctx를 넘는 오류(동일 요청 재시도 무의미)."""
    if isinstance(exc_or_msg, BaseException):
        last = getattr(exc_or_msg, "last_error", None)
        if last and is_context_size_exceeded(str(last)):
            return True
        msg = str(exc_or_msg or "")
    else:
        msg = str(exc_or_msg or "")
    s = msg.lower()
    if "exceed_context_size" in s:
        return True
    if "exceeds the available context size" in s:
        return True
    if "n_prompt_tokens" in s and "n_ctx" in s and "exceed" in s:
        return True
    return False


async def await_cancellable(
    coro: Any,
    *,
    should_cancel: Callable[[], bool] | None = None,
    poll_sec: float = 0.4,
) -> Any:
    """코루틴 대기 중 should_cancel이 True면 task를 취소하고 STTCancelled를 올린다."""
    if should_cancel is None:
        return await coro
    task = asyncio.ensure_future(coro)
    try:
        while True:
            if should_cancel():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
                raise STTCancelled()
            done, _ = await asyncio.wait({task}, timeout=max(0.1, poll_sec))
            if done:
                return await task
    except STTCancelled:
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        raise


def retryable_api_error(e: BaseException) -> bool:
    if is_context_size_exceeded(e):
        return False
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
    should_cancel: Callable[[], bool] | None = None,
) -> str:
    last: BaseException | None = None
    for attempt in range(max_attempts):
        if should_cancel and should_cancel():
            raise STTCancelled()
        try:
            return await await_cancellable(
                router.route(messages, tier_override=tier, json_mode=json_mode),
                should_cancel=should_cancel,
            )
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
            # sleep 중에도 취소 반영
            slept = 0.0
            while slept < wait:
                if should_cancel and should_cancel():
                    raise STTCancelled()
                step = min(0.4, wait - slept)
                await asyncio.sleep(step)
                slept += step
    assert last is not None
    raise last
