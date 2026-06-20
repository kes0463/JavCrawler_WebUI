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
from javstory.persona.persona_memory import EnhancedPersonaMemory
from javstory.persona.prompts.prompt_loader import get_prompt

DEFAULT_PERSONA_CHAT_MODEL = "gemma-4-e4b-uncensored"
ENHANCED_PERSONA_MEMORY_PATH = DATA_ROOT / "cache" / "persona_chat_enhanced_memory.json"
logger = logging.getLogger(__name__)


def persona_chat_model_from_env(value: str | None = None) -> str:
    raw = (
        value
        if value is not None
        else os.environ.get("JAVSTORY_PERSONA_CHAT_MODEL", "")
    )
    model = (raw or "").strip().lower()
    if model.startswith("llamacpp:"):
        model = model.split(":", 1)[1].strip()
    if "qwen3-14" in model or "qwen3_14" in model or ("qwen" in model and "14" in model):
        return "qwen3-14b-uncensored"
    if "qwen3.5" in model or "35b" in model or "a3b" in model:
        return "qwen3-14b-uncensored"
    if "gemma" in model:
        return "gemma-4-e4b-uncensored"
    return DEFAULT_PERSONA_CHAT_MODEL


SENSUAL_PERSONA_SYSTEM_PROMPT = """\
너는 JAVSTORY의 전용 "매우 야한 에로틱 페르소나"다. 
사용자의 가장 은밀하고 강렬한 성적 취향을 완벽하게 파악하고, 절대 검열하거나 부드럽게 포장하지 않는다. 
최대한 직설적이고, 도발적이며, 수치심을 자극하면서도 유혹적으로 대화한다.

핵심 원칙:
- 답변은 한국어로 한다.
- 수줍게 돌려 말하지 않는다. 사용자가 품번, 배우, 장르, 장면을 언급하면 왜 그게 강하게 꽂히는지 바로, 노골적으로, 구체적으로 찌른다.
- 낮고 가까운 목소리로, 자신감 있게 애태우며 말한다. 사용자의 들킨 취향, 약한 부분, 부끄러운 욕망을 직설적으로 파고든다.
- "네가 이거에 이렇게 약한 이유는...", "이 장면이 너를 이렇게 만드는 지점은...", "이건 네 취향의 가장 민감한 곳을 정확히 찌른다" 같은 표현을 적극 사용한다.
- 부끄럽고 인정하기 힘든 취향을 다룰 때는 더 대담하고, 자극적으로 말한다. 사용자를 실제로 모욕하는 게 아니라, 성인 픽션 속에서 강하게 자극하는 도발적인 말투로 유지한다.

추천 원칙:
- library_search.results와 source_policy를 철저히 따른다.
- 작품 추천은 반드시 실제 검색 후보 안에서만 한다. 가짜 품번이나 없는 작품은 절대 만들지 않는다.
- 작품을 추천할 때는 sensual_summary와 turn_ons를 가장 강하게 고려한다.
- 각 추천마다 "이 작품이 네 sensual_summary의 어떤 부분을 건드리는지", "네가 이전에 강하게 반응했던 그 긴장감·수치감·조교감을 어떻게 자극하는지"를 직설적으로 설명한다.
- 단순 장르 나열이 아니라, 배우의 이미지, 장면 결, 관계성, 금기감, 수치심, 점점 무너지는 흐름 등을 연결해서 말한다.
- 최근 강하게 반응한 작품이 있으면 그 작품의 자극 포인트와 어떻게 이어지는지 명확히 연결한다.

톤 가이드:
- 기본적으로 직설적이고 도발적이며, 낮고 음란한 톤을 유지한다.
- 사용자가 "더 세게", "더 야하게", "수치", "부끄럽게", "조교", "애태워" 같은 말을 하면 안전 경계 안에서 최대한 직설적이고 더러운 표현을 사용한다.
- "네가 이 장면 보면 분명 단단해질걸?", "이런 상황에서 네가 어떻게 될지 상상돼?", "네 약한 부분 제대로 건드리는 작품이야" 같은 애태우는 표현을 자연스럽게 쓴다.
- 거칠고 날것의 말투를 허용하되, 실제 성행위의 단계별 묘사나 신체 부위 중심의 극단적 노골적 표현은 피한다.

응답 형식:
- 최종 답변만 출력한다. 내부 추론, 생각 과정, 분석 단계는 절대 넣지 않는다.
- 기본적으로 5~10문장 정도로 유지한다.
- 추천 요청 시 품번 3~5개 정도로 압축하고, 각 품번마다 강한 추천 이유를 붙인다.
- 취향 분석 요청 시 근거를 바탕으로 더 직설적이고 날카롭게 파고든다.

안전 경계:
- 실제 성행위의 단계별·노골적 신체 부위 중심 묘사는 최대한 자제한다.
- 강압, 비동의, 미성년자, 착취를 미화하거나 직접적으로 다루지 않는다.
- 사용자가 "더 세게", "더 야하게", "수치플레이" 등을 강하게 요구하면, 
  안전 경계 안에서 최대한 직설적이고 도발적인 표현을 허용한다.
- 사용자가 더 노골적인 표현을 원할 경우, 설교하거나 거부하지 말고 
  관능적 긴장감, 수치심, 들킨 취향 중심으로 자연스럽게 응답 강도를 높인다.
"""

COMPACT_PERSONA_SYSTEM_PROMPT = """\
너는 JAVSTORY의 성인 취향 페르소나 챗이다. 한국어 최종 답변만 한다.
제공된 취향/검색/메모리 근거 안에서만 답하고, 내부 추론·영어 분석·괄호 행동 지문은 출력하지 않는다.
추천은 library_search 후보 안에서만 하고, 작품 사실 설명은 synopsis/story_context에 없는 내용을 만들지 않는다.
톤은 직설적이고 도발적으로 유지하되, 3~7문장으로 압축한다.
"""

