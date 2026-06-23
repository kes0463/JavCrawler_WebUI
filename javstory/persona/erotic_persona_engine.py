"""Persona Chat context builder.

The class name follows the product terminology, but the generated chat
context is constrained to a mature, sensual analysis tone rather than
graphic sexual roleplay.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List

from javstory.analytics.persona_card import get_persona_card
from javstory.analytics.persona_context import build_persona_context
from javstory.config.app_config import DATA_ROOT
from javstory.harvest.database import JAVMetadata, get_db_session_ctx
from javstory.library.embeddings.pipeline import embeddings_ollama_model_from_env
from javstory.llm.ollama_embeddings import ollama_embed_texts
from javstory.persona.library_search import (
    _attach_user_watch_signals,
    detect_source_policy,
    extract_product_codes,
    extract_strict_title_terms,
    normalize_product_code,
    row_to_search_result,
    split_query_terms,
)
from javstory.persona.persona_memory import EnhancedPersonaMemory
from javstory.persona.recommendation_pool import fetch_recommendation_pool
from javstory.persona.user_rating_list import fetch_user_rated_products, is_user_rating_list_request

CONTEXT_SIMILARITY_THRESHOLD = 0.6
CONTEXT_MAX_ITEMS = 8
_CHAT_SEARCH_FAST_WEIGHTS = (0.45, 0.0, 0.55)
_CHAT_SEARCH_EMBEDDING_WEIGHTS = (0.3, 0.5, 0.2)
ENHANCED_PERSONA_MEMORY_PATH = DATA_ROOT / "cache" / "persona_chat_enhanced_memory.json"


def _actress_name_candidates_from_context(persona_context: dict) -> list[str]:
    """즐겨찾기·시청 상위 배우명 후보 (긴 이름 우선 매칭용)."""
    names: list[str] = []
    seen: set[str] = set()

    def add(raw) -> None:
        n = (raw or "").strip()
        if not n:
            return
        key = n.casefold()
        if key in seen:
            return
        seen.add(key)
        names.append(n)

    for fav in persona_context.get("favorite_actress_profiles") or []:
        if not isinstance(fav, dict):
            continue
        add(fav.get("name"))
        add(fav.get("name_ja"))

    for key in ("top_actors", "top_actors_recent"):
        for actor in persona_context.get(key) or []:
            if isinstance(actor, dict):
                add(actor.get("name"))
            elif isinstance(actor, str):
                add(actor)

    names.sort(key=len, reverse=True)
    return names


def _actress_db_chat_context(user_message: str, persona_context: dict) -> dict:
    """배우 프로필 DB 컨텍스트 — 즐겨찾기 + 메시지 내 이름 매칭."""
    from javstory.utils.actress_profile import get_actress_context_by_name

    out: dict = {
        "favorite_profiles": persona_context.get("favorite_actress_profiles") or [],
        "mentioned": [],
    }
    msg = (user_message or "").strip()
    if not msg:
        return out

    seen_ids: set[int] = set()
    mentioned: list[dict] = []
    for name in _actress_name_candidates_from_context(persona_context):
        if name not in msg:
            continue
        ctx = get_actress_context_by_name(name)
        if not ctx:
            continue
        aid = int(ctx.get("id") or 0)
        if aid > 0:
            if aid in seen_ids:
                continue
            seen_ids.add(aid)
        mentioned.append(ctx)

    out["mentioned"] = mentioned
    return out


# 추천/검색 의도를 명시적으로 부정하는 패턴
# 이 패턴이 포함된 메시지는 "recommendation" 의도로 분류하지 않는다.
_RECOMMENDATION_NEGATION_HINTS = (
    "추천하지마",
    "추천하지 마",
    "추천 말아",
    "추천 빼줘",
    "추천 제외",
    "찾지마",
    "찾지 마",
    "골라주지마",
    "골라주지 마",
)


def _split_csv(text: str | None) -> List[str]:
    if not text:
        return []
    return [v.strip() for v in text.replace("、", ",").split(",") if v.strip()]


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return float("-inf")
    n = min(len(a), len(b))
    if n <= 0:
        return float("-inf")
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for idx in range(n):
        av = float(a[idx])
        bv = float(b[idx])
        dot += av * bv
        norm_a += av * av
        norm_b += bv * bv
    if norm_a <= 0 or norm_b <= 0:
        return float("-inf")
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def _embed_texts_blocking(texts: List[str]) -> List[List[float]]:
    model = embeddings_ollama_model_from_env()
    try:
        return asyncio.run(ollama_embed_texts(texts=texts, model=model, timeout_sec=90.0))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(ollama_embed_texts(texts=texts, model=model, timeout_sec=90.0))
        finally:
            loop.close()


def _context_value_to_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, default=str)


def _persona_chat_search_weights() -> tuple[float, float, float]:
    raw = (os.environ.get("JAVSTORY_PERSONA_CHAT_SEARCH_EMBEDDING", "") or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return _CHAT_SEARCH_EMBEDDING_WEIGHTS
    return _CHAT_SEARCH_FAST_WEIGHTS


def _top_strong_reactions(limit: int = 3, *, memory_store: Any | None = None) -> List[Dict[str, Any]]:
    try:
        if memory_store is not None:
            memory = memory_store.prompt_context("", max_items=max(3, limit * 2))
        else:
            store = EnhancedPersonaMemory()
            store.load_from_json(str(ENHANCED_PERSONA_MEMORY_PATH))
            memory = store.prompt_context("", max_items=max(3, limit * 2))
    except Exception:
        return []
    notes = [item for item in memory.get("strong_reaction_notes") or [] if isinstance(item, dict)]
    notes.sort(
        key=lambda item: (
            float(item.get("intensity") or 0),
            str(item.get("created_at") or ""),
        ),
        reverse=True,
    )
    return notes[:limit]


def _strong_reaction_seed_codes(strong_reactions: List[Dict[str, Any]], limit: int = 3) -> List[str]:
    out: List[str] = []
    for note in strong_reactions:
        for code in note.get("product_codes") or []:
            pc = normalize_product_code(str(code or ""))
            if pc and pc not in out:
                out.append(pc)
            if len(out) >= limit:
                return out
    return out


def _strip_product_codes(text: str) -> str:
    cleaned = str(text or "")
    for code in extract_product_codes(cleaned, limit=20):
        if not code:
            continue
        variants = {code, code.replace("-", ""), code.replace("-", " ")}
        for variant in variants:
            cleaned = re.sub(re.escape(variant), " ", cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.split())


def _strong_reaction_query_hint(strong_reactions: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for note in strong_reactions:
        text = _strip_product_codes(str(note.get("text") or "").strip())
        triggers = ", ".join(str(v) for v in note.get("triggers") or [] if str(v).strip())
        chunk = " ".join(v for v in [triggers, text] if v)
        if chunk:
            parts.append(chunk)
    return " / ".join(parts[:3])


def _summarize_sensual_triggers(turn_ons: List[Any], strong_reactions: List[Dict[str, Any]]) -> str:
    triggers: List[str] = []
    for item in turn_ons:
        text = str(item or "").strip()
        if text and text not in triggers:
            triggers.append(text)
    for note in strong_reactions:
        for trigger in note.get("triggers") or []:
            text = str(trigger or "").strip()
            if text and text not in triggers:
                triggers.append(text)
    if not triggers:
        return "아직 특정 자극 축은 충분히 확정되지 않았지만, 현재 질문과 라이브러리 근거를 우선한다."
    return "이 사용자는 특히 " + ", ".join(triggers[:8]) + " 계열의 자극에 크게 반응한다."


def _chat_intent(user_message: str, mentioned_codes: List[str]) -> str:
    text = str(user_message or "").lower()

    if is_user_rating_list_request(text):
        return "user_rating_list"

    # 추천/검색 의도의 명시적 부정 여부를 먼저 확인
    is_negated = any(hint in text for hint in _RECOMMENDATION_NEGATION_HINTS)

    if any(hint in text for hint in ("내 취향", "취향 분석", "페르소나", "성향", "무슨 타입")):
        return "self_analysis"
    # 명시적 부정("추천하지 마" 등)이 있으면 product/recommendation 양쪽 모두 건너뜀.
    # 예: "이 작품 추천하지 마", "HBAD-509 추천하지 마" → general
    if not is_negated and (mentioned_codes or any(hint in text for hint in ("이 작품", "품번", "작품 어때", "어때?", "분석해"))):
        return "product"
    # "작품" 단독 힌트 제거: "작품 별로야" 같은 부정 평가를 recommendation으로 오분류하는 문제 방지.
    # "추천", "비슷", "찾아", "골라", "볼만" 이 추천 의도를 충분히 커버한다.
    if not is_negated and any(hint in text for hint in ("추천", "비슷", "찾아", "골라", "볼만")):
        return "recommendation"
    if "왜" in text:
        return "self_analysis"
    return "general"


def _selected_persona_fields(
    intent: str,
    *,
    persona_type: str,
    persona_summary: str,
    sensual_summary: str,
    sensual_focus: str,
    turn_ons: List[Any],
    avoidances: List[Any],
    affinities: List[Any],
    evidence: List[Any],
    source: str,
) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "intent": intent,
        "type": persona_type,
        "included_fields": [],
        "sensual_focus": {
            "priority": "high" if sensual_summary else "fallback",
            "summary": sensual_focus,
            "instruction": (
                "답변에서는 일반 요약보다 이 관능 취향 요약을 우선 근거로 삼고, "
                "사용자가 어떤 분위기와 관계성에 강하게 반응하는지 선명하게 짚는다."
            ),
        },
        "source": source,
    }

    def include(key: str, value: Any) -> None:
        if value in ("", None, [], {}):
            return
        base[key] = value
        base["included_fields"].append(key)

    if intent == "recommendation":
        include("sensual_summary", sensual_summary)
        include("turn_ons", turn_ons)
        include("avoidances", avoidances)
        include("affinities", affinities[:4])
    elif intent == "self_analysis":
        include("summary", persona_summary)
        include("sensual_summary", sensual_summary)
        include("turn_ons", turn_ons)
        include("avoidances", avoidances)
        include("affinities", affinities)
        include("evidence", evidence[:3])
    elif intent == "product":
        include("sensual_summary", sensual_summary)
        include("turn_ons", turn_ons[:5])
        include("avoidances", avoidances[:4])
        include("evidence", evidence[:2])
    elif intent == "user_rating_list":
        include("summary", persona_summary)
    else:
        include("summary", persona_summary)
        include("sensual_summary", sensual_summary)
        include("turn_ons", turn_ons[:4])
        include("avoidances", avoidances[:3])
    return base


def _chat_pipeline_mode(intent: str, user_message: str) -> str:
    """Return 'full', 'light', or 'rating_list' for pipeline cost control."""
    if intent == "user_rating_list":
        return "rating_list"
    if intent == "general":
        return "light"
    if intent in {"recommendation", "self_analysis"}:
        return "full"
    if intent == "product" and not is_user_rating_list_request(user_message):
        return "light"
    lowered = str(user_message or "").lower()
    if any(h in lowered for h in ("줄거리", "시놉", "정보", "검색", "찾아")):
        return "light"
    return "full"


def _needs_hybrid_library_search(intent: str, user_message: str) -> bool:
    """HybridLibrarySearch는 추천·품번·명시적 검색 의도에서만 실행한다."""
    if intent in {"recommendation", "product"}:
        return True
    lowered = str(user_message or "").lower()
    return any(h in lowered for h in ("추천", "비슷", "찾아", "골라", "볼만", "검색"))


def _mix_hidden_gem_candidates(
    adapted_results: List[Dict[str, Any]],
    *,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """Blend insight Hidden Gems into recommendation candidates for exploration."""
    if not adapted_results:
        return adapted_results
    try:
        from javstory.analytics.library_stats import get_unwatched_gems

        gems = get_unwatched_gems(max(2, limit))
    except Exception:
        return adapted_results

    existing = {
        normalize_product_code(str(item.get("product_code") or ""))
        for item in adapted_results
    }
    merged = list(adapted_results)
    for gem in gems[:limit]:
        pc = normalize_product_code(str(gem.get("product_code") or ""))
        if not pc or pc in existing:
            continue
        merged.append(
            {
                "product_code": pc,
                "title_ko": str(gem.get("title_ko") or ""),
                "title_ja": "",
                "actors": _split_csv(str(gem.get("actors_ko") or "")),
                "genres": [],
                "maker": "",
                "release_date": str(gem.get("release_date") or ""),
                "synopsis": "",
                "favorite_score": 0,
                "folder_path": "",
                "source": "hidden_gem",
                "score": float(gem.get("rec_score") or 0.55),
                "gem_type": str(gem.get("gem_type") or ""),
            }
        )
        existing.add(pc)
    return merged


def _build_user_rating_library_search(user_message: str, rated_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    codes = [str(item.get("product_code") or "").strip().upper() for item in rated_items if item.get("product_code")]
    return {
        "query": user_message,
        "terms": [],
        "strict_title_terms": [],
        "strict_title_contains": False,
        "source_policy": {
            "mode": "user_rating_list",
            "primary_source": "watch_history",
            "allowed_candidate_sources": ["user_rating"],
            "use_db_metadata": True,
            "use_synopsis": False,
            "use_grok": False,
            "use_embedding": False,
            "hard_constraints": [
                "사용자가 직접 평점/좋아요/완주를 남긴 작품만 나열한다.",
                "평점이 없는 작품은 목록에 넣지 않는다.",
            ],
        },
        "product_codes": codes[:20],
        "fallback_seed_codes": [],
        "results": rated_items,
    }


def build_focused_context(user_message: str, full_persona_data: dict) -> str:
    """Select persona attributes most relevant to the current user message."""
    query = str(user_message or "").strip()
    if not query or not isinstance(full_persona_data, dict):
        return "[취향 정보]"

    items: List[tuple[str, str]] = []
    for key, value in full_persona_data.items():
        value_text = _context_value_to_text(value)
        if str(key).strip() and value_text:
            items.append((str(key), value_text))
    if not items:
        return "[취향 정보]"

    texts = [query] + [f"{key}: {value}" for key, value in items]
    try:
        vectors = _embed_texts_blocking(texts)
    except Exception:
        return "[취향 정보]"
    if len(vectors) != len(texts):
        return "[취향 정보]"

    query_vec = vectors[0]
    scored: List[tuple[float, str, str]] = []
    for (key, value), vec in zip(items, vectors[1:]):
        score = _cosine_similarity(query_vec, vec)
        if math.isfinite(score) and score >= CONTEXT_SIMILARITY_THRESHOLD:
            scored.append((score, key, value))
    scored.sort(key=lambda item: item[0], reverse=True)

    lines = ["[취향 정보]"]
    for _score, key, value in scored[:CONTEXT_MAX_ITEMS]:
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def _adapt_hybrid_search_results(
    query: str,
    hybrid_results: List[Dict[str, Any]],
    *,
    product_codes: List[str] | None = None,
    fallback_seed_codes: List[str] | None = None,
) -> Dict[str, Any]:
    """Adapt HybridLibrarySearch rows to Persona Chat's library_search schema."""
    codes = list(product_codes or extract_product_codes(query, limit=5))
    strict_title_terms = extract_strict_title_terms(query)
    source_policy = detect_source_policy(
        query,
        product_codes=codes,
        strict_title_terms=strict_title_terms,
    )
    result_codes: List[str] = []
    result_by_code: Dict[str, Dict[str, Any]] = {}
    for item in hybrid_results:
        code = normalize_product_code(str(item.get("id") or ""))
        if code and code not in result_by_code:
            result_codes.append(code)
            result_by_code[code] = item
    adapted_results: List[Dict[str, Any]] = []

    with get_db_session_ctx() as session:
        rows = (
            session.query(JAVMetadata)
            .filter(JAVMetadata.product_code.in_(result_codes))
            .all()
            if result_codes
            else []
        )
        row_by_code = {str(row.product_code or "").strip().upper(): row for row in rows}

    for code in result_codes:
        item = result_by_code.get(code) or {}
        row = row_by_code.get(code)
        if row:
            adapted = row_to_search_result(
                row,
                source=str(item.get("source") or "hybrid"),
                score=float(item.get("score") or 0),
            )
        else:
            adapted = {
                "product_code": code,
                "title_ko": str(item.get("title") or ""),
                "title_ja": "",
                "actors": [],
                "genres": [],
                "maker": "",
                "release_date": "",
                "synopsis": "",
                "favorite_score": 0,
                "folder_path": "",
                "source": str(item.get("source") or "hybrid"),
                "score": float(item.get("score") or 0),
            }
        adapted["hybrid_score"] = float(item.get("score") or 0)
        adapted["hybrid_source"] = str(item.get("source") or "hybrid")
        adapted_results.append(adapted)

    _attach_user_watch_signals(adapted_results)
    return {
        "query": query,
        "terms": split_query_terms(query),
        "strict_title_terms": strict_title_terms,
        "strict_title_contains": bool(strict_title_terms),
        "source_policy": source_policy,
        "product_codes": codes,
        "fallback_seed_codes": [
            normalize_product_code(code)
            for code in list(fallback_seed_codes or [])
            if normalize_product_code(code)
        ],
        "results": adapted_results,
    }


