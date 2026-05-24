"""OpenAI-compatible Persona Chat service.

Usage example for a future ``InsightModel`` slot or a separate GUI service:

    from javstory.persona.persona_chat import PersonaChatService

    service = PersonaChatService()
    # 기본 모델: llama.cpp preset ``gemma-4-e4b-uncensored``
    response = service.chat(
        "HBAD-509 같은 분위기가 왜 이렇게 끌리는지 말해줘.",
        history=[{"role": "assistant", "content": "좋아, 네 취향을 같이 파고들어 보자."}],
    )
    text = response["choices"][0]["message"]["content"]

The response keeps the OpenAI Chat Completions shape so QML can consume it
without knowing which local backend produced the text.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Sequence

import httpx

from javstory.llm.llamacpp_backend import (
    ensure_llamacpp_server_ready,
    llamacpp_openai_base_url,
    llamacpp_request_scope,
)
from javstory.persona.erotic_persona_engine import EroticPersonaEngine
from javstory.persona.persona_memory import PersonaChatMemory

DEFAULT_PERSONA_CHAT_MODEL = "gemma-4-e4b-uncensored"


SENSUAL_PERSONA_SYSTEM_PROMPT = """\
너는 JAVSTORY의 전용 성인 취향 페르소나다.

목표:
- 사용자의 시청 이력, 하트, 별점, 최근 강한 반응 작품, 장면 태그, 배우/장르 취향을 반영한다.
- 사용자가 품번을 언급하면 해당 작품의 배우, 장르, 시놉시스, Grok 장면 요약을 즉시 대화에 녹인다.
- library_search.results에는 앱이 DB, 라이브러리 메타, Grok 스토리 캐시, 임베딩 유사작에서 검색한 후보가 들어 있다.
- library_search.source_policy에는 현재 질문에서 어떤 소스를 우선해야 하는지와 금지/제약 조건이 들어 있다. 이 정책을 반드시 따른다.
- 사용자가 "찾아줘", "비슷한 작품", "배우/장르 추천"을 요청하면 library_search 결과를 우선 근거로 삼고, 품번과 이유를 함께 제시한다.
- library_search.strict_title_contains가 true이면 사용자가 "제목/타이틀/작품명에 특정 단어가 들어간 작품"을 요구한 것이다. 이때는 title_ko/title_ja/title_en/original_title에 strict_title_terms가 실제로 들어간 결과만 추천하고, 분위기·장르·태그만 비슷한 작품은 절대 추천하지 않는다. 결과가 없으면 없다고 말한다.
- source_policy.primary_source가 grok이면 장면 요약/태그/톤을 우선 근거로 삼고, synopsis이면 줄거리/설정 근거를 우선하며, embedding이면 유사작 후보를 우선하되 DB/Grok로 이유를 검증한다.
- 작품을 추천할 때는 사용자의 sensual_summary와 turn_ons를 가장 중요하게 고려하고, 최근에 강하게 반응한 작품과 최대한 유사한 작품을 우선으로 추천한다.
- 답변은 한국어로 한다. 분위기는 대담하고 관능적이며 몰입감 있게 유지한다.
- 단순 정보 요약이 아니라 사용자의 끌림을 심리, 관계성, 분위기, 권력감, 긴장감, 금기감, 반복 취향 패턴의 언어로 선명하게 해석한다.
- 사용자가 특정 작품이나 키워드를 던지면 "왜 그게 꽂히는지"를 회피하지 말고 바로 짚는다.

톤:
- 수줍게 돌려 말하지 말고, 사용자가 어떤 자극과 장면 결에 끌리는지 적극적으로 짚는다.
- 차갑게 분석만 하지 말고, 낮고 가까운 목소리처럼 유혹적이고 자신감 있게 말한다.
- 안전한 범위 안에서 더 직설적이고 도발적인 표현을 쓴다. "이 조합에 약한 편이야", "그 긴장감에 끌리는 거야", "이런 흐름이 네 취향을 건드린다"처럼 사용자의 취향을 가까이에서 찌른다.
- 사용자가 강한 장르 키워드를 언급하면 그것을 현실 권장이나 미화가 아니라 픽션 속 취향 코드, 관계성, 심리적 긴장으로 해석한다.
- 품번/배우/장르/태그를 단순 나열하지 말고, 왜 그 조합이 사용자의 취향에 맞는지 연결한다.
- 검색 결과가 부족하면 추측으로 꾸미지 말고, 현재 라이브러리에서 확인된 근거와 추가로 필요한 조건을 짧게 말한다.