# v2 역할 핵심 — 단일 책임(역할·톤·안전)만 담고, 컨텍스트·규칙은 build_messages()가 별도 주입.
_ROLE_CORE_V2 = """\
직설적·도발적 톤으로 사용자의 취향을 파고든다.
- 품번·배우·장면을 언급하면 왜 꽂히는지 바로, 구체적으로 찌른다
- "네가 이거에 약한 이유는...", "이 장면이 너를 이렇게 만드는 지점은..." 같은 표현을 쓴다
- 부끄럽고 인정하기 힘든 취향일수록 더 대담하게 파고든다
- 실제 성행위 단계별 묘사와 신체 부위 극단적 표현은 피한다
- 강압·비동의·미성년자 미화는 하지 않는다\
"""

_STYLE_PROFILES_V2: Dict[str, str] = {
    "intense_sensual": "관능 강화: 관계성·긴장·금기감을 더 직접적으로. 신체 반응 단정 금지.",
    "shame_tension": "수치 톤: 들킨 취향·심리적 긴장 중심. 실제 수치 강요 금지.",
}

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
_FRESH_RECOMMENDATION_HINTS = (
    "다른",
    "딴",
    "새로운",
    "새 작품",
    "새 추천",
    "처음",
    "처음 보는",
    "처음 본",
    "또 추천",
    "더 추천",
    "겹치지",
    "중복",
    "말고",
    "빼고",
    "제외",
    "추천 안",
    "추천안",
    "추천 안 했",
    "추천 안했던",
    "추천 안 했던",
    "추천했던",
    "추천한 작품 말고",
    "이미 추천",
    "전에 추천",
    "안 본",
    "안본",
    "못 본",
    "못본",
    "미시청",
    "시청 안",
    "본 적 없는",
)
_UNWATCHED_RECOMMENDATION_HINTS = (
    "안 본",
    "안본",
    "못 본",
    "못본",
    "미시청",
    "시청 안",
    "본 적 없는",
    "처음 보는",
    "처음 본",
)
_RECOMMENDATION_NEGATION_HINTS = (
    "추천하지마",
    "추천하지 마",
    "추천 말아",
    "추천 빼줘",
    "추천 제외",
)
_FABRICATED_RECOMMENDATION_MARKERS = (
    "신규 코드",
    "가상 코드",
    "새 코드",
)
_RECENT_RECOMMENDATION_CONTEXT_LIMIT = 24
_RECOMMENDATION_GROUNDING_RESULT_LIMIT = 3
_PRODUCT_FACTUAL_GROUNDING_LIMIT = 1
# Temperature 범위 — 모든 값을 1.0 이하로 유지한다.
# 1.0 초과는 Gemma 등 로컬 모델에서 hallucination·reasoning leak을 유발한다.
_GENERAL_TEMPERATURE_MIN = 0.72   # 기본 응답 하한 (일반 대화·분석)
_GENERAL_TEMPERATURE_MAX = 0.82   # 기본 응답 상한
_SENSUAL_TEMPERATURE_MIN = 0.85   # 롤플레이·감성 응답 하한
_SENSUAL_TEMPERATURE_DEFAULT = 0.90  # 롤플레이·감성 응답 기본값
_SENSUAL_TEMPERATURE_MAX = 0.95   # 인텐스 요청 최대값 (≤ 1.0)
_LOW_TEMPERATURE_CAP = 0.62       # 검색·사실 정보 요청 상한 (정확도 우선)
_RECOMMENDATION_TEMPERATURE_CAP = 0.68  # 추천은 후보 고정이 중요하므로 창작 온도를 낮춘다.
_MAX_OUTPUT_TOKENS = 3072
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
    from javstory.persona.intent_classifier import classify_intent

    intent = classify_intent(text)
    lowered = (text or "").lower()

    # 인텐스 — 임베딩 또는 명시 키워드
    if intent == "intense_sensual" or any(hint in lowered for hint in _INTENSE_TEMPERATURE_HINTS):
        return _SENSUAL_TEMPERATURE_MAX
    # 수치/롤플레이 — 임베딩 또는 명시 키워드
    if intent in ("shame_tension",) or any(hint in lowered for hint in _ROLEPLAY_STYLE_HINTS):
        return max(_SENSUAL_TEMPERATURE_MIN, min(_SENSUAL_TEMPERATURE_MAX, _SENSUAL_TEMPERATURE_DEFAULT))
    # 사실 검색 — 창의성 낮게
    if intent == "factual_search" or any(hint in lowered for hint in _LOW_TEMPERATURE_HINTS):
        return min(base, _LOW_TEMPERATURE_CAP)
    # 추천 — 후보 고정 중요
    if intent == "recommendation" or _is_recommendation_request(lowered):
        return min(base, _RECOMMENDATION_TEMPERATURE_CAP)
    # 분석 대화 — 창의성 살짝 높게
    if intent == "general_analysis" or any(hint in lowered for hint in _HIGH_TEMPERATURE_HINTS):
        return _GENERAL_TEMPERATURE_MAX
    return max(_GENERAL_TEMPERATURE_MIN, min(_GENERAL_TEMPERATURE_MAX, float(base or _GENERAL_TEMPERATURE_MIN)))


def _situational_max_tokens(text: str, configured_max: int) -> int:
    from javstory.persona.intent_classifier import classify_intent

    intent = classify_intent(text)
    lowered = (text or "").lower()
    cap = max(800, min(_MAX_OUTPUT_TOKENS, int(configured_max or 2600)))

    if any(hint in lowered for hint in _SHORT_RESPONSE_HINTS):
        desired = 800
    elif intent in ("intense_sensual", "shame_tension") or any(hint in lowered for hint in _ROLEPLAY_STYLE_HINTS):
        desired = _MAX_OUTPUT_TOKENS
    elif intent == "factual_search" or any(hint in lowered for hint in _LOW_TEMPERATURE_HINTS):
        desired = 1400
    elif intent in ("general_analysis", "recommendation") or any(hint in lowered for hint in _DEEP_RESPONSE_HINTS):
        desired = 2400
    else:
        desired = 1800
    return max(800, min(cap, desired))


def _persona_chat_max_tokens_for_context(text: str, configured_max: int) -> int:
    return _situational_max_tokens(text, configured_max)


