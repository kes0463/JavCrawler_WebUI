"""AI 취향 페르소나 카드 v3 (Ollama JSON, 주간 캐시)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from javstory.analytics.library_stats import compute_taste_vector, get_library_stats
from javstory.analytics.preference_engine import get_top_actors, get_top_genres
from javstory.analytics.persona_context import (
    build_persona_context,
    persona_deep_enabled,
)

_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "cache" / "persona_card.json"
_CACHE_TTL_DAYS = 7
_SCHEMA_VERSION = 2


def _cache_valid(payload: Dict[str, Any]) -> bool:
    gen = payload.get("generated_at") or ""
    try:
        ts = datetime.fromisoformat(str(gen))
    except (TypeError, ValueError):
        return False
    if datetime.now() - ts >= timedelta(days=_CACHE_TTL_DAYS):
        return False
    if int(payload.get("schema_version") or 0) >= _SCHEMA_VERSION:
        return bool(payload.get("summary") or payload.get("body"))
    return bool(payload.get("body"))


def _normalize_v2_payload(raw: Dict[str, Any], source: str) -> Dict[str, Any]:
    """UI·캐시 공통 v2 형태 (+ v1 호환 body/title)."""
    persona_type = str(raw.get("persona_type") or "탐색형 감상자").strip()
    summary = str(raw.get("summary") or raw.get("body") or "").strip()
    drift = str(raw.get("drift_note") or "").strip()
    affinities = raw.get("affinities") or []
    if not isinstance(affinities, list):
        affinities = []
    affinities = [str(a).strip() for a in affinities if str(a).strip()][:8]

    evidence = raw.get("evidence") or []
    if not isinstance(evidence, list):
        evidence = []
    clean_evidence: List[Dict[str, str]] = []
    for e in evidence[:5]:
        if isinstance(e, dict):
            pc = str(e.get("product_code") or "").strip()
            reason = str(e.get("reason") or "").strip()
            if pc or reason:
                clean_evidence.append({"product_code": pc, "reason": reason})

    coverage = raw.get("coverage") or {}
    if not isinstance(coverage, dict):
        coverage = {}

    return {
        "schema_version": _SCHEMA_VERSION,
        "title": "나의 취향 페르소나",
        "persona_type": persona_type,
        "summary": summary,
        "body": summary,
        "drift_note": drift,
        "affinities": affinities,
        "evidence": clean_evidence,
        "coverage": coverage,
        "generated_at": raw.get("generated_at") or datetime.now().isoformat(timespec="seconds"),
        "source": source,
    }


def _fallback_v2(ctx: Dict[str, Any] | None = None) -> Dict[str, Any]:
    actors = get_top_actors(1)
    genres = get_top_genres(3)
    a = actors[0]["name"] if actors else "다양한 배우"
    g = genres[0]["name"] if genres else "여러 장르"
    drift = (ctx or {}).get("drift_hint") or ""
    tags = (ctx or {}).get("tag_counter") or []
    aff: List[str] = [f"{g} 장르 선호"]
    if tags:
        aff.append(f"씬 태그: {tags[0].get('name', '')}")
    summary = f"'{g}' 쪽 취향이 두드러지며, '{a}' 작품에 관심이 큰 감상자 타입입니다."
    if drift:
        summary += " " + drift
    return _normalize_v2_payload(
        {
            "persona_type": "탐색형 감상자",
            "summary": summary,
            "drift_note": drift,
            "affinities": aff,
            "evidence": [],
            "coverage": (ctx or {}).get("coverage") or {},
        },
        "fallback",
    )


def _context_for_prompt(ctx: Dict[str, Any]) -> str:
    """LLM 프롬프트용 축약 JSON."""
    slim = {
        "stats": ctx.get("stats"),
        "taste_axes": (ctx.get("taste_axes") or [])[:6],
        "top_actors": (ctx.get("top_actors") or [])[:5],
        "top_genres": (ctx.get("top_genres") or [])[:8],
        "top_genres_recent": (ctx.get("top_genres_recent") or [])[:5],
        "drift_hint": ctx.get("drift_hint"),
        "tag_counter": (ctx.get("tag_counter") or [])[:12],
        "tone_counter": (ctx.get("tone_counter") or [])[:6],
        "subtitle_profile": ctx.get("subtitle_profile"),
        "coverage": ctx.get("coverage"),
        "samples": [],
    }
    for s in (ctx.get("samples") or [])[:6]:
        slim["samples"].append({
            "product_code": s.get("product_code"),
            "grok_summary": (s.get("grok") or {}).get("overall_summary", "")[:200],
            "grok_tags": (s.get("grok") or {}).get("tags", [])[:6],
            "subtitle_density": (s.get("subtitle") or {}).get("dialogue_density"),
        })
    return json.dumps(slim, ensure_ascii=False, indent=0)


def synthesize_persona_v3(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Ollama JSON 합성 → v2 payload."""
    from javstory.translation.story_context_prompts import parse_grok_story_json

    prompt = (
        "당신은 미디어 라이브러리 취향 분석가입니다. 아래 JSON 통계·샘플을 바탕으로 "
        "사용자 페르소나를 한국어로 작성하세요. 반드시 유효한 JSON 객체 하나만 출력하세요.\n\n"
        "스키마:\n"
        '{"persona_type":"짧은 유형명 예: 스토리텔러형 감상자",'
        '"summary":"2~4문장 본문",'
        '"drift_note":"최근 취향 변화 1~2문장",'
        '"affinities":["선호 특성 3~5개"],'
        '"evidence":[{"product_code":"품번","reason":"근거 한 줄"}]}\n\n'
        "데이터:\n"
        + _context_for_prompt(ctx)
    )
    model = (os.environ.get("JAVSTORY_OLLAMA_MODEL", "") or "").strip() or "qwen3:8b"

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
            return _normalize_v2_payload(parsed, "ollama")
    except Exception:
        pass

    return _fallback_v2(ctx)