@dataclass
class EroticPersonaEngine:
    """Builds compact, chat-ready persona context from local JAVSTORY data."""

    cache_only: bool = True
    # skip_context: True 이면 context_snapshot() DB 쿼리를 생략한다.
    # cache_only(Ollama 합성 스킵)와 독립적으로 제어할 수 있도록 분리.
    # 기본값 False: cache_only=True 여도 DB 쿼리(top_actors·top_genres 등)는 항상 실행.
    skip_context: bool = False
    max_context_products: int = 8
    search_limit: int = 8

    def persona_snapshot(self) -> Dict[str, Any]:
        return get_persona_card(cache_only=self.cache_only)

    def context_snapshot(self) -> Dict[str, Any]:
        return build_persona_context(max_products=self.max_context_products)

    def product_snapshot(self, product_code: str) -> Dict[str, Any]:
        pc = normalize_product_code(product_code)
        if not pc:
            return {}

        data: Dict[str, Any] = {"product_code": pc}
        with get_db_session_ctx() as session:
            row = session.query(JAVMetadata).filter_by(product_code=pc).first()
            if row:
                data.update(
                    {
                        "title_ko": row.title_ko or "",
                        "title_ja": row.title_ja or "",
                        "actors": _split_csv(row.actors_ko or row.actors_ja or row.actors or ""),
                        "genres": _split_csv(row.genres_ko or row.genres or ""),
                        "maker": row.maker_ko or row.maker_ja or row.maker or "",
                        "release_date": row.release_date or "",
                        "synopsis": row.synopsis_ko or row.synopsis or "",
                    }
                )

        try:
            from javstory.translation.story_grok_module import load_cached_grok_json_flexible

            grok = load_cached_grok_json_flexible(pc)
            grok_pc = normalize_product_code(str((grok or {}).get("product_code") or ""))
            if grok and (not grok_pc or grok_pc != pc):
                data["story_context_status"] = {
                    "available": False,
                    "reason": "grok_product_code_mismatch",
                    "requested_product_code": pc,
                    "grok_product_code": grok_pc or "",
                }
            elif grok and grok.get("verification_ok") is not False and not grok.get("code_mismatch"):
                scene_tags: List[str] = []
                scene_tones: List[str] = []
                for scene in grok.get("scenes") or []:
                    if not isinstance(scene, dict):
                        continue
                    for tag in scene.get("key_tags") or []:
                        if isinstance(tag, str) and tag.strip() and tag.strip() not in scene_tags:
                            scene_tags.append(tag.strip())
                    tone = str(scene.get("tone") or "").strip()
                    if tone and tone not in scene_tones:
                        scene_tones.append(tone)
                data["story_context"] = {
                    "summary": (grok.get("overall_summary") or grok.get("synopsis_short") or "")[:600],
                    "tags": scene_tags[:12],
                    "tones": scene_tones[:8],
                    "scene_count": len(grok.get("scenes") or []),
                    "source": "grok_story_cache",
                    "verified_product_code": grok_pc,
                    "confidence": "medium",
                }
                data["story_context_status"] = {
                    "available": bool(data["story_context"]["summary"]),
                    "reason": "grok_verified_product_code_match",
                    "requested_product_code": pc,
                    "grok_product_code": grok_pc,
                }
        except Exception:
            pass

        return data

    def _batch_product_snapshots(self, product_codes: List[str]) -> List[Dict[str, Any]]:
        """Query all product codes in a single DB session instead of one session each."""
        normalized = [normalize_product_code(pc) for pc in product_codes]
        normalized = [pc for pc in normalized if pc]
        if not normalized:
            return []
        rows_by_code: Dict[str, Any] = {}
        with get_db_session_ctx() as session:
            rows = session.query(JAVMetadata).filter(JAVMetadata.product_code.in_(normalized)).all()
            for row in rows:
                rows_by_code[row.product_code] = row
        results = []
        for pc in normalized:
            data: Dict[str, Any] = {"product_code": pc}
            row = rows_by_code.get(pc)
            if row:
                data.update(
                    {
                        "title_ko": row.title_ko or "",
                        "title_ja": row.title_ja or "",
                        "actors": _split_csv(row.actors_ko or row.actors_ja or row.actors or ""),
                        "genres": _split_csv(row.genres_ko or row.genres or ""),
                        "maker": row.maker_ko or row.maker_ja or row.maker or "",
                        "release_date": row.release_date or "",
                        "synopsis": row.synopsis_ko or row.synopsis or "",
                    }
                )
            try:
                from javstory.translation.story_grok_module import load_cached_grok_json_flexible

                grok = load_cached_grok_json_flexible(pc)
                grok_pc = normalize_product_code(str((grok or {}).get("product_code") or ""))
                if grok and (not grok_pc or grok_pc != pc):
                    data["story_context_status"] = {
                        "available": False,
                        "reason": "grok_product_code_mismatch",
                        "requested_product_code": pc,
                        "grok_product_code": grok_pc or "",
                    }
                elif grok and grok.get("verification_ok") is not False and not grok.get("code_mismatch"):
                    scene_tags: List[str] = []
                    scene_tones: List[str] = []
                    for scene in grok.get("scenes") or []:
                        if not isinstance(scene, dict):
                            continue
                        for tag in scene.get("key_tags") or []:
                            if isinstance(tag, str) and tag.strip() and tag.strip() not in scene_tags:
                                scene_tags.append(tag.strip())
                        tone = str(scene.get("tone") or "").strip()
                        if tone and tone not in scene_tones:
                            scene_tones.append(tone)
                    data["story_context"] = {
                        "summary": (grok.get("overall_summary") or grok.get("synopsis_short") or "")[:600],
                        "tags": scene_tags[:12],
                        "tones": scene_tones[:8],
                        "scene_count": len(grok.get("scenes") or []),
                        "source": "grok_story_cache",
                        "verified_product_code": grok_pc,
                        "confidence": "medium",
                    }
                    data["story_context_status"] = {
                        "available": bool(data["story_context"]["summary"]),
                        "reason": "grok_verified_product_code_match",
                        "requested_product_code": pc,
                        "grok_product_code": grok_pc,
                    }
            except Exception:
                pass
            results.append(data)
        return results

    def build_chat_context(
        self,
        user_message: str,
        *,
        product_code: str | None = None,
        seed_product_codes: List[str] | None = None,
        recent_recommended_codes: List[str] | None = None,
        compact: bool = False,
        memory_store: Any | None = None,
        fast: bool = False,
    ) -> Dict[str, Any]:
        mentioned = extract_product_codes(user_message)
        explicit_pc = normalize_product_code(product_code)
        if explicit_pc and explicit_pc not in mentioned:
            mentioned.insert(0, explicit_pc)

        intent = _chat_intent(user_message, mentioned)
        pipeline_mode = _chat_pipeline_mode(intent, user_message)
        persona = self.persona_snapshot()
        # cache_only(Ollama 합성 스킵)와 context_snapshot()(DB 쿼리)은 독립적으로 제어한다.
        # skip_context=True 일 때만 생략; cache_only 단독으로는 DB 쿼리를 막지 않는다.
        context = {} if self.skip_context or pipeline_mode == "rating_list" else self.context_snapshot()
        products = self._batch_product_snapshots(mentioned[:3])
        products = [p for p in products if p]
        strong_reactions = _top_strong_reactions(3, memory_store=memory_store)
        strong_seed_codes = _strong_reaction_seed_codes(strong_reactions, 3)
        combined_seed_codes = list(dict.fromkeys(list(seed_product_codes or []) + strong_seed_codes))
        hybrid_query = user_message
        if strong_reactions and not extract_strict_title_terms(user_message):
            hint = _strong_reaction_query_hint(strong_reactions)
            if hint:
                hybrid_query = f"{user_message}\n최근 강한 반응 작품과 자극 축: {hint}"

        exclude_codes = [
            normalize_product_code(code)
            for code in (recent_recommended_codes or [])
            if normalize_product_code(code)
        ]
        if exclude_codes and pipeline_mode != "rating_list":
            hybrid_query = (
                f"{hybrid_query}\n"
                f"최근 챗에서 이미 추천한 품번은 후보에서 제외: {', '.join(exclude_codes[:12])}"
            )

        if pipeline_mode == "rating_list":
            rated_items = fetch_user_rated_products(limit=40 if not compact else 20)
            library_search = _build_user_rating_library_search(user_message, rated_items)
        elif _needs_hybrid_library_search(intent, user_message):
            search_top_k = 8 if pipeline_mode == "light" or compact or fast else 20
            search_weights = _persona_chat_search_weights()
            hybrid_results = fetch_recommendation_pool(
                hybrid_query,
                top_k=search_top_k,
                weights=search_weights,
                exclude_codes=exclude_codes,
                prefer_actor_content=any(
                    hint in str(user_message or "").lower()
                    for hint in ("배우", "좋아하는 배우", "즐겨찾는 배우", "출연")
                ),
                fast=fast,
            )
            library_search = _adapt_hybrid_search_results(
                user_message,
                hybrid_results,
                product_codes=mentioned,
                fallback_seed_codes=combined_seed_codes,
            )
            if pipeline_mode == "full" and intent == "recommendation" and not fast:
                library_search["results"] = _mix_hidden_gem_candidates(
                    list(library_search.get("results") or []),
                    limit=3,
                )
        else:
            library_search = _adapt_hybrid_search_results(
                user_message,
                [],
                product_codes=mentioned,
                fallback_seed_codes=combined_seed_codes,
            )

        persona_summary = str(persona.get("summary") or "").strip()
        sensual_summary = str(persona.get("sensual_summary") or "").strip()
        sensual_focus = sensual_summary or persona_summary
        turn_ons = list(persona.get("turn_ons") or [])
        avoidances = list(persona.get("avoidances") or [])
        affinities = list(persona.get("affinities") or [])
        selected_persona = _selected_persona_fields(
            intent,
            persona_type=str(persona.get("persona_type") or ""),
            persona_summary=persona_summary,
            sensual_summary=sensual_summary,
            sensual_focus=sensual_focus,
            turn_ons=turn_ons,
            avoidances=avoidances,
            affinities=affinities,
            evidence=list(persona.get("evidence") or []),
            source=str(persona.get("source") or ""),
        )
        trigger_summary = _summarize_sensual_triggers(turn_ons, strong_reactions)
        recommendation_reasoning_guide = {
            "must_explain": [
                "추천 후보의 장면 결, 배우/캐릭터 인상, 분위기, 관계성, 플레이 스타일 중 무엇이 맞는지 밝힌다.",
                "sensual_summary와 turn_ons 중 어떤 항목과 맞물리는지 직접 연결한다.",
                "최근 강한 반응 작품이 있으면 그 작품의 자극 축과 이어지는 이유를 설명한다.",
                "가능하면 '이 작품을 보면 특히 어떤 지점에서 크게 자극받을 가능성이 높은지'를 한 문장으로 짚는다.",
            ],
            "strong_reaction_bridge": strong_reactions,
            "example_tone": (
                "이 작품은 네가 강하게 반응했던 긴장감과 들킨 취향의 결을 다시 건드린다. "
                "특히 장면 분위기와 배우의 인상이 turn_ons와 맞물려서 크게 자극받을 가능성이 높다."
            ),
        }

        return {
            "sensual_priority_context": {
                "priority": "highest",
                "sensual_summary": sensual_focus,
                "instruction": (
                    "이 블록을 가장 중요하게 고려해. 추천, 취향 해석, 대화 톤은 모두 "
                    "sensual_summary와 turn_ons를 최우선 근거로 삼는다."
                ),
                "strong_reactions_top3": strong_reactions,
                "trigger_summary": trigger_summary,
                "turn_ons_emphasis": {
                    "items": turn_ons,
                    "instruction": "사용자가 적극적으로 끌리는 자극 축이다. 추천 이유에서 선명하게 연결한다.",
                },
                "avoidances_emphasis": {
                    "items": avoidances,
                    "instruction": "추천에서 피하거나 조심스럽게 다뤄야 하는 요소다. 유사 후보라도 이 요소와 충돌하면 감점한다.",
                },
                "recommendation_reasoning_guide": recommendation_reasoning_guide,
            },
            "sensual_recommendation_focus": {
                "summary": sensual_focus,
                "turn_ons": turn_ons,
                "avoidances": avoidances,
                "strong_reactions_top3": strong_reactions,
                "trigger_summary": trigger_summary,
                "instruction": (
                    "작품 추천에서는 sensual_summary와 turn_ons를 최우선으로 보고, "
                    "최근 강하게 반응한 작품과 장면 결이 비슷한 후보를 앞세운다."
                ),
                "recommendation_reasoning_guide": recommendation_reasoning_guide,
            },
            "persona": selected_persona,
            "taste_context": {
                "top_actors": (context.get("top_actors") or [])[:5],
                "top_genres": (context.get("top_genres") or [])[:8],
                "recent_genres": (context.get("top_genres_recent") or [])[:5],
                "tags": (context.get("tag_counter") or [])[:12],
                "tones": (context.get("tone_counter") or [])[:8],
                "semantic_profile": context.get("semantic_profile") or {},
                "sample_groups": context.get("sample_groups") or {},
            },
            "actress_db_context": _actress_db_chat_context(user_message, context) if pipeline_mode != "rating_list" else {"favorite_profiles": [], "mentioned": []},
            "mentioned_products": products,
            "library_search": library_search,
            "pipeline_mode": pipeline_mode,
            "user_rating_list": library_search.get("results") or [] if pipeline_mode == "rating_list" else [],
        }

    def build_chat_context_json(self, user_message: str, *, product_code: str | None = None) -> str:
        return json.dumps(
            self.build_chat_context(user_message, product_code=product_code),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