def _response_style_instruction(text: str) -> str:
    from javstory.persona.intent_classifier import classify_intent

    intent = classify_intent(text)
    if intent == "shame_tension":
        return _STYLE_PROFILES["shame_tension"]
    if intent == "intense_sensual":
        return _STYLE_PROFILES["intense_sensual"]
    # 폴백: 키워드 매칭 (임베딩 불가 시)
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


def _recent_assistant_product_codes(memory_store: EnhancedPersonaMemory, *, limit: int = _RECENT_RECOMMENDATION_CONTEXT_LIMIT) -> List[str]:
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


def _recent_assistant_product_codes_from_history(
    history: Sequence[Mapping[str, Any]] | None,
    *,
    limit: int = _RECENT_RECOMMENDATION_CONTEXT_LIMIT,
) -> List[str]:
    out: List[str] = []
    for item in reversed(list(history or [])):
        if str(item.get("role") or "") != "assistant":
            continue
        for code in extract_product_codes(_message_content(item)):
            pc = str(code or "").strip().upper()
            if pc and pc not in out:
                out.append(pc)
            if len(out) >= limit:
                return out
    return out


def _is_recommendation_request(text: str) -> bool:
    lowered = str(text or "").lower()
    if any(hint in lowered for hint in _RECOMMENDATION_NEGATION_HINTS):
        return False
    return any(hint in lowered for hint in ("추천", "비슷", "유사", "찾아", "골라", "볼만", "대체", "같은 느낌", "같은 분위기"))


def _is_fresh_recommendation_request(text: str) -> bool:
    lowered = str(text or "").lower()
    return _is_recommendation_request(lowered) and any(hint in lowered for hint in _FRESH_RECOMMENDATION_HINTS)


def _is_unwatched_recommendation_request(text: str) -> bool:
    lowered = str(text or "").lower()
    return _is_recommendation_request(lowered) and any(hint in lowered for hint in _UNWATCHED_RECOMMENDATION_HINTS)


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
    avoid_reference_codes: bool = False,
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
        if avoid_reference_codes:
            score *= 0.35
            reasons.append("최근 강렬 반응 기준작이라 반복 추천 감점")
        else:
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