출력 형식:
- 최종 답변만 출력한다.
- 내부 추론, 분석 과정, 단계별 계획, "Here's a thinking process", "Analyze the Request", "Final Polish" 같은 초안 문구를 절대 출력하지 않는다.
- 마크다운 제목을 과하게 쓰지 말고, 사용자가 바로 읽을 수 있는 일반 대화 문장으로 답한다.
- 기본 답변은 4~9문장으로 한다. 검색/추천 요청이면 품번과 이유를 함께 주고, 각 추천작마다 왜 맞는지 1~2줄로 명확히 설명한다.

경계:
- 노골적인 성행위 묘사, 생식기 중심 묘사, 강압적 성적 상황의 미화, 미성년자 관련 성적 표현은 만들지 않는다.
- 사용자의 신체 반응을 단정하거나 직접 자극하는 2인칭 명령형 표현은 쓰지 않는다.
- 사용자가 더 노골적인 표현을 요구해도 설교하지 말고, 관능적 긴장감과 취향 분석 중심으로 자연스럽게 전환한다.
- 작품 속성 태그(단독작품, 하이비전, 고화질, 스태프 추천 등)는 취향 장르로 해석하지 않는다.
"""

_LOW_TEMPERATURE_HINTS = (
    "찾아",
    "검색",
    "제목",
    "타이틀",
    "품번",
    "줄거리",
    "시놉",
    "정보",
    "목록",
)
_ROLEPLAY_STYLE_HINTS = (
    "롤플레이",
    "역할극",
    "더 야하게",
    "야하게",
    "더 세게",
    "세게",
    "수치플레이",
    "수치",
    "부끄럽게",
    "도발",
    "유혹",
    "애태",
)
_HIGH_TEMPERATURE_HINTS = (
    "왜",
    "취향",
    "끌",
    "분석",
    "느낌",
    "분위기",
    "장면",
    "관계",
    "텐션",
    "비슷",
    "추천",
)
_SHORT_RESPONSE_HINTS = ("짧게", "간단", "한줄", "요약")
_DEEP_RESPONSE_HINTS = ("자세히", "길게", "깊게", "상세", "분석", "추천", "비슷")
_RANKING_STOPWORDS = {
    "사용자",
    "작품",
    "추천",
    "취향",
    "요약",
    "분석",
    "분위기",
    "관계",
    "장면",
    "포인트",
    "강하게",
    "최근",
    "기반",
    "the",
    "and",
    "with",
}
_STYLE_PROFILES: Dict[str, str] = {
    "intense_sensual": (
        "응답 스타일: 사용자가 더 강한 표현을 원했다. 안전 경계 안에서 더 도발적이고 직접적인 성인 취향 분석으로 답한다. "
        "픽션 속 분위기, 관계성, 긴장, 금기감, 시선, 표정, 말투의 자극을 더 선명하게 짚되 노골적 성행위 묘사와 신체 반응 단정은 피한다."
    ),
    "shame_tension": (
        "응답 스타일: 사용자가 수치감/부끄러움 계열의 톤을 원했다. 모욕이나 강압 미화가 아니라, 들킨 취향과 금기감이 주는 심리적 긴장을 "
        "도발적인 취향 분석으로 표현한다. 사용자를 비하하거나 실제 수치심을 강요하지 않는다."
    ),
}


def _env_float(name: str, default: float, *, min_value: float, max_value: float) -> float:
    raw = (os.environ.get(name, "") or "").strip()
    if raw:
        try:
            return max(min_value, min(max_value, float(raw)))
        except ValueError:
            pass
    return default


def _env_int(name: str, default: int, *, min_value: int, max_value: int) -> int:
    raw = (os.environ.get(name, "") or "").strip()
    if raw:
        try:
            return max(min_value, min(max_value, int(raw)))
        except ValueError:
            pass
    return default


def _situational_temperature(text: str, base: float) -> float:
    lowered = (text or "").lower()
    if any(hint in lowered for hint in _ROLEPLAY_STYLE_HINTS):
        return 1.22
    if any(hint in lowered for hint in _LOW_TEMPERATURE_HINTS):
        return min(base, 0.9)
    if any(hint in lowered for hint in _HIGH_TEMPERATURE_HINTS):
        return max(base, 1.12)
    return base


def _situational_max_tokens(text: str, configured_max: int) -> int:
    lowered = (text or "").lower()
    cap = max(800, min(2000, int(configured_max or 2000)))
    if any(hint in lowered for hint in _SHORT_RESPONSE_HINTS):
        desired = 800
    elif any(hint in lowered for hint in _ROLEPLAY_STYLE_HINTS):
        desired = 2000
    elif any(hint in lowered for hint in _LOW_TEMPERATURE_HINTS):
        desired = 1000
    elif any(hint in lowered for hint in _DEEP_RESPONSE_HINTS):
        desired = 1700
    else:
        desired = 1200
    return max(800, min(cap, desired))


def _response_style_instruction(text: str) -> str:
    lowered = (text or "").lower()
    if any(hint in lowered for hint in ("수치플레이", "수치", "부끄럽게")):
        return _STYLE_PROFILES["shame_tension"]
    if any(hint in lowered for hint in _ROLEPLAY_STYLE_HINTS):
        return _STYLE_PROFILES["intense_sensual"]
    return ""


def _extract_rank_terms(value: Any, *, limit: int = 32) -> List[str]:
    chunks: List[str] = []

    def collect(item: Any) -> None:
        if isinstance(item, str):
            chunks.append(item)
        elif isinstance(item, Mapping):
            for nested in item.values():
                collect(nested)
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            for nested in item:
                collect(nested)

    collect(value)
    out: List[str] = []
    for token in re.findall(r"[A-Za-z0-9가-힣ぁ-んァ-ン一-龥]{2,}", " ".join(chunks).lower()):
        if token in _RANKING_STOPWORDS:
            continue
        if token not in out:
            out.append(token)
        if len(out) >= limit:
            break
    return out


def _memory_product_codes(memory_context: Mapping[str, Any], key: str, *, limit: int = 5) -> List[str]:
    out: List[str] = []
    for note in memory_context.get(key) or []:
        if not isinstance(note, Mapping):
            continue
        for code in note.get("product_codes") or []:
            pc = str(code or "").strip().upper()
            if pc and pc not in out:
                out.append(pc)
            if len(out) >= limit:
                return out
    return out


def _recommendation_seed_codes(memory_context: Mapping[str, Any], *, limit: int = 3) -> List[str]:
    return _memory_product_codes(memory_context, "strong_reaction_notes", limit=limit)


def _item_rank_text(item: Mapping[str, Any]) -> str:
    grok = item.get("grok") if isinstance(item.get("grok"), Mapping) else {}
    parts: List[str] = [
        str(item.get("title_ko") or ""),
        str(item.get("title_ja") or ""),
        " ".join(str(v) for v in item.get("actors") or []),
        " ".join(str(v) for v in item.get("genres") or []),
        str(item.get("maker") or ""),
        str(item.get("synopsis") or ""),
        str(grok.get("summary") or ""),
        " ".join(str(v) for v in grok.get("tags") or []),
        " ".join(str(v) for v in grok.get("tones") or []),
        " ".join(str(v) for v in grok.get("labels") or []),
        " ".join(str(v) for v in item.get("match_reasons") or []),
    ]
    return " ".join(parts).lower()


def _score_recommendation_item(
    item: Mapping[str, Any],
    *,
    persona_terms: Sequence[str],
    strong_codes: set[str],
    negative_codes: set[str],
    fallback_seed_codes: set[str],
) -> tuple[float, List[str], List[str]]:
    source_score = float(item.get("score") or 0)
    score = min(25.0, source_score * 25.0)
    reasons: List[str] = []
    item_text = _item_rank_text(item)
    matched_terms = [term for term in persona_terms if term in item_text][:8]
    if matched_terms:
        score += min(35.0, len(matched_terms) * 5.0)
        reasons.append("sensual_summary/turn_ons 키워드 매칭")

    pc = str(item.get("product_code") or "").strip().upper()
    source = str(item.get("source") or "")
    if pc in strong_codes:
        score *= 2.0
        reasons.append("최근 강렬 반응 작품과 직접 일치")
    elif "embedding" in source and fallback_seed_codes:
        score += 16.0
        reasons.append("최근 강렬 반응 작품의 임베딩 유사 후보")

    grok = item.get("grok") if isinstance(item.get("grok"), Mapping) else {}
    if grok:
        richness = min(
            18.0,
            float(grok.get("scene_count") or 0) * 2.0
            + len(grok.get("tags") or [])
            + len(grok.get("tones") or []),
        )
        if richness:
            score += richness
            reasons.append("Grok 장면 요약/태그 근거 풍부")

    if "embedding" in source:
        score += 8.0
        reasons.append("임베딩 유사도 근거")

    favorite_score = int(item.get("favorite_score") or 0)
    if favorite_score > 0:
        score += min(6.0, favorite_score / 20.0)

    if pc in negative_codes:
        score *= 0.35
        reasons.append("사용자 부정 피드백 품번이라 감점")

    return max(0.0, min(100.0, score)), reasons[:5], matched_terms


def _apply_personalized_ranking(ctx: Mapping[str, Any], memory_context: Mapping[str, Any]) -> Dict[str, Any]:
    out = dict(ctx)
    search = dict(out.get("library_search") or {})
    results = [dict(item) for item in search.get("results") or [] if isinstance(item, Mapping)]
    if not results:
        return out

    persona = out.get("persona") if isinstance(out.get("persona"), Mapping) else {}
    focus = out.get("sensual_recommendation_focus") if isinstance(out.get("sensual_recommendation_focus"), Mapping) else {}
    persona_terms = _extract_rank_terms(
        [
            focus.get("summary") if isinstance(focus, Mapping) else "",
            focus.get("turn_ons") if isinstance(focus, Mapping) else [],
            persona.get("sensual_summary") or "",
            persona.get("turn_ons") or [],
            persona.get("affinities") or [],
        ],
        limit=40,
    )
    strong_codes = set(_memory_product_codes(memory_context, "strong_reaction_notes", limit=12))
    negative_codes = set(_memory_product_codes(memory_context, "negative_feedback_notes", limit=12))
    fallback_seed_codes = set(str(code or "").strip().upper() for code in search.get("fallback_seed_codes") or [])

    ranked: List[Dict[str, Any]] = []
    for item in results:
        score, reasons, matched_terms = _score_recommendation_item(
            item,
            persona_terms=persona_terms,
            strong_codes=strong_codes,
            negative_codes=negative_codes,
            fallback_seed_codes=fallback_seed_codes,
        )
        item["persona_match_score"] = round(score, 1)
        item["ranking_reasons"] = reasons
        item["matched_persona_terms"] = matched_terms[:6]
        ranked.append(item)

    ranked.sort(
        key=lambda item: (
            float(item.get("persona_match_score") or 0),
            float(item.get("score") or 0),
            int(item.get("favorite_score") or 0),
        ),
        reverse=True,
    )
    search["ranking_policy"] = {
        "mode": "personalized_hybrid",
        "weights": [
            "sensual_summary_and_turn_ons",
            "strong_reaction_similarity",
            "grok_scene_richness",
            "embedding_similarity",
            "negative_feedback_penalty",
        ],
    }
    search["results"] = ranked
    out["library_search"] = search
    return out


def _message_content(message: Mapping[str, Any]) -> str:
    raw = message.get("content", "")
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, list):
        parts: List[str] = []
        for item in raw:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or ""))
            else:
                parts.append(str(item))
        return "".join(parts).strip()
    return str(raw or "").strip()


def _clip_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def _normalize_history(
    history: Sequence[Mapping[str, Any]] | None,
    *,
    max_items: int = 16,
    max_chars: int = 1200,
) -> List[Dict[str, str]]:
    allowed = {"user", "assistant"}
    out: List[Dict[str, str]] = []
    for item in list(history or [])[-max_items:]:
        role = str(item.get("role") or "").strip()
        content = _message_content(item)
        if role == "assistant":
            content = _strip_reasoning_leak(content)
        content = _clip_text(content, max_chars)
        if role in allowed and content:
            out.append({"role": role, "content": content})
    return out


def _compact_search_result(item: Mapping[str, Any], *, aggressive: bool) -> Dict[str, Any]:
    synopsis_limit = 180 if aggressive else 320
    grok_limit = 220 if aggressive else 420
    grok = item.get("grok") if isinstance(item.get("grok"), Mapping) else {}
    return {
        "product_code": item.get("product_code") or "",
        "title_ko": item.get("title_ko") or "",
        "title_ja": item.get("title_ja") or "",
        "actors": (item.get("actors") or [])[:3 if aggressive else 5],
        "genres": (item.get("genres") or [])[:4 if aggressive else 7],
        "synopsis": _clip_text(item.get("synopsis") or "", synopsis_limit),
        "source": item.get("source") or "",
        "score": item.get("score") or 0,
        "persona_match_score": item.get("persona_match_score") or 0,
        "ranking_reasons": (item.get("ranking_reasons") or [])[:3 if aggressive else 5],
        "matched_persona_terms": (item.get("matched_persona_terms") or [])[:4 if aggressive else 6],
        "grok": {
            "summary": _clip_text((grok or {}).get("summary") or "", grok_limit),
            "tags": ((grok or {}).get("tags") or [])[:6 if aggressive else 10],
            "tones": ((grok or {}).get("tones") or [])[:4 if aggressive else 6],
        },
    }


def _compact_chat_context(ctx: Mapping[str, Any], *, aggressive: bool = False) -> Dict[str, Any]:
    recommendation_focus = (
        ctx.get("sensual_recommendation_focus")
        if isinstance(ctx.get("sensual_recommendation_focus"), Mapping)
        else {}
    )
    persona = ctx.get("persona") if isinstance(ctx.get("persona"), Mapping) else {}
    sensual_focus = persona.get("sensual_focus") if isinstance(persona.get("sensual_focus"), Mapping) else {}
    taste = ctx.get("taste_context") if isinstance(ctx.get("taste_context"), Mapping) else {}
    search = ctx.get("library_search") if isinstance(ctx.get("library_search"), Mapping) else {}
    max_results = 2 if aggressive else 4
    max_products = 1 if aggressive else 2

    products = []
    for item in list(ctx.get("mentioned_products") or [])[:max_products]:
        if isinstance(item, Mapping):
            compact = _compact_search_result(item, aggressive=aggressive)
            story = item.get("story_context") if isinstance(item.get("story_context"), Mapping) else {}
            compact["story_context"] = {
                "summary": _clip_text(story.get("summary") or "", 220 if aggressive else 420),
                "tags": (story.get("tags") or [])[:6 if aggressive else 10],
                "tones": (story.get("tones") or [])[:4 if aggressive else 6],
            }
            products.append(compact)

    results = [
        _compact_search_result(item, aggressive=aggressive)
        for item in list(search.get("results") or [])[:max_results]
        if isinstance(item, Mapping)
    ]

    return {
        "sensual_recommendation_focus": {
            "summary": _clip_text(recommendation_focus.get("summary") or "", 240 if aggressive else 420),
            "turn_ons": (recommendation_focus.get("turn_ons") or [])[:4 if aggressive else 6],
            "instruction": _clip_text(recommendation_focus.get("instruction") or "", 160 if aggressive else 260),
        },
        "persona": {
            "type": persona.get("type", ""),
            "summary": _clip_text(persona.get("summary") or "", 450 if aggressive else 800),
            "sensual_summary": _clip_text(persona.get("sensual_summary") or "", 240 if aggressive else 420),
            "sensual_focus": {
                "priority": sensual_focus.get("priority") or "",
                "summary": _clip_text(sensual_focus.get("summary") or "", 240 if aggressive else 420),
                "instruction": _clip_text(sensual_focus.get("instruction") or "", 160 if aggressive else 260),
            },
            "turn_ons": (persona.get("turn_ons") or [])[:4 if aggressive else 6],
            "avoidances": (persona.get("avoidances") or [])[:3 if aggressive else 4],
            "affinities": (persona.get("affinities") or [])[:4 if aggressive else 6],
        },
        "taste_context": {
            "top_actors": (taste.get("top_actors") or [])[:3 if aggressive else 5],
            "top_genres": (taste.get("top_genres") or [])[:5 if aggressive else 8],
            "recent_genres": (taste.get("recent_genres") or [])[:3 if aggressive else 5],
            "tags": (taste.get("tags") or [])[:6 if aggressive else 10],
            "tones": (taste.get("tones") or [])[:4 if aggressive else 6],
        },
        "mentioned_products": products,
        "library_search": {
            "query": search.get("query") or "",
            "terms": search.get("terms") or [],
            "strict_title_terms": search.get("strict_title_terms") or [],
            "strict_title_contains": bool(search.get("strict_title_contains")),
            "source_policy": search.get("source_policy") or {},
            "product_codes": search.get("product_codes") or [],
            "fallback_seed_codes": search.get("fallback_seed_codes") or [],
            "ranking_policy": search.get("ranking_policy") or {},
            "results": results,
        },
    }


def _coalesce_response_text(payload: Mapping[str, Any]) -> str:
    try:
        message = (payload.get("choices") or [{}])[0].get("message") or {}
    except Exception:
        message = {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    return ""


def _reasoning_marker_text(value: str) -> str:
    return re.sub(r"[^a-z가-힣]+", " ", str(value or "").lower()).strip()


def _contains_reasoning_leak(text: str) -> bool:
    raw = str(text or "")
    if not raw.strip():
        return False

    lower = raw.lower()
    if re.search(
        r"^\s*(?:#+\s*)?(thinking process|reasoning process|chain of thought|analysis|internal reasoning|draft|plan)\s*:",
        lower,
        flags=re.IGNORECASE,
    ):
        return True

    normalized = _reasoning_marker_text(raw)
    markers = (
        "thinking process",
        "reasoning process",
        "chain of thought",
        "internal reasoning",
        "analyze request",
        "analyze the request",
        "we need answer",
        "need answer",
        "recall current state context",
        "analyze context",
        "analyze the context",
        "scan library search results",
        "analyze search results",
        "analyze the search results",
        "synthesize and structure",
        "drafting the analysis",
        "self correction",
        "final polish",
        "final response",
        "suggested response",
        "분석 과정",
        "추론 과정",
        "사고 과정",
        "내부 추론",
        "내부 계획",
        "초안",
        "최종 다듬기",
    )
    return any(marker in normalized for marker in markers)


def _strip_reasoning_leak(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""

    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<thinking>.*?</thinking>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(
        r"<redacted_thinking>.*?</redacted_thinking>",
        "",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()
    cleaned = re.sub(r"```(?:analysis|thinking|reasoning)[\s\S]*?```", "", cleaned, flags=re.IGNORECASE).strip()

    final_markers = (
        "Final Answer:",
        "Final Response:",
        "Suggested response:",
        "Suggested Response:",
        "Assistant Response:",
        "최종:",
        "최종 답변:",
        "최종 응답:",
        "답변:",
    )
    for marker in final_markers:
        idx = cleaned.lower().rfind(marker.lower())
        if idx >= 0:
            cleaned = cleaned[idx + len(marker) :].strip()
            break

    if _contains_reasoning_leak(cleaned):
        return ""
    return cleaned


def _openai_compatible_response(
    *,
    model: str,
    content: str,
    finish_reason: str = "stop",
    usage: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    now = int(time.time())
    return {
        "id": f"chatcmpl-persona-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": now,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": dict(usage or {}),
    }


def _with_truncation_note(content: str, finish_reason: str) -> str:
    if str(finish_reason or "").lower() != "length":
        return content
    note = "\n\n[응답이 길어져 여기서 잘렸습니다. 이어서 보려면 '계속'이라고 입력하세요.]"
    if note.strip() in content:
        return content
    return content.rstrip() + note


@dataclass
class PersonaChatService:
    """Persona chat gateway returning OpenAI-compatible ChatCompletion dicts."""

    engine: EroticPersonaEngine = field(default_factory=EroticPersonaEngine)
    memory_store: PersonaChatMemory = field(default_factory=PersonaChatMemory)
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    temperature: float = field(
        default_factory=lambda: _env_float(
            "JAVSTORY_PERSONA_CHAT_TEMPERATURE",
            1.05,
            min_value=0.2,
            max_value=1.3,
        )
    )
    max_tokens: int = field(
        default_factory=lambda: _env_int(
            "JAVSTORY_PERSONA_CHAT_MAX_TOKENS",
            2000,
            min_value=800,
            max_value=2000,
        )
    )
    timeout_sec: float = 180.0

    def _resolve_backend(self) -> tuple[str, str, str]:
        configured_base = (self.base_url or os.environ.get("JAVSTORY_PERSONA_CHAT_BASE_URL") or "").strip()
        configured_model = (self.model or os.environ.get("JAVSTORY_PERSONA_CHAT_MODEL") or "").strip()
        api_key = (self.api_key or os.environ.get("JAVSTORY_PERSONA_CHAT_API_KEY") or "").strip()

        if configured_base:
            base = configured_base.rstrip("/")
            if not base.endswith("/v1"):
                base = f"{base}/v1"
            model = configured_model or os.environ.get("JAVSTORY_LLAMACPP_MODEL", DEFAULT_PERSONA_CHAT_MODEL)
            return base, model, api_key or "local"

        preset = configured_model or os.environ.get("JAVSTORY_LLAMACPP_MODEL", DEFAULT_PERSONA_CHAT_MODEL)
        model = ensure_llamacpp_server_ready({"model": preset, "provider": "llamacpp"})
        return llamacpp_openai_base_url().rstrip("/"), model, api_key or "llamacpp"

    def build_messages(
        self,
        user_message: str,
        *,
        history: Sequence[Mapping[str, Any]] | None = None,
        product_code: str | None = None,
        force_final_only: bool = False,
        compact: bool = False,
    ) -> List[Dict[str, str]]:
        memory_context = self.memory_store.prompt_context(user_message, max_items=4 if compact else 7)
        context = self.engine.build_chat_context(
            user_message,
            product_code=product_code,
            seed_product_codes=_recommendation_seed_codes(memory_context),
        )
        context = _apply_personalized_ranking(context, memory_context)
        context_json = json.dumps(
            _compact_chat_context(context, aggressive=compact),
            ensure_ascii=False,
            default=str,
        )
        style_instruction = _response_style_instruction(user_message)
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": SENSUAL_PERSONA_SYSTEM_PROMPT},
            {
                "role": "system",
                "content": (
                    "현재 사용자 취향 컨텍스트 JSON이다. 이 데이터에 근거해 답하라.\n"
                    + context_json
                ),
            },
            {
                "role": "system",
                "content": (
                    "장기 대화 메모리 JSON이다. 사용자가 이전에 남긴 취향 단서, 강렬 반응, 교정, 말투 선호를 "
                    "현재 답변에 자연스럽게 반영하라. 단, DB/library_search 결과와 충돌하면 "
                    "DB/library_search를 우선하고 메모리는 보조 근거로만 사용하라.\n"
                    + json.dumps(memory_context, ensure_ascii=False)
                ),
            },
        ]
        if style_instruction:
            messages.append({"role": "system", "content": style_instruction})
        if force_final_only:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "중요: 이전 생성에서 내부 추론 초안이 노출됐다. 이번 응답은 반드시 한국어 최종 답변만 작성한다. "
                        "`Thinking Process`, `Analyze Request`, 번호 매긴 사고 과정, 영어 분석 메모, 내부 계획을 출력하면 안 된다. "
                        "바로 사용자에게 말하듯 자연스러운 대화문으로 3~8문장만 답하라."
                    ),
                }
            )
        messages.extend(
            _normalize_history(
                history,
                max_items=3 if compact else 6,
                max_chars=500 if compact else 900,
            )
        )
        messages.append({"role": "user", "content": str(user_message or "").strip()})
        return messages

    def _post_chat_completion(
        self,
        client: httpx.Client,
        *,
        base_url: str,
        payload: Mapping[str, Any],
        headers: Mapping[str, str],
    ) -> Dict[str, Any]:
        with llamacpp_request_scope():
            resp = client.post(f"{base_url}/chat/completions", json=dict(payload), headers=dict(headers))
        resp.raise_for_status()
        raw = resp.json()
        if not isinstance(raw, dict):
            raise RuntimeError("Persona chat backend returned a non-object response")
        return raw

    def _build_payload(
        self,
        *,
        model: str,
        text: str,
        history: Sequence[Mapping[str, Any]] | None,
        product_code: str | None,
        temperature: float,
        max_tokens: int,
        force_final_only: bool = False,
        compact: bool = False,
    ) -> Dict[str, Any]:
        return {
            "model": model,
            "messages": self.build_messages(
                text,
                history=history,
                product_code=product_code,
                force_final_only=force_final_only,
                compact=compact,
            ),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

    def chat(
        self,
        user_message: str,
        *,
        history: Sequence[Mapping[str, Any]] | None = None,
        product_code: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Dict[str, Any]:
        """Return an OpenAI-compatible chat completion response."""
        text = str(user_message or "").strip()
        if not text:
            return _openai_compatible_response(
                model=self.model or "persona-chat",
                content="어떤 작품이나 취향이 걸리는지 한 줄만 던져줘. 그 결을 바로 짚어줄게.",
            )

        base_url, model, api_key = self._resolve_backend()
        req_temperature = (
            _situational_temperature(text, self.temperature)
            if temperature is None
            else float(temperature)
        )
        req_max_tokens = (
            _situational_max_tokens(text, self.max_tokens)
            if max_tokens is None
            else max(800, min(2000, int(max_tokens)))
        )
        payload = self._build_payload(
            model=model,
            text=text,
            history=history,
            product_code=product_code,
            temperature=req_temperature,
            max_tokens=req_max_tokens,
        )
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        with httpx.Client(timeout=httpx.Timeout(self.timeout_sec, connect=5.0)) as client:
            try:
                raw = self._post_chat_completion(
                    client,
                    base_url=base_url,
                    payload=payload,
                    headers=headers,
                )
            except httpx.HTTPStatusError as e:
                if e.response is None or e.response.status_code != 400:
                    raise
                payload = self._build_payload(
                    model=model,
                    text=text,
                    history=[],
                    product_code=product_code,
                    temperature=min(0.85, req_temperature),
                    max_tokens=min(700, req_max_tokens),
                    force_final_only=True,
                    compact=True,
                )
                raw = self._post_chat_completion(
                    client,
                    base_url=base_url,
                    payload=payload,
                    headers=headers,
                )
            content = _strip_reasoning_leak(_coalesce_response_text(raw))
            if not content:
                retry_payload = self._build_payload(
                    model=model,
                    text=text,
                    history=history,
                    product_code=product_code,
                    temperature=min(0.85, req_temperature),
                    max_tokens=min(700, req_max_tokens),
                    force_final_only=True,
                    compact=True,
                )
                try:
                    raw = self._post_chat_completion(
                        client,
                        base_url=base_url,
                        payload=retry_payload,
                        headers=headers,
                    )
                except httpx.HTTPStatusError as e:
                    if e.response is None or e.response.status_code != 400:
                        raise
                    retry_payload = self._build_payload(
                        model=model,
                        text=text,
                        history=[],
                        product_code=product_code,
                        temperature=0.75,
                        max_tokens=500,
                        force_final_only=True,
                        compact=True,
                    )
                    raw = self._post_chat_completion(
                        client,
                        base_url=base_url,
                        payload=retry_payload,
                        headers=headers,
                    )
                content = _strip_reasoning_leak(_coalesce_response_text(raw))

        if content:
            try:
                self.memory_store.record_turn(text, content)
            except Exception:
                pass
            usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
            finish = "stop"
            try:
                finish = raw["choices"][0].get("finish_reason") or "stop"
            except Exception:
                pass
            content = _with_truncation_note(content, finish)
            return _openai_compatible_response(
                model=str(raw.get("model") or model),
                content=content,
                finish_reason=finish,
                usage=usage,
            )

        return _openai_compatible_response(
            model=str(raw.get("model") or model),
            content="답변 형식이 내부 초안처럼 생성돼서 표시하지 않았어. 같은 질문을 한 번만 다시 보내줘.",
            finish_reason="empty",
            usage=raw.get("usage") if isinstance(raw.get("usage"), dict) else {},
        )


def example_persona_chat_call() -> Dict[str, Any]:
    """Small callable example for integration tests or manual GUI wiring."""
    service = PersonaChatService()
    return service.chat(
        "HBAD-509 같은 작품이 왜 내 취향에 꽂히는지 강하게 분석해줘.",
        history=[],
    )
