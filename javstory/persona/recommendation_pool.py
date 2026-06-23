"""Unified recommendation candidate pool for Persona Chat and Insight."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Sequence

from javstory.persona.library_search import normalize_product_code
from javstory.search.library_search import HybridLibrarySearch


def _persona_chat_embeddings_enabled() -> bool:
    """Persona chat embedding merge is opt-in only (avoid Ollama/GPU contention with llama.cpp)."""
    raw = (os.environ.get("JAVSTORY_PERSONA_CHAT_SEARCH_EMBEDDING", "") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _embeddings_enabled() -> bool:
    return _persona_chat_embeddings_enabled()


def _use_hybrid_fusion(weights: tuple[float, float, float]) -> bool:
    return len(weights) > 1 and float(weights[1]) > 0


def _search_persona_library(query: str, *, top_k: int, fast: bool = True) -> List[Dict[str, Any]]:
    """SQL-limited persona search — avoids loading the entire library for BM25."""
    from javstory.persona.library_search import PersonaLibrarySearch

    payload = PersonaLibrarySearch(limit=max(1, int(top_k or 8))).search(query, fast=fast)
    out: List[Dict[str, Any]] = []
    for item in list(payload.get("results") or []):
        if not isinstance(item, dict):
            continue
        pc = normalize_product_code(str(item.get("product_code") or ""))
        if not pc:
            continue
        out.append(
            {
                "id": pc,
                "title": str(item.get("title_ko") or item.get("title_ja") or pc),
                "score": float(item.get("score") or 0),
                "source": str(item.get("source") or "persona_sql"),
            }
        )
    return out


def _merge_candidate(
    merged: Dict[str, Dict[str, Any]],
    *,
    product_code: str,
    title: str = "",
    score: float = 0.0,
    source: str,
) -> None:
    pc = normalize_product_code(product_code)
    if not pc:
        return
    existing = merged.get(pc)
    if existing is None:
        merged[pc] = {
            "id": pc,
            "title": title or pc,
            "source": source,
            "score": float(score),
        }
        return
    sources = set(str(existing.get("source") or "").split("+"))
    sources.add(source)
    existing["source"] = "+".join(sorted(s for s in sources if s))
    existing["score"] = max(float(existing.get("score") or 0), float(score))
    if title and not existing.get("title"):
        existing["title"] = title


def _is_actor_recommendation_intent(query: str) -> bool:
    text = (query or "").lower()
    hints = (
        "배우",
        "좋아하는 배우",
        "즐겨찾는 배우",
        "favorite actor",
        "출연",
        "그 배우",
    )
    return any(hint in text for hint in hints)


def fetch_recommendation_pool(
    query: str,
    *,
    top_k: int = 20,
    weights: tuple[float, float, float] | None = None,
    exclude_codes: Sequence[str] | None = None,
    prefer_actor_content: bool = False,
    fast: bool = True,
) -> List[Dict[str, Any]]:
    """Merge hybrid search with insight-style embedding recommendations."""
    exclude = {
        normalize_product_code(code)
        for code in (exclude_codes or [])
        if normalize_product_code(code)
    }
    merged: Dict[str, Dict[str, Any]] = {}

    actor_intent = bool(prefer_actor_content) or _is_actor_recommendation_intent(query)
    if actor_intent and _embeddings_enabled():
        try:
            from javstory.analytics.actor_content_recommender import recommend_favorite_actor_content

            for rec in recommend_favorite_actor_content(min(12, top_k)):
                pc = normalize_product_code(str(rec.get("product_code") or ""))
                if not pc or pc in exclude:
                    continue
                _merge_candidate(
                    merged,
                    product_code=pc,
                    title=str(rec.get("title_ko") or ""),
                    score=float(rec.get("rec_score") or 0.7) + 0.15,
                    source=str(rec.get("source") or "actor_content"),
                )
        except Exception:
            pass

    search_weights = weights or (0.45, 0.0, 0.55)
    if _use_hybrid_fusion(search_weights):
        hybrid_results = HybridLibrarySearch(top_k=top_k, weights=search_weights).search_with_fusion(query)
    else:
        hybrid_results = _search_persona_library(query, top_k=top_k, fast=fast)
    for item in hybrid_results:
        pc = normalize_product_code(str(item.get("id") or ""))
        if not pc or pc in exclude:
            continue
        _merge_candidate(
            merged,
            product_code=pc,
            title=str(item.get("title") or ""),
            score=float(item.get("score") or 0),
            source=str(item.get("source") or "hybrid"),
        )

    if _embeddings_enabled():
        try:
            from javstory.analytics.preference_engine import get_recommendations

            for rec in get_recommendations(min(12, top_k), use_embeddings=True):
                pc = normalize_product_code(str(rec.get("product_code") or ""))
                if not pc or pc in exclude:
                    continue
                _merge_candidate(
                    merged,
                    product_code=pc,
                    title=str(rec.get("title_ko") or ""),
                    score=float(rec.get("rec_score") or 0.5),
                    source=str(rec.get("source") or "insight_rec"),
                )
        except Exception:
            pass

    ranked = sorted(merged.values(), key=lambda item: float(item.get("score") or 0), reverse=True)
    return ranked[:top_k]