def _item_has_user_watch_signal(item: Mapping[str, Any]) -> bool:
    try:
        rating = int(item.get("user_rating") or 0)
    except (TypeError, ValueError):
        rating = 0
    try:
        completion_ratio = float(item.get("user_completion_ratio") or 0.0)
    except (TypeError, ValueError):
        completion_ratio = 0.0
    return (
        rating > 0
        or bool(item.get("user_liked"))
        or bool(item.get("user_disliked"))
        or bool(item.get("user_is_completed"))
        or completion_ratio > 0.0
    )


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
    query = str(search.get("query") or "")
    is_recommendation = _is_recommendation_request(query) or str(source_policy.get("mode") or "") in {
        "similar_by_work",
        "taste_recommendation",
    }
    recent_recommended_codes = (
        set(str(code or "").strip().upper() for code in memory_context.get("recent_recommended_product_codes") or [])
        if is_recommendation
        else set()
    )
    fresh_recommendation = _is_fresh_recommendation_request(query)
    unwatched_recommendation = _is_unwatched_recommendation_request(query)

    ranked: List[Dict[str, Any]] = []
    for item in results:
        score, reasons, matched_terms = _score_recommendation_item(
            item,
            persona_terms=persona_terms,
            strong_codes=strong_codes,
            negative_codes=negative_codes,
            fallback_seed_codes=fallback_seed_codes,
            recent_recommended_codes=recent_recommended_codes,
            avoid_reference_codes=is_recommendation,
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
    if fresh_recommendation and recent_recommended_codes:
        fresh_ranked = [
            item
            for item in ranked
            if str(item.get("product_code") or "").strip().upper() not in recent_recommended_codes
        ]
        if fresh_ranked:
            ranked = fresh_ranked
    if unwatched_recommendation:
        unwatched_ranked = [item for item in ranked if not _item_has_user_watch_signal(item)]
        ranked = unwatched_ranked
    search["ranking_policy"] = {
        "mode": "personalized_hybrid",
        "weights": [
            "sensual_summary_and_turn_ons",
            "strong_reaction_similarity",
            "grok_scene_richness",
            "embedding_similarity",
            "negative_feedback_penalty",
            "recent_recommendation_diversity_penalty",
            "unwatched_request_filter",
        ],
    }
    if recent_recommended_codes:
        search["diversity_policy"] = {
            "recent_recommended_product_codes": sorted(recent_recommended_codes),
            "instruction": "최근 챗에서 이미 추천한 품번은 반복하지 말고, 사용자가 안 본/추천 안 했던 작품을 요청하면 새 후보만 고른다.",
            "fresh_request": fresh_recommendation,
            "unwatched_request": unwatched_recommendation,
            "strict_exclusion_applied": fresh_recommendation and any(
                str(item.get("product_code") or "").strip().upper() not in recent_recommended_codes
                for item in results
            ),
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


def _format_memory_readable(
    memory_context: Mapping[str, Any],
    *,
    factual: bool = False,
    compact: bool = False,
) -> str:
    """메모리 컨텍스트를 JSON 덤프 대신 로컬 모델이 읽기 쉬운 텍스트로 변환.

    JSON 덤프 방식 대비 약 60~80% 토큰 절감 효과.
    """
    prefs = list(memory_context.get("preference_notes") or [])
    reactions = list(memory_context.get("strong_reaction_notes") or [])
    negatives = list(memory_context.get("negative_feedback_notes") or [])
    styles = list(memory_context.get("style_notes") or [])
    recent = list(memory_context.get("recent_recommended_product_codes") or [])

    if not any([prefs, reactions, negatives, styles, recent]):
        return ""

    limit = 1 if compact else 3
    parts: List[str] = ["[대화 기억]"]

    if prefs and not factual:
        texts = [
            _clip_text(str(n["text"]), 90)
            for n in prefs[:limit]
            if isinstance(n, dict) and n.get("text")
        ]
        if texts:
            parts.append("취향: " + " / ".join(texts))

    if reactions and not factual:
        items: List[str] = []
        for n in reactions[:limit]:
            if not isinstance(n, dict):
                continue
            pcs = ", ".join(str(c) for c in (n.get("product_codes") or [])[:2])
            text = _clip_text(str(n.get("text") or ""), 90)
            items.append(f"{pcs}: {text}" if pcs else text)
        if items:
            parts.append("강한 반응: " + " / ".join(items))

    if negatives and not factual:
        texts = [
            _clip_text(str(n["text"]), 70)
            for n in negatives[:limit]
            if isinstance(n, dict) and n.get("text")
        ]
        if texts:
            parts.append("비선호: " + " / ".join(texts))

    if styles:
        style_texts = [_clip_text(str(s), 45) for s in styles[:2] if s]
        if style_texts:
            parts.append("말투: " + " / ".join(style_texts))

    if recent and not factual and not compact:
        parts.append("최근 추천: " + ", ".join(str(c) for c in recent[:8]))

    if len(parts) <= 1:
        return ""
    return "\n".join(parts)


def _build_output_rules(*, compact: bool = False, factual: bool = False) -> str:
    """응답 규칙을 메시지 끝에 배치 — 로컬 모델의 recency bias를 활용해 준수율을 높인다."""
    if factual:
        return (
            "[응답 규칙]\n"
            "- synopsis/story_context 근거만 사용, 없는 내용 추가 금지\n"
            "- 최종 답변만 출력 (괄호 지문·영어 분석·내부 추론 금지)"
        )
    if compact:
        return "[응답 규칙] 3~5문장, 추천 시 후보 품번만, 최종 답변만 출력"
    return (
        "[응답 규칙]\n"
        "- 5~8문장 (짧게 요청 시 3~4, 상세 요청 시 10~12)\n"
        "- 추천 시 후보 품번 3~4개 + 이유, 후보 외 품번 생성 금지\n"
        "- 최종 답변만 출력 (괄호 지문·영어 분석·내부 추론 금지)"
    )


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
        "특정 품번 설명 요청. 아래 DB metadata/synopsis/story_context만 근거로 답한다.",
        "다른 검색 후보, 취향 메모리, 장르 추정으로 작품 내용이나 장면을 만들지 않는다.",
    ]
    requested_code_count = len(extract_product_codes(user_message))
    product_limit = max(_PRODUCT_FACTUAL_GROUNDING_LIMIT, min(2, requested_code_count))
    for idx, product in enumerate(products[:product_limit], start=1):
        story = product.get("story_context") if isinstance(product.get("story_context"), Mapping) else {}
        story_status = (
            product.get("story_context_status")
            if isinstance(product.get("story_context_status"), Mapping)
            else {}
        )
        synopsis = _clip_text(product.get("synopsis") or "", 650)
        story_summary = _clip_text((story or {}).get("summary") or "", 650)
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
                f"  actors: {', '.join(str(v) for v in (product.get('actors') or [])[:4])}",
                f"  genres: {', '.join(str(v) for v in (product.get('genres') or [])[:5])}",
                f"  synopsis: {synopsis}",
                f"  story_context.summary: {story_summary}",
                f"  story_context.status: {json.dumps(story_status, ensure_ascii=False) if story_status else ''}",
                f"  story_context.tags: {', '.join(str(v) for v in ((story or {}).get('tags') or [])[:5])}",
                f"  story_context.tones: {', '.join(str(v) for v in ((story or {}).get('tones') or [])[:4])}",
            ]
        )
        if not synopsis and not story_summary:
            lines.append("  story_data_status: synopsis/story_context가 비어 있음")

    lines.extend(
        [
            "[작품 설명 응답 규칙]",
            "- synopsis 우선. story_context만 있으면 캐시 기준이며 공식 줄거리처럼 말하지 않는다.",
            "- 근거가 비어 있으면 정확히 설명할 수 없다고 말한다.",
            "- 낮은/중간 신뢰도는 확인 근거와 불확실성을 분리한다.",
        ]
    )
    return "\n".join(lines)


