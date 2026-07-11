"""
Grok 웹검색 스토리 맥락(JSON 캐시) — **공통 SoT**.

- **저장 파일명**: `{기준품번}_grok.json` (`__HD__A` 등 폴더·화질 꼬리는 제외 후 `strip_split_suffixes`)
- **레거시 읽기**: `{품번}__{모델슬러그}.json` 등 기존 규칙은 로드 폴백으로 계속 지원
- **생성**: Harvest / 라이브러리 스토리 컨텍스트 / 자막 교정 등에서 Grok API 후 위 경로에 저장
- **소비**: `load_cached_grok_json_flexible` 등(API 없음, tone 주입용)
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Optional

from javstory.config.app_config import story_context_llm_tier
from javstory.llm.engine import AllTiersExhaustedError, MultiTierRouter
from javstory.translation.llm_backoff import is_openrouter_credit_exhausted
from .story_context_prompts import (
    SYSTEM_STORY_CONTEXT_GROK,
    render_story_context_user_message,
    parse_grok_story_json,
    story_context_json_dumps,
)

OptionalLogger = Optional[Callable[[str], None]]

_ROOT = Path(__file__).resolve().parent.parent.parent
_LEGACY_STORY_CONTEXT_CACHE_DIR = _ROOT / "Transcription" / "story_context_cache"
_story_cache_migrated = False

# 폴더/파일명에 붙는 `품번__HD__A` 꼬리 — 기준 품번만으로 `*_grok.json` 을 맞추기 위함
_STORY_CACHE_TAG_TOKENS = frozenset(
    {
        "HD", "FHD", "SD", "4K", "UHD", "HR", "LR", "HQ", "RAW",
        "DVD", "BR", "BLURAY", "WEB", "SUB", "ENG", "JPN", "RIP",
        "MOSAIC", "NOMOSAIC", "UNCENSORED", "CENSORED",
    }
)


def _is_story_cache_tag_token(tok: str) -> bool:
    t = (tok or "").strip()
    if not t:
        return False
    u = t.upper()
    if u in _STORY_CACHE_TAG_TOKENS:
        return True
    if len(t) == 1 and t.isalpha():
        return True
    if "모자이크" in t:
        return True
    return False


def _normalize_story_cache_product_upper(product_code: str) -> str:
    """`FC2-PPV-xxx__HD__A` 처럼 품번 뒤에 붙은 화질/분할 태그만 제거한 뒤 strip_split_suffixes."""
    from javstory.utils.product_code import strip_split_suffixes

    raw = (product_code or "").strip().upper()
    if "__" in raw:
        head, tail = raw.split("__", 1)
        head = head.strip()
        tail = tail.strip()
        parts = [p for p in tail.split("__") if p.strip()]
        if head and parts and all(_is_story_cache_tag_token(p) for p in parts):
            raw = head
    raw = (strip_split_suffixes(raw) or raw).strip()
    return raw


def _story_cache_base_id(product_code: str) -> str:
    """스토리 캐시 파일명용: 정규화 품번 + 경로 안전 sanitize (레거시 `__모델` 접두와 glob 용)."""
    norm = _normalize_story_cache_product_upper(product_code)
    return re.sub(r"[^\w\-.]", "_", norm, flags=re.ASCII) or "unknown"


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


def story_context_legacy_cache_dir() -> Path:
    """레거시 캐시 루트(읽기·이관 폴백 전용). 신규 저장은 `story_context_cache_dir`만 사용."""
    return _LEGACY_STORY_CONTEXT_CACHE_DIR


def story_context_cache_dir() -> Path:
    """SoT: `data/cache/story_context/` ([`app_config.STORY_CONTEXT_CACHE_DIR`](d:/App/JAVSTORY/javstory/config/app_config.py))."""
    from javstory.config.app_config import STORY_CONTEXT_CACHE_DIR

    d = Path(STORY_CONTEXT_CACHE_DIR)
    d.mkdir(parents=True, exist_ok=True)
    _ensure_story_context_cache_migrated()
    return d


def _ensure_story_context_cache_migrated() -> None:
    global _story_cache_migrated
    if _story_cache_migrated:
        return
    _story_cache_migrated = True
    try:
        migrate_story_context_cache_files()
    except Exception:
        pass


def migrate_story_context_cache_files(*, log: OptionalLogger = None) -> dict[str, int]:
    """
    `Transcription/story_context_cache/*.json` → `data/cache/story_context/` 1회 이관.
    동일 파일명이 있으면 mtime이 더 최신인 쪽만 유지.
    """
    from javstory.config.app_config import STORY_CONTEXT_CACHE_DIR

    primary = Path(STORY_CONTEXT_CACHE_DIR)
    legacy = story_context_legacy_cache_dir()
    primary.mkdir(parents=True, exist_ok=True)
    stats = {"copied": 0, "skipped": 0, "errors": 0}
    if not legacy.is_dir():
        return stats

    for src in legacy.glob("*.json"):
        if not src.is_file():
            continue
        dst = primary / src.name
        try:
            if dst.is_file():
                if src.stat().st_mtime <= dst.stat().st_mtime:
                    stats["skipped"] += 1
                    continue
            dst.write_bytes(src.read_bytes())
            stats["copied"] += 1
        except OSError:
            stats["errors"] += 1
    if log and stats["copied"]:
        log(
            f"[Grok 캐시] 레거시 폴더에서 {stats['copied']}개 JSON을 "
            f"{primary} 로 이관했습니다."
        )
    return stats


def _sanitized_product_code(product_code: str) -> str:
    """원본 문자열 기준 sanitize (레거시 `품번__모델` 경로 호환, 꼬리 태그 제거 없음)."""
    raw_pc = (product_code or "").strip().upper()
    return re.sub(r"[^\w\-.]", "_", raw_pc, flags=re.ASCII) or "unknown"


def story_context_cache_path_grok(product_code: str) -> Path:
    """현행 SoT: `{기준품번}_grok.json` (`__HD__A` 등 폴더 꼬리는 제외)."""
    bid = _story_cache_base_id(product_code)
    return story_context_cache_dir() / f"{bid}_grok.json"


def story_context_cache_path(product_code: str, model_hint: str = "") -> Path:
    """레거시·폴백: `{품번}__{모델}.json` 또는 힌트 없으면 `{품번}.json`."""
    pc = _sanitized_product_code(product_code)
    suffix = re.sub(r"[^\w\-.]", "_", model_hint.strip(), flags=re.ASCII) if model_hint else ""
    name = f"{pc}__{suffix}.json" if suffix else f"{pc}.json"
    return story_context_cache_dir() / name


def _legacy_model_suffix_cache_exists(product_code: str) -> bool:
    """`품번__*.json` 레거시 캐시 (기준 품번 접두 또는 원본 접두)."""
    base = _story_cache_base_id(product_code)
    raw_san = _sanitized_product_code(product_code)
    for d in (story_context_cache_dir(), story_context_legacy_cache_dir()):
        if not d.is_dir():
            continue
        try:
            if any(d.glob(f"{base}__*.json")):
                return True
            if raw_san != base and any(d.glob(f"{raw_san}__*.json")):
                return True
        except OSError:
            continue
    return False


def has_disk_grok_story_cache(product_code: str) -> bool:
    """라이브러리 목록 필터용: Grok 스토리 캐시 JSON이 디스크에 있는지(파싱·API 없음)."""
    raw = (product_code or "").strip()
    if not raw:
        return False
    try:
        if story_context_cache_path_grok(raw).is_file():
            return True
        if _legacy_model_suffix_cache_exists(raw):
            return True
        pc_u = raw.upper()
        if story_context_cache_path(pc_u, "").is_file():
            return True
        # 이관 전: 레거시 디렉터리만 있는 경우
        leg = story_context_legacy_cache_dir()
        if leg.is_dir():
            bid = _story_cache_base_id(raw)
            if (leg / f"{bid}_grok.json").is_file():
                return True
    except OSError:
        return False
    return False


def merge_story_context_tier(raw: dict[str, Any] | None) -> dict[str, Any]:
    """env 기본 `story_context_llm_tier`에 호출자 오버라이드를 합친다."""
    base = story_context_llm_tier()
    if isinstance(raw, dict) and raw:
        return {**base, **raw}
    return base


async def ensure_grok_story_cache_for_translation(
    *,
    product_code: str,
    logger_func: Any,
    story_context_tier: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """자막 번역용 Grok 캐시: 디스크 우선, 없으면 API 생성. 크레딧 부족 등 실패 시 None(번역 계속)."""
    pc = (product_code or "").strip().upper()
    if not pc:
        return None
    tier = merge_story_context_tier(story_context_tier)
    cached = load_cached_grok_json_flexible(pc, tier)
    if cached:
        return cached
    await run_story_grok_after_harvest_async(
        product_code=pc,
        logger_func=logger_func,
        story_context_tier=tier,
        force_refresh=False,
    )
    return load_cached_grok_json_flexible(pc, tier)


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
    path_primary = story_context_cache_path_grok(pc)

    if not force_refresh:
        if path_primary.is_file():
            log(f"✅ Grok 스토리 캐시 이미 존재: {path_primary.name}")
            return
        if _legacy_model_suffix_cache_exists(pc):
            log(f"✅ Grok 스토리 캐시 이미 존재(레거시 __모델 파일): {pc} — 스킵")
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
        log(f"✅ [Grok 스토리 응답 ({pc})]:\n{res_raw}\n")

        data = parse_grok_story_json(res_raw)
        if not data:
            log(f"❌ Grok 응답 파싱 실패 (JSON 형식 아님).")
            return

        # 캐시 저장 (현행 파일명만 사용)
        path_primary.parent.mkdir(parents=True, exist_ok=True)
        path_primary.write_text(story_context_json_dumps(data), encoding="utf-8")
        log(f"✅ Grok 스토리 캐시 생성 완료: {path_primary.name}")

    except AllTiersExhaustedError as e:
        detail = str(getattr(e, "last_error", "") or e)
        if is_openrouter_credit_exhausted(detail) or is_openrouter_credit_exhausted(e):
            log(
                f"⚠️ Grok 스토리 컨텍스트 스킵: OpenRouter 크레딧 부족 ({pc}). "
                "번역은 Grok 없이 계속합니다."
            )
        else:
            log(f"❌ Grok 스토리 분석 실패 (모든 티어 소진): {e}")
    except Exception as e:
        if is_openrouter_credit_exhausted(e):
            log(
                f"⚠️ Grok 스토리 컨텍스트 스킵: OpenRouter 크레딧 부족 ({pc}). "
                "번역은 Grok 없이 계속합니다."
            )
        else:
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
    """디스크 캐시 JSON만 로드(API 없음). `{품번}_grok.json` 우선, 이어 티어별 레거시 경로."""
    pc = (product_code or "").strip()
    if not pc:
        return None
    tier = merge_story_context_tier(story_context_tier)
    grok_primary = story_context_cache_path_grok(pc)
    paths_try: list[Path] = [
        grok_primary,
        story_context_legacy_cache_dir() / grok_primary.name,
        story_context_cache_path(pc, str(tier.get("model") or "")),
    ]
    for path in paths_try:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            continue
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

    def _read(path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    grok_primary = story_context_cache_path_grok(pc_upper)
    for grok_path in (grok_primary, story_context_legacy_cache_dir() / grok_primary.name):
        got = _read(grok_path)
        if got:
            return got

    hit = load_cached_grok_json(raw, tier)
    if hit:
        return hit
    hit = load_cached_grok_json(pc_upper, tier)
    if hit:
        return hit

    model = str(tier.get("model") or "")
    env_model = str(story_context_llm_tier().get("model") or "")

    legacy_seed: list[str | None] = [
        env_model if env_model != model else None,
        "",
        f"{model}:online" if model and ":online" not in model else None,
        f"{env_model}:online" if env_model and ":online" not in env_model else None,
        "x-ai/grok-4.3:online",
        "x-ai/grok-4.3",
        "x-ai/grok-4.1-fast:online",
        "grok-4-fast:online",
    ]
    legacy_hints: list[str] = []
    seen_h: set[str] = set()
    for h in legacy_seed:
        if h is None:
            continue
        if h in seen_h:
            continue
        seen_h.add(h)
        legacy_hints.append(h)

    for hint in legacy_hints:
        cand = story_context_cache_path(pc_upper, hint)
        got = _read(cand)
        if got:
            return got

    try:
        base_id = _story_cache_base_id(pc_upper)
        raw_id = _sanitized_product_code(pc_upper)
        matches: list[Path] = []
        seen: set[Path] = set()
        for d in (story_context_cache_dir(), story_context_legacy_cache_dir()):
            if not d.is_dir():
                continue
            for prefix in (base_id, raw_id):
                if not prefix:
                    continue
                for p in d.glob(f"{prefix}__*.json"):
                    if p.is_file() and p not in seen:
                        seen.add(p)
                        matches.append(p)
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
    "ensure_grok_story_cache_for_translation",
    "run_story_grok_after_harvest_async",
    "load_cached_grok_json",
    "load_cached_grok_json_flexible",
    "story_context_cache_dir",
    "story_context_legacy_cache_dir",
    "migrate_story_context_cache_files",
    "story_context_cache_path",
    "story_context_cache_path_grok",
    "has_disk_grok_story_cache",
]
