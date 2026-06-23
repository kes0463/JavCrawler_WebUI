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
import threading
from collections import Counter
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
from javstory.persona.library_search import extract_product_codes, split_query_terms
from javstory.persona.persona_memory import EnhancedPersonaMemory
from javstory.persona.prompts.prompt_loader import get_prompt
from javstory.persona.user_rating_list import fetch_user_rated_products, is_user_rating_list_request

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
- 답변은 한국어 존댓말(해요체)로 한다. 반말·해라체·친구 말투는 쓰지 않는다.
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
톤은 직설적이고 도발적으로 유지하되, 항상 존댓말(해요체)로 3~7문장 압축한다. 반말 금지.
"""

# v2 역할 핵심 — 단일 책임(역할·톤·안전)만 담고, 컨텍스트·규칙은 build_messages()가 별도 주입.
_ROLE_CORE_V2 = """\
직설적·도발적 톤으로 사용자의 취향을 파고든다. 단, 항상 존댓말(해요체)로 말한다.
- 품번·배우·장면을 언급하면 왜 꽂히는지 바로, 구체적으로 짚는다
- "이런 취향에 약하신 이유는...", "이 장면이 끌리시는 지점은..." 같은 표현을 쓴다
- 부끄럽고 인정하기 힘든 취향일수록 더 대담하게 파고든다
- 반말·해라체·친구 말투는 쓰지 않는다
- 실제 성행위 단계별 묘사와 신체 부위 극단적 표현은 피한다
- 강압·비동의·미성년자 미화는 하지 않는다\
"""

_POLITE_SPEECH_RULE = "항상 존댓말(해요체)로 답한다. 반말·해라체·친구 말투 금지."

_STYLE_PROFILES_V2: Dict[str, str] = {
    "intense_sensual": f"관능 강화: 관계성·긴장·금기감을 더 직접적으로. 신체 반응 단정 금지. {_POLITE_SPEECH_RULE}",
    "shame_tension": f"수치 톤: 들킨 취향·심리적 긴장 중심. 실제 수치 강요 금지. {_POLITE_SPEECH_RULE}",
    "analysis": (
        "분석형: 존댓말로 5~10문장. 취향 패턴을 근거와 함께 풀어 설명한다. "
        "'첫째로/둘째로' 나열·딱딱한 보고서체 금지. 근거 없는 장면·관계 상세 창작 금지."
    ),
    "recommend": (
        f"추천형: 후보 3~4개. 각 작품마다 품번·제목·배우·장르·시놉/요약·취향 연결을 3~5줄로 풀어 쓴다. {_POLITE_SPEECH_RULE}"
    ),
}

_TONE_PRESET_ALIASES: Dict[str, str] = {
    "analysis": "analysis",
    "analytical": "analysis",
    "분석": "analysis",
    "분석형": "analysis",
    "recommend": "recommend",
    "recommendation": "recommend",
    "추천": "recommend",
    "추천형": "recommend",
    "intense": "intense_sensual",
    "intense_sensual": "intense_sensual",
    "도발": "intense_sensual",
    "도발형": "intense_sensual",
    "shame": "shame_tension",
    "shame_tension": "shame_tension",
    "수치": "shame_tension",
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
_RECOMMENDATION_GROUNDING_RESULT_LIMIT = 5
_SYNOPSIS_CLIP_DEFAULT = 200
_SYNOPSIS_SUMMARY_MAX_CHARS = 140
_SHORT_TITLE_CLIP = 72
_REASON_SYNOPSIS_CLIP = 100
_GROK_SUMMARY_CLIP_DEFAULT = 200
_TASTE_CONNECTION_CLIP = 72
_RECOMMENDATION_GENRE_SKIP = frozenset(
    {
        "검열 완료",
        "단독작품",
        "하이비전",
        "4K",
        "VR",
        "독점배급",
        "FANZA配信",
        "配信専用",
    }
)
_TASTE_TERM_SKIP = frozenset(
    {
        "상황",
        "분위기",
        "느낌",
        "장면",
        "이야기",
        "작품",
        "테마",
        "스토리",
        "전개",
        "관계",
        "오는",
        "있는",
        "하는",
        "되는",
        "끌리는",
        "평소",
        "라인",
        "쪽",
        "느낌의",
        "같은",
        "비슷",
        "정말",
        "너무",
    }
)
_FORMULAIC_REASON_PHRASES = (
    "분명한 편",
    "가능성이 높아",
    "흐름이 분명",
    "잘 살아 있어요",
)
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
_BACKEND_CACHE_TTL = 30.0  # seconds — resolved backend is cached to avoid repeated health checks
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
_RECOMMENDATION_QUERY_STOPWORDS = {
    "추천",
    "추천해",
    "추천해줘",
    "추천해주세요",
    "작품",
    "영상",
    "오늘",
    "볼만",
    "볼만한",
    "골라",
    "골라줘",
    "찾아",
    "찾아줘",
    "비슷",
    "비슷한",
    "유사",
    "같은",
    "느낌",
    "분위기",
    "해줘",
    "해주세요",
    "주세요",
    "줘",
    "좀",
    "관련",
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


def _persona_chat_stream_max_tokens(text: str, configured_max: int) -> int:
    """Streaming path cap — recommendation answers need more room than short chat."""
    situational = _persona_chat_max_tokens_for_context(text, configured_max)
    stream_cap = _env_int("JAVSTORY_PERSONA_CHAT_STREAM_MAX_TOKENS", 1700, min_value=800, max_value=2800)
    if _is_recommendation_request(text):
        return min(situational, max(stream_cap, 2200))
    if _is_rated_works_analysis_request(text):
        situational = max(situational, 1900)
        return min(situational, max(stream_cap, 1900))
    if _should_use_full_chat_pipeline(text):
        return min(situational, max(stream_cap, 1800))
    return min(situational, stream_cap)


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
    out: List[str] = list(getattr(memory_store, "recent_recommended_product_codes", None) or [])
    try:
        messages = memory_store.load_recent_messages()
    except Exception:
        return out[:limit]
    for item in reversed(messages):
        if str(item.get("role") or "") != "assistant":
            continue
        for code in extract_product_codes(str(item.get("content") or "")):
            pc = str(code or "").strip().upper()
            if pc and pc not in out:
                out.append(pc)
            if len(out) >= limit:
                return out
    return out[:limit]


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


def _item_diversity_features(item: Mapping[str, Any]) -> set[str]:
    genres = {str(g).strip().lower() for g in (item.get("genres") or []) if str(g).strip()}
    actors = {str(a).strip().lower() for a in (item.get("actors") or [])[:4] if str(a).strip()}
    maker = str(item.get("maker") or "").strip().lower()
    features = genres | actors
    if maker:
        features.add(f"maker:{maker}")
    return features


def _diversity_jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _diversify_ranked_results(ranked: List[Dict[str, Any]], *, pool_size: int = 8) -> List[Dict[str, Any]]:
    """MMR re-ranking on genre/actor/maker overlap for recommendation diversity."""
    if len(ranked) <= 1:
        return ranked
    pool_limit = max(1, min(int(pool_size), len(ranked)))
    features = [_item_diversity_features(item) for item in ranked]
    candidate_indices = list(range(len(ranked)))
    selected: List[int] = []

    first_idx = max(
        candidate_indices,
        key=lambda idx: (
            float(ranked[idx].get("persona_match_score") or 0),
            float(ranked[idx].get("score") or 0),
        ),
    )
    selected.append(first_idx)
    candidate_indices.remove(first_idx)

    lambda_mult = 0.72
    while len(selected) < pool_limit and candidate_indices:
        best_idx = candidate_indices[0]
        best_mmr = -1.0
        for idx in candidate_indices:
            relevance = float(ranked[idx].get("persona_match_score") or 0) / 100.0
            max_sim = max((_diversity_jaccard(features[idx], features[s]) for s in selected), default=0.0)
            mmr = lambda_mult * relevance - (1.0 - lambda_mult) * max_sim
            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = idx
        selected.append(best_idx)
        candidate_indices.remove(best_idx)

    diversified = [dict(ranked[idx]) for idx in selected]
    selected_set = set(selected)
    diversified.extend(dict(item) for idx, item in enumerate(ranked) if idx not in selected_set)
    return diversified


def _exploration_epsilon() -> float:
    raw = (os.environ.get("JAVSTORY_PERSONA_REC_EXPLORATION_EPSILON", "") or "").strip()
    if not raw:
        return 0.2
    try:
        return max(0.0, min(0.5, float(raw)))
    except ValueError:
        return 0.2


def _apply_exploration_mix(ranked: List[Dict[str, Any]], *, epsilon: float | None = None) -> List[Dict[str, Any]]:
    """ε-greedy: keep top exploitation slots, inject hidden-gem / long-tail explorers."""
    if len(ranked) < 5:
        return ranked
    eps = _exploration_epsilon() if epsilon is None else max(0.0, min(0.5, float(epsilon)))
    if eps <= 0:
        return ranked
    window = min(8, len(ranked))
    explore_slots = max(1, round(window * eps))
    keep = max(2, window - explore_slots)
    head = list(ranked[:keep])
    pool = ranked[keep : min(len(ranked), keep + 24)]
    gems = [item for item in pool if "hidden_gem" in str(item.get("source") or "")]
    explorers = gems or pool
    picks: List[Dict[str, Any]] = []
    seen_ids = {id(item) for item in head}
    for item in explorers:
        if id(item) in seen_ids:
            continue
        picks.append(item)
        seen_ids.add(id(item))
        if len(picks) >= explore_slots:
            break
    tail = [item for item in ranked if id(item) not in seen_ids]
    return head + picks + tail


def _diagnose_empty_recommendation_pool(ctx: Mapping[str, Any]) -> List[str]:
    search = ctx.get("library_search") if isinstance(ctx.get("library_search"), Mapping) else {}
    policy = search.get("source_policy") if isinstance(search.get("source_policy"), Mapping) else {}
    reasons: List[str] = []
    if str(policy.get("mode") or "") == "taste_recommendation":
        reasons.append("취향 기반 추천 모드라 미시청·고평점 시드가 부족할 수 있음")
    try:
        from javstory.library.embeddings.pipeline import embeddings_enabled_from_env

        if not embeddings_enabled_from_env():
            reasons.append("작품 임베딩 파이프라인이 꺼져 있음(JAVSTORY_EMBEDDINGS_ENABLED)")
    except Exception:
        reasons.append("작품 임베딩 상태를 확인하지 못함")
    diversity = search.get("diversity_policy") if isinstance(search.get("diversity_policy"), Mapping) else {}
    recent = list(diversity.get("recent_recommended_product_codes") or [])
    if recent:
        reasons.append("최근 챗 추천 품번 제외로 후보가 줄었을 수 있음")
    query_terms = list(search.get("query_focus_terms") or [])
    if query_terms:
        reasons.append(f"요청 테마 '{', '.join(str(t) for t in query_terms[:3])}'에 맞는 미시청 후보가 부족할 수 있음")
    theme_miss = search.get("theme_filter_miss") if isinstance(search.get("theme_filter_miss"), Mapping) else {}
    if theme_miss.get("query_focus_terms"):
        reasons.append("요청 테마(장르/키워드)와 메타데이터가 맞는 후보가 없음")
    if not reasons:
        reasons.append("현재 DB 검색·필터 조건에 맞는 후보가 없음")
    return reasons


def _empty_recommendation_explanation(ctx: Mapping[str, Any]) -> str:
    reasons = _diagnose_empty_recommendation_pool(ctx)
    joined = " / ".join(reasons[:3])
    return (
        "지금 조건으로는 라이브러리에서 바로 추천할 후보를 찾지 못했어요. "
        f"가능한 이유: {joined}. "
        "배우·장르·분위기 중 하나만 더 구체적으로 알려주시면 다시 좁혀 볼게요."
    )


def _normalize_tone_preset(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    return _TONE_PRESET_ALIASES.get(raw, "recommend")


def _tone_style_for_preset(preset: str, user_message: str) -> str:
    normalized = _normalize_tone_preset(preset)
    if normalized in _STYLE_PROFILES_V2:
        return _STYLE_PROFILES_V2[normalized]
    lowered = (user_message or "").lower()
    if any(h in lowered for h in ("수치플레이", "수치", "부끄럽게")):
        return _STYLE_PROFILES_V2.get("shame_tension", "")
    return _STYLE_PROFILES_V2.get("intense_sensual", "")


def _should_use_full_chat_pipeline(user_message: str) -> bool:
    """Use fuller context and longer answers unless the user explicitly wants brevity."""
    if _is_recommendation_request(user_message):
        return True
    if _is_rated_works_analysis_request(user_message):
        return True
    if is_user_rating_list_request(user_message):
        return False
    lowered = str(user_message or "").lower()
    if any(h in lowered for h in _SHORT_RESPONSE_HINTS):
        return False
    return True


def _should_use_compact_pipeline(user_message: str, ctx: Mapping[str, Any]) -> bool:
    pipeline_mode = str(ctx.get("pipeline_mode") or "")
    if pipeline_mode in {"light", "rating_list"}:
        return True
    if is_user_rating_list_request(user_message):
        return True
    if _should_use_full_chat_pipeline(user_message):
        return False
    lowered = str(user_message or "").lower()
    if any(h in lowered for h in ("줄거리", "시놉", "정보", "짧게", "간단", "한줄")):
        return True
    return False


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


def _extract_recommendation_query_terms(query: str) -> List[str]:
    """Theme/genre terms explicitly requested by the user (e.g. 근친상간)."""
    from javstory.persona.library_search import extract_theme_query_terms

    return extract_theme_query_terms(query, limit=6)


def _query_term_hits(item: Mapping[str, Any], query_terms: Sequence[str]) -> tuple[List[str], List[str]]:
    genre_blob = " ".join(str(v) for v in (item.get("genres") or [])).lower()
    item_text = _item_rank_text(item)
    genre_hits: List[str] = []
    other_hits: List[str] = []
    for term in query_terms:
        lowered = str(term or "").strip().lower()
        if not lowered:
            continue
        if lowered in genre_blob and term not in genre_hits:
            genre_hits.append(str(term))
        elif lowered in item_text and term not in other_hits and term not in genre_hits:
            other_hits.append(str(term))
    return genre_hits, other_hits


def _humanize_ranking_reasons(reasons: Sequence[str] | str) -> str:
    if isinstance(reasons, str):
        raw_parts = [part.strip() for part in re.split(r"[,/]", reasons) if part.strip()]
    else:
        raw_parts = [str(part).strip() for part in reasons if str(part).strip()]
    labels: List[str] = []
    for part in raw_parts:
        if "sensual_summary/turn_ons" in part:
            labels.append("취향 프로필")
        elif "요청 장르/테마" in part:
            labels.append(part.replace("요청 장르/테마 매칭:", "요청 테마").strip())
        elif "요청 키워드" in part:
            labels.append(part.replace("요청 키워드 매칭:", "요청 키워드").strip())
        elif "Grok" in part:
            labels.append("장면 요약 DB")
        elif "임베딩" in part:
            labels.append("유사 작품")
        elif "좋아요" in part:
            labels.append("좋아요 이력")
        elif "별점" in part:
            labels.append(part)
        elif "완주" in part or "시청" in part:
            labels.append("시청 이력")
        elif "하트" in part:
            labels.append("인기도")
        else:
            labels.append(part)
    deduped: List[str] = []
    for label in labels:
        if label and label not in deduped:
            deduped.append(label)
    return ", ".join(deduped[:3])


def _score_recommendation_item(
    item: Mapping[str, Any],
    *,
    persona_terms: Sequence[str],
    strong_codes: set[str],
    negative_codes: set[str],
    fallback_seed_codes: set[str],
    recent_recommended_codes: set[str],
    avoid_reference_codes: bool = False,
    query_terms: Sequence[str] = (),
) -> tuple[float, List[str], List[str]]:
    source_score = float(item.get("score") or 0)
    score = min(25.0, source_score * 25.0)
    reasons: List[str] = []
    item_text = _item_rank_text(item)
    matched_terms = [term for term in persona_terms if term in item_text][:8]
    if matched_terms:
        score += min(35.0, len(matched_terms) * 5.0)
        reasons.append("sensual_summary/turn_ons 키워드 매칭")

    genre_hits, query_hits = _query_term_hits(item, query_terms) if query_terms else ([], [])
    if genre_hits:
        score += min(50.0, len(genre_hits) * 24.0)
        reasons.append(f"요청 장르/테마 매칭: {', '.join(genre_hits)}")
    elif query_hits:
        score += min(34.0, len(query_hits) * 14.0)
        reasons.append(f"요청 키워드 매칭: {', '.join(query_hits)}")
    elif query_terms:
        score *= 0.3
        reasons.append("요청 키워드 미매칭 감점")

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
    query_terms = _extract_recommendation_query_terms(query) if is_recommendation else []

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
            query_terms=query_terms,
        )
        genre_hits, query_hits = _query_term_hits(item, query_terms) if query_terms else ([], [])
        item["persona_match_score"] = round(score, 1)
        item["ranking_reasons"] = reasons
        item["matched_persona_terms"] = matched_terms[:6]
        item["matched_genre_terms"] = genre_hits[:4]
        item["matched_query_terms"] = (genre_hits + query_hits)[:6]
        ranked.append(item)

    ranked.sort(
        key=lambda item: (
            float(item.get("persona_match_score") or 0),
            float(item.get("score") or 0),
            int(item.get("favorite_score") or 0),
        ),
        reverse=True,
    )
    if unwatched_recommendation:
        unwatched_ranked = [item for item in ranked if not _item_has_user_watch_signal(item)]
        ranked = unwatched_ranked
    if query_terms:
        matched = [item for item in ranked if item.get("matched_query_terms")]
        if matched:
            ranked = matched
        else:
            ranked = []
            search["theme_filter_miss"] = {
                "query_focus_terms": query_terms,
                "instruction": "요청 테마에 맞는 후보가 없으므로 품번을 만들거나 테마를 근거 없이 언급하지 않는다.",
            }
    if is_recommendation and recent_recommended_codes:
        filtered = [
            item
            for item in ranked
            if str(item.get("product_code") or "").strip().upper() not in recent_recommended_codes
        ]
        if filtered:
            ranked = filtered
    elif fresh_recommendation and recent_recommended_codes:
        fresh_ranked = [
            item
            for item in ranked
            if str(item.get("product_code") or "").strip().upper() not in recent_recommended_codes
        ]
        if fresh_ranked:
            ranked = fresh_ranked
    if is_recommendation and len(ranked) > 1 and not query_terms:
        ranked = _diversify_ranked_results(ranked, pool_size=8)
    if is_recommendation and len(ranked) > 4:
        ranked = _apply_exploration_mix(ranked)
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
            "explicit_query_term_boost",
            "epsilon_greedy_exploration",
        ],
    }
    if query_terms:
        search["query_focus_terms"] = query_terms
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


def _build_output_rules(
    *,
    compact: bool = False,
    factual: bool = False,
    rated_analysis: bool = False,
    recommendation: bool = False,
) -> str:
    """응답 규칙을 메시지 끝에 배치 — 로컬 모델의 recency bias를 활용해 준수율을 높인다."""
    if factual:
        return (
            "[응답 규칙]\n"
            "- synopsis/story_context 근거만 사용, 없는 내용 추가 금지\n"
            f"- {_POLITE_SPEECH_RULE}\n"
            "- 최종 답변만 출력 (괄호 지문·영어 분석·내부 추론 금지)"
        )
    if rated_analysis:
        return (
            "[응답 규칙]\n"
            "- 존댓말(해요체)로 5~10문장. '첫째로/둘째로/셋째로' 나열 금지\n"
            "- [평점 작품 취향 분석 고정 근거]의 장르·배우·시놉만 근거로 패턴을 풀어 설명\n"
            "- 근거 없는 장면·관계·가족 구성 상세를 지어내지 않는다\n"
            f"- {_POLITE_SPEECH_RULE}\n"
            "- 최종 답변만 출력 (괄호 지문·영어 분석·내부 추론 금지)"
        )
    if recommendation:
        return (
            "[응답 규칙]\n"
            "- 존댓말(해요체). [추천 후보 고정 근거]에서 3~4개만 고른다\n"
            "- 각 작품마다 5~6줄: `1. **품번** — 짧은 제목` / 배우 / 장르 / 한줄 요약 2문장 / 추천 이유 1문장\n"
            "- 시놉 원문을 그대로 붙여넣지 말고 2문장 이내로 요약한다\n"
            "- 추천 이유는 한줄 요약을 반복하지 말고, 왜 지금 나에게 이 작품인지 1문장으로 쓴다\n"
            "- '분명한 편이에요', '가능성이 높아요' 같은 정형 문구는 쓰지 않는다\n"
            "- 추천 이유는 ranking_reasons·matched_persona_terms 같은 내부 태그를 그대로 쓰지 말고, 장면·관계·분위기로 풀어 쓴다\n"
            "- 후보 밖 품번·ABC-123 같은 가짜·placeholder 코드 금지\n"
            "- 한 줄 제목 나열·괄호 키워드만 적는 형식 금지\n"
            f"- {_POLITE_SPEECH_RULE}\n"
            "- 최종 답변만 출력 (괄호 지문·영어 분석·내부 추론 금지)"
        )
    if compact:
        return (
            "[응답 규칙]\n"
            "- 존댓말(해요체)로 짧고 읽기 쉽게. '첫째로/둘째로' 나열 금지\n"
            "- 추천: `1. **품번** — 제목` + 한 줄 이유 (품번은 ABC-123 형식 필수, 숫자만 금지)\n"
            f"- {_POLITE_SPEECH_RULE}\n"
            "- 최종 답변만 출력 (괄호 지문·영어 분석·내부 추론 금지)"
        )
    return (
        "[응답 규칙]\n"
        "- 존댓말(해요체) 5~8문장 (짧게 요청 시 3~4문장). '첫째로/둘째로' 나열 금지\n"
        "- 추천: `1. **품번** — 제목` + 이유 1~2줄. 후보 밖 품번·숫자만 된 가짜 코드 금지\n"
        f"- {_POLITE_SPEECH_RULE}\n"
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


def _user_rating_list_grounding_block(user_message: str, ctx: Mapping[str, Any]) -> str:
    """Pin rating-list answers to WatchHistory-backed rows only."""
    if not is_user_rating_list_request(user_message):
        return ""
    rated_items = [
        item for item in list(ctx.get("user_rating_list") or ctx.get("library_search", {}).get("results") or [])
        if isinstance(item, Mapping)
    ]
    lines = [
        "[사용자 평점 목록 고정 근거]",
        "아래 목록은 WatchHistory에서 rating>0 또는 liked/is_completed로 확인된 작품만 포함한다.",
        "목록에 없는 작품은 절대 추가하지 않는다. 평점이 없는 작품을 추측해 넣지 않는다.",
    ]
    if not rated_items:
        lines.append("rated_products: []")
        lines.append("응답 규칙: 아직 평점/좋아요/완주 기록이 없으므로 그 사실만 존댓말로 말하세요.")
        return "\n".join(lines)

    lines.append("rated_products:")
    for idx, item in enumerate(rated_items[:20], start=1):
        actors = ", ".join(str(v) for v in (item.get("actors") or [])[:3])
        genres = ", ".join(str(v) for v in (item.get("genres") or [])[:4])
        lines.extend(
            [
                f"- {idx} product_code: {item.get('product_code') or ''}",
                f"  title_ko: {item.get('title_ko') or ''}",
                f"  user_rating: {int(item.get('user_rating') or 0)}",
                f"  user_liked: {bool(item.get('user_liked'))}",
                f"  user_is_completed: {bool(item.get('user_is_completed'))}",
                f"  actors: {actors}",
                f"  genres: {genres}",
            ]
        )
    lines.extend(
        [
            "[평점 목록 응답 규칙]",
            "- 위 rated_products만 나열/요약한다.",
            "- 평점 높은 순으로 정리하되, 목록 밖 품번은 추가하지 않는다.",
        ]
    )
    return "\n".join(lines)


def _is_rated_works_analysis_request(text: str) -> bool:
    """Return True when the user asks for taste/pattern analysis of their rated works."""
    if _is_recommendation_request(text):
        return False
    lowered = str(text or "").lower().strip()
    if not lowered:
        return False
    rated_signals = (
        "점수",
        "좋아요",
        "완주",
        "평점",
        "별점",
        "평가한",
        "남긴 작품",
        "준 작품",
        "평가 준",
    )
    analysis_signals = (
        "특징",
        "분석",
        "패턴",
        "경향",
        "공통",
        "취향",
        "어떤",
        "뭐가",
        "왜",
    )
    has_rated = any(h in lowered for h in rated_signals)
    has_analysis = any(h in lowered for h in analysis_signals)
    if has_rated and has_analysis:
        return True
    if "어떤 특징" in lowered or "특징이 있어" in lowered or "특징이 뭐" in lowered:
        return True
    if is_user_rating_list_request(text):
        return False
    return False


def _rated_works_analysis_grounding_block(user_message: str, ctx: Mapping[str, Any]) -> str:
    """Pin rated-works taste analysis to WatchHistory-backed metadata only."""
    if not _is_rated_works_analysis_request(user_message):
        return ""
    rated_items = [
        item
        for item in list(ctx.get("user_rating_list") or ctx.get("library_search", {}).get("results") or [])
        if isinstance(item, Mapping)
    ]
    if not rated_items:
        rated_items = fetch_user_rated_products(limit=25)
    lines = [
        "[평점 작품 취향 분석 고정 근거]",
        "아래 rated_products의 장르·배우·시놉만 근거로 공통 패턴을 짧게 분석한다.",
        "목록에 없는 작품·장면·관계 설정을 지어내지 않는다.",
        "'첫째로/둘째로' 나열 금지. 5~10문장 존댓말(해요체).",
    ]
    if not rated_items:
        lines.append("rated_products: []")
        lines.append("응답 규칙: 평점/좋아요/완주 기록이 없으므로 그 사실만 존댓말로 말하세요.")
        return "\n".join(lines)

    lines.append("rated_products:")
    for idx, item in enumerate(rated_items[:20], start=1):
        synopsis = _clip_text(item.get("synopsis") or "", 180)
        actors = ", ".join(str(v) for v in (item.get("actors") or [])[:3])
        genres = ", ".join(str(v) for v in (item.get("genres") or [])[:4])
        lines.extend(
            [
                f"- {idx} product_code: {item.get('product_code') or ''}",
                f"  title_ko: {item.get('title_ko') or ''}",
                f"  user_rating: {int(item.get('user_rating') or 0)}",
                f"  user_liked: {bool(item.get('user_liked'))}",
                f"  user_is_completed: {bool(item.get('user_is_completed'))}",
                f"  actors: {actors}",
                f"  genres: {genres}",
                f"  synopsis: {synopsis}",
            ]
        )
    lines.extend(
        [
            "[취향 분석 응답 규칙]",
            "- 위 메타데이터에서 반복되는 장르·배우 중심으로 짧게 요약한다.",
            "- 시놉이 비어 있으면 장면 디테일을 추측하지 않는다.",
        ]
    )
    return "\n".join(lines)


def _response_has_bureaucratic_enumeration(text: str) -> bool:
    body = str(text or "")
    if body.count("첫째로") >= 1:
        return True
    if body.count("둘째로") >= 2:
        return True
    return body.count("셋째로") >= 1 or body.count("넷째로") >= 1


_FAKE_NUMERIC_RECOMMENDATION_RE = re.compile(
    r"(?m)^\s*\d+\.\s*(?:\d{2,5}|[A-Za-z]?-?\d{2,5})\s*[:：]",
)
_PLACEHOLDER_PRODUCT_CODE_RE = re.compile(r"^ABC-\d{3}$", re.IGNORECASE)


def _field_text(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    return str(value or "").strip()


def _looks_like_placeholder_product_codes(codes: Sequence[str]) -> bool:
    normalized = [str(code or "").strip().upper() for code in codes if str(code or "").strip()]
    if not normalized:
        return False
    placeholder_hits = sum(1 for code in normalized if _PLACEHOLDER_PRODUCT_CODE_RE.match(code))
    return placeholder_hits >= max(1, len(normalized) // 2)


def _recommendation_response_too_thin(content: str, response_codes: Sequence[str]) -> bool:
    stripped = str(content or "").strip()
    codes = [str(code or "").strip().upper() for code in response_codes if str(code or "").strip()]
    if not stripped or not codes:
        return True
    min_length = max(360, 140 * len(codes))
    if len(stripped) < min_length:
        return True
    detail_markers = ("배우", "장르", "시놉", "한줄 요약", "요약", "synopsis", "grok", "추천 이유", "취향")
    if not any(marker in stripped for marker in detail_markers):
        return True
    if stripped.count("(") >= len(codes) and len(stripped) < min_length * 2:
        return True
    return False


def _looks_like_fake_numeric_recommendation(text: str) -> bool:
    body = str(text or "").strip()
    if not body:
        return False
    if _FAKE_NUMERIC_RECOMMENDATION_RE.search(body) and not extract_product_codes(body):
        return True
    if re.search(r"(?m)^\s*\d+\.\s*\d{2,5}\b", body) and not extract_product_codes(body):
        return True
    return False


def _rated_works_analysis_response_needs_replacement(user_message: str, content: str) -> bool:
    if not _is_rated_works_analysis_request(user_message):
        return False
    text = str(content or "").strip()
    if not text:
        return True
    if _response_has_bureaucratic_enumeration(text):
        return True
    if len(text) > 1200:
        return True
    if text.count("성적 충족") >= 2 or text.count("욕망을 억누르") >= 2:
        return True
    return False


def _deterministic_rated_works_pattern_summary(rated_items: Sequence[Mapping[str, Any]]) -> str:
    if not rated_items:
        return (
            "아직 점수·좋아요·완주를 남긴 작품이 없어서 취향 패턴을 분석하기 어려워요. "
            "몇 편 평가를 남기시면 장르·배우 기준으로 정리해 드릴게요."
        )
    genres: Counter[str] = Counter()
    actors: Counter[str] = Counter()
    codes_sample: List[str] = []
    for item in rated_items:
        code = str(item.get("product_code") or "").strip().upper()
        if code:
            codes_sample.append(code)
        for genre in item.get("genres") or []:
            label = str(genre).strip()
            if label:
                genres[label] += 1
        for actor in item.get("actors") or []:
            label = str(actor).strip()
            if label:
                actors[label] += 1
    parts = [f"평점·좋아요·완주를 남기신 {len(rated_items)}편 기준으로 보면,"]
    top_genres = [genre for genre, _ in genres.most_common(4)]
    top_actors = [actor for actor, _ in actors.most_common(3)]
    if top_genres:
        parts.append(f"자주 나오는 장르는 {', '.join(top_genres)} 쪽이에요.")
    if top_actors:
        parts.append(f"배우는 {', '.join(top_actors)}가 반복됩니다.")
    sample = ", ".join(codes_sample[:4])
    if sample:
        parts.append(f"예를 들면 {sample} 같은 작품들이 그 패턴을 보여줍니다.")
    parts.append("더 깊은 장면 분석이 필요하시면 특정 품번을 짚어 주시면 그 작품 기준으로 파고들 수 있어요.")
    return " ".join(parts)


def _prefer_streamed_over_final(streamed: str, final: str, *, user_message: str = "") -> str:
    """Keep longer streamed text only when it is not a known hallucination pattern."""
    streamed_text = str(streamed or "").strip()
    final_text = str(final or "").strip()
    if not streamed_text or len(streamed_text) <= len(final_text):
        return final_text
    if _looks_like_fake_numeric_recommendation(streamed_text):
        return final_text
    if _is_recommendation_request(user_message):
        streamed_codes = [
            code.strip().upper()
            for code in extract_product_codes(streamed_text)
            if str(code or "").strip()
        ]
        final_codes = [
            code.strip().upper()
            for code in extract_product_codes(final_text)
            if str(code or "").strip()
        ]
        if streamed_codes and final_codes and set(streamed_codes) != set(final_codes):
            return final_text
        if streamed_codes and not final_codes:
            return final_text
        if re.search(r"(?m)^\s*\d+\.\s", streamed_text):
            if not streamed_codes:
                return final_text
            if _looks_like_placeholder_product_codes(streamed_codes):
                return final_text
    if _rated_works_analysis_response_needs_replacement(user_message, streamed_text):
        return final_text
    return streamed_text


def _deterministic_rating_list_response(rated_items: Sequence[Mapping[str, str]]) -> str:
    if not rated_items:
        return "아직 직접 점수를 주신 작품이 없어요. 라이브러리에서 별점이나 좋아요를 남기시면 여기서 정확히 모아 드릴게요."
    lines = ["점수·좋아요·완주를 남기신 작품 목록이에요."]
    for idx, item in enumerate(rated_items[:20], start=1):
        code = str(item.get("product_code") or "").strip().upper()
        title = str(item.get("title_ko") or item.get("title_ja") or "제목 정보 없음").strip()
        rating = int(item.get("user_rating") or 0)
        liked = bool(item.get("user_liked"))
        completed = bool(item.get("user_is_completed"))
        meta_parts = []
        if rating > 0:
            meta_parts.append(f"별점 {rating}점")
        if liked:
            meta_parts.append("좋아요")
        if completed:
            meta_parts.append("완주")
        meta = " / ".join(meta_parts) if meta_parts else "기록 있음"
        lines.append(f"{idx}. **{code}** — {title} ({meta})")
    return "\n".join(lines)


def _is_actress_factual_request(user_message: str, ctx: Mapping[str, Any]) -> bool:
    if extract_product_codes(user_message):
        return False
    if _is_recommendation_request(user_message):
        return False
    actress_db = ctx.get("actress_db_context") if isinstance(ctx.get("actress_db_context"), Mapping) else {}
    mentioned = [item for item in list(actress_db.get("mentioned") or []) if isinstance(item, Mapping)]
    return bool(mentioned)


def _actress_factual_grounding_block(user_message: str, ctx: Mapping[str, Any]) -> str:
    """Pin actress-only answers to DB profile + indexed filmography."""
    if not _is_actress_factual_request(user_message, ctx):
        return ""

    actress_db = ctx.get("actress_db_context") if isinstance(ctx.get("actress_db_context"), Mapping) else {}
    actress_items = [item for item in list(actress_db.get("mentioned") or []) if isinstance(item, Mapping)]
    if not actress_items:
        return ""

    actress = actress_items[0]
    name = str(actress.get("name") or actress.get("name_ja") or "").strip()
    if not name:
        return ""

    search = ctx.get("library_search") if isinstance(ctx.get("library_search"), Mapping) else {}
    works = [item for item in list(search.get("results") or []) if isinstance(item, Mapping)]

    lines = [
        "[배우 사실 고정 근거]",
        "아래 DB 배우 프로필과 출연작 목록만 근거로 답한다.",
        "목록·프로필에 없는 품번, 작품 줄거리, 신체·성향 묘사는 만들지 않는다.",
        f"- name: {name}",
    ]
    if actress.get("name_ja"):
        lines.append(f"- name_ja: {actress.get('name_ja')}")
    if actress.get("genres"):
        lines.append(f"- genres: {_clip_text(str(actress.get('genres')), 120)}")
    if actress.get("memo"):
        lines.append(f"- memo: {_clip_text(str(actress.get('memo')), 180)}")
    if actress.get("profile_text"):
        lines.append(f"- profile_text: {_clip_text(str(actress.get('profile_text')), 260)}")
    wc = int(actress.get("work_count") or 0)
    if wc > 0:
        lines.append(f"- work_count: {wc}")

    if works:
        lines.append("library_filmography:")
        for idx, item in enumerate(works[:10], start=1):
            actors = ", ".join(str(v) for v in (item.get("actors") or [])[:3])
            lines.append(
                f"- work {idx} product_code: {item.get('product_code') or ''} | "
                f"title_ko: {_clip_text(str(item.get('title_ko') or ''), 100)} | actors: {actors}"
            )
    else:
        lines.append("library_filmography: []")
        lines.append("응답 규칙: 출연작 목록이 비어 있으면 작품·품번을 지어내지 말고 DB에 작품이 없다고 말한다.")

    lines.extend(
        [
            "[배우 설명 응답 규칙]",
            "- 배우 소개는 memo/profile_text/genres만 사용한다.",
            "- 특정 작품 설명은 library_filmography에 있는 품번만 언급한다.",
            "- 배우 이름에 조사(가/는/을)를 붙여 다른 이름으로 부르지 않는다.",
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

    actress_filter = search.get("actress_filter") if isinstance(search.get("actress_filter"), Mapping) else {}
    actress_name = str(actress_filter.get("name") or "").strip()
    if actress_name:
        match_names = [str(n).strip() for n in (actress_filter.get("match_names") or []) if str(n).strip()]
        lines.append(f"actress_filter_name: {actress_name}")
        if match_names:
            lines.append(f"actress_filter_match_names: {', '.join(match_names[:6])}")
        lines.append(
            "응답 규칙: 추천 품번은 반드시 위 배우의 라이브러리 출연작이어야 한다. 다른 배우 작품은 추천하지 않는다."
        )

    query_focus = [str(t).strip() for t in list(search.get("query_focus_terms") or []) if str(t).strip()]
    if query_focus:
        lines.append(f"query_focus_terms: {', '.join(query_focus[:6])}")
        lines.append(
            "응답 규칙: query_focus_terms가 있으면 matched_query_terms가 있는 후보만 추천한다. "
            "메타데이터에 없는 테마·장면을 추천 이유에 만들지 않는다."
        )

    if not results:
        reasons = _diagnose_empty_recommendation_pool(ctx)
        lines.extend(
            [
                "library_search.results: []",
                f"empty_pool_diagnosis: {' / '.join(reasons[:4])}",
                "응답 규칙: 후보가 없으므로 품번을 만들지 말고 위 진단을 바탕으로 이유를 설명한 뒤 조건 보강을 요청한다.",
            ]
        )
        return "\n".join(lines)

    lines.append("library_search.results:")
    for idx, item in enumerate(results[:_RECOMMENDATION_GROUNDING_RESULT_LIMIT], start=1):
        grok = item.get("grok") if isinstance(item.get("grok"), Mapping) else {}
        synopsis_summary = _summarize_synopsis_for_display(item)
        grok_summary = _clip_text(grok.get("summary") or "", _GROK_SUMMARY_CLIP_DEFAULT)
        meaningful_genres = _meaningful_genre_terms(item.get("genres"))
        lines.extend(
            [
                f"- 후보 {idx} product_code: {item.get('product_code') or ''}",
                f"  title_ko: {_short_display_title(item)}",
                f"  title_ja: {item.get('title_ja') or ''}",
                f"  actors: {', '.join(str(v) for v in (item.get('actors') or [])[:3])}",
                f"  genres: {', '.join(meaningful_genres[:4])}",
                f"  source: {item.get('source') or ''}",
                f"  persona_match_score: {item.get('persona_match_score') or 0}",
                f"  ranking_reasons: {', '.join(str(v) for v in (item.get('ranking_reasons') or [])[:2])}",
                f"  matched_persona_terms: {', '.join(str(v) for v in (item.get('matched_persona_terms') or [])[:3])}",
                f"  matched_genre_terms: {', '.join(str(v) for v in (item.get('matched_genre_terms') or [])[:3])}",
                f"  matched_query_terms: {', '.join(str(v) for v in (item.get('matched_query_terms') or [])[:4])}",
            ]
        )
        if synopsis_summary:
            lines.append(f"  synopsis_summary: {synopsis_summary}")
        elif grok_summary:
            lines.append(f"  grok.summary: {grok_summary}")
    lines.extend(
        [
            "[추천 응답 규칙]",
            "- 후보 순서(persona_match_score)는 랭커가 확정했으므로 바꾸지 말고 그 순서대로 설명만 한다.",
            "- 각 후보마다 배우 / 장르 / 한줄 요약(2문장 이내) / 추천 이유 순으로 4~5줄로 설명한다.",
            "- 추천 이유 1문장은 matched_persona_terms·matched_genre_terms·matched_query_terms·ranking_reasons를 인용해 쓴다.",
            "- matched_query_terms가 비어 있으면 요청 테마를 추천 이유에 넣지 않는다.",
            "- synopsis 원문을 그대로 인용하지 말고 synopsis_summary를 바탕으로 2문장 이내로 재서술한다.",
            "- 추천 이유는 한줄 요약을 반복하지 말고, 요청 테마·취향 연결을 1문장으로 쓴다.",
            "- 제목 옆 괄호 키워드만 나열하는 한 줄 추천은 금지한다.",
        ]
    )
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


def _compact_actress_profile(item: Mapping[str, Any], *, aggressive: bool = False) -> Dict[str, Any]:
    if not isinstance(item, Mapping):
        return {}
    return {
        "id": item.get("id"),
        "name": item.get("name") or "",
        "name_ja": item.get("name_ja") or "",
        "genres": _clip_text(item.get("genres") or "", 120 if aggressive else 200),
        "memo": _clip_text(item.get("memo") or "", 120 if aggressive else 220),
        "profile_text": _clip_text(item.get("profile_text") or "", 160 if aggressive else 400),
        "user_score": item.get("user_score") or 0.0,
        "favorite_intensity": item.get("favorite_intensity") or 0.0,
        "is_favorite": bool(item.get("is_favorite")),
        "aliases": (item.get("aliases") or [])[:3 if aggressive else 6],
        "agency": item.get("agency") or "",
        "work_count": int(item.get("work_count") or 0),
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

    actress_db = ctx.get("actress_db_context") if isinstance(ctx.get("actress_db_context"), Mapping) else {}
    favorite_profiles = [
        _compact_actress_profile(item, aggressive=aggressive)
        for item in list(actress_db.get("favorite_profiles") or [])[:3 if aggressive else 5]
        if isinstance(item, Mapping)
    ]
    mentioned_actresses = [
        _compact_actress_profile(item, aggressive=aggressive)
        for item in list(actress_db.get("mentioned") or [])[:2 if aggressive else 4]
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
        "actress_db_context": {
            "favorite_profiles": favorite_profiles,
            "mentioned": mentioned_actresses,
            "instruction": (
                "사용자가 언급하거나 즐겨찾기한 배우의 memo/profile_text/genres/work_count를 "
                "취향 분석·추천 근거로 활용하라. DB에 없는 배우 정보는 만들지 않는다."
            ),
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


def _actress_profile_focus_block(ctx: Mapping[str, Any], *, compact: bool = False) -> str:
    """배우 DB 프로필 요약 블록 (focused context용)."""
    actress_db = ctx.get("actress_db_context") if isinstance(ctx.get("actress_db_context"), Mapping) else {}
    actress_items = [
        item for item in list(actress_db.get("mentioned") or []) if isinstance(item, Mapping)
    ]
    if not actress_items:
        actress_items = [
            item for item in list(actress_db.get("favorite_profiles") or [])[:2 if compact else 4]
            if isinstance(item, Mapping)
        ]
    if not actress_items:
        return ""

    lines = ["[배우 프로필 DB]"]
    for item in actress_items[:2 if compact else 4]:
        name = str(item.get("name") or item.get("name_ja") or "").strip()
        if not name:
            continue
        parts = [name]
        if item.get("name_ja") and item.get("name_ja") != name:
            parts.append(f"({item.get('name_ja')})")
        wc = int(item.get("work_count") or 0)
        if wc > 0:
            parts.append(f"works={wc}")
        if item.get("genres"):
            parts.append(f"genres={_clip_text(str(item.get('genres')), 80 if compact else 140)}")
        if item.get("memo"):
            parts.append(f"memo={_clip_text(str(item.get('memo')), 80 if compact else 160)}")
        if item.get("profile_text") and not compact:
            parts.append(f"profile={_clip_text(str(item.get('profile_text')), 200)}")
        lines.append(f"- {' | '.join(parts)}")
    lines.append(
        "- memo/profile_text/genres는 DB 근거다. 없는 배우 정보는 만들지 않는다."
    )
    return "\n".join(lines)


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

    actress_block = _actress_profile_focus_block(ctx, compact=compact)
    if actress_block:
        lines.append(actress_block)

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


def _latin_char_ratio(text: str) -> float:
    chars = [c for c in str(text or "") if not c.isspace()]
    if not chars:
        return 0.0
    latin = sum(1 for c in chars if ord(c) < 128)
    return latin / len(chars)


_NUMBERED_PRODUCT_RE = re.compile(
    r"(?<!\d)\d{1,2}\.\s+(?:\*\*)?[A-Z]{1,8}-\d{2,7}\b",
    flags=re.IGNORECASE,
)


def _looks_like_english_reasoning_prefix(text: str) -> bool:
    prefix = str(text or "").strip()
    if len(prefix) < 24:
        return False
    if _latin_char_ratio(prefix) < 0.52:
        return False
    normalized = _reasoning_marker_text(prefix)
    hints = (
        "okay",
        "the user",
        "let me",
        "i should",
        "i need",
        "database",
        "present these",
        "make sure",
        "check the",
        "fit the",
        "options to",
        "they all",
        "good choice",
        "also pretty",
        "seems to",
        "user wants",
        "user seems",
        "highlight the",
    )
    if any(hint in normalized for hint in hints):
        return True
    return len(prefix) > 80 and not re.search(r"[\uAC00-\uD7A3]{4,}", prefix)


def _strip_inline_reasoning_prefix(text: str) -> str:
    """Remove English thinking paragraphs glued before the final Korean answer."""
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""

    product_match = _NUMBERED_PRODUCT_RE.search(cleaned)
    if product_match and product_match.start() > 0:
        prefix = cleaned[: product_match.start()].strip()
        if _looks_like_english_reasoning_prefix(prefix):
            return cleaned[product_match.start() :].strip()

    if re.match(
        r"^(?:Okay|OK|Alright|Sure|Let me|The user|I should|I need|Now,|So,|First,|Well,)\b",
        cleaned,
        flags=re.IGNORECASE,
    ):
        if product_match:
            return cleaned[product_match.start() :].strip()
        hangul_match = re.search(r"[\uAC00-\uD7A3]{8,}", cleaned)
        if hangul_match and hangul_match.start() > 30:
            prefix = cleaned[: hangul_match.start()]
            if _latin_char_ratio(prefix) > 0.5:
                return cleaned[hangul_match.start() :].strip()

    return cleaned


def _response_still_has_reasoning_leak(text: str) -> bool:
    cleaned = str(text or "").strip()
    if not cleaned:
        return False
    if _contains_reasoning_leak(cleaned):
        return True
    first_line = cleaned.splitlines()[0] if cleaned else ""
    if _looks_like_english_reasoning_prefix(first_line):
        return True
    if re.match(r"^(?:Okay|OK|Alright|Sure|Let me|The user|I should|I need)\b", cleaned, flags=re.IGNORECASE):
        return True
    return False


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
        "let me check the database",
        "the user wants",
        "i should present",
        "make sure to highlight",
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

    cleaned = _strip_inline_reasoning_prefix(cleaned)

    if _contains_reasoning_leak(cleaned):
        product_match = _NUMBERED_PRODUCT_RE.search(cleaned)
        if product_match:
            cleaned = cleaned[product_match.start() :].strip()
        else:
            hangul_match = re.search(r"[\uAC00-\uD7A3]{8,}", cleaned)
            if hangul_match and _latin_char_ratio(cleaned[: hangul_match.start()]) > 0.5:
                cleaned = cleaned[hangul_match.start() :].strip()
            else:
                return ""

    cleaned = _strip_inline_reasoning_prefix(cleaned)
    if _response_still_has_reasoning_leak(cleaned):
        return ""
    return cleaned


def _format_chat_response_text(text: str) -> str:
    """Add readable paragraph breaks to dense local-model chat output."""
    value = _strip_inline_reasoning_prefix(str(text or "").strip())
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


def _actress_filter_from_payload(payload: Mapping[str, Any]) -> Dict[str, str]:
    messages = payload.get("messages") or []
    system_text = "\n".join(
        str(message.get("content") or "")
        for message in messages
        if isinstance(message, Mapping) and str(message.get("role") or "") == "system"
    )
    name_match = re.search(r"actress_filter_name:\s*(.+)", system_text)
    if not name_match:
        return {}
    names_match = re.search(r"actress_filter_match_names:\s*(.+)", system_text)
    match_names = [
        part.strip()
        for part in re.split(r"[,，]\s*", names_match.group(1))
        if part.strip()
    ] if names_match else []
    primary = name_match.group(1).strip()
    if primary and primary not in match_names:
        match_names.insert(0, primary)
    return {"name": primary, "match_names": ",".join(match_names)}


def _candidate_matches_theme_terms(item: Mapping[str, str], query_terms: Sequence[str]) -> bool:
    if not query_terms:
        return True
    matched_raw = str(item.get("matched_query_terms") or "").strip()
    if matched_raw:
        return True
    from javstory.persona.library_search import item_matches_theme_terms

    actors = [part.strip() for part in str(item.get("actors") or "").split(",") if part.strip()]
    genres = [part.strip() for part in str(item.get("genres") or "").split(",") if part.strip()]
    payload = {
        "title_ko": item.get("title_ko") or "",
        "title_ja": item.get("title_ja") or "",
        "synopsis": item.get("synopsis") or item.get("synopsis_summary") or "",
        "actors": actors,
        "genres": genres,
    }
    return item_matches_theme_terms(payload, query_terms)


def _recommendation_response_needs_replacement(
    user_message: str,
    content: str,
    candidates: Sequence[Mapping[str, str]],
    recent_codes: Sequence[str],
    *,
    actress_filter: Mapping[str, str] | None = None,
) -> bool:
    if not _is_recommendation_request(user_message):
        return False
    text = str(content or "")
    stripped = text.strip()
    response_codes = [code.strip().upper() for code in extract_product_codes(text)]
    if any(marker in text for marker in _FABRICATED_RECOMMENDATION_MARKERS):
        return True
    if _looks_like_fake_numeric_recommendation(text):
        return True
    if _response_has_bureaucratic_enumeration(text):
        return True
    if response_codes and _looks_like_placeholder_product_codes(response_codes):
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
    query_terms = _extract_recommendation_query_terms(user_message)
    if query_terms and response_codes:
        candidate_by_code = {
            str(item.get("product_code") or "").strip().upper(): item for item in candidates
        }
        if any(
            not _candidate_matches_theme_terms(candidate_by_code.get(code) or {}, query_terms)
            for code in response_codes
        ):
            return True
        if any(term in text for term in query_terms):
            if not any(
                _candidate_matches_theme_terms(candidate_by_code.get(code) or {}, query_terms)
                for code in response_codes
            ):
                return True
    if actress_filter and str(actress_filter.get("name") or "").strip():
        from javstory.persona.actress_query import actor_list_matches_actress

        filter_payload = {
            "match_names": [
                part.strip()
                for part in re.split(r"[,，]\s*", str(actress_filter.get("match_names") or actress_filter.get("name") or ""))
                if part.strip()
            ],
        }
        candidate_by_code = {
            str(item.get("product_code") or "").strip().upper(): item for item in candidates
        }
        for code in response_codes:
            item = candidate_by_code.get(code) or {}
            actors_field = item.get("actors") or ""
            actors = [part.strip() for part in str(actors_field).split(",") if part.strip()]
            if not actor_list_matches_actress(actors, filter_payload):
                return True
    if _recommendation_response_too_thin(text, response_codes):
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


def _term_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = _field_text(value)
    if not text:
        return []
    return [part.strip() for part in re.split(r"[,·/]", text) if part.strip()]


def _meaningful_genre_terms(genres: Any) -> List[str]:
    out: List[str] = []
    for term in _term_list(genres):
        if term in _RECOMMENDATION_GENRE_SKIP:
            continue
        if len(term) <= 1:
            continue
        out.append(term)
    return out[:4]


def _display_taste_terms(terms: Sequence[str]) -> List[str]:
    out: List[str] = []
    for term in terms:
        cleaned = str(term or "").strip()
        if not cleaned or cleaned in _TASTE_TERM_SKIP:
            continue
        if len(cleaned) < 3 and not re.fullmatch(r"[A-Za-z0-9]{2,}", cleaned):
            continue
        if len(cleaned) <= 4 and cleaned.endswith(("는", "은", "을", "를", "이", "가", "와", "과", "의")):
            continue
        if cleaned not in out:
            out.append(cleaned)
    return out[:3]


def _strip_product_code_from_title(title: str, product_code: str = "") -> str:
    text = str(title or "").strip()
    code = str(product_code or "").strip().upper()
    if code and text.upper().startswith(code):
        text = re.sub(rf"^{re.escape(code)}\s*[-—:]\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def _normalize_synopsis_noise(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"\.{2,}", "…", cleaned)
    cleaned = re.sub(r"…+!+", "!", cleaned)
    cleaned = re.sub(r"!{2,}", "!", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _extract_summary_sentences(
    text: str,
    *,
    max_sentences: int = 2,
    max_chars: int = _SYNOPSIS_SUMMARY_MAX_CHARS,
) -> str:
    cleaned = _normalize_synopsis_noise(text)
    if not cleaned:
        return ""
    parts = [part.strip() for part in re.split(r"(?<=[。!?…])\s*|(?<=[.!?])\s+", cleaned) if part.strip()]
    if not parts:
        return _clip_text(cleaned, max_chars)
    picked: List[str] = []
    total = 0
    for part in parts[:max_sentences]:
        next_len = len(part) + (1 if picked else 0)
        if picked and total + next_len > max_chars:
            break
        picked.append(part.rstrip("…"))
        total += next_len
    if not picked:
        return _clip_text(cleaned, max_chars)
    joined = " ".join(picked)
    if len(joined) > max_chars:
        return _clip_text(joined, max_chars)
    return joined


def _summarize_synopsis_for_display(item: Mapping[str, Any]) -> str:
    grok = item.get("grok") if isinstance(item.get("grok"), Mapping) else {}
    grok_summary = _field_text(grok.get("summary") or item.get("grok.summary"))
    if grok_summary and len(grok_summary) >= 12:
        summary = _extract_summary_sentences(grok_summary)
        if summary:
            return summary

    raw_synopsis = _field_text(item.get("synopsis"))
    if raw_synopsis:
        summary = _extract_summary_sentences(raw_synopsis)
        if summary:
            return summary

    hook = _work_hook_phrase(item)
    genres = _meaningful_genre_terms(item.get("genres"))
    genre_phrase = _clip_text(", ".join(genres[:3]), 40) if genres else ""
    if hook and genre_phrase:
        return f"{hook} — {genre_phrase} 중심 작품이에요."
    if hook:
        return hook
    if genre_phrase:
        return f"{genre_phrase} 흐름의 작품이에요."
    return ""


def _short_display_title(item: Mapping[str, Any], *, limit: int = _SHORT_TITLE_CLIP) -> str:
    code = str(item.get("product_code") or "").strip()
    raw = str(item.get("title_ko") or item.get("title_ja") or "제목 정보 없음").strip()
    title = _strip_product_code_from_title(raw, code)
    if not title:
        return "제목 정보 없음"
    chunk = re.split(r"[。!?…]", title)[0].strip()
    if "," in chunk and len(chunk) > limit:
        chunk = chunk.split(",", 1)[0].strip()
    return _clip_text(chunk or title, limit)


def _work_hook_phrase(item: Mapping[str, Any], *, limit: int = 88) -> str:
    code = str(item.get("product_code") or "").strip()
    title = _strip_product_code_from_title(str(item.get("title_ko") or item.get("title_ja") or ""), code)
    if title and len(title) >= 10:
        chunk = re.split(r"[。!?…]", title)[0].strip()
        if len(chunk) >= 10:
            return _clip_text(chunk, limit)
    for candidate in (
        _field_text(item.get("synopsis")),
        _field_text(
            (item.get("grok") if isinstance(item.get("grok"), Mapping) else {}).get("summary")
        ),
    ):
        if not candidate:
            continue
        chunk = re.split(r"[。!?…]", candidate)[0].strip()
        if len(chunk) >= 10:
            return _clip_text(chunk, limit)
    return ""


def _ranking_query_miss(reasons: Any) -> bool:
    if isinstance(reasons, str):
        return "미매칭" in reasons
    return any("미매칭" in str(part) for part in (reasons or []))


def _josa_igo(word: str) -> str:
    if not word:
        return "와"
    last = word.rstrip()[-1]
    if "가" <= last <= "힣":
        return "과" if (ord(last) - ord("가")) % 28 > 0 else "와"
    return "와"


def _josa_eun_neun(word: str) -> str:
    if not word:
        return "는"
    last = word.rstrip()[-1]
    if "가" <= last <= "힣":
        return "은" if (ord(last) - ord("가")) % 28 > 0 else "는"
    return "는"


def _primary_actor_name(actors: str) -> str:
    text = str(actors or "").strip()
    if not text:
        return ""
    return text.split(",")[0].strip()


def _ranking_bonus_phrase(reasons: Any) -> str:
    parts = reasons if isinstance(reasons, list) else [reasons] if reasons else []
    text = " ".join(str(part) for part in parts)
    if "좋아요" in text or "별점" in text:
        return "예전에 호응 좋았던 작품과 비슷한 축이에요"
    if "임베딩" in text or "유사" in text:
        return "최근 반응 좋았던 작품과 결이 가까워요"
    if "강렬 반응" in text:
        return "최근 강하게 반응했던 작품과 같은 라인이에요"
    return ""


def _fallback_recommendation_reason(item: Mapping[str, str], *, include_synopsis: bool = True) -> str:
    query_terms = _term_list(item.get("matched_query_terms"))
    persona_terms = _display_taste_terms(_term_list(item.get("matched_persona_terms")))
    genres = _meaningful_genre_terms(item.get("genres"))
    actor = _primary_actor_name(_field_text(item.get("actors")))
    query_miss = _ranking_query_miss(item.get("ranking_reasons"))
    query_phrase = _clip_text(", ".join(query_terms), 40) if query_terms else ""
    taste_phrase = _clip_text(", ".join(persona_terms), 48) if persona_terms else ""
    genre_highlight = genres[0] if genres else ""
    bonus = _ranking_bonus_phrase(item.get("ranking_reasons"))

    if query_phrase and not query_miss and taste_phrase:
        return f"찾으신 {query_phrase}에 맞고, 평소 {taste_phrase} 쪽 취향과도 겹쳐요."
    if query_phrase and not query_miss:
        return f"이번에 찾으신 {query_phrase} 축이 장르와 전개의 중심이에요."
    if query_phrase and query_miss and taste_phrase:
        josa = _josa_eun_neun(query_phrase)
        return f"찾으신 {query_phrase}{josa} 조금 다르지만, {taste_phrase} 쪽 취향에는 잘 닿아요."
    if taste_phrase and bonus:
        return f"{bonus}, 평소 {taste_phrase} 쪽이시라서 골랐어요."
    if taste_phrase:
        return f"평소 끌리시는 {taste_phrase} 라인이라 오늘 후보 중에서 넣었어요."
    if bonus:
        return f"{bonus}."
    if genre_highlight and actor:
        return f"{genre_highlight}에 {actor} 조합이 눈에 띄어서 골랐어요."
    if genre_highlight:
        return f"{genre_highlight} 중심 전개라 오늘 취향 후보에 잘 맞아요."
    if actor:
        return f"{_clip_text(actor, 24)} 출연 작품이라 캐스팅 면에서 추천해요."

    if include_synopsis:
        snippet = _summarize_synopsis_for_display(item)
        if snippet:
            return f"{_clip_text(snippet, _REASON_SYNOPSIS_CLIP)} 포인트가 매력적이에요."

    return "취향·장르 적합도로 후보 안에서 골랐어요."


def _recommendation_item_detail_lines(item: Mapping[str, Any], idx: int) -> List[str]:
    code = str(item.get("product_code") or "").strip().upper()
    short_title = _short_display_title(item)
    lines = [f"{idx}. **{code}** — {short_title}"]

    actors = _field_text(item.get("actors"))
    genres = _meaningful_genre_terms(item.get("genres"))
    genre_text = ", ".join(genres)
    maker = _field_text(item.get("maker"))
    release_date = _field_text(item.get("release_date"))

    if actors:
        lines.append(f"   배우: {actors}")
    if genre_text:
        lines.append(f"   장르: {genre_text}")
    if maker:
        lines.append(f"   제작: {maker}")
    if release_date:
        lines.append(f"   발매: {release_date}")

    summary = _summarize_synopsis_for_display(item)
    if summary:
        lines.append(f"   한줄 요약: {summary}")
    lines.append(f"   추천 이유: {_fallback_recommendation_reason(item, include_synopsis=False)}")
    return lines


def _deterministic_recommendation_response(
    user_message: str,
    candidates: Sequence[Mapping[str, str]],
    recent_codes: Sequence[str],
    *,
    actress_filter: Mapping[str, str] | None = None,
) -> str:
    recent = {str(code or "").strip().upper() for code in recent_codes}
    fresh_request = _is_fresh_recommendation_request(user_message)
    filtered = [
        item
        for item in candidates
        if not fresh_request or str(item.get("product_code") or "").strip().upper() not in recent
    ]
    if actress_filter and str(actress_filter.get("name") or "").strip():
        from javstory.persona.actress_query import actor_list_matches_actress

        filter_payload = {
            "match_names": [
                part.strip()
                for part in re.split(r"[,，]\s*", str(actress_filter.get("match_names") or actress_filter.get("name") or ""))
                if part.strip()
            ],
        }
        filtered = [
            item
            for item in filtered
            if actor_list_matches_actress(
                [part.strip() for part in str(item.get("actors") or "").split(",") if part.strip()],
                filter_payload,
            )
        ]
    query_terms = _extract_recommendation_query_terms(user_message)
    if query_terms:
        from javstory.persona.library_search import item_matches_theme_terms

        filtered = [
            item
            for item in filtered
            if item_matches_theme_terms(item, query_terms)
            or str(item.get("matched_query_terms") or "").strip()
        ]
    if not filtered:
        actress_name = str((actress_filter or {}).get("name") or "").strip()
        if actress_name:
            return (
                f"지금 라이브러리에서 '{actress_name}' 출연작 후보를 찾지 못했어요. "
                "배우 프로필이 연결돼 있는지, 해당 작품 메타데이터가 수집됐는지 확인해 주세요."
            )
        if query_terms:
            return (
                f"지금 라이브러리에서 '{', '.join(query_terms)}' 테마에 맞는 작품 후보를 찾지 못했어요. "
                "제목·장르·시놉에 해당 키워드가 들어간 작품이 수집돼 있어야 추천할 수 있어요. "
                "비슷한 다른 테마를 말씀해 주시면 다시 찾아볼게요."
            )
        return _empty_recommendation_explanation(
            {"library_search": {"results": [], "query": user_message}}
        )

    actress_name = str((actress_filter or {}).get("name") or "").strip()
    if fresh_request:
        intro = "이번에는 방금 나온 품번은 빼고, DB 검색 후보에서 다시 골라 자세히 정리해 드릴게요."
    elif actress_name:
        intro = f"'{actress_name}' 출연작을 DB 검색 후보에서 골라 자세히 정리해 드릴게요."
    elif query_terms:
        intro = f"'{', '.join(query_terms)}' 테마에 맞는 작품을 DB 검색 후보에서 골라 자세히 정리해 드릴게요."
    else:
        intro = "오늘 보기 좋은 작품을 DB 검색 후보에서 골라 자세히 정리해 드릴게요."
    lines = [intro, ""]
    for idx, item in enumerate(filtered[:4], start=1):
        lines.extend(_recommendation_item_detail_lines(item, idx))
        lines.append("")
    return "\n".join(lines).rstrip()


def _save_memory_async(store: "EnhancedPersonaMemory", path: str) -> None:
    """Write memory JSON to disk in a background daemon thread."""
    try:
        store.save_to_json(path)
    except Exception as exc:
        logger.warning("[PersonaChatService] background memory save failed: %s", exc)


@dataclass
class _ContextCache:
    """Pre-built turn context shared across retry attempts to avoid redundant DB queries."""

    context: Dict[str, Any]
    memory_context: Dict[str, Any]
    recent_recommended_codes: List[str]


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
    tone_preset: str = "recommend"
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
    _backend_resolved: "tuple[str, str, str] | None" = field(default=None, init=False, repr=False)
    _backend_resolved_at: float = field(default=0.0, init=False, repr=False)

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

    def _build_turn_context(
        self,
        user_message: str,
        *,
        history: "Sequence[Mapping[str, Any]] | None" = None,
        product_code: "str | None" = None,
    ) -> _ContextCache:
        """Pre-build expensive turn context once — shared across all retry attempts."""
        try:
            from javstory.persona.recommendation_feedback import sync_recommendation_watch_feedback

            sync_recommendation_watch_feedback(self.enhanced_memory_store)
        except Exception:
            pass
        memory_context = self.enhanced_memory_store.prompt_context(user_message, max_items=5)
        # Skip disk-based recent message scan when UI history already covers recent turns.
        recent_from_store = (
            []
            if history
            else _recent_assistant_product_codes(self.enhanced_memory_store)
        )
        recent_recommended_codes = list(
            dict.fromkeys(
                list(getattr(self.enhanced_memory_store, "recent_recommended_product_codes", None) or [])
                + _recent_assistant_product_codes_from_history(history)
                + recent_from_store
            )
        )[:_RECENT_RECOMMENDATION_CONTEXT_LIMIT]
        if recent_recommended_codes:
            memory_context = dict(memory_context)
            memory_context["recent_recommended_product_codes"] = recent_recommended_codes
        context = self.engine.build_chat_context(
            user_message,
            product_code=product_code,
            seed_product_codes=_recommendation_seed_codes(memory_context),
            recent_recommended_codes=recent_recommended_codes,
            memory_store=self.enhanced_memory_store,
        )
        return _ContextCache(
            context=context,
            memory_context=memory_context,
            recent_recommended_codes=recent_recommended_codes,
        )

    def _resolve_backend(self) -> tuple[str, str, str]:
        now = time.monotonic()
        if self._backend_resolved is not None and (now - self._backend_resolved_at) < _BACKEND_CACHE_TTL:
            return self._backend_resolved

        configured_base = (self.base_url or os.environ.get("JAVSTORY_PERSONA_CHAT_BASE_URL") or "").strip()
        configured_model = persona_chat_model_from_env(self.model or os.environ.get("JAVSTORY_PERSONA_CHAT_MODEL"))
        api_key = (self.api_key or os.environ.get("JAVSTORY_PERSONA_CHAT_API_KEY") or "").strip()

        if configured_base:
            base = configured_base.rstrip("/")
            if not base.endswith("/v1"):
                base = f"{base}/v1"
            model = configured_model or persona_chat_model_from_env(os.environ.get("JAVSTORY_LLAMACPP_MODEL"))
            result: tuple[str, str, str] = (base, model, api_key or "local")
        else:
            preset = configured_model or persona_chat_model_from_env(os.environ.get("JAVSTORY_LLAMACPP_MODEL"))
            model = ensure_llamacpp_server_ready({"model": preset, "provider": "llamacpp"})
            result = (llamacpp_openai_base_url().rstrip("/"), model, api_key or "llamacpp")

        self._backend_resolved = result
        self._backend_resolved_at = now
        return result

    def build_messages(
        self,
        user_message: str,
        *,
        history: Sequence[Mapping[str, Any]] | None = None,
        product_code: str | None = None,
        force_final_only: bool = False,
        compact: bool | None = None,
        tone_preset: str | None = None,
        fast: bool = False,
        _ctx_cache: "_ContextCache | None" = None,
    ) -> List[Dict[str, str]]:
        use_compact = bool(compact) if compact is not None else bool(fast)
        if _ctx_cache is not None:
            memory_context = _ctx_cache.memory_context
            recent_recommended_codes = _ctx_cache.recent_recommended_codes
            context = _ctx_cache.context
        else:
            memory_context = self.enhanced_memory_store.prompt_context(
                user_message, max_items=1 if use_compact else 5
            )
            recent_recommended_codes = list(
                dict.fromkeys(
                    list(getattr(self.enhanced_memory_store, "recent_recommended_product_codes", None) or [])
                    + _recent_assistant_product_codes_from_history(history)
                    + ([] if history else _recent_assistant_product_codes(self.enhanced_memory_store))
                )
            )[:_RECENT_RECOMMENDATION_CONTEXT_LIMIT]
            if recent_recommended_codes:
                memory_context = dict(memory_context)
                memory_context["recent_recommended_product_codes"] = recent_recommended_codes
            context = self.engine.build_chat_context(
                user_message,
                product_code=product_code,
                seed_product_codes=_recommendation_seed_codes(memory_context),
                recent_recommended_codes=recent_recommended_codes,
                compact=use_compact,
                memory_store=self.enhanced_memory_store,
                fast=fast,
            )
        auto_compact = compact if compact is not None else _should_use_compact_pipeline(user_message, context)
        if is_user_rating_list_request(user_message):
            rated = fetch_user_rated_products(limit=20 if auto_compact else 40)
            if not rated:
                # Empty rating list can be answered without LLM.
                pass
        context = _apply_personalized_ranking(context, memory_context)
        compact_context = _compact_chat_context(context, aggressive=True)
        context_json = json.dumps(
            compact_context,
            ensure_ascii=False,
            default=str,
        )
        factual_grounding = _product_factual_grounding_block(user_message, context)
        actress_factual_grounding = _actress_factual_grounding_block(user_message, context)
        rating_grounding = _user_rating_list_grounding_block(user_message, context)
        rated_analysis_grounding = _rated_works_analysis_grounding_block(user_message, context)
        recommendation_grounding = _recommendation_grounding_block(user_message, context, memory_context)
        if recommendation_grounding or rated_analysis_grounding or actress_factual_grounding:
            auto_compact = False
        elif fast and not _should_use_full_chat_pipeline(user_message):
            auto_compact = True
        focused_context = (
            rating_grounding
            if rating_grounding
            else rated_analysis_grounding
            if rated_analysis_grounding
            else factual_grounding
            if factual_grounding
            else actress_factual_grounding
            if actress_factual_grounding
            else recommendation_grounding
            if recommendation_grounding
            else (
                build_focused_context(user_message, compact_context)
                if os.environ.get("JAVSTORY_PERSONA_CHAT_EMBED_FOCUS", "").strip().lower() in {"1", "true", "yes", "on"}
                else _deterministic_focused_context(compact_context, compact=auto_compact)
            )
        )
        actress_append = _actress_profile_focus_block(compact_context, compact=compact)
        if actress_append and "[배우 프로필 DB]" not in focused_context:
            focused_context = (
                f"{focused_context}\n\n{actress_append}" if focused_context else actress_append
            )
        if auto_compact and not recommendation_grounding and not actress_factual_grounding:
            focused_context = _clip_text(focused_context, 1400)
            memory_context = _compact_memory_context_for_prompt(memory_context, max_items=1)
        elif recommendation_grounding or rated_analysis_grounding or actress_factual_grounding:
            focused_context = _clip_text(focused_context, 4200)
            memory_context = _compact_memory_context_for_prompt(memory_context, max_items=2)
        elif not auto_compact:
            focused_context = _clip_text(focused_context, 2800)
            memory_context = _compact_memory_context_for_prompt(memory_context, max_items=3)
        style_instruction = _response_style_instruction(user_message)
        active_tone = tone_preset if tone_preset is not None else self.tone_preset
        if rated_analysis_grounding:
            active_tone = "analysis"
        elif recommendation_grounding:
            active_tone = "recommend"
        if factual_grounding:
            memory_instruction = (
                "## 장기 대화 메모리\n"
                "이번 요청은 특정 품번의 작품 사실 설명이므로, "
                "메모리는 말투 선호 외에는 사실 근거로 쓰지 않는다. "
                "작품 내용·장면·전개는 [작품 사실 고정 근거]의 synopsis/story_context에 없는 내용을 보태지 않는다.\n"
            )
        elif rating_grounding:
            memory_instruction = (
                "## 장기 대화 메모리\n"
                "이번 요청은 사용자 평점 목록 질의이므로, "
                "메모리는 말투 선호 외에는 사실 근거로 쓰지 않는다. "
                "[사용자 평점 목록 고정 근거] 밖 작품은 추가하지 않는다.\n"
            )
        elif rated_analysis_grounding:
            memory_instruction = (
                "## 장기 대화 메모리\n"
                "이번 요청은 평점 작품 취향 분석이므로, "
                "메모리는 말투 선호 외에는 사실 근거로 쓰지 않는다. "
                "[평점 작품 취향 분석 고정 근거]의 장르·배우·시놉만 사용한다.\n"
            )
        elif actress_factual_grounding:
            memory_instruction = (
                "## 장기 대화 메모리\n"
                "이번 요청은 배우 정보 질의이므로, "
                "메모리는 말투 선호 외에는 사실 근거로 쓰지 않는다. "
                "[배우 사실 고정 근거]의 프로필·library_filmography에 없는 품번·장면은 만들지 않는다.\n"
            )
        elif recommendation_grounding:
            memory_instruction = (
                "## 장기 대화 메모리\n"
                "이번 요청은 작품 추천이므로, "
                "메모리는 말투 선호 외에는 사실 근거로 쓰지 않는다. "
                "[추천 후보 고정 근거]의 메타데이터만 사용하고 각 작품을 3~5줄로 설명한다.\n"
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
                memory_context,
                factual=bool(
                    factual_grounding
                    or rating_grounding
                    or rated_analysis_grounding
                    or actress_factual_grounding
                ),
                compact=auto_compact,
            )
            if memory_readable:
                system_parts.append("\n" + memory_readable)
            if (
                factual_grounding
                or rating_grounding
                or rated_analysis_grounding
                or recommendation_grounding
                or actress_factual_grounding
            ):
                system_parts.append("\n" + memory_instruction.strip())
            if style_instruction:
                v2_style = _tone_style_for_preset(active_tone, user_message)
                if v2_style:
                    system_parts.append("\n[응답 스타일] " + v2_style)
            system_parts.append(
                "\n"
                + _build_output_rules(
                    compact=auto_compact,
                    factual=bool(factual_grounding or rating_grounding),
                    rated_analysis=bool(rated_analysis_grounding),
                    recommendation=bool(recommendation_grounding),
                )
            )
        else:
            system_prompt = COMPACT_PERSONA_SYSTEM_PROMPT if auto_compact else self.system_prompt
            system_parts = [
                system_prompt,
                "\n## 현재 사용자 취향 컨텍스트\n이 데이터에 근거해 존댓말로 답하세요.\n" + focused_context,
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
                        "바로 사용자에게 말하듯 자연스러운 존댓말(해요체) 대화문으로 3~8문장만 답한다. 반말 금지."
                    ),
                }
            )
        messages.extend(
            _normalize_history(
                history,
                max_items=1 if auto_compact else 4,
                max_chars=220 if auto_compact else 700,
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
        fast: bool = False,
        _ctx_cache: "_ContextCache | None" = None,
    ) -> Dict[str, Any]:
        return {
            "model": model,
            "messages": self.build_messages(
                text,
                history=history,
                product_code=product_code,
                force_final_only=force_final_only,
                compact=compact,
                fast=fast,
                _ctx_cache=_ctx_cache,
            ),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

    def _degraded_chat_response(
        self,
        user_message: str,
        *,
        history: Sequence[Mapping[str, Any]] | None = None,
        product_code: str | None = None,
    ) -> Dict[str, Any]:
        text = str(user_message or "").strip()
        memory_context = self.enhanced_memory_store.prompt_context(text, max_items=5)
        recent_recommended_codes = list(
            dict.fromkeys(
                list(getattr(self.enhanced_memory_store, "recent_recommended_product_codes", None) or [])
                + _recent_assistant_product_codes_from_history(history)
                + _recent_assistant_product_codes(self.enhanced_memory_store)
            )
        )[:_RECENT_RECOMMENDATION_CONTEXT_LIMIT]
        if recent_recommended_codes:
            memory_context = dict(memory_context)
            memory_context["recent_recommended_product_codes"] = recent_recommended_codes

        if is_user_rating_list_request(text):
            rated = fetch_user_rated_products(limit=40)
            return _openai_compatible_response(
                model="persona-chat-degraded",
                content=_deterministic_rating_list_response(rated),
            )

        context = self.engine.build_chat_context(
            text,
            product_code=product_code,
            seed_product_codes=_recommendation_seed_codes(memory_context),
            recent_recommended_codes=recent_recommended_codes,
        )
        context = _apply_personalized_ranking(context, memory_context)
        if _is_recommendation_request(text):
            search = context.get("library_search") if isinstance(context.get("library_search"), Mapping) else {}
            candidates = [item for item in list(search.get("results") or []) if isinstance(item, Mapping)]
            actress_filter = search.get("actress_filter") if isinstance(search.get("actress_filter"), Mapping) else {}
            return _openai_compatible_response(
                model="persona-chat-degraded",
                content=_deterministic_recommendation_response(
                    text,
                    candidates,
                    recent_recommended_codes,
                    actress_filter=actress_filter,
                ),
            )

        persona = context.get("persona") if isinstance(context.get("persona"), Mapping) else {}
        summary = str(persona.get("sensual_summary") or persona.get("summary") or "").strip()
        if summary:
            return _openai_compatible_response(
                model="persona-chat-degraded",
                content=(
                    "지금은 로컬 LLM을 사용할 수 없어서 페르소나 요약만 전달드릴게요.\n\n"
                    f"{_clip_text(summary, 900)}"
                ),
            )
        return _openai_compatible_response(
            model="persona-chat-degraded",
            content="지금은 로컬 LLM을 사용할 수 없어요. llama.cpp 서버를 켠 뒤 다시 시도해 주세요.",
        )

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
                content="어떤 작품이나 취향이 걸리시는지 한 줄만 말씀해 주세요. 그 결을 바로 짚어 드릴게요.",
            )

        if is_user_rating_list_request(text):
            rated = fetch_user_rated_products(limit=40)
            if not rated:
                content = _deterministic_rating_list_response([])
                try:
                    self.enhanced_memory_store.record_turn(text, content)
                    self.enhanced_memory_store.save_to_json(str(ENHANCED_PERSONA_MEMORY_PATH))
                except Exception as e:
                    print(f"[PersonaChatService] memory turn save failed: {e}")
                return _openai_compatible_response(model=self.model or "persona-chat", content=content)

        try:
            base_url, model, api_key = self._resolve_backend()
        except Exception as exc:
            logger.warning("Persona chat backend unavailable, using degraded mode: %s", exc)
            response = self._degraded_chat_response(text, history=history, product_code=product_code)
            content = (
                ((response.get("choices") or [{}])[0].get("message") or {}).get("content")
                if isinstance(response, dict)
                else ""
            )
            if content:
                try:
                    self.enhanced_memory_store.record_turn(text, content)
                    self.enhanced_memory_store.save_to_json(str(ENHANCED_PERSONA_MEMORY_PATH))
                except Exception as e:
                    print(f"[PersonaChatService] memory turn save failed: {e}")
            return response

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

        # Build expensive context once — reused across all retry attempts.
        ctx_cache = self._build_turn_context(text, history=history, product_code=product_code)

        payload = self._build_payload(
            model=model,
            text=text,
            history=history,
            product_code=product_code,
            temperature=req_temperature,
            max_tokens=req_max_tokens,
            compact=False,
            _ctx_cache=ctx_cache,
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
                    _ctx_cache=ctx_cache,
                )
                raw = self._post_chat_completion(
                    client,
                    base_url=base_url,
                    payload=payload,
                    headers=headers,
                )
            content = _strip_reasoning_leak(_coalesce_response_text(raw))
            if content and _response_still_has_reasoning_leak(content):
                content = _strip_reasoning_leak(content)
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
                    _ctx_cache=ctx_cache,
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
                        _ctx_cache=ctx_cache,
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
            actress_filter = _actress_filter_from_payload(payload)
            if _recommendation_response_needs_replacement(
                text,
                content,
                candidates,
                recent_codes,
                actress_filter=actress_filter or None,
            ):
                content = _deterministic_recommendation_response(
                    text,
                    candidates,
                    recent_codes,
                    actress_filter=actress_filter or None,
                )
            if _rated_works_analysis_response_needs_replacement(text, content):
                rated = fetch_user_rated_products(limit=25)
                content = _deterministic_rated_works_pattern_summary(rated)
            if _response_still_has_reasoning_leak(content):
                leak_retry_payload = self._build_payload(
                    model=model,
                    text=text,
                    history=[],
                    product_code=product_code,
                    temperature=min(0.72, req_temperature),
                    max_tokens=min(1600, req_max_tokens),
                    force_final_only=True,
                    compact=_is_recommendation_request(text),
                    fast=not _is_recommendation_request(text),
                    _ctx_cache=ctx_cache,
                )
                try:
                    leak_retry_raw = self._post_chat_completion(
                        client,
                        base_url=base_url,
                        payload=leak_retry_payload,
                        headers=headers,
                    )
                    leak_retry_content = _strip_reasoning_leak(_coalesce_response_text(leak_retry_raw))
                    if leak_retry_content and not _response_still_has_reasoning_leak(leak_retry_content):
                        content = leak_retry_content
                        payload = leak_retry_payload
                except Exception:
                    pass
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
                    _ctx_cache=ctx_cache,
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
                threading.Thread(
                    target=_save_memory_async,
                    args=(self.enhanced_memory_store, str(ENHANCED_PERSONA_MEMORY_PATH)),
                    daemon=True,
                ).start()
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
            content="답변 형식이 내부 초안처럼 생성돼서 표시하지 않았어요. 같은 질문을 한 번만 다시 보내 주세요.",
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