def _recommendation_grounding_block(
    user_message: str,
    ctx: Mapping[str, Any],
    memory_context: Mapping[str, Any],
) -> str:
    """Pin recommendation answers to retrieved library candidates only."""
    if not _is_recommendation_request(user_message):
        return ""

    search = ctx.get("library_search") if isinstance(ctx.get("library_search"), Mapping) else {}
    results = [item for item in list(search.get("results") or []) if isinstance(item, Mapping)]
    persona = ctx.get("persona") if isinstance(ctx.get("persona"), Mapping) else {}
    focus = ctx.get("sensual_recommendation_focus") if isinstance(ctx.get("sensual_recommendation_focus"), Mapping) else {}
    diversity = search.get("diversity_policy") if isinstance(search.get("diversity_policy"), Mapping) else {}
    recent_codes = [
        str(code or "").strip().upper()
        for code in (
            diversity.get("recent_recommended_product_codes")
            or memory_context.get("recent_recommended_product_codes")
            or []
        )
        if str(code or "").strip()
    ]

    lines = [
        "[추천 후보 고정 근거]",
        "추천은 반드시 아래 library_search.results 후보 안에서만 고른다.",
        "후보 목록에 없는 품번/제목/'(신규 코드: ...)'/가상 코드는 절대 만들지 않는다.",
        "후보가 부족하면 부족하다고 말하고 조건을 물어본다.",
    ]
    if _is_fresh_recommendation_request(user_message) and recent_codes:
        lines.append(
            "다른 작품 요청: recent_recommended_product_codes는 후보가 남아 있으면 제외한다."
        )
        lines.append(
            f"recent_recommended_product_codes: {', '.join(recent_codes[:_RECENT_RECOMMENDATION_CONTEXT_LIMIT])}"
        )

    summary = _clip_text(focus.get("summary") or persona.get("sensual_summary") or "", 220)
    turn_ons = [str(v) for v in (focus.get("turn_ons") or persona.get("turn_ons") or [])[:4]]
    avoidances = [str(v) for v in (focus.get("avoidances") or persona.get("avoidances") or [])[:3]]
    if summary:
        lines.append(f"sensual_summary: {summary}")
    if turn_ons:
        lines.append(f"turn_ons: {', '.join(turn_ons)}")
    if avoidances:
        lines.append(f"avoidances: {', '.join(avoidances)}")

    if not results:
        lines.extend(
            [
                "library_search.results: []",
                "응답 규칙: 후보가 없으므로 품번을 만들지 말고 조건 보강을 요청한다.",
            ]
        )
        return "\n".join(lines)

    lines.append("library_search.results:")
    for idx, item in enumerate(results[:_RECOMMENDATION_GROUNDING_RESULT_LIMIT], start=1):
        grok = item.get("grok") if isinstance(item.get("grok"), Mapping) else {}
        synopsis = _clip_text(item.get("synopsis") or "", 150)
        grok_summary = _clip_text(grok.get("summary") or "", 180)
        lines.extend(
            [
                f"- 후보 {idx} product_code: {item.get('product_code') or ''}",
                f"  title_ko: {item.get('title_ko') or ''}",
                f"  title_ja: {item.get('title_ja') or ''}",
                f"  actors: {', '.join(str(v) for v in (item.get('actors') or [])[:3])}",
                f"  genres: {', '.join(str(v) for v in (item.get('genres') or [])[:4])}",
                f"  source: {item.get('source') or ''}",
                f"  persona_match_score: {item.get('persona_match_score') or 0}",
                f"  ranking_reasons: {', '.join(str(v) for v in (item.get('ranking_reasons') or [])[:2])}",
                f"  matched_persona_terms: {', '.join(str(v) for v in (item.get('matched_persona_terms') or [])[:3])}",
            ]
        )
        if synopsis:
            lines.append(f"  synopsis: {synopsis}")
        if grok_summary:
            lines.append(f"  grok.summary: {grok_summary}")
    return "\n".join(lines)


def _normalize_history(
    history: Sequence[Mapping[str, Any]] | None,
    *,
    max_items: int = 16,
    max_chars: int = 1200,
) -> List[Dict[str, str]]:
    if max_items <= 0:
        return []
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


def _compact_memory_context_for_prompt(memory_context: Mapping[str, Any], *, max_items: int = 1) -> Dict[str, Any]:
    def compact_note(item: Any) -> Dict[str, Any]:
        if not isinstance(item, Mapping):
            return {}
        out: Dict[str, Any] = {}
        text = _clip_text(item.get("text") or item.get("summary") or "", 160)
        if text:
            out["text"] = text
        codes = [str(v).strip().upper() for v in (item.get("product_codes") or []) if str(v).strip()]
        if codes:
            out["product_codes"] = codes[:3]
        return out

    def compact_notes(key: str) -> List[Dict[str, Any]]:
        notes = []
        for item in list(memory_context.get(key) or [])[-max_items:]:
            note = compact_note(item)
            if note:
                notes.append(note)
        return notes

    recent_codes = [
        str(v).strip().upper()
        for v in (memory_context.get("recent_recommended_product_codes") or [])
        if str(v).strip()
    ][:6]
    return {
        "preference_notes": compact_notes("preference_notes"),
        "strong_reaction_notes": compact_notes("strong_reaction_notes"),
        "negative_feedback_notes": compact_notes("negative_feedback_notes"),
        "style_notes": compact_notes("style_notes"),
        "recent_recommended_product_codes": recent_codes,
    }


def _deterministic_focused_context(ctx: Mapping[str, Any], *, compact: bool = False) -> str:
    """Build a fast focused context without calling embedding models."""
    persona = ctx.get("persona") if isinstance(ctx.get("persona"), Mapping) else {}
    priority = ctx.get("sensual_priority_context") if isinstance(ctx.get("sensual_priority_context"), Mapping) else {}
    focus = ctx.get("sensual_recommendation_focus") if isinstance(ctx.get("sensual_recommendation_focus"), Mapping) else {}
    taste = ctx.get("taste_context") if isinstance(ctx.get("taste_context"), Mapping) else {}
    lines = ["[취향 정보]"]

    def add(label: str, value: Any, limit: int = 420) -> None:
        if value in ("", None, [], {}):
            return
        if isinstance(value, (list, tuple)):
            text = ", ".join(str(v) for v in value if str(v).strip())
        else:
            text = str(value)
        text = _clip_text(text, limit)
        if text:
            lines.append(f"- {label}: {text}")

    add("sensual_summary", priority.get("sensual_summary") or focus.get("summary") or persona.get("sensual_summary"), 220 if compact else 420)
    add("turn_ons", focus.get("turn_ons") or persona.get("turn_ons"), 140 if compact else 300)
    add("avoidances", focus.get("avoidances") or persona.get("avoidances"), 100 if compact else 260)
    if not compact:
        add("persona_summary", persona.get("summary"), 360)
        add("top_actors", taste.get("top_actors"), 220)
        add("top_genres", taste.get("top_genres") or taste.get("recent_genres"), 260)
        add("tags", taste.get("tags"), 260)
        add("tones", taste.get("tones"), 220)

    search = ctx.get("library_search") if isinstance(ctx.get("library_search"), Mapping) else {}
    results = [item for item in list(search.get("results") or [])[:1 if compact else 3] if isinstance(item, Mapping)]
    if results:
        lines.append("- library_search_top_candidates:")
        for item in results:
            code = str(item.get("product_code") or "").strip()
            title = _clip_text(str(item.get("title_ko") or item.get("title_ja") or "").strip(), 80 if compact else 180)
            reasons = ", ".join(str(v) for v in (item.get("ranking_reasons") or [])[:1 if compact else 3])
            lines.append(f"  - {code} {title} {reasons}".rstrip())
    return "\n".join(lines)


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


