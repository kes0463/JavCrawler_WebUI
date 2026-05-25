"""AI 취향 페르소나 카드 v3 (Ollama JSON, 주간 캐시)."""

from __future__ import annotations

import json
import os
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from javstory.analytics.library_stats import compute_taste_vector, get_library_stats
from javstory.analytics.preference_engine import get_top_actors, get_top_genres
from javstory.analytics.persona_context import (
    build_persona_context,
    persona_deep_enabled,
    persona_prompt_budget,
)

_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "cache" / "persona_card.json"
_CACHE_TTL_DAYS = 7
_SCHEMA_VERSION = 3


def _env_int(name: str, default: int, min_value: int, max_value: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        value = default
    return max(min_value, min(max_value, value))


def _cache_ttl_days() -> int:
    return _env_int("JAVSTORY_PERSONA_CACHE_TTL_DAYS", _CACHE_TTL_DAYS, 1, 30)


def _cache_watch_delta_threshold() -> int:
    return _env_int("JAVSTORY_PERSONA_CACHE_WATCH_DELTA", 10, 1, 200)


def _context_cache_metrics(ctx: Dict[str, Any]) -> Dict[str, Any]:
    stats = ctx.get("stats") or {}
    sample_codes = [str(c).strip().upper() for c in (ctx.get("sample_codes") or []) if str(c).strip()]
    return {
        "total": int(stats.get("total") or 0),
        "watched_count": int(stats.get("watched_count") or 0),
        "completed": int(stats.get("completed") or 0),
        "sample_codes": sample_codes[:24],
    }


def _cache_metrics_changed(old: Dict[str, Any], new: Dict[str, Any]) -> bool:
    threshold = _cache_watch_delta_threshold()
    for key in ("watched_count", "completed"):
        if abs(int(new.get(key) or 0) - int(old.get(key) or 0)) >= threshold:
            return True
    old_codes = set(old.get("sample_codes") or [])
    new_codes = set(new.get("sample_codes") or [])
    return bool(old_codes and new_codes and old_codes != new_codes)


def _cache_valid(payload: Dict[str, Any], ctx: Dict[str, Any] | None = None) -> bool:
    gen = payload.get("generated_at") or ""
    try:
        ts = datetime.fromisoformat(str(gen))
    except (TypeError, ValueError):
        return False
    if datetime.now() - ts >= timedelta(days=_cache_ttl_days()):
        return False
    has_body = bool(payload.get("summary") or payload.get("body"))
    if int(payload.get("schema_version") or 0) < _SCHEMA_VERSION:
        return has_body if ctx is None else False
    if not has_body:
        return False
    if ctx is None:
        return True

    current_fingerprint = _context_fingerprint(ctx)
    if str(payload.get("input_fingerprint") or "") != current_fingerprint:
        return False
    old_metrics = payload.get("cache_metrics") or {}
    if not isinstance(old_metrics, dict):
        return False
    return not _cache_metrics_changed(old_metrics, _context_cache_metrics(ctx))


def _context_fingerprint(ctx: Dict[str, Any]) -> str:
    basis = {
        "stats": ctx.get("stats") or {},
        "sample_groups": ctx.get("sample_groups") or {},
        "top_genres": ctx.get("top_genres") or [],
        "top_actors": ctx.get("top_actors") or [],
        "tag_counter": ctx.get("tag_counter") or [],
        "tone_counter": ctx.get("tone_counter") or [],
        "recent_window": ctx.get("recent_window") or {},
        "drift_hint": ctx.get("drift_hint") or "",
        "interaction_signals": ctx.get("interaction_signals") or {},
    }
    raw = json.dumps(basis, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _semantic_fingerprint(ctx: Dict[str, Any]) -> str:
    raw = json.dumps(ctx.get("semantic_profile") or {}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _clip_for_signal(text: Any, limit: int = 220) -> str:
    value = " ".join(str(text or "").split())
    return value[:limit]


def _chat_memory_summary(limit: int = 5) -> Dict[str, Any]:
    try:
        from javstory.persona.persona_memory import PersonaChatMemory

        memory = PersonaChatMemory().prompt_context("", max_items=limit)
    except Exception:
        return {}

    def note_texts(key: str) -> List[str]:
        out: List[str] = []
        for item in memory.get(key) or []:
            if isinstance(item, dict):
                text = _clip_for_signal(item.get("text"))
                if text:
                    out.append(text)
        return out[:limit]

    def note_codes(key: str) -> List[str]:
        codes: List[str] = []
        for item in memory.get(key) or []:
            if not isinstance(item, dict):
                continue
            for code in item.get("product_codes") or []:
                value = str(code or "").strip().upper()
                if value and value not in codes:
                    codes.append(value)
        return codes[:limit]

    summary = {
        "turn_count": int(memory.get("turn_count") or 0),
        "preference_notes": note_texts("preference_notes"),
        "strong_reaction_notes": note_texts("strong_reaction_notes"),
        "negative_feedback_notes": note_texts("negative_feedback_notes"),
        "correction_notes": note_texts("correction_notes"),
        "strong_reaction_codes": note_codes("strong_reaction_notes"),
        "negative_feedback_codes": note_codes("negative_feedback_notes"),
    }
    return {key: value for key, value in summary.items() if value not in ([], "", 0)}


def _persona_feedback_summary(limit: int = 8) -> Dict[str, Any]:
    from javstory.config.app_config import DATA_ROOT

    path = DATA_ROOT / "cache" / "persona_feedback.jsonl"
    if not path.is_file():
        return {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-max(1, limit):]
    except OSError:
        return {}

    recent: List[Dict[str, Any]] = []
    positive = 0
    negative = 0
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        feedback = str(item.get("feedback") or "").strip().lower()
        if feedback == "positive":
            positive += 1
        elif feedback == "negative":
            negative += 1
        recent.append(
            {
                "feedback": feedback,
                "persona_type": str(item.get("persona_type") or ""),
                "summary": _clip_for_signal(item.get("summary"), 180),
                "created_at": str(item.get("created_at") or ""),
            }
        )
    if not recent:
        return {}
    return {
        "positive": positive,
        "negative": negative,
        "recent": recent[-limit:],
    }


def _augment_context_with_interaction_signals(ctx: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(ctx or {})
    signals = {
        "chat_memory": _chat_memory_summary(),
        "persona_feedback": _persona_feedback_summary(),
    }
    out["interaction_signals"] = {
        key: value for key, value in signals.items() if value
    }
    return out


def _contains_excluded_property(text: str, excluded: set[str]) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    compact = value.replace(" ", "").lower()
    return any(ex in value or ex.replace(" ", "").lower() in compact for ex in excluded)


def _text_key(value: str) -> str:
    return str(value or "").replace(" ", "").strip().lower()


def _texts_conflict(left: str, right: str) -> bool:
    a = _text_key(left)
    b = _text_key(right)
    if not a or not b:
        return False
    return a == b or (min(len(a), len(b)) >= 2 and (a in b or b in a))


def _clean_text_list(values: Any, *, limit: int, excluded: set[str] | None = None) -> List[str]:
    if not isinstance(values, list):
        return []
    excluded = excluded or set()
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or _contains_excluded_property(text, excluded):
            continue
        key = _text_key(text)
        if key not in seen:
            seen.add(key)
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _remove_conflicting_avoidances(
    turn_ons: List[str],
    avoidances: List[str],
    affinities: List[str],
) -> tuple[List[str], List[str]]:
    positive = list(turn_ons or []) + list(affinities or [])
    cleaned: List[str] = []
    removed: List[str] = []
    for item in avoidances or []:
        if any(_texts_conflict(item, pos) for pos in positive):
            removed.append(item)
            continue
        cleaned.append(item)
    return cleaned, removed


def _normalize_v2_payload(raw: Dict[str, Any], source: str) -> Dict[str, Any]:
    """UI·캐시 공통 형태 (+ v1/v2 호환 body/title)."""
    from javstory.config.app_config import similarity_excluded_genres_from_env

    excluded = similarity_excluded_genres_from_env()
    persona_type = str(raw.get("persona_type") or "탐색형 감상자").strip()
    summary = str(raw.get("summary") or raw.get("body") or "").strip()
    sensual_summary = str(raw.get("sensual_summary") or "").strip()
    drift = str(raw.get("drift_note") or "").strip()
    affinities = _clean_text_list(raw.get("affinities") or [], limit=8, excluded=excluded)
    turn_ons = _clean_text_list(raw.get("turn_ons") or [], limit=8, excluded=excluded)
    avoidances = _clean_text_list(raw.get("avoidances") or [], limit=6, excluded=excluded)
    avoidances, removed_avoidances = _remove_conflicting_avoidances(turn_ons, avoidances, affinities)
    validation_warnings = list(raw.get("validation_warnings") or [])
    if removed_avoidances:
        validation_warnings.append(
            "removed_conflicting_avoidances:" + ",".join(removed_avoidances[:4])
        )
    if not summary and sensual_summary:
        summary = sensual_summary
        validation_warnings.append("filled_summary_from_sensual_summary")

    evidence = raw.get("evidence") or []
    if not isinstance(evidence, list):
        evidence = []
    clean_evidence: List[Dict[str, str]] = []
    seen_evidence: set[str] = set()
    for e in evidence[:5]:
        if isinstance(e, dict):
            pc = str(e.get("product_code") or "").strip().upper()
            reason = str(e.get("reason") or "").strip()[:180]
            key = pc or reason
            if key and key not in seen_evidence:
                seen_evidence.add(key)
                clean_evidence.append({"product_code": pc, "reason": reason})

    coverage = raw.get("coverage") or {}
    if not isinstance(coverage, dict):
        coverage = {}

    semantic_profile = raw.get("semantic_profile") or {}
    if not isinstance(semantic_profile, dict):
        semantic_profile = {}
    sample_groups = raw.get("sample_groups") or {}
    if not isinstance(sample_groups, dict):
        sample_groups = {}

    return {
        "schema_version": _SCHEMA_VERSION,
        "title": "나의 취향 페르소나",
        "persona_type": persona_type,
        "summary": summary,
        "body": summary,
        "sensual_summary": sensual_summary,
        "drift_note": drift,
        "affinities": affinities,
        "turn_ons": turn_ons,
        "avoidances": avoidances,
        "evidence": clean_evidence,
        "coverage": coverage,
        "coverage_detail": raw.get("coverage_detail") or coverage,
        "sample_groups": sample_groups,
        "sample_codes": raw.get("sample_codes") or [],
        "semantic_profile": semantic_profile,
        "input_fingerprint": str(raw.get("input_fingerprint") or "").strip(),
        "semantic_fingerprint": str(raw.get("semantic_fingerprint") or "").strip(),
        "cache_metrics": raw.get("cache_metrics") or {},
        "validation_warnings": validation_warnings,
        "model": str(raw.get("model") or "").strip(),
        "embedding_model": str(raw.get("embedding_model") or "").strip(),
        "generated_reason": str(raw.get("generated_reason") or "").strip(),
        "generated_at": raw.get("generated_at") or datetime.now().isoformat(timespec="seconds"),
        "source": source,
    }


def _fallback_v2(ctx: Dict[str, Any] | None = None) -> Dict[str, Any]:
    from javstory.config.app_config import similarity_excluded_genres_from_env

    excluded = similarity_excluded_genres_from_env()
    actors = get_top_actors(1)
    genres = get_top_genres(3, excluded=excluded)
    a = actors[0]["name"] if actors else "다양한 배우"
    g = genres[0]["name"] if genres else "여러 장르"
    drift = (ctx or {}).get("drift_hint") or ""
    tags = (ctx or {}).get("tag_counter") or []
    aff: List[str] = [f"{g} 장르의 자극 선호"]
    if tags:
        aff.append(f"끌리는 장면 키워드: {tags[0].get('name', '')}")
    summary = f"'{g}' 쪽의 자극과 '{a}' 작품에 반응이 강한 성인 취향입니다."
    sensual = "선호 장면의 분위기와 관계성 데이터가 쌓일수록 더 노골적인 끌림 포인트를 분리해 보여줄 수 있습니다."
    if drift:
        summary += " " + drift
    return _normalize_v2_payload(
        {
            "persona_type": "탐색형 감상자",
            "summary": summary,
            "sensual_summary": sensual,
            "drift_note": drift,
            "affinities": aff,
            "turn_ons": aff[:3],
            "avoidances": [],
            "evidence": [],
            "coverage": (ctx or {}).get("coverage") or {},
            "coverage_detail": (ctx or {}).get("coverage") or {},
            "sample_groups": (ctx or {}).get("sample_groups") or {},
            "sample_codes": (ctx or {}).get("sample_codes") or [],
            "semantic_profile": (ctx or {}).get("semantic_profile") or {},
            "input_fingerprint": _context_fingerprint(ctx or {}),
            "semantic_fingerprint": _semantic_fingerprint(ctx or {}),
            "cache_metrics": _context_cache_metrics(ctx or {}),
            "embedding_model": ((ctx or {}).get("semantic_profile") or {}).get("model", ""),
            "generated_reason": "fallback",
        },
        "fallback",
    )


def _context_for_prompt(ctx: Dict[str, Any]) -> str:
    """LLM 프롬프트용 축약 JSON."""
    budget = persona_prompt_budget()
    slim = {
        "stats": ctx.get("stats"),
        "taste_axes": (ctx.get("taste_axes") or [])[:budget["taste_axes"]],
        "top_actors": (ctx.get("top_actors") or [])[:budget["top_actors"]],
        "top_genres": (ctx.get("top_genres") or [])[:budget["top_genres"]],
        "top_genres_recent": (ctx.get("top_genres_recent") or [])[:budget["recent_genres"]],
        "recent_window": ctx.get("recent_window") or {},
        "drift_hint": ctx.get("drift_hint"),
        "sample_groups": ctx.get("sample_groups") or {},
        "tag_counter": (ctx.get("tag_counter") or [])[:budget["tag_counter"]],
        "tone_counter": (ctx.get("tone_counter") or [])[:budget["tone_counter"]],
        "subtitle_profile": ctx.get("subtitle_profile"),
        "semantic_profile": ctx.get("semantic_profile") or {},
        "coverage": ctx.get("coverage"),
        "interaction_signals": ctx.get("interaction_signals") or {},
        "context_budget": {
            "prompt_samples": budget["samples"],
            "prompt_grok_summary_chars": budget["grok_summary_chars"],
            "prompt_sample_tags": budget["sample_tags"],
        },
        "samples": [],
    }
    for s in (ctx.get("samples") or [])[:budget["samples"]]:
        watch = s.get("watch") or {}
        slim["samples"].append({
            "product_code": s.get("product_code"),
            "roles": s.get("sample_roles") or [],
            "watch": {
                "completion_ratio": watch.get("completion_ratio"),
                "liked": watch.get("liked"),
                "rating": watch.get("rating"),
            },
            "grok_summary": (s.get("grok") or {}).get("overall_summary", "")[:budget["grok_summary_chars"]],
            "grok_tags": (s.get("grok") or {}).get("tags", [])[:budget["sample_tags"]],
            "canonical_tags": (s.get("canonical") or {}).get("tags", [])[:budget["sample_tags"]],
            "subtitle_density": (s.get("subtitle") or {}).get("dialogue_density"),
        })
    return json.dumps(slim, ensure_ascii=False, indent=0)


def synthesize_persona_v3(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Ollama JSON 합성 → v3 payload."""
    from javstory.translation.story_context_prompts import parse_grok_story_json

    model = (os.environ.get("JAVSTORY_OLLAMA_MODEL", "") or "").strip() or "qwen3:8b"
    embedding_model = ((ctx.get("semantic_profile") or {}).get("model") or "").strip()
    fingerprint = _context_fingerprint(ctx)
    semantic_fingerprint = _semantic_fingerprint(ctx)
    cache_metrics = _context_cache_metrics(ctx)
    prompt = (
        "당신은 성인 미디어 라이브러리의 취향 분석가입니다. 아래 JSON 통계·샘플을 바탕으로 "
        "사용자 페르소나를 한국어로 작성하세요. 장르명 중 유통/화질/프로모션/포맷 속성은 취향으로 해석하지 마세요. "
        "표현은 관능적이고 직설적으로 하되 비속어와 과장된 농담은 피하고, 실제로 끌리는 장면 분위기·관계성·텐션·상황 취향을 짚으세요. "
        "interaction_signals의 챗 메모리와 카드 피드백은 최신 사용자 교정 신호이므로, 통계와 충돌하지 않는 범위에서 우선 반영하세요. "
        "negative 피드백이 많으면 기존 페르소나 문구를 반복하지 말고 더 조심스럽게 수정하세요. "
        "반드시 유효한 JSON 객체 하나만 출력하세요.\n\n"
        "스키마:\n"
        '{"persona_type":"짧은 유형명 예: 텐션 몰입형 감상자",'
        '"summary":"2~4문장 본문",'
        '"sensual_summary":"좀 더 관능적인 취향 해석 1~2문장",'
        '"drift_note":"최근 취향 변화 1~2문장",'
        '"affinities":["취향 키워드 3~5개"],'
        '"turn_ons":["끌리는 포인트 3~6개"],'
        '"avoidances":["덜 맞는 패턴 0~4개"],'
        '"evidence":[{"product_code":"품번","reason":"근거 한 줄"}]}\n\n'
        "데이터:\n"
        + _context_for_prompt(ctx)
    )

    try:
        import httpx
        from javstory.config.app_config import OLLAMA_BASE_URL

        r = httpx.post(
            f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=120.0,
        )
        r.raise_for_status()
        raw_text = (r.json().get("response") or "").strip()
        parsed = parse_grok_story_json(raw_text)
        if parsed:
            parsed["coverage"] = ctx.get("coverage") or {}
            parsed["coverage_detail"] = ctx.get("coverage") or {}
            parsed["sample_groups"] = ctx.get("sample_groups") or {}
            parsed["sample_codes"] = ctx.get("sample_codes") or []
            parsed["semantic_profile"] = ctx.get("semantic_profile") or {}
            parsed["input_fingerprint"] = fingerprint
            parsed["semantic_fingerprint"] = semantic_fingerprint
            parsed["cache_metrics"] = cache_metrics
            parsed["model"] = model
            parsed["embedding_model"] = embedding_model
            parsed["generated_reason"] = "ollama_deep"
            return _normalize_v2_payload(parsed, "ollama")
    except Exception:
        pass

    return _fallback_v2(ctx)


def _synthesize_v1_light() -> Dict[str, Any]:
    """deep 분석 비활성 시 경량 v1."""
    from javstory.config.app_config import similarity_excluded_genres_from_env

    excluded = similarity_excluded_genres_from_env()
    stats = get_library_stats()
    actors = get_top_actors(3)
    genres = get_top_genres(5, excluded=excluded)
    taste = compute_taste_vector()
    lines = [
        f"전체 {stats.get('total', 0)}편, 시청 {stats.get('watched_count', 0)}편",
        f"TOP 배우: {', '.join(a['name'] for a in actors[:3]) or '없음'}",
        f"TOP 장르: {', '.join(g['name'] for g in genres[:5]) or '없음'}",
    ]
    for ax in (taste.get("axes") or [])[:4]:
        lines.append(f"{ax.get('label')}: {round(float(ax.get('value') or 0) * 100)}%")

    body = ""
    source = "fallback"
    try:
        import httpx
        from javstory.config.app_config import OLLAMA_BASE_URL

        prompt = (
            "다음 통계로 성인 취향을 관능적이지만 깔끔한 한국어 2~3문장으로 요약. 이모지 1개 이내.\n\n"
            + "\n".join(lines)
        )
        model = (os.environ.get("JAVSTORY_OLLAMA_MODEL", "") or "").strip() or "qwen3:8b"
        r = httpx.post(
            f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=90.0,
        )
        r.raise_for_status()
        body = (r.json().get("response") or "").strip()
        if body:
            source = "ollama"
    except Exception:
        body = ""

    if not body:
        fb = _fallback_v2()
        return fb

    return _normalize_v2_payload(
        {
            "persona_type": "탐색형",
            "summary": body,
            "sensual_summary": body,
            "drift_note": "",
            "affinities": [],
            "turn_ons": [],
            "avoidances": [],
            "evidence": [],
            "cache_metrics": {
                "total": int(stats.get("total") or 0),
                "watched_count": int(stats.get("watched_count") or 0),
                "completed": int(stats.get("completed") or 0),
                "sample_codes": [],
            },
            "generated_reason": "light",
        },
        source,
    )


def _write_cache(payload: Dict[str, Any]) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _read_cache() -> Dict[str, Any] | None:
    if not _CACHE_PATH.is_file():
        return None
    try:
        payload = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _normalize_cached_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if int(payload.get("schema_version") or 0) < _SCHEMA_VERSION:
        return _normalize_v2_payload(
            {
                "summary": payload.get("body") or payload.get("summary", ""),
                "persona_type": payload.get("persona_type") or "탐색형",
                "generated_at": payload.get("generated_at"),
                "cache_metrics": payload.get("cache_metrics") or {},
                "input_fingerprint": payload.get("input_fingerprint") or "",
                "semantic_fingerprint": payload.get("semantic_fingerprint") or "",
            },
            "cache",
        )
    return _normalize_v2_payload(payload, "cache")


def refresh_persona_semantic_profile() -> Dict[str, Any]:
    """
    기존 카드 문구는 유지하고 semantic_profile/근접작만 최신 컨텍스트로 갱신한다.
    LLM 재호출 없이 임베딩 기반 근접작 캐시만 새로 쓰는 경로다.
    """
    payload = _read_cache()
    if not payload:
        return _empty_persona_payload()

    ctx = build_persona_context()
    normalized = _normalize_cached_payload(payload)
    normalized["semantic_profile"] = ctx.get("semantic_profile") or {}
    normalized["semantic_fingerprint"] = _semantic_fingerprint(ctx)
    normalized["sample_groups"] = ctx.get("sample_groups") or {}
    normalized["sample_codes"] = ctx.get("sample_codes") or []
    normalized["input_fingerprint"] = _context_fingerprint(ctx)
    normalized["cache_metrics"] = _context_cache_metrics(ctx)
    normalized["embedding_model"] = ((ctx.get("semantic_profile") or {}).get("model") or "").strip()
    normalized["generated_reason"] = "semantic_refresh"
    _write_cache(normalized)
    return normalized


def _empty_persona_payload() -> Dict[str, Any]:
    return _normalize_v2_payload(
        {
            "persona_type": "탐색형",
            "summary": "",
            "sensual_summary": "",
            "drift_note": "",
            "affinities": [],
            "turn_ons": [],
            "avoidances": [],
            "evidence": [],
        },
        "none",
    )


def get_persona_card(
    *,
    force_refresh: bool = False,
    cache_only: bool = False,
    refresh_semantic: bool = False,
) -> Dict[str, Any]:
    """
    v2: persona_type, summary, drift_note, affinities, evidence, coverage, ...
  v1 호환: body == summary

    cache_only: 캐시만 읽고 Ollama/딥 합성은 생략 (시작 시 UI 블로킹 방지).
    """
    if refresh_semantic and not force_refresh:
        return refresh_persona_semantic_profile()

    if cache_only and not force_refresh:
        payload = _read_cache()
        if payload and _cache_valid(payload):
            return _normalize_cached_payload(payload)
        return _empty_persona_payload()

    ctx: Dict[str, Any] | None = None
    if not force_refresh and _CACHE_PATH.is_file():
        payload = _read_cache()
        if payload and _cache_valid(payload):
            if persona_deep_enabled():
                ctx = _augment_context_with_interaction_signals(build_persona_context())
                if _cache_valid(payload, ctx):
                    return _normalize_cached_payload(payload)
            else:
                return _normalize_cached_payload(payload)

    if persona_deep_enabled():
        if ctx is None:
            ctx = _augment_context_with_interaction_signals(build_persona_context())
        payload = synthesize_persona_v3(ctx)
    else:
        payload = _synthesize_v1_light()

    payload["generated_at"] = datetime.now().isoformat(timespec="seconds")
    _write_cache(payload)
    return payload