def _synthesize_v1_light() -> Dict[str, Any]:
    """deep 분석 비활성 시 경량 v1."""
    stats = get_library_stats()
    actors = get_top_actors(3)
    genres = get_top_genres(5)
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
            "다음 통계로 2~3문장 한국어 취향 요약. 이모지 1개 이내.\n\n"
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
        {"persona_type": "탐색형", "summary": body, "drift_note": "", "affinities": [], "evidence": []},
        source,
    )


def _write_cache(payload: Dict[str, Any]) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _empty_persona_payload() -> Dict[str, Any]:
    return _normalize_v2_payload(
        {"persona_type": "탐색형", "summary": "", "drift_note": "", "affinities": [], "evidence": []},
        "none",
    )


def get_persona_card(*, force_refresh: bool = False, cache_only: bool = False) -> Dict[str, Any]:
    """
    v2: persona_type, summary, drift_note, affinities, evidence, coverage, ...
  v1 호환: body == summary

    cache_only: 캐시만 읽고 Ollama/딥 합성은 생략 (시작 시 UI 블로킹 방지).
    """
    if cache_only and not force_refresh:
        if _CACHE_PATH.is_file():
            try:
                payload = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
                if isinstance(payload, dict) and _cache_valid(payload):
                    if int(payload.get("schema_version") or 0) < _SCHEMA_VERSION:
                        payload = _normalize_v2_payload(
                            {"summary": payload.get("body", ""), "persona_type": "탐색형"},
                            "cache",
                        )
                    else:
                        payload = _normalize_v2_payload(payload, "cache")
                    return payload
            except (OSError, json.JSONDecodeError):
                pass
        return _empty_persona_payload()

    if not force_refresh and _CACHE_PATH.is_file():
        try:
            payload = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and _cache_valid(payload):
                if int(payload.get("schema_version") or 0) < _SCHEMA_VERSION:
                    payload = _normalize_v2_payload(
                        {"summary": payload.get("body", ""), "persona_type": "탐색형"},
                        "cache",
                    )
                else:
                    payload = _normalize_v2_payload(payload, "cache")
                return payload
        except (OSError, json.JSONDecodeError):
            pass

    if persona_deep_enabled():
        ctx = build_persona_context()
        payload = synthesize_persona_v3(ctx)
    else:
        payload = _synthesize_v1_light()

    payload["generated_at"] = datetime.now().isoformat(timespec="seconds")
    _write_cache(payload)
    return payload