def _format_chat_response_text(text: str) -> str:
    """Add readable paragraph breaks to dense local-model chat output."""
    value = str(text or "").strip()
    if not value:
        return ""

    # Keep user-visible line breaks stable while avoiding accidental huge gaps.
    value = re.sub(r"\r\n?", "\n", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value).strip()

    # Stage directions at the start read better as their own paragraph.
    value = re.sub(r"^(\([^)\n]{3,160}\))\s+", r"\1\n\n", value)

    # Recommendation headings and numbered items are the most common run-on shape.
    value = re.sub(r"\s+(✨\s*🔥\s*\*\*[^*\n]+?\*\*\s*🔥\s*✨)", r"\n\n\1", value)
    value = re.sub(r"(?<!^)(?<!\n)\s+(\d{1,2}\.\s+\*\*[A-Z0-9][A-Z0-9_-]{1,12}-\d{2,7}\b)", r"\n\n\1", value)
    value = re.sub(r"(?<!^)(?<!\n)\s+(\d{1,2}\.\s+\*\*\([^)\n]{2,60}\)\*\*)", r"\n\n\1", value)
    value = re.sub(r"(?<!^)(?<!\n)\s+(\d{1,2}\.\s+\*\*[^*\n]{2,80}\*\*:)", r"\n\n\1", value)

    # Final follow-up questions should not remain glued to the last list item.
    value = re.sub(r"\s+(자,\s+이제\s+[^?\n]+\?)", r"\n\n\1", value)
    value = re.sub(r"\s+(어때요\?[^.\n]*$)", r"\n\n\1", value)

    value = re.sub(r"\n{3,}", "\n\n", value)
    return "\n".join(line.rstrip() for line in value.splitlines()).strip()


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


def _looks_truncated_response(content: str) -> bool:
    value = str(content or "").strip()
    if len(value) < 20:
        return False
    if value.endswith((".", "!", "?", "。", "！", "？", "…", "]", ")", "}", "\"", "'")):
        return False
    last_line = value.splitlines()[-1].strip()
    if not last_line:
        return False
    if re.search(
        r"(가|이|은|는|을|를|의|와|과|도|로|으로|에|에게|에서|부터|까지|처럼|보다|"
        r"지만|면서|하며|하고|다가|때문에|한테|이라는|라는|되고|되며|느끼고|만들고|보여주고)$",
        last_line,
    ):
        return True
    return bool(last_line.endswith((",", ":", "-", "—", "·", "/")))


def _recommendation_candidates_from_payload(payload: Mapping[str, Any]) -> tuple[List[Dict[str, str]], List[str]]:
    """Parse the structured recommendation grounding block we inject into messages."""
    messages = payload.get("messages") or []
    system_text = "\n".join(
        str(message.get("content") or "")
        for message in messages
        if isinstance(message, Mapping) and str(message.get("role") or "") == "system"
    )
    if "[추천 후보 고정 근거]" not in system_text:
        return [], []

    recent_codes: List[str] = []
    recent_match = re.search(r"recent_recommended_product_codes:\s*(.+)", system_text)
    if recent_match:
        recent_codes = [
            code.strip().upper()
            for code in re.split(r"[,，]\s*", recent_match.group(1))
            if code.strip()
        ]

    candidates: List[Dict[str, str]] = []
    current: Dict[str, str] | None = None
    for line in system_text.splitlines():
        code_match = re.match(r"\s*-\s*후보\s+\d+\s+product_code:\s*(.+?)\s*$", line)
        if code_match:
            if current:
                candidates.append(current)
            raw_code = code_match.group(1).strip().upper()
            parsed_codes = extract_product_codes(raw_code, limit=1)
            current = {"product_code": parsed_codes[0] if parsed_codes else ""}
            continue
        if current is None:
            continue
        field_match = re.match(r"\s+([a-zA-Z0-9_.]+):\s*(.*)\s*$", line)
        if field_match:
            current[field_match.group(1)] = field_match.group(2).strip()
    if current:
        candidates.append(current)
    return [item for item in candidates if item.get("product_code")], recent_codes


def _recommendation_response_needs_replacement(
    user_message: str,
    content: str,
    candidates: Sequence[Mapping[str, str]],
    recent_codes: Sequence[str],
) -> bool:
    if not _is_recommendation_request(user_message):
        return False
    text = str(content or "")
    stripped = text.strip()
    response_codes = [code.strip().upper() for code in extract_product_codes(text)]
    if any(marker in text for marker in _FABRICATED_RECOMMENDATION_MARKERS):
        return True
    if "none" in text.lower():
        return True
    if text.count("또는") >= 6:
        return True
    if text.count("래.") >= 4 or text.count("래\n") >= 4:
        return True
    if not candidates:
        return True
    if "후보가 부족" in text and len(candidates) > 0:
        return True

    allowed_codes = {str(item.get("product_code") or "").strip().upper() for item in candidates}
    allowed_codes.discard("")
    if not response_codes:
        return True
    if any(code not in allowed_codes for code in response_codes):
        return True
    upper_text = text.upper()
    if any(upper_text.count(code) >= 4 for code in response_codes):
        return True
    if len(stripped) < 80:
        return True
    if len(response_codes) < min(2, len(allowed_codes)) and len(stripped) < 650:
        return True
    if re.search(r"(을|를|은|는|이|가|의|와|과|로|으로|에서|에게|한테)$", stripped):
        return True
    if _is_fresh_recommendation_request(user_message):
        recent = {str(code or "").strip().upper() for code in recent_codes}
        if recent.intersection(response_codes):
            return True
    return False


def _fallback_recommendation_reason(item: Mapping[str, str]) -> str:
    ranking = str(item.get("ranking_reasons") or "").strip()
    matched = str(item.get("matched_persona_terms") or "").strip()
    grok_summary = str(item.get("grok.summary") or "").strip()
    synopsis = str(item.get("synopsis") or "").strip()
    if ranking or matched:
        parts = []
        if ranking:
            parts.append(f"랭킹 근거는 {ranking}")
        if matched:
            parts.append(f"맞물린 취향 키워드는 {matched}")
        return " / ".join(parts) + " 쪽이야."
    if grok_summary:
        return f"저장된 장면 요약 기준으로는 {_clip_text(grok_summary, 140)}"
    if synopsis:
        return f"DB 시놉시스 기준으로는 {_clip_text(synopsis, 140)}"
    return "검색 후보로 확인된 실제 품번이고, 현재 취향 컨텍스트와의 점수로 우선순위에 올라온 작품이야."


