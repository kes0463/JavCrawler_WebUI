"""Unified recommendation candidate pool for Persona Chat and Insight."""

from __future__ import annotations

import hashlib
import os
import time
from typing import Any, Dict, List, Sequence

from javstory.persona.library_search import extract_theme_query_terms, normalize_product_code
from javstory.search.library_search import HybridLibrarySearch

_RRF_K = 60
_SESSION_POOL_CACHE: Dict[str, tuple[float, List[Dict[str, Any]]]] = {}
_SESSION_POOL_TTL_SEC = 900


def build_session_pool_key(
    query: str,
    *,
    exclude_codes: Sequence[str] | None = None,
    seed_codes: Sequence[str] | None = None,
) -> str:
    parts = [
        (query or "").strip().lower(),
        ",".join(sorted(normalize_product_code(c) or "" for c in (exclude_codes or []) if normalize_product_code(c))),
        ",".join(sorted(normalize_product_code(c) or "" for c in (seed_codes or []) if normalize_product_code(c))),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]


def clear_session_pool_cache() -> None:
    _SESSION_POOL_CACHE.clear()


def _persona_chat_embeddings_enabled() -> bool:
    """Hybrid query-embedding fusion — opt-in (Ollama/GPU may contend with llama.cpp)."""
    raw = (os.environ.get("JAVSTORY_PERSONA_CHAT_SEARCH_EMBEDDING", "") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _work_embeddings_enabled() -> bool:
    """Per-work embedding cache on disk (no query-time embed if vectors exist)."""
    try:
        from javstory.library.embeddings.pipeline import embeddings_enabled_from_env

        return bool(embeddings_enabled_from_env())
    except Exception:
        return False


def _use_hybrid_fusion(weights: tuple[float, float, float]) -> bool:
    return len(weights) > 1 and float(weights[1]) > 0


def _env_int(name: str, default: int, *, lo: int, hi: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return max(lo, min(hi, int(raw)))
    except ValueError:
        return default


def _resolve_pool_k(top_k: int, pool_k: int | None) -> int:
    if pool_k is not None and int(pool_k) > 0:
        return max(int(top_k), int(pool_k))
    env_default = _env_int("JAVSTORY_PERSONA_REC_POOL_K", 0, lo=0, hi=200)
    if env_default > 0:
        return max(int(top_k), env_default)
    return max(int(top_k), min(100, int(top_k) * 4))


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


def _channel_ranked_list(
    items: Sequence[Dict[str, Any]],
    *,
    exclude: set[str],
) -> List[tuple[str, float]]:
    ranked: List[tuple[str, float]] = []
    for item in items:
        pc = normalize_product_code(str(item.get("id") or item.get("product_code") or ""))
        if not pc or pc in exclude:
            continue
        ranked.append((pc, float(item.get("score") or 0)))
    ranked.sort(key=lambda it: it[1], reverse=True)
    return ranked


def _rrf_fuse(
    channel_lists: Sequence[Sequence[tuple[str, float]]],
    *,
    k: int = _RRF_K,
    channel_weights: Sequence[float] | None = None,
) -> List[tuple[str, float]]:
    """Reciprocal rank fusion across retrieval channels."""
    scores: Dict[str, float] = {}
    for ch_idx, ranked in enumerate(channel_lists):
        if not ranked:
            continue
        weight = 1.0
        if channel_weights is not None and ch_idx < len(channel_weights):
            weight = float(channel_weights[ch_idx])
        for rank, (pc, _raw) in enumerate(ranked, start=1):
            scores[pc] = scores.get(pc, 0.0) + weight * (1.0 / (float(k) + float(rank)))
    return sorted(scores.items(), key=lambda it: it[1], reverse=True)


def _is_actor_recommendation_intent(query: str) -> bool:
    text = (query or "").lower()
    hints = (
        "배우",
        "좋아하는 배우",
        "즐겨찾는 배우",
        "favorite actor",
        "출연",
        "그 배우",
        "출연작",
        "필모",
    )
    if any(hint in text for hint in hints):
        return True
    try:
        from javstory.persona.actress_query import actress_name_span_candidates, resolve_actress_by_name

        for span in actress_name_span_candidates(query):
            if resolve_actress_by_name(span):
                return True
    except Exception:
        pass
    return False


def _is_similar_work_intent(query: str) -> bool:
    text = (query or "").lower()
    hints = ("비슷", "같은 느낌", "비슷한", "similar", "like this")
    return any(hint in text for hint in hints)


def _taste_recommendation_channel(limit: int, *, exclude: set[str]) -> List[Dict[str, Any]]:
    if not _work_embeddings_enabled():
        return []
    try:
        from javstory.analytics.preference_engine import get_recommendations

        out: List[Dict[str, Any]] = []
        for rec in get_recommendations(min(limit, 24), use_embeddings=True):
            pc = normalize_product_code(str(rec.get("product_code") or ""))
            if not pc or pc in exclude:
                continue
            out.append(
                {
                    "id": pc,
                    "title": str(rec.get("title_ko") or ""),
                    "score": float(rec.get("rec_score") or 0.5),
                    "source": str(rec.get("source") or "taste_embedding"),
                }
            )
        return out
    except Exception:
        return []


def _semantic_profile_channel(
    seed_codes: Sequence[str],
    *,
    limit: int,
    exclude: set[str],
) -> List[Dict[str, Any]]:
    if not _work_embeddings_enabled() or not seed_codes:
        return []
    try:
        from javstory.analytics.persona_context import semantic_unwatched_candidates

        return semantic_unwatched_candidates(
            list(seed_codes),
            exclude_codes=exclude,
            top_k=limit,
        )
    except Exception:
        return []


def _hidden_gems_channel(limit: int, *, exclude: set[str]) -> List[Dict[str, Any]]:
    try:
        from javstory.analytics.library_stats import get_unwatched_gems

        out: List[Dict[str, Any]] = []
        for gem in get_unwatched_gems(max(2, limit)):
            pc = normalize_product_code(str(gem.get("product_code") or ""))
            if not pc or pc in exclude:
                continue
            out.append(
                {
                    "id": pc,
                    "title": str(gem.get("title_ko") or ""),
                    "score": float(gem.get("rec_score") or 0.55),
                    "source": "hidden_gem",
                }
            )
        return out
    except Exception:
        return []


def _actor_content_channel(limit: int, *, exclude: set[str]) -> List[Dict[str, Any]]:
    try:
        from javstory.analytics.actor_content_recommender import recommend_favorite_actor_content

        out: List[Dict[str, Any]] = []
        for rec in recommend_favorite_actor_content(min(12, limit)):
            pc = normalize_product_code(str(rec.get("product_code") or ""))
            if not pc or pc in exclude:
                continue
            out.append(
                {
                    "id": pc,
                    "title": str(rec.get("title_ko") or ""),
                    "score": float(rec.get("rec_score") or 0.7) + 0.15,
                    "source": str(rec.get("source") or "actor_content"),
                }
            )
        return out
    except Exception:
        return []


def _actress_works_channel(
    actress_id: int,
    limit: int,
    *,
    exclude: set[str],
) -> List[Dict[str, Any]]:
    try:
        from javstory.persona.actress_query import actress_work_pool_items

        return actress_work_pool_items(int(actress_id), limit=limit, exclude_codes=exclude)
    except Exception:
        return []


def fetch_recommendation_pool(
    query: str,
    *,
    top_k: int = 20,
    pool_k: int | None = None,
    weights: tuple[float, float, float] | None = None,
    exclude_codes: Sequence[str] | None = None,
    prefer_actor_content: bool = False,
    seed_codes: Sequence[str] | None = None,
    fast: bool = True,
    include_hidden_gems: bool = True,
    session_key: str | None = None,
    use_session_cache: bool = True,
    actress_id: int | None = None,
) -> List[Dict[str, Any]]:
    """Merge multi-channel retrieval with RRF, then return top_k for ranking/LLM."""
    final_k = max(1, min(50, int(top_k or 20)))
    retrieve_k = _resolve_pool_k(final_k, pool_k)

    if session_key and use_session_cache:
        cached = _SESSION_POOL_CACHE.get(session_key)
        if cached and (time.monotonic() - cached[0]) < _SESSION_POOL_TTL_SEC:
            return [dict(item) for item in cached[1][:final_k]]

    exclude = {
        normalize_product_code(code)
        for code in (exclude_codes or [])
        if normalize_product_code(code)
    }
    seeds = [
        normalize_product_code(code)
        for code in (seed_codes or [])
        if normalize_product_code(code)
    ]

    channel_lists: List[List[tuple[str, float]]] = []
    channel_weights: List[float] = []
    title_by_code: Dict[str, str] = {}
    source_by_code: Dict[str, set[str]] = {}

    def _ingest(items: Sequence[Dict[str, Any]], *, weight: float = 1.0) -> None:
        channel_lists.append(_channel_ranked_list(items, exclude=exclude))
        channel_weights.append(float(weight))
        for item in items:
            pc = normalize_product_code(str(item.get("id") or item.get("product_code") or ""))
            if not pc or pc in exclude:
                continue
            title = str(item.get("title") or item.get("title_ko") or "")
            if title:
                title_by_code.setdefault(pc, title)
            src = str(item.get("source") or "channel")
            source_by_code.setdefault(pc, set()).add(src)

    search_weights = weights or (0.45, 0.0, 0.55)
    actress_only = int(actress_id or 0) > 0
    theme_terms = extract_theme_query_terms(query)
    theme_strict = bool(theme_terms) and not actress_only
    if actress_only:
        _ingest(_actress_works_channel(int(actress_id), retrieve_k, exclude=exclude), weight=4.0)
    elif theme_strict:
        theme_query = " ".join(theme_terms)
        _ingest(_search_persona_library(theme_query, top_k=retrieve_k, fast=fast), weight=3.0)
    else:
        if _use_hybrid_fusion(search_weights) and _persona_chat_embeddings_enabled():
            hybrid_results = HybridLibrarySearch(top_k=retrieve_k, weights=search_weights).search_with_fusion(query)
            _ingest(hybrid_results)
        else:
            _ingest(_search_persona_library(query, top_k=retrieve_k, fast=fast))

        _ingest(_taste_recommendation_channel(retrieve_k, exclude=exclude))
        _ingest(_semantic_profile_channel(seeds, limit=retrieve_k, exclude=exclude))

        actor_intent = bool(prefer_actor_content) or _is_actor_recommendation_intent(query)
        if actor_intent:
            _ingest(_actor_content_channel(retrieve_k, exclude=exclude), weight=2.0)

        if include_hidden_gems and not fast:
            _ingest(_hidden_gems_channel(max(3, retrieve_k // 10), exclude=exclude))

        # Legacy path: chat-embedding flag also merges insight rec (same as taste channel)
        if _persona_chat_embeddings_enabled() and not _work_embeddings_enabled():
            try:
                from javstory.analytics.preference_engine import get_recommendations

                legacy: List[Dict[str, Any]] = []
                for rec in get_recommendations(min(12, retrieve_k), use_embeddings=True):
                    pc = normalize_product_code(str(rec.get("product_code") or ""))
                    if not pc or pc in exclude:
                        continue
                    legacy.append(
                        {
                            "id": pc,
                            "title": str(rec.get("title_ko") or ""),
                            "score": float(rec.get("rec_score") or 0.5),
                            "source": "insight_rec",
                        }
                    )
                _ingest(legacy)
            except Exception:
                pass

    fused = _rrf_fuse(channel_lists, channel_weights=channel_weights)
    if not fused:
        return []

    merged: Dict[str, Dict[str, Any]] = {}
    for pc, rrf_score in fused[:retrieve_k]:
        sources = "+".join(sorted(source_by_code.get(pc) or {"fused"}))
        _merge_candidate(
            merged,
            product_code=pc,
            title=title_by_code.get(pc, ""),
            score=rrf_score,
            source=sources,
        )

    ranked = sorted(merged.values(), key=lambda item: float(item.get("score") or 0), reverse=True)
    result = ranked[:final_k]

    if session_key and use_session_cache:
        _SESSION_POOL_CACHE[session_key] = (time.monotonic(), [dict(item) for item in ranked[:retrieve_k]])

    try:
        from javstory.library.embeddings.priority_queue import (
            collect_recommendation_embedding_priorities,
            ensure_priority_embeddings_async,
        )

        warmup_codes = collect_recommendation_embedding_priorities(
            extra_codes=[*seeds, *(str(item.get("id") or "") for item in result[:12])],
            limit=24,
        )
        ensure_priority_embeddings_async(warmup_codes, max_batch=6)
    except Exception:
        pass

    return result
