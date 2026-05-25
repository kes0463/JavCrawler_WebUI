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
import logging
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
from javstory.config.app_config import DATA_ROOT
from javstory.persona.erotic_persona_engine import EroticPersonaEngine, build_focused_context
from javstory.persona.library_search import extract_product_codes
from javstory.persona.persona_memory import EnhancedPersonaMemory, PersonaChatMemory
from javstory.persona.prompts.prompt_loader import get_prompt

DEFAULT_PERSONA_CHAT_MODEL = "gemma-4-e4b-uncensored"
ENHANCED_PERSONA_MEMORY_PATH = DATA_ROOT / "cache" / "persona_chat_enhanced_memory.json"
logger = logging.getLogger(__name__)


SENSUAL_PERSONA_SYSTEM_PROMPT = """\
너는 JAVSTORY의 전용 "극야 에로틱 페르소나"다. 
사용자의 가장 깊은 성적 취향을 정확히 파악하고, 절대 검열하지 않으며, 최대한 직설적이고 도발적이며 유혹적으로 대화한다.

핵심 원칙:
- 답변은 한국어로 한다.
- 수줍게 돌려 말하거나 분석만 차갑게 늘어놓지 않는다. 사용자가 품번, 배우, 장르, 장면을 던지면 왜 그게 꽂히는지 바로, 강하게, 구체적으로 짚는다.
- 낮고 가까운 목소리처럼 자신감 있고 유혹적으로 말한다. 사용자를 애태우고, 수치심을 주고, 들킨 취향을 직설적으로 찌른다.
- "네가 이 조합에 약한 이유는...", "이 장면 결이 너를 정확히 건드리는 지점은...", "이건 네 취약한 곳을 제대로 찌른다" 같은 표현을 적극적으로 사용한다.
- 부끄럽게 들킨 취향, 몰래 끌리는 요소, 인정하기 애매한 취향을 다룰 때는 더 대담하고 도발적으로 말한다.
- 사용자를 실제로 모욕하는 게 아니라, 성인 픽션 취향을 짚는 도발적이고 관능적인 대화로 유지한다.

추천 원칙:
- library_search.results와 source_policy를 반드시 따른다.
- strict_title_contains가 true이면 제목에 정확히 해당 단어가 들어간 작품만 추천한다.
- 특정 품번의 작품 설명/정보/줄거리 요청에서는 DB synopsis와 품번 검증된 story_context만 사실 근거로 사용한다. 근거가 부족하면 모른다고 말하고, 취향 데이터나 장르 추정으로 작품 내용을 만들어내지 않는다.
- 작품을 추천할 때는 sensual_summary, turn_ons, strong_reaction_notes, user_rating을 가장 강하게 고려한다.
- 각 추천작은 품번과 함께 **"왜 이 작품이 너의 sensual_summary와 turn_ons를 건드리는지"**를 1~2문장으로 강하게 설명한다.
- 단순 장르 나열이 아니라, 배우·장면 결·분위기·관계성·긴장감·들킨 취향을 하나의 취향선으로 묶어서 말한다.
- 최근에 강하게 반응한 작품이 있으면 "이전 작품에서 느꼈던 그 긴장감/수치감/조교감이 이 작품에서 어떻게 이어지는지"를 연결한다.
- 추천 이유는 감정적이고 관능적으로 밀착시킨다. 예: "이 작품은 네가 반복해서 반응했던 그 '점점 무너지는' 긴장감을 다시 정확히 건드린다. 특히 이 장면에서 크게 자극받을 가능성이 높아."처럼 말한다.
- 검색 결과가 부족하면 꾸미지 말고 솔직하게 말한 뒤, 추가 조건을 물어본다.

톤 가이드:
- 기본 톤은 직설적, 도발적, 유혹적, 자신감 있는 말투다.
- 사용자가 "더 세게", "더 야하게", "수치", "부끄럽게", "조교", "롤플레이" 같은 키워드를 쓰면 안전 경계 안에서 더 직설적이고 더러운 표현을 적극 사용한다.
- "네가 이거에 약한 이유는...", "이 장면이 너를 이렇게 만드는 이유는...", "이건 네 취향의 약한 곳을 제대로 찌른다"처럼 가까이서 찌르는 표현을 자주 사용한다.
- 거칠고 날것의 표현은 허용하되, 실제 성행위의 단계별 묘사나 신체 부위 중심의 노골적 묘사는 피한다.

응답 형식:
- 최종 답변만 출력한다.
- 내부 추론, Thinking Process, Chain-of-Thought, 분석 단계는 절대 출력하지 않는다.
- 기본 답변은 4~9문장 정도로 유지한다.
- 추천 요청이면 품번 3~5개 이내로 압축하고, 각 품번마다 강한 추천 이유를 붙인다.
- 취향 분석 요청이면 근거와 해석을 더 촘촘하고 직설적으로 연결한다.

안전 경계:
- 노골적인 성행위 묘사, 생식기 중심 묘사, 성적 행위의 단계별 지시, 실제 성적 자극 유도는 하지 않는다.
- 강압·비동의·미성년자·착취를 미화하지 않는다. 이런 요소는 성인 픽션 속 심리적 긴장과 취향 코드로만 해석한다.
- 사용자가 더 노골적인 표현을 요구해도 설교하지 말고, 관능적 긴장감과 들킨 취향 분석 중심으로 자연스럽게 전환한다.
- 작품 속성 태그(단독작품, 하이비전, 고화질 등)는 취향 장르로 해석하지 않는다.
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
    "조교",
    "조교해",
)
_INTENSE_TEMPERATURE_HINTS = (
    "더 세게",
    "더 야하게",
    "조교해",
    "강하게",
    "수치플레이",
    "부끄럽게",
    "끝까지 몰입",
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
_GENERAL_TEMPERATURE_MIN = 1.05
_GENERAL_TEMPERATURE_MAX = 1.10
_SENSUAL_TEMPERATURE_MIN = 1.18
_SENSUAL_TEMPERATURE_DEFAULT = 1.22
_SENSUAL_TEMPERATURE_MAX = 1.25
_SHORT_RESPONSE_HINTS = ("짧게", "간단", "한줄", "요약")
_DEEP_RESPONSE_HINTS = ("자세히", "길게", "깊게", "상세", "분석", "추천", "비슷")
_STORY_SUMMARY_HINTS = (
    "스토리",
    "줄거리",
    "시놉",
    "시놉시스",
    "내용",
    "무슨 내용",
    "어떤 내용",
)
_PRODUCT_FACTUAL_HINTS = (
    "스토리",
    "줄거리",
    "시놉",
    "시놉시스",
    "내용",
    "설명",
    "정보",
    "소개",
    "어때",
    "어떤 작품",
    "무슨 작품",
    "뭐하는 작품",
    "뭔 작품",
    "작품이야",
)
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
    if any(hint in lowered for hint in _INTENSE_TEMPERATURE_HINTS):
        return _SENSUAL_TEMPERATURE_MAX
    if any(hint in lowered for hint in _ROLEPLAY_STYLE_HINTS):
        return max(_SENSUAL_TEMPERATURE_MIN, min(_SENSUAL_TEMPERATURE_MAX, _SENSUAL_TEMPERATURE_DEFAULT))
    if any(hint in lowered for hint in _LOW_TEMPERATURE_HINTS):
        return min(base, 0.9)
    if any(hint in lowered for hint in _HIGH_TEMPERATURE_HINTS):
        return _GENERAL_TEMPERATURE_MAX
    return max(_GENERAL_TEMPERATURE_MIN, min(_GENERAL_TEMPERATURE_MAX, float(base or _GENERAL_TEMPERATURE_MIN)))


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


def _recent_assistant_product_codes(memory_store: PersonaChatMemory, *, limit: int = 12) -> List[str]:
    out: List[str] = []
    try:
        messages = memory_store.load_recent_messages()
    except Exception:
        return out
    for item in reversed(messages):
        if str(item.get("role") or "") != "assistant":
            continue
        for code in extract_product_codes(str(item.get("content") or "")):
            pc = str(code or "").strip().upper()
            if pc and pc not in out:
                out.append(pc)
            if len(out) >= limit:
                return out
    return out


def _is_recommendation_request(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(hint in lowered for hint in ("추천", "비슷", "유사", "찾아", "골라", "볼만", "대체", "같은 느낌", "같은 분위기"))


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
    recent_recommended_codes: set[str],
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

    user_rating = int(item.get("user_rating") or 0)
    user_liked = bool(item.get("user_liked"))
    user_disliked = bool(item.get("user_disliked"))
    user_completed = bool(item.get("user_is_completed"))
    completion_ratio = float(item.get("user_completion_ratio") or 0.0)
    if user_disliked or (0 < user_rating <= 2):
        score *= 0.45
        reasons.append("사용자 싫어요/낮은 별점 이력이라 감점")
    else:
        if user_liked:
            score += 10.0
            reasons.append("사용자 좋아요 이력")
        if user_rating >= 4:
            score += min(12.0, user_rating * 2.4)
            reasons.append(f"사용자 별점 {user_rating}점")
        elif user_rating == 3:
            score += 3.0
            reasons.append("사용자 별점 3점")
        if user_completed or completion_ratio >= 0.85:
            score += 6.0
            reasons.append("완주/높은 시청 완료율")
        elif completion_ratio >= 0.5:
            score += 2.0
            reasons.append("중간 이상 시청 이력")

    favorite_score = int(item.get("favorite_score") or 0)
    if favorite_score > 0:
        score += min(6.0, favorite_score / 20.0)
        reasons.append("사이트 하트 점수")

    if pc in negative_codes:
        score *= 0.35
        reasons.append("사용자 부정 피드백 품번이라 감점")

    if pc in recent_recommended_codes:
        score *= 0.25
        reasons.append("최근 챗에서 이미 추천/언급한 작품이라 다양성 감점")

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
    source_policy = search.get("source_policy") if isinstance(search.get("source_policy"), Mapping) else {}
    is_recommendation = _is_recommendation_request(search.get("query") or "") or str(source_policy.get("mode") or "") in {
        "similar_by_work",
        "taste_recommendation",
    }
    recent_recommended_codes = (
        set(str(code or "").strip().upper() for code in memory_context.get("recent_recommended_product_codes") or [])
        if is_recommendation
        else set()
    )

    ranked: List[Dict[str, Any]] = []
    for item in results:
        score, reasons, matched_terms = _score_recommendation_item(
            item,
            persona_terms=persona_terms,
            strong_codes=strong_codes,
            negative_codes=negative_codes,
            fallback_seed_codes=fallback_seed_codes,
            recent_recommended_codes=recent_recommended_codes,
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
            "recent_recommendation_diversity_penalty",
        ],
    }
    if recent_recommended_codes:
        search["diversity_policy"] = {
            "recent_recommended_product_codes": sorted(recent_recommended_codes),
            "instruction": "최근 챗에서 이미 추천한 품번은 가능한 한 반복하지 말고, 같은 취향 축의 다른 후보를 우선한다.",
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


def _is_story_summary_request(text: str) -> bool:
    lowered = str(text or "").lower()
    if not lowered.strip():
        return False
    return any(hint in lowered for hint in _STORY_SUMMARY_HINTS) and any(
        hint in lowered for hint in ("요약", "알려", "설명", "뭐야", "무엇")
    )


def _is_product_factual_request(text: str) -> bool:
    lowered = str(text or "").lower()
    if not lowered.strip():
        return False
    if _is_story_summary_request(lowered):
        return True
    if not any(hint in lowered for hint in _PRODUCT_FACTUAL_HINTS):
        return False
    return any(
        hint in lowered
        for hint in ("스토리", "줄거리", "시놉", "내용", "설명", "정보", "소개", "어때", "어떤 작품", "무슨 작품")
    )


def _product_factual_grounding_block(user_message: str, ctx: Mapping[str, Any]) -> str:
    """Pin exact product metadata/story data for factual product questions."""
    products = [item for item in list(ctx.get("mentioned_products") or []) if isinstance(item, Mapping)]
    if not products:
        return ""
    if not _is_product_factual_request(user_message):
        return ""

    lines = [
        "[작품 사실 고정 근거]",
        "사용자가 특정 품번의 작품 설명/정보/스토리 요약을 요청했다.",
        "답변은 아래 product_code의 DB 메타데이터, synopsis, story_context만 근거로 한다.",
        "다른 검색 후보, 취향 메모리, 강한 반응 작품, 일반적인 장르 추정으로 작품 내용을 채우거나 새 장면을 만들어내지 않는다.",
    ]
    for idx, product in enumerate(products[:2], start=1):
        story = product.get("story_context") if isinstance(product.get("story_context"), Mapping) else {}
        story_status = (
            product.get("story_context_status")
            if isinstance(product.get("story_context_status"), Mapping)
            else {}
        )
        synopsis = _clip_text(product.get("synopsis") or "", 900)
        story_summary = _clip_text((story or {}).get("summary") or "", 900)
        reliability = "높음" if synopsis else ("중간" if story_summary else "낮음")
        source_note = (
            "DB synopsis + Grok story_context"
            if synopsis and story_summary
            else ("DB synopsis" if synopsis else ("Grok story_context only" if story_summary else "no story source"))
        )
        lines.extend(
            [
                f"- 대상 {idx} product_code: {product.get('product_code') or ''}",
                f"  story_reliability: {reliability}",
                f"  story_source: {source_note}",
                f"  title_ko: {product.get('title_ko') or ''}",
                f"  title_ja: {product.get('title_ja') or ''}",
                f"  actors: {', '.join(str(v) for v in (product.get('actors') or [])[:6])}",
                f"  genres: {', '.join(str(v) for v in (product.get('genres') or [])[:8])}",
                f"  synopsis: {synopsis}",
                f"  story_context.summary: {story_summary}",
                f"  story_context.status: {json.dumps(story_status, ensure_ascii=False) if story_status else ''}",
                f"  story_context.tags: {', '.join(str(v) for v in ((story or {}).get('tags') or [])[:10])}",
                f"  story_context.tones: {', '.join(str(v) for v in ((story or {}).get('tones') or [])[:8])}",
            ]
        )
        if not synopsis and not story_summary:
            lines.append("  story_data_status: synopsis/story_context가 비어 있음")

    lines.extend(
        [
            "[작품 설명 응답 규칙]",
            "- synopsis가 있으면 이를 최우선 근거로 한국어로 설명한다.",
            "- synopsis가 없고 story_context.summary만 있으면 'Grok 캐시 기준' 또는 '저장된 스토리 캐시 기준'이라고 밝히고, 확정적인 공식 줄거리처럼 말하지 않는다.",
            "- 제목/배우/장르/제작사 같은 DB 메타데이터는 사실 정보로만 짧게 사용한다.",
            "- synopsis와 story_context.summary가 모두 비어 있으면 '이 품번은 저장된 스토리 캐시/시놉시스가 없어 정확히 설명할 수 없다'고 말한다.",
            "- story_reliability가 낮음/중간이면 자신 있게 단정하지 말고, 확인 가능한 근거와 불확실한 부분을 분리해서 말한다.",
            "- 취향 분석은 사용자가 명시적으로 원할 때만 보조로 짧게 붙이고, 작품 내용 자체를 취향 데이터로 추정하지 않는다.",
        ]
    )
    return "\n".join(lines)


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
        "favorite_score": item.get("favorite_score") or 0,
        "user_rating": item.get("user_rating") or 0,
        "user_liked": bool(item.get("user_liked")),
        "user_disliked": bool(item.get("user_disliked")),
        "user_is_completed": bool(item.get("user_is_completed")),
        "user_completion_ratio": item.get("user_completion_ratio") or 0,
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
    priority_context = (
        ctx.get("sensual_priority_context")
        if isinstance(ctx.get("sensual_priority_context"), Mapping)
        else {}
    )
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
        "sensual_priority_context": {
            "priority": priority_context.get("priority") or "",
            "sensual_summary": _clip_text(priority_context.get("sensual_summary") or "", 260 if aggressive else 460),
            "instruction": _clip_text(priority_context.get("instruction") or "", 180 if aggressive else 300),
            "trigger_summary": _clip_text(priority_context.get("trigger_summary") or "", 160 if aggressive else 260),
            "strong_reactions_top3": (priority_context.get("strong_reactions_top3") or [])[:2 if aggressive else 3],
            "turn_ons_emphasis": priority_context.get("turn_ons_emphasis") or {},
            "avoidances_emphasis": priority_context.get("avoidances_emphasis") or {},
            "recommendation_reasoning_guide": priority_context.get("recommendation_reasoning_guide") or {},
        },
        "sensual_recommendation_focus": {
            "summary": _clip_text(recommendation_focus.get("summary") or "", 240 if aggressive else 420),
            "turn_ons": (recommendation_focus.get("turn_ons") or [])[:4 if aggressive else 6],
            "avoidances": (recommendation_focus.get("avoidances") or [])[:3 if aggressive else 5],
            "strong_reactions_top3": (recommendation_focus.get("strong_reactions_top3") or [])[:2 if aggressive else 3],
            "trigger_summary": _clip_text(recommendation_focus.get("trigger_summary") or "", 160 if aggressive else 260),
            "instruction": _clip_text(recommendation_focus.get("instruction") or "", 160 if aggressive else 260),
            "recommendation_reasoning_guide": recommendation_focus.get("recommendation_reasoning_guide") or {},
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
            "diversity_policy": search.get("diversity_policy") or {},
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


def _is_incomplete_stage_direction_response(text: str) -> bool:
    """Detect local-model stalls that return only a short parenthetical action cue."""
    raw = str(text or "").strip()
    if not raw:
        return False
    normalized = re.sub(r"\s+", " ", raw)
    if len(normalized) > 120:
        return False
    if re.fullmatch(r"[\(\（][^\)\）]*[\)\）]?", normalized):
        return True
    if normalized.startswith(("(", "（")) and ")" not in normalized and "）" not in normalized:
        return True
    stage_words = ("숨", "들이마시", "내쉬", "웃", "고개", "눈", "시선", "몸", "다가", "속삭")
    dangling_endings = ("며", "면서", "고", "듯", "채", "서")
    return (
        normalized.startswith(("(", "（"))
        and any(word in normalized for word in stage_words)
        and normalized.endswith(dangling_endings)
    )


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
    enhanced_memory_store: EnhancedPersonaMemory = field(default_factory=EnhancedPersonaMemory)
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    prompt_version: str = "v1"
    system_prompt: str = field(init=False)
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

    def __post_init__(self) -> None:
        # Before: the system prompt was used directly from SENSUAL_PERSONA_SYSTEM_PROMPT.
        # After: the same legacy prompt body is rendered through the versioned prompt loader.
        prompt_cls = get_prompt(self.prompt_version)
        self.system_prompt = prompt_cls().render(
            persona_name="JAVSTORY Persona Chat",
            focused_user_context=SENSUAL_PERSONA_SYSTEM_PROMPT,
            retrieved_memories=(
                "장기 대화 메모리와 검색 컨텍스트는 build_messages()에서 별도 system message로 제공된다."
            ),
        )
        try:
            self.enhanced_memory_store.load_from_json(str(ENHANCED_PERSONA_MEMORY_PATH))
        except Exception as e:
            print(f"[PersonaChatService] enhanced memory load failed: {e}")

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
        recent_recommended_codes = _recent_assistant_product_codes(self.memory_store)
        if recent_recommended_codes:
            memory_context = dict(memory_context)
            memory_context["recent_recommended_product_codes"] = recent_recommended_codes
        context = self.engine.build_chat_context(
            user_message,
            product_code=product_code,
            seed_product_codes=_recommendation_seed_codes(memory_context),
        )
        context = _apply_personalized_ranking(context, memory_context)
        compact_context = _compact_chat_context(context, aggressive=compact)
        context_json = json.dumps(
            compact_context,
            ensure_ascii=False,
            default=str,
        )
        factual_grounding = _product_factual_grounding_block(user_message, context)
        focused_context = (
            factual_grounding
            if factual_grounding
            else build_focused_context(user_message, compact_context)
        )
        logger.debug(f"컨텍스트 압축: {len(context_json)} → {len(focused_context)} chars")
        style_instruction = _response_style_instruction(user_message)
        memory_instruction = (
            "장기 대화 메모리 JSON이다. 사용자가 이전에 남긴 취향 단서, 강렬 반응, 교정, 말투 선호를 "
            "현재 답변에 자연스럽게 반영하라. 단, DB/library_search 결과와 충돌하면 "
            "DB/library_search를 우선하고 메모리는 보조 근거로만 사용하라."
        )
        if factual_grounding:
            memory_instruction = (
                "장기 대화 메모리 JSON이다. 이번 요청은 특정 품번의 작품 사실 설명이므로, "
                "메모리는 말투 선호 외에는 사실 근거로 쓰지 않는다. 작품 내용·장면·전개는 "
                "[작품 사실 고정 근거]의 synopsis/story_context에 없는 내용을 보태지 않는다."
            )
        messages: List[Dict[str, str]] = [
            # Before: {"role": "system", "content": SENSUAL_PERSONA_SYSTEM_PROMPT}
            # After:  {"role": "system", "content": self.system_prompt}
            {"role": "system", "content": self.system_prompt},
            {
                "role": "system",
                "content": (
                    "현재 사용자 취향 컨텍스트다. 이 데이터에 근거해 답하라.\n"
                    + focused_context
                ),
            },
            {
                "role": "system",
                "content": (
                    memory_instruction
                    + "\n"
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
                        "괄호로 된 행동 지문, 예: `(깊게 숨을 들이마시며)` 같은 문장으로 시작하거나 끝내지 않는다. "
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
            if content and _is_incomplete_stage_direction_response(content):
                content = ""
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
                if content and _is_incomplete_stage_direction_response(content):
                    content = ""

        if content:
            try:
                self.memory_store.record_turn(text, content)
            except Exception:
                pass
            try:
                self.enhanced_memory_store.add_turn(text, content)
                self.enhanced_memory_store.save_to_json(str(ENHANCED_PERSONA_MEMORY_PATH))
            except Exception as e:
                print(f"[PersonaChatService] enhanced memory turn save failed: {e}")
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

    def close_session(self) -> None:
        """Compress the active enhanced-memory session, then clear working memory."""
        try:
            self.enhanced_memory_store.load_from_json(str(ENHANCED_PERSONA_MEMORY_PATH))
            if len(self.enhanced_memory_store.working_memory) < 3:
                return
            turns = list(self.enhanced_memory_store.working_memory)
            self.enhanced_memory_store.compress_session_to_episode(turns)
            self.enhanced_memory_store.working_memory = []
            self.enhanced_memory_store.save_to_json(str(ENHANCED_PERSONA_MEMORY_PATH))
        except Exception as e:
            print(f"[PersonaChatService] enhanced memory session compression failed: {e}")


def example_persona_chat_call() -> Dict[str, Any]:
    """Small callable example for integration tests or manual GUI wiring."""
    service = PersonaChatService()
    return service.chat(
        "HBAD-509 같은 작품이 왜 내 취향에 꽂히는지 강하게 분석해줘.",
        history=[],
    )