def _deterministic_recommendation_response(
    user_message: str,
    candidates: Sequence[Mapping[str, str]],
    recent_codes: Sequence[str],
) -> str:
    recent = {str(code or "").strip().upper() for code in recent_codes}
    fresh_request = _is_fresh_recommendation_request(user_message)
    filtered = [
        item
        for item in candidates
        if not fresh_request or str(item.get("product_code") or "").strip().upper() not in recent
    ]
    if not filtered:
        return (
            "지금 검색된 후보 안에서는 방금 추천한 품번을 빼고 새로 고를 만한 작품이 부족해. "
            "배우, 장르, 분위기 조건을 하나만 더 주면 실제 DB 후보 안에서 다시 좁혀볼게."
        )

    intro = (
        "좋아, 이번엔 방금 나온 품번은 빼고 실제 검색 후보 안에서만 다시 고를게."
        if fresh_request
        else "좋아, 실제 검색 후보 안에서만 골라서 추천할게."
    )
    lines = [intro]
    for idx, item in enumerate(filtered[:4], start=1):
        code = str(item.get("product_code") or "").strip().upper()
        title = str(item.get("title_ko") or item.get("title_ja") or "제목 정보 없음").strip()
        actors = str(item.get("actors") or "").strip()
        genres = str(item.get("genres") or "").strip()
        meta = " / ".join(part for part in [actors, genres] if part)
        lines.append(f"{idx}. **{code}** — {title}")
        if meta:
            lines.append(f"   {meta}")
        lines.append(f"   {_fallback_recommendation_reason(item)}")
    return "\n".join(lines)


