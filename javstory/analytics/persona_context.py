"""페르소나 v3 — Grok/canonical/자막 샘플링·집계 컨텍스트."""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from javstory.analytics.library_stats import compute_taste_vector, get_library_stats, get_monthly_genre_trend
from javstory.analytics.preference_engine import compute_recent_trend, get_top_actors, get_top_genres
from javstory.harvest.database import JAVMetadata, WatchHistory, get_db_session_ctx


def persona_deep_enabled() -> bool:
    raw = (os.environ.get("JAVSTORY_PERSONA_DEEP_ENABLED", "1") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def persona_sample_size() -> int:
    try:
        n = int(os.environ.get("JAVSTORY_PERSONA_SAMPLE_SIZE", "8") or "8")
    except ValueError:
        n = 8
    return max(4, min(12, n))


def _completion_ratio(h: WatchHistory) -> float:
    total = int(h.total_duration or 0)
    watched = int(h.watch_duration or 0)
    if total <= 0:
        return 1.0 if h.is_completed else 0.0
    return max(0.0, min(1.0, watched / float(total)))


def _sample_product_groups(max_products: int) -> Dict[str, List[str]]:
    """긍정/최근/장기/부정 신호를 분리해 페르소나 근거 샘플을 뽑는다."""
    groups: Dict[str, List[str]] = {
        "positive": [],
        "recent": [],
        "long_term": [],
        "negative": [],
        "codes": [],
    }
    seen: set[str] = set()

    def add(group: str, product_code: str | None) -> None:
        pc = str(product_code or "").strip().upper()
        if not pc:
            return
        if pc not in groups[group]:
            groups[group].append(pc)
        if pc not in seen:
            seen.add(pc)
            groups["codes"].append(pc)

    with get_db_session_ctx() as session:
        preferred = (
            session.query(WatchHistory)
            .filter(
                (WatchHistory.liked == True)  # noqa: E712
                | (WatchHistory.is_completed == True)  # noqa: E712
                | (WatchHistory.rating >= 4)
            )
            .order_by(WatchHistory.updated_at.desc())
            .limit(max_products)
            .all()
        )
        for h in preferred:
            add("positive", h.product_code)

        recent = (
            session.query(WatchHistory)
            .order_by(WatchHistory.updated_at.desc())
            .limit(max_products)
            .all()
        )
        for h in recent:
            add("recent", h.product_code)

        long_term = (
            session.query(WatchHistory)
            .filter(
                (WatchHistory.liked == True)  # noqa: E712
                | (WatchHistory.is_completed == True)  # noqa: E712
                | (WatchHistory.rating >= 4)
            )
            .order_by(WatchHistory.updated_at.asc())
            .limit(max(2, max_products // 2))
            .all()
        )
        for h in long_term:
            add("long_term", h.product_code)

        candidates = (
            session.query(WatchHistory)
            .order_by(WatchHistory.updated_at.desc())
            .limit(max_products * 6)
            .all()
        )
        for h in candidates:
            rating = int(h.rating or 0)
            low_completion = (
                int(h.watch_duration or 0) >= 60
                and not bool(h.is_completed)
                and _completion_ratio(h) <= 0.35
            )
            if (0 < rating <= 2) or low_completion:
                add("negative", h.product_code)
            if len(groups["negative"]) >= max(2, max_products // 3):
                break

    groups["codes"] = groups["codes"][: max_products * 2]
    return groups


def _watch_meta_by_codes(codes: List[str]) -> Dict[str, Dict[str, Any]]:
    if not codes:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    with get_db_session_ctx() as session:
        for h in session.query(WatchHistory).filter(WatchHistory.product_code.in_(codes)).all():
            pc = str(h.product_code or "").strip().upper()
            if not pc:
                continue
            out[pc] = {
                "watch_duration": int(h.watch_duration or 0),
                "total_duration": int(h.total_duration or 0),
                "is_completed": bool(h.is_completed),
                "liked": bool(h.liked),
                "rating": int(h.rating or 0),
                "completion_ratio": round(_completion_ratio(h), 3),
                "updated_at": h.updated_at.isoformat() if h.updated_at else "",
            }
        for row in session.query(JAVMetadata).filter(JAVMetadata.product_code.in_(codes)).all():
            pc = str(row.product_code or "").strip().upper()
            if not pc:
                continue
            out.setdefault(pc, {})
            out[pc]["folder_path"] = (row.folder_path or "").strip()
            out[pc]["title_ko"] = row.title_ko or ""
            out[pc]["actors_ko"] = row.actors_ko or ""
    return out


def _extract_grok_product(pc: str, grok: Dict[str, Any]) -> Dict[str, Any]:
    tags: List[str] = []
    tones: List[str] = []
    for s in grok.get("scenes") or []:
        if not isinstance(s, dict):
            continue
        for t in s.get("key_tags") or []:
            if isinstance(t, str) and t.strip():
                tags.append(t.strip())
        tone = (s.get("tone") or "").strip()
        if tone:
            tones.append(tone)
    summary = (grok.get("overall_summary") or grok.get("synopsis_short") or "").strip()
    return {
        "product_code": pc,
        "source": "grok",
        "overall_summary": summary[:400] if summary else "",
        "tags": tags,
        "tones": tones,
        "scene_count": len(grok.get("scenes") or []),
    }


def _extract_canonical_product(pc: str, state) -> Dict[str, Any]:
    tags: List[str] = []
    tones: List[str] = []
    labels: List[str] = []
    for s in state.scenes or []:
        for t in s.key_tags or []:
            if t and str(t).strip():
                tags.append(str(t).strip())
        if s.tone and str(s.tone).strip():
            tones.append(str(s.tone).strip())
        if s.scene_label and str(s.scene_label).strip():
            labels.append(str(s.scene_label).strip())
    return {
        "product_code": pc,
        "source": "canonical",
        "scene_count": len(state.scenes or []),
        "tags": tags,
        "tones": tones,
        "labels": labels[:5],
    }


def _subtitle_metrics_for_paths(paths: List[Path], duration_sec: int) -> Optional[Dict[str, Any]]:
    if not paths:
        return None
    try:
        import pysrt
    except ImportError:
        return None

    cue_count = 0
    char_count = 0
    picked: List[str] = []
    for p in paths:
        if not p.is_file():
            continue
        try:
            subs = pysrt.open(str(p), encoding="utf-8")
            cue_count += len(subs)
            for sub in subs:
                char_count += len((sub.text or "").strip())
            picked.append(str(p))
            if cue_count > 0:
                break
        except Exception:
            continue
    if cue_count <= 0:
        return None
    dur_min = max(1.0, duration_sec / 60.0) if duration_sec > 0 else 90.0
    cues_per_min = round(cue_count / dur_min, 2)
    density = "높음" if cues_per_min >= 12 else ("보통" if cues_per_min >= 6 else "낮음")
    return {
        "cue_count": cue_count,
        "char_count": char_count,
        "cues_per_min": cues_per_min,
        "dialogue_density": density,
        "paths": picked[:2],
    }


def _find_srt_paths(pc: str, folder_path: str, meta: Dict[str, Any]) -> List[Path]:
    paths: List[Path] = []
    try:
        from javstory.library.canonical.store import load_library_state
        from javstory.library.paths import library_state_path
        from javstory.library.embeddings.document_builder import _find_subtitle_candidate_paths

        state_path = library_state_path(pc)
        if state_path.is_file():
            state = load_library_state(state_path)
            paths = _find_subtitle_candidate_paths(state)
    except Exception:
        paths = []

    if not paths and folder_path:
        base = Path(folder_path)
        if base.is_dir():
            for pat in ("*.ko.srt", "*.ja.srt", "*.srt"):
                try:
                    for p in sorted(base.glob(pat)):
                        if p.is_file():
                            paths.append(p)
                            return paths
                except OSError:
                    continue
    return paths


def _is_excluded_tag(value: str, excluded: set[str]) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    compact = text.replace(" ", "").lower()
    return any(
        text == ex or ex in text or compact == ex.replace(" ", "").lower()
        for ex in excluded
    )


def _filtered_counter(counter: Counter, excluded: set[str], limit: int) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for name, count in counter.most_common(limit * 2):
        if _is_excluded_tag(name, excluded):
            continue
        items.append({"name": name, "count": count})
        if len(items) >= limit:
            break
    return items


def _sample_roles_by_code(groups: Dict[str, List[str]]) -> Dict[str, List[str]]:
    roles: Dict[str, List[str]] = {}
    for group in ("positive", "recent", "long_term", "negative"):
        for pc in groups.get(group) or []:
            roles.setdefault(pc, []).append(group)
    return roles


def _build_semantic_profile(seed_codes: List[str], exclude_codes: set[str]) -> Dict[str, Any]:
    try:
        from javstory.library.embeddings.pipeline import (
            embeddings_enabled_from_env,
            embeddings_ollama_model_from_env,
        )
        from javstory.library.embeddings.similarity import (
            build_user_profile_vector,
            rank_unwatched_by_vector,
        )
    except Exception:
        return {}

    if not embeddings_enabled_from_env():
        return {}

    model = embeddings_ollama_model_from_env()
    profile = build_user_profile_vector(model=model, seed_codes=seed_codes[:30])
    if not profile:
        return {"enabled": True, "model": model, "seed_count": len(seed_codes), "nearest_unwatched": []}

    nearest = []
    for item in rank_unwatched_by_vector(profile, model=model, exclude_codes=exclude_codes, top_k=5):
        nearest.append({
            "product_code": item.product_code,
            "score": round(float(item.score), 4),
            "reasons": list(item.match_reasons or []),
        })
    return {
        "enabled": True,
        "model": model,
        "seed_count": len(seed_codes),
        "nearest_unwatched": nearest,
    }


def _build_drift_hint(monthly: List[Dict[str, Any]], recent_genres: List[Dict[str, Any]]) -> str:
    if not monthly and not recent_genres:
        return ""
    old_top: List[str] = []
    if len(monthly) >= 2:
        genres = monthly[-1].get("genres") or []
        old_top = [g.get("name", "") for g in genres[:2] if g.get("name")]
    recent_top = [g.get("name", "") for g in (recent_genres or [])[:2] if g.get("name")]
    if not recent_top:
        return ""
    if old_top and recent_top[0] and recent_top[0] not in old_top:
        return f"최근 취향은 '{recent_top[0]}' 장르 쪽으로 이동하는 경향이 있습니다."
    if recent_top:
        return f"최근 자주 보는 장르: {', '.join(recent_top)}."
    return ""


def build_persona_context(*, max_products: int | None = None) -> Dict[str, Any]:
    """
    페르소나 합성용 구조화 컨텍스트.
    """
    n = int(max_products or persona_sample_size())
    from javstory.config.app_config import similarity_excluded_genres_from_env

    excluded = similarity_excluded_genres_from_env()

    stats = get_library_stats()
    taste = compute_taste_vector()
    monthly = get_monthly_genre_trend(3)
    recent = compute_recent_trend(30, excluded_genres=excluded)
    drift_hint = _build_drift_hint(monthly, recent.get("genres") or [])

    ctx: Dict[str, Any] = {
        "stats": stats,
        "taste_axes": taste.get("axes") or [],
        "top_actors": get_top_actors(5),
        "top_genres": get_top_genres(8, excluded=excluded),
        "top_actors_recent": get_top_actors(5, use_recent=True),
        "top_genres_recent": get_top_genres(5, use_recent=True, excluded=excluded),
        "monthly_genres": monthly,
        "drift_hint": drift_hint,
        "samples": [],
        "sample_codes": [],
        "sample_groups": {},
        "excluded_genres": sorted(excluded),
        "semantic_profile": {},
        "coverage": {"grok": 0, "canonical": 0, "subtitle": 0},
        "tag_counter": [],
        "tone_counter": [],
        "subtitle_profile": {},
    }

    if not persona_deep_enabled():
        return ctx

    from javstory.translation.story_grok_module import load_cached_grok_json_flexible

    sample_groups = _sample_product_groups(n)
    codes = sample_groups.get("codes") or []
    ctx["sample_codes"] = codes
    roles_by_code = _sample_roles_by_code(sample_groups)
    ctx["sample_groups"] = {
        key: value
        for key, value in sample_groups.items()
        if key in ("positive", "recent", "long_term", "negative")
    }
    positive_seed_codes = []
    for key in ("positive", "long_term", "recent"):
        for pc in sample_groups.get(key) or []:
            if pc not in positive_seed_codes and pc not in set(sample_groups.get("negative") or []):
                positive_seed_codes.append(pc)
    ctx["semantic_profile"] = _build_semantic_profile(positive_seed_codes, set(codes))

    meta_by_code = _watch_meta_by_codes(codes)
    tag_counter: Counter = Counter()
    tone_counter: Counter = Counter()
    cues_per_min_list: List[float] = []
    products: List[Dict[str, Any]] = []

    for pc in codes:
        entry: Dict[str, Any] = {"product_code": pc, "sample_roles": roles_by_code.get(pc, [])}
        meta = meta_by_code.get(pc, {})
        folder_path = meta.get("folder_path") or ""
        if meta:
            entry["watch"] = {
                "completion_ratio": meta.get("completion_ratio", 0),
                "is_completed": bool(meta.get("is_completed")),
                "liked": bool(meta.get("liked")),
                "rating": int(meta.get("rating") or 0),
            }

        grok = load_cached_grok_json_flexible(pc)
        if grok and grok.get("verification_ok") is not False and not grok.get("code_mismatch"):
            g = _extract_grok_product(pc, grok)
            entry["grok"] = g
            ctx["coverage"]["grok"] += 1
            for t in g.get("tags") or []:
                if not _is_excluded_tag(t, excluded):
                    tag_counter[t] += 1
            for t in g.get("tones") or []:
                tone_counter[t] += 1

        try:
            from javstory.library.paths import library_state_path
            from javstory.library.canonical.store import load_library_state

            sp = library_state_path(pc)
            if sp.is_file():
                state = load_library_state(sp)
                c = _extract_canonical_product(pc, state)
                entry["canonical"] = c
                ctx["coverage"]["canonical"] += 1
                for t in c.get("tags") or []:
                    if not _is_excluded_tag(t, excluded):
                        tag_counter[t] += 1
                for t in c.get("tones") or []:
                    tone_counter[t] += 1
        except Exception:
            pass

        dur = int(meta.get("total_duration") or meta.get("watch_duration") or 0)
        srt_paths = _find_srt_paths(pc, folder_path, meta)
        sm = _subtitle_metrics_for_paths(srt_paths, dur)
        if sm:
            entry["subtitle"] = sm
            ctx["coverage"]["subtitle"] += 1
            cues_per_min_list.append(float(sm.get("cues_per_min") or 0))

        if len(entry) > 1:
            products.append(entry)

    ctx["samples"] = products
    ctx["tag_counter"] = _filtered_counter(tag_counter, excluded, 15)
    ctx["tone_counter"] = [{"name": k, "count": v} for k, v in tone_counter.most_common(8)]

    if cues_per_min_list:
        avg = sum(cues_per_min_list) / len(cues_per_min_list)
        density = "높음" if avg >= 12 else ("보통" if avg >= 6 else "낮음")
        ctx["subtitle_profile"] = {
            "avg_cues_per_min": round(avg, 2),
            "dialogue_density": density,
            "sample_count": len(cues_per_min_list),
        }

    return ctx
