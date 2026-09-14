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


def is_free_tier_daily_quota_exceeded(exc_or_msg: BaseException | str) -> bool:
    """Gemini FreeTier 일일(day) quota 초과 여부 — RPM(분당) 초과와 구분해 장기 쿨다운 판단에 쓴다.

    `router.route()`는 실패를 `AllTiersExhaustedError`로 감싸며 원문 메시지는
    `.last_error`에만 남기고 `str(e)`는 고정 요약 문구가 되므로, 예외 객체를 받으면
    `last_error`까지 확인한다(`is_context_size_exceeded`와 동일 패턴).
    """
    if isinstance(exc_or_msg, BaseException):
        last = getattr(exc_or_msg, "last_error", None)
        if last and is_free_tier_daily_quota_exceeded(str(last)):
            return True
        msg = str(exc_or_msg or "")
    else:
        msg = str(exc_or_msg or "")
    s = msg.lower()
    if "generaterequestsperdayperprojectpermodel-freetier" in s.replace(" ", ""):
        return True
    if "requests, limit: 20" in s:
        return True
    # Google 쿼터 메타 실패(QuotaFailure)의 quota_metric/quota_id는 일일 한도일 때
    # 관례적으로 "PerDay"를 포함한다 — 정확한 모델별 문자열이 바뀌어도 넓게 잡는다.
    compact = s.replace("_", "").replace(" ", "")
    if "resource_exhausted" in s and "perday" in compact:
        return True
    if "quota" in s and "perday" in compact:
        return True
    return False


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


def is_model_not_found(exc_or_msg: BaseException | str) -> bool:
    """모델이 폐기·이동되어 영구적으로 404를 내는 경우(동일 요청 재시도 무의미).

    예: Gemini가 구버전 모델을 은퇴시키면 ``models/gemini-2.0-flash-lite is no
    longer available`` 같은 404 NOT_FOUND를 반환한다 — 몇 초 뒤 재시도해도
    똑같이 실패하므로, 429/타임아웃과 달리 백오프 재시도 대상에서 제외한다.
    """
    if isinstance(exc_or_msg, BaseException):
        last = getattr(exc_or_msg, "last_error", None)
        if last and is_model_not_found(str(last)):
            return True
        status = getattr(exc_or_msg, "status_code", None)
        msg = str(exc_or_msg or "")
    else:
        status = None
        msg = str(exc_or_msg or "")
    s = msg.lower()
    has_404 = status == 404 or "404" in s or "not_found" in s or "'status': 'not_found'" in s
    if not has_404:
        return False
    return "no longer available" in s or "not_found" in s or "not found" in s


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
    if is_context_size_exceeded(e) or is_model_not_found(e):
        return False
    msg = str(e).lower()
    # 단어 경계 매칭 — 순수 substring이면 "recommend"/"delimiter"/"unlimited" 같은
    # 무관한 단어에 "rate"/"limit"이 우연히 포함돼 영구 오류까지 재시도 대상으로 오판한다.
    if "429" in msg or re.search(r"\brate\b", msg) or re.search(r"\blimit\b", msg) or "timeout" in msg:
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