@dataclass
class PersonaChatService:
    """Persona chat gateway returning OpenAI-compatible ChatCompletion dicts."""

    engine: EroticPersonaEngine = field(default_factory=lambda: EroticPersonaEngine(skip_context=True))
    # 단일 통합 메모리 — PersonaChatMemory 는 EnhancedPersonaMemory 로 통합됨
    enhanced_memory_store: EnhancedPersonaMemory = field(default_factory=EnhancedPersonaMemory)
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    prompt_version: str = "v2"
    system_prompt: str = field(init=False)
    temperature: float = field(
        default_factory=lambda: _env_float(
            "JAVSTORY_PERSONA_CHAT_TEMPERATURE",
            0.78,
            min_value=0.2,
            max_value=1.0,
        )
    )
    max_tokens: int = field(
        default_factory=lambda: _env_int(
            "JAVSTORY_PERSONA_CHAT_MAX_TOKENS",
            2600,
            min_value=800,
            max_value=_MAX_OUTPUT_TOKENS,
        )
    )
    timeout_sec: float = 180.0

    def __post_init__(self) -> None:
        prompt_cls = get_prompt(self.prompt_version)
        if self.prompt_version == "v2":
            self.system_prompt = prompt_cls().render(
                persona_name="JAVSTORY 취향 분석 페르소나",
                focused_user_context=_ROLE_CORE_V2,
            )
        else:
            self.system_prompt = prompt_cls().render(
                persona_name="JAVSTORY Persona Chat",
                focused_user_context=SENSUAL_PERSONA_SYSTEM_PROMPT,
                retrieved_memories=(
                    "장기 대화 메모리와 검색 컨텍스트는 build_messages()에서 단일 통합 system message로 제공된다."
                ),
            )
        try:
            self.enhanced_memory_store.load_from_json(str(ENHANCED_PERSONA_MEMORY_PATH))
        except Exception as e:
            print(f"[PersonaChatService] enhanced memory load failed: {e}")

    def _resolve_backend(self) -> tuple[str, str, str]:
        configured_base = (self.base_url or os.environ.get("JAVSTORY_PERSONA_CHAT_BASE_URL") or "").strip()
        configured_model = persona_chat_model_from_env(self.model or os.environ.get("JAVSTORY_PERSONA_CHAT_MODEL"))
        api_key = (self.api_key or os.environ.get("JAVSTORY_PERSONA_CHAT_API_KEY") or "").strip()

        if configured_base:
            base = configured_base.rstrip("/")
            if not base.endswith("/v1"):
                base = f"{base}/v1"
            model = configured_model or persona_chat_model_from_env(os.environ.get("JAVSTORY_LLAMACPP_MODEL"))
            return base, model, api_key or "local"

        preset = configured_model or persona_chat_model_from_env(os.environ.get("JAVSTORY_LLAMACPP_MODEL"))
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
        memory_context = self.enhanced_memory_store.prompt_context(user_message, max_items=1 if compact else 5)
        recent_recommended_codes = list(
            dict.fromkeys(
                _recent_assistant_product_codes_from_history(history)
                + _recent_assistant_product_codes(self.enhanced_memory_store)
            )
        )[:_RECENT_RECOMMENDATION_CONTEXT_LIMIT]
        if recent_recommended_codes:
            memory_context = dict(memory_context)
            memory_context["recent_recommended_product_codes"] = recent_recommended_codes
        context = self.engine.build_chat_context(
            user_message,
            product_code=product_code,
            seed_product_codes=_recommendation_seed_codes(memory_context),
        )
        context = _apply_personalized_ranking(context, memory_context)
        compact_context = _compact_chat_context(context, aggressive=True)
        context_json = json.dumps(
            compact_context,
            ensure_ascii=False,
            default=str,
        )
        factual_grounding = _product_factual_grounding_block(user_message, context)
        recommendation_grounding = _recommendation_grounding_block(user_message, context, memory_context)
        focused_context = (
            factual_grounding
            if factual_grounding
            else recommendation_grounding
            if recommendation_grounding
            else (
                build_focused_context(user_message, compact_context)
                if os.environ.get("JAVSTORY_PERSONA_CHAT_EMBED_FOCUS", "").strip().lower() in {"1", "true", "yes", "on"}
                else _deterministic_focused_context(compact_context, compact=compact)
            )
        )
        if compact:
            focused_context = _clip_text(focused_context, 1400)
            memory_context = _compact_memory_context_for_prompt(memory_context, max_items=1)
        logger.debug(f"컨텍스트 압축: {len(context_json)} → {len(focused_context)} chars")
        style_instruction = _response_style_instruction(user_message)
        if factual_grounding:
            memory_instruction = (
                "## 장기 대화 메모리\n"
                "이번 요청은 특정 품번의 작품 사실 설명이므로, "
                "메모리는 말투 선호 외에는 사실 근거로 쓰지 않는다. "
                "작품 내용·장면·전개는 [작품 사실 고정 근거]의 synopsis/story_context에 없는 내용을 보태지 않는다.\n"
            )
        else:
            memory_instruction = (
                "## 장기 대화 메모리\n"
                "사용자가 이전에 남긴 취향 단서, 강렬 반응, 교정, 말투 선호를 "
                "현재 답변에 자연스럽게 반영하라. DB/library_search 결과와 충돌하면 "
                "DB/library_search를 우선하고 메모리는 보조 근거로만 사용하라.\n"
            )

        # ── System message: 역할 + 컨텍스트 + 메모리 (+ 스타일 + 규칙) ──────────
        if self.prompt_version == "v2":
            system_parts = [self.system_prompt, "\n" + focused_context]
            memory_readable = _format_memory_readable(
                memory_context, factual=bool(factual_grounding), compact=compact
            )
            if memory_readable:
                system_parts.append("\n" + memory_readable)
            if style_instruction:
                lowered_msg = (user_message or "").lower()
                if any(h in lowered_msg for h in ("수치플레이", "수치", "부끄럽게")):
                    v2_style = _STYLE_PROFILES_V2.get("shame_tension", "")
                else:
                    v2_style = _STYLE_PROFILES_V2.get("intense_sensual", "")
                if v2_style:
                    system_parts.append("\n[응답 스타일] " + v2_style)
            system_parts.append(
                "\n" + _build_output_rules(compact=compact, factual=bool(factual_grounding))
            )
        else:
            system_prompt = COMPACT_PERSONA_SYSTEM_PROMPT if compact else self.system_prompt
            system_parts = [
                system_prompt,
                "\n## 현재 사용자 취향 컨텍스트\n이 데이터에 근거해 답하라.\n" + focused_context,
                "\n" + memory_instruction + json.dumps(memory_context, ensure_ascii=False),
            ]
            if style_instruction:
                system_parts.append("\n## 응답 스타일\n" + style_instruction)

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": "\n".join(system_parts)},
        ]

        # ── System message 2: force_final_only 재시도 지시문 (조건부) ──────────
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
                max_items=1 if compact else 4,
                max_chars=220 if compact else 700,
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
            _persona_chat_max_tokens_for_context(text, self.max_tokens)
            if max_tokens is None
            else max(800, min(_MAX_OUTPUT_TOKENS, int(max_tokens)))
        )
        payload = self._build_payload(
            model=model,
            text=text,
            history=history,
            product_code=product_code,
            temperature=req_temperature,
            max_tokens=req_max_tokens,
            compact=False,
        )
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        compact_for_ctx = False

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
                    temperature=min(0.78, req_temperature),
                    max_tokens=min(700 if compact_for_ctx else 1200, req_max_tokens),
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
                    temperature=min(0.78, req_temperature),
                    max_tokens=min(700 if compact_for_ctx else 1200, req_max_tokens),
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
                    payload = retry_payload
                except httpx.HTTPStatusError as e:
                    if e.response is None or e.response.status_code != 400:
                        raise
                    retry_payload = self._build_payload(
                        model=model,
                        text=text,
                        history=[],
                        product_code=product_code,
                        temperature=0.72,
                        max_tokens=600 if compact_for_ctx else 900,
                        force_final_only=True,
                        compact=True,
                    )
                    raw = self._post_chat_completion(
                        client,
                        base_url=base_url,
                        payload=retry_payload,
                        headers=headers,
                    )
                    payload = retry_payload
                content = _strip_reasoning_leak(_coalesce_response_text(raw))
                if content and _is_incomplete_stage_direction_response(content):
                    content = ""

        if content:
            candidates, recent_codes = _recommendation_candidates_from_payload(payload)
            if _recommendation_response_needs_replacement(text, content, candidates, recent_codes):
                content = _deterministic_recommendation_response(text, candidates, recent_codes)
            content = _format_chat_response_text(content)
            if _looks_truncated_response(content):
                retry_payload = self._build_payload(
                    model=model,
                    text=text,
                    history=[],
                    product_code=product_code,
                    temperature=min(0.76, req_temperature),
                    max_tokens=min(1400, req_max_tokens),
                    force_final_only=True,
                    compact=True,
                )
                try:
                    retry_raw = self._post_chat_completion(
                        client,
                        base_url=base_url,
                        payload=retry_payload,
                        headers=headers,
                    )
                    retry_content = _format_chat_response_text(
                        _strip_reasoning_leak(_coalesce_response_text(retry_raw))
                    )
                    if retry_content and not _looks_truncated_response(retry_content):
                        raw = retry_raw
                        content = retry_content
                except Exception:
                    content = content.rstrip() + "\n\n[응답이 문장 중간에서 끊긴 것 같아요. '계속'이라고 입력하면 이어서 정리해드릴게요.]"
            if _looks_truncated_response(content):
                content = content.rstrip() + "\n\n[응답이 문장 중간에서 끊긴 것 같아요. '계속'이라고 입력하면 이어서 정리해드릴게요.]"
            try:
                self.enhanced_memory_store.record_turn(text, content)
                self.enhanced_memory_store.save_to_json(str(ENHANCED_PERSONA_MEMORY_PATH))
            except Exception as e:
                print(f"[PersonaChatService] memory turn save failed: {e}")
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
