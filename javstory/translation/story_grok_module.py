"""
Grok 웹검색 스토리 맥락(JSON 캐시) — **공통 SoT**.

- **생성**: Harvest 단계에서 Grok API로 캐시 생성
- **소비**: `load_cached_grok_json` (API 없음, tone 주입용)
- 중간 LLM 분석(story_context_report)은 제거됨.
  Harvest에서 이미 캐시된 JSON을 직접 사용.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Optional

from javstory.config.app_config import story_context_llm_tier
from javstory.llm.engine import MultiTierRouter
from .story_context_prompts import (
    SYSTEM_STORY_CONTEXT_GROK,
    render_story_context_user_message,
    parse_grok_story_json,
    story_context_json_dumps,
)

OptionalLogger = Optional[Callable[[str], None]]

_ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve_openrouter_api_key() -> str:
    """
    Grok 캐시 생성용 OpenRouter API 키를 해석한다.
    우선순위:
    - (레거시) JAVSTORY_OPENROUTER_API_KEY
    - (표준) OPENROUTER_API_KEY (secrets_manager가 관리)
    - keyring/.env 기반 secrets_manager.get_openrouter_api_key()
    """
    k = (os.environ.get("JAVSTORY_OPENROUTER_API_KEY") or "").strip()
    if k:
        return k
    k = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if k:
        return k
    try:
        from javstory.config import secrets_manager

        k2 = secrets_manager.get_openrouter_api_key() or ""
        return k2.strip()
    except Exception:
        return ""


def story_context_cache_dir() -> Path:
    d = _ROOT / "Transcription" / "story_context_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def story_context_cache_path(product_code: str, model_hint: str = "") -> Path:
    pc = re.sub(r"[^\w\-.]", "_", product_code.strip(), flags=re.ASCII) or "unknown"
    suffix = re.sub(r"[^\w\-.]", "_", model_hint.strip(), flags=re.ASCII) if model_hint else ""
    name = f"{pc}__{suffix}.json" if suffix else f"{pc}.json"
    return story_context_cache_dir() / name


def merge_story_context_tier(raw: dict[str, Any] | None) -> dict[str, Any]:
    """env 기본 `story_context_llm_tier`에 호출자 오버라이드를 합친다."""
    base = story_context_llm_tier()
    if isinstance(raw, dict) and raw:
        return {**base, **raw}
    return base


async def run_story_grok_after_harvest_async(
    *,
    product_code: str,
    logger_func: Any,
    story_context_tier: dict[str, Any] | None = None,
    force_refresh: bool = False,
) -> None:
    """
    Harvest 메타 저장 직후 호출: OpenRouter 키가 있으면 Grok 스토리 캐시를 채운다.
    """
    log = logger_func
    pc = (product_code or "").strip().upper()
    if not pc:
        return

    tier = merge_story_context_tier(story_context_tier)
    model_name = tier.get("model", "")
    provider = str(tier.get("provider") or "openrouter").strip().lower()
    path = story_context_cache_path(pc, str(model_name))

    if path.is_file() and not force_refresh:
        log(f"✅ Grok 스토리 캐시 이미 존재: {path.name}")
        return

    api_key = _resolve_openrouter_api_key()
    if not api_key:
        log("⚠️ Grok 수집 스킵: OpenRouter API 키가 없습니다. (JAVSTORY_OPENROUTER_API_KEY / OPENROUTER_API_KEY / keyring)")
        return

    log(f"🚀 Grok 웹검색 스토리 분석 시작: {pc} (Model: {model_name})")

    router: MultiTierRouter | None = None
    try:
        messages = [
            {"role": "system", "content": SYSTEM_STORY_CONTEXT_GROK},
            {"role": "user", "content": render_story_context_user_message(product_code=pc)},
        ]

        router = MultiTierRouter(api_key=api_key, logger_func=log)
        # Grok 모델은 웹 검색 성능을 위해 json_mode 없이 자연어 응답에서 추출 선호할 수 있으나,
        # 프롬프트에서 이미 JSON만 요청하므로 route() 호출.
        # :online 모델의 경우 가끔 JSON 모드가 안 될 수 있으므로 일반 호출 후 파싱.
        res_raw = await router.route(messages, tier_override=tier, json_mode=False)
        log(f"✅ [Grok4.1 실제 응답 ({pc})]:\n{res_raw}\n")

        data = parse_grok_story_json(res_raw)
        if not data:
            log(f"❌ Grok 응답 파싱 실패 (JSON 형식 아님).")
            return

        # 캐시 저장
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(story_context_json_dumps(data), encoding="utf-8")
        log(f"✅ Grok 스토리 캐시 생성 완료: {path.name}")

    except Exception as e:
        log(f"❌ Grok 스토리 분석 중 오류 발생: {e}")
    finally:
        # AsyncOpenAI/httpx 연결 정리 — 미호출 시 루프 종료 후 aclose 되며 RuntimeError 발생 가능
        if router is not None:
            try:
                await router.close()
            except Exception:
                pass


def load_cached_grok_json(
    product_code: str,
    story_context_tier: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """디스크 캐시 JSON만 로드(API 없음). KO 번역 청크의 scene tone 등에 사용."""
    pc = (product_code or "").strip()
    if not pc:
        return None
    tier = merge_story_context_tier(story_context_tier)
    path = story_context_cache_path(pc, str(tier.get("model") or ""))
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def load_cached_grok_json_flexible(
    product_code: str,
    story_context_tier: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """디스크 캐시 로드. 기본 경로 실패 시 라이브러리 그리드와 동일한 레거시 파일명·glob 폴백."""
    tier = merge_story_context_tier(story_context_tier)
    raw = (product_code or "").strip()
    if not raw:
        return None
    pc_upper = raw.upper()

    hit = load_cached_grok_json(raw, tier)
    if hit:
        return hit
    hit = load_cached_grok_json(pc_upper, tier)
    if hit:
        return hit

    model = str(tier.get("model") or "")

    def _read(path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    legacy_hints = [
        "",
        f"{model}:online" if model and ":online" not in model else "",
        "x-ai/grok-4.1-fast:online",
        "grok-4-fast:online",
    ]
    for hint in legacy_hints:
        cand = story_context_cache_path(pc_upper, hint)
        got = _read(cand)
        if got:
            return got

    try:
        pc_prefix = f"{pc_upper}__"
        d = story_context_cache_dir()
        matches = [p for p in d.glob(f"{pc_prefix}*.json") if p.is_file()]
        if matches:
            matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            got = _read(matches[0])
            if got:
                return got
    except Exception:
        pass

    return None


__all__ = [
    "merge_story_context_tier",
    "run_story_grok_after_harvest_async",
    "load_cached_grok_json",
    "load_cached_grok_json_flexible",
    "story_context_cache_dir",
    "story_context_cache_path",
]
