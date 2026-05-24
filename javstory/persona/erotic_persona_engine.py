"""Persona Chat context builder.

The class name follows the product terminology, but the generated chat
context is constrained to a mature, sensual analysis tone rather than
graphic sexual roleplay.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List

from javstory.analytics.persona_card import get_persona_card
from javstory.analytics.persona_context import build_persona_context
from javstory.harvest.database import JAVMetadata, get_db_session_ctx
from javstory.persona.library_search import (
    PersonaLibrarySearch,
    extract_product_codes,
    normalize_product_code,
)


def _split_csv(text: str | None) -> List[str]:
    if not text:
        return []
    return [v.strip() for v in text.replace("、", ",").split(",") if v.strip()]


@dataclass
class EroticPersonaEngine:
    """Builds compact, chat-ready persona context from local JAVSTORY data."""

    cache_only: bool = True
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
            if grok and grok.get("verification_ok") is not False and not grok.get("code_mismatch"):
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
                }
        except Exception:
            pass

        return data

    def build_chat_context(
        self,
        user_message: str,
        *,
        product_code: str | None = None,
        seed_product_codes: List[str] | None = None,
    ) -> Dict[str, Any]:
        mentioned = extract_product_codes(user_message)
        explicit_pc = normalize_product_code(product_code)
        if explicit_pc and explicit_pc not in mentioned:
            mentioned.insert(0, explicit_pc)

        persona = self.persona_snapshot()
        context = self.context_snapshot() if not self.cache_only else {}
        products = [self.product_snapshot(pc) for pc in mentioned[:3]]
        products = [p for p in products if p]
        library_search = PersonaLibrarySearch(limit=self.search_limit).search(
            user_message,
            product_codes=mentioned,
            fallback_seed_codes=seed_product_codes,
        )
        persona_summary = str(persona.get("summary") or "").strip()
        sensual_summary = str(persona.get("sensual_summary") or "").strip()
        sensual_focus = sensual_summary or persona_summary

        return {
            "sensual_recommendation_focus": {
                "summary": sensual_focus,
                "turn_ons": persona.get("turn_ons") or [],
                "instruction": (
                    "작품 추천에서는 sensual_summary와 turn_ons를 최우선으로 보고, "
                    "최근 강하게 반응한 작품과 장면 결이 비슷한 후보를 앞세운다."
                ),
            },
            "persona": {
                "type": persona.get("persona_type", ""),
                "summary": persona_summary,
                "sensual_summary": sensual_summary,
                "sensual_focus": {
                    "priority": "high" if sensual_summary else "fallback",
                    "summary": sensual_focus,
                    "instruction": (
                        "답변에서는 일반 요약보다 이 관능 취향 요약을 우선 근거로 삼고, "
                        "사용자가 어떤 분위기와 관계성에 강하게 반응하는지 선명하게 짚는다."
                    ),
                },
                "turn_ons": persona.get("turn_ons") or [],
                "avoidances": persona.get("avoidances") or [],
                "affinities": persona.get("affinities") or [],
                "evidence": persona.get("evidence") or [],
                "source": persona.get("source", ""),
            },
            "taste_context": {
                "top_actors": (context.get("top_actors") or [])[:5],
                "top_genres": (context.get("top_genres") or [])[:8],
                "recent_genres": (context.get("top_genres_recent") or [])[:5],
                "tags": (context.get("tag_counter") or [])[:12],
                "tones": (context.get("tone_counter") or [])[:8],
                "semantic_profile": context.get("semantic_profile") or {},
                "sample_groups": context.get("sample_groups") or {},
            },
            "mentioned_products": products,
            "library_search": library_search,
        }

    def build_chat_context_json(self, user_message: str, *, product_code: str | None = None) -> str:
        return json.dumps(
            self.build_chat_context(user_message, product_code=product_code),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
