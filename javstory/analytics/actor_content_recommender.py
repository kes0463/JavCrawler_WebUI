"""Favorite-actor × content-taste two-stage recommender."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from javstory.analytics.preference_engine import (
    _collect_embedding_seed_histories,
    _split_positive_negative_seeds,
)
from javstory.harvest.database import (
    Actress,
    ActressWork,
    JAVMetadata,
    WatchHistory,
    get_db_session_ctx,
)

_MAX_SCORED_ACTOR_CANDIDATES = 200


def _actor_display_name(actress: Actress) -> str:
    return (
        str(actress.name_ko or actress.korean or actress.name_ja or actress.japanese or "")
        .strip()
    )


def _normalize_actor_pref(score: float, *, max_score: float) -> float:
    if max_score <= 0:
        return 0.0
    return max(0.0, min(1.0, float(score) / max_score))


def _collect_favorite_actors(limit: int = 12) -> List[Dict[str, Any]]:
    """Merge is_favorite actresses with top UserPreference(actor) entries."""
    from javstory.analytics.preference_engine import get_top_actors

    merged: Dict[str, Dict[str, Any]] = {}

    with get_db_session_ctx() as session:
        fav_rows = (
            session.query(Actress)
            .filter(Actress.is_favorite == True)  # noqa: E712
            .order_by(Actress.favorite_intensity.desc(), Actress.watch_count.desc())
            .limit(limit)
            .all()
        )
        for row in fav_rows:
            name = _actor_display_name(row)
            if not name:
                continue
            merged[name] = {
                "name": name,
                "actress_id": int(row.id),
                "actor_pref": float(row.favorite_intensity or row.user_score or 5.0),
                "favorite_intensity": float(row.favorite_intensity or 0.0),
                "is_favorite": True,
            }

    for actor in get_top_actors(limit, use_recent=True):
        name = str(actor.get("name") or "").strip()
        if not name:
            continue
        pref = float(actor.get("recent_score") or actor.get("score") or 0)
        existing = merged.get(name)
        if existing:
            existing["actor_pref"] = max(existing["actor_pref"], pref)
            if not existing.get("favorite_intensity"):
                existing["favorite_intensity"] = pref / 10.0
        else:
            merged[name] = {
                "name": name,
                "actress_id": None,
                "actor_pref": pref,
                "favorite_intensity": 0.0,
                "is_favorite": False,
            }

    ranked = sorted(merged.values(), key=lambda item: float(item.get("actor_pref") or 0), reverse=True)
    return ranked[:limit]


def _resolve_actress_ids(actors: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """Fill missing actress_id values by name lookup."""
    out: Dict[int, Dict[str, Any]] = {}
    unresolved: List[Dict[str, Any]] = []

    for actor in actors:
        aid = actor.get("actress_id")
        if aid:
            out[int(aid)] = actor
        else:
            unresolved.append(actor)

    if not unresolved:
        return out

    names = [str(a.get("name") or "").strip() for a in unresolved if a.get("name")]
    if not names:
        return out

    with get_db_session_ctx() as session:
        rows = (
            session.query(Actress)
            .filter(
                (Actress.name_ko.in_(names))
                | (Actress.korean.in_(names))
                | (Actress.japanese.in_(names))
                | (Actress.name_ja.in_(names))
            )
            .all()
        )
        by_name: Dict[str, Actress] = {}
        for row in rows:
            for key in (_actor_display_name(row), row.korean, row.japanese, row.name_ja):
                if key:
                    by_name[str(key).strip()] = row

        for actor in unresolved:
            name = str(actor.get("name") or "").strip()
            row = by_name.get(name)
            if not row:
                continue
            actor["actress_id"] = int(row.id)
            if actor.get("is_favorite"):
                actor["favorite_intensity"] = float(row.favorite_intensity or actor.get("favorite_intensity") or 0)
            out[int(row.id)] = actor

    return out


def _collect_unwatched_actor_works(
    actress_ids: List[int],
    watched_codes: set[str],
) -> Dict[str, List[Dict[str, Any]]]:
    """Map product_code -> list of contributing favorite actors."""
    if not actress_ids:
        return {}

    candidates: Dict[str, List[Dict[str, Any]]] = {}
    with get_db_session_ctx() as session:
        rows = (
            session.query(ActressWork.actress_id, ActressWork.product_code)
            .filter(ActressWork.actress_id.in_(actress_ids))
            .all()
        )
        for actress_id, product_code in rows:
            pc = str(product_code or "").strip().upper()
            if not pc or pc in watched_codes:
                continue
            candidates.setdefault(pc, []).append({"actress_id": int(actress_id)})

    return candidates


def _trim_actor_candidates(
    candidate_map: Dict[str, List[Dict[str, Any]]],
    actor_by_id: Dict[int, Dict[str, Any]],
    *,
    max_candidates: int = _MAX_SCORED_ACTOR_CANDIDATES,
) -> Dict[str, List[Dict[str, Any]]]:
    """Cap unwatched actor works before embedding scoring."""
    if len(candidate_map) <= max_candidates:
        return candidate_map

    ranked: List[tuple[str, float, List[Dict[str, Any]]]] = []
    for pc, actor_refs in candidate_map.items():
        actor_ids = {int(ref["actress_id"]) for ref in actor_refs}
        best_actor = max(
            (actor_by_id[aid] for aid in actor_ids if aid in actor_by_id),
            key=lambda a: float(a.get("actor_pref") or 0),
            default=None,
        )
        if not best_actor:
            continue
        ranked.append((pc, float(best_actor.get("actor_pref") or 0), actor_refs))

    ranked.sort(key=lambda item: item[1], reverse=True)
    return {pc: refs for pc, _, refs in ranked[:max_candidates]}


def _build_content_profile_vector(model: str):
    from javstory.library.embeddings.similarity import build_weighted_user_profile_vector

    histories = _collect_embedding_seed_histories(limit=30)
    positive_codes, positive_weights, _, _ = _split_positive_negative_seeds(histories)
    return build_weighted_user_profile_vector(
        model=model,
        seed_codes=positive_codes,
        seed_weights=positive_weights,
    )


def recommend_favorite_actor_content(
    limit: int = 10,
    *,
    model: str | None = None,
) -> List[Dict[str, Any]]:
    """
    Recommend unwatched works from favorite actors, re-ranked by content taste vector.

    score = 0.6 * content_sim + 0.3 * actor_pref_norm + 0.1 * favorite_intensity_norm
    """
    limit = max(1, min(20, int(limit or 10)))

    from javstory.library.embeddings.pipeline import embeddings_ollama_model_from_env
    from javstory.library.embeddings.similarity import (
        cosine_similarity,
        vector_for_product_code,
    )

    model = model or embeddings_ollama_model_from_env()
    actors = _collect_favorite_actors(limit=12)
    actor_by_id = _resolve_actress_ids(actors)
    if not actor_by_id:
        return []

    max_actor_pref = max(float(a.get("actor_pref") or 0) for a in actor_by_id.values()) or 1.0
    max_fav_intensity = max(float(a.get("favorite_intensity") or 0) for a in actor_by_id.values()) or 1.0

    with get_db_session_ctx() as session:
        watched_codes = {
            str(r.product_code or "").strip().upper()
            for r in session.query(WatchHistory.product_code).all()
            if r.product_code
        }

    candidate_map = _collect_unwatched_actor_works(list(actor_by_id.keys()), watched_codes)
    if not candidate_map:
        return []

    candidate_map = _trim_actor_candidates(candidate_map, actor_by_id)
    profile_vec = _build_content_profile_vector(model)
    scored: List[Tuple[str, float, List[str], int]] = []

    for pc, actor_refs in candidate_map.items():
        actor_ids = {int(ref["actress_id"]) for ref in actor_refs}
        best_actor = max(
            (actor_by_id[aid] for aid in actor_ids if aid in actor_by_id),
            key=lambda a: float(a.get("actor_pref") or 0),
            default=None,
        )
        if not best_actor:
            continue

        actor_pref_norm = _normalize_actor_pref(float(best_actor.get("actor_pref") or 0), max_score=max_actor_pref)
        fav_norm = _normalize_actor_pref(
            float(best_actor.get("favorite_intensity") or 0),
            max_score=max_fav_intensity,
        )

        content_sim = 0.5
        if profile_vec:
            work_vec = vector_for_product_code(pc, model=model)
            if work_vec:
                sim = cosine_similarity(profile_vec, work_vec)
                if sim > float("-inf"):
                    content_sim = max(0.0, min(1.0, (float(sim) + 1.0) / 2.0))

        score = 0.6 * content_sim + 0.3 * actor_pref_norm + 0.1 * fav_norm
        reasons = [f"좋아하는 배우 {best_actor.get('name')}"]
        if content_sim >= 0.55:
            reasons.append("선호 장르/장면 결 유사")

        scored.append((pc, score, reasons, int(best_actor.get("actress_id") or 0)))

    if not scored:
        return []

    scored.sort(key=lambda item: item[1], reverse=True)
    top = scored[:limit]
    codes = [pc for pc, _, _, _ in top]

    meta_by_code: Dict[str, JAVMetadata] = {}
    with get_db_session_ctx() as session:
        for row in session.query(JAVMetadata).filter(JAVMetadata.product_code.in_(codes)).all():
            meta_by_code[row.product_code] = row

    out: List[Dict[str, Any]] = []
    for pc, score, reasons, actress_id in top:
        row = meta_by_code.get(pc)
        if not row:
            continue
        actor = actor_by_id.get(actress_id) or {}
        out.append({
            "product_code": pc,
            "title_ko": row.title_ko or "",
            "cover_path": row.cover_image_local_path or "",
            "actors_ko": row.actors_ko or "",
            "release_date": row.release_date or "",
            "rec_score": round(float(score), 4),
            "source": "actor_content",
            "match_reasons": reasons,
            "actor_name": actor.get("name") or "",
        })
    return out
