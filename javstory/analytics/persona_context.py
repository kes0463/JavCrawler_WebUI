"""페르소나 v3 — Grok/canonical/자막 샘플링·집계 컨텍스트."""

from __future__ import annotations

import hashlib
import json
import os
import time as _time_module
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from javstory.analytics.library_stats import compute_taste_vector, get_library_stats, get_monthly_genre_trend
from javstory.analytics.preference_engine import compute_recent_trend, get_top_actors, get_top_genres
from javstory.harvest.database import JAVMetadata, WatchHistory, get_db_session_ctx


def _env_int(name: str, default: int, min_value: int, max_value: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        value = default
    return max(min_value, min(max_value, value))


def persona_deep_enabled() -> bool:
    raw = (os.environ.get("JAVSTORY_PERSONA_DEEP_ENABLED", "1") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def persona_sample_size() -> int:
    try:
        n = int(os.environ.get("JAVSTORY_PERSONA_SAMPLE_SIZE", "8") or "8")
    except ValueError:
        n = 8
    return max(4, min(12, n))


def persona_recent_days() -> int:
    return _env_int("JAVSTORY_PERSONA_RECENT_DAYS", 30, 3, 90)


def persona_short_recent_days() -> int:
    return min(persona_recent_days(), _env_int("JAVSTORY_PERSONA_SHORT_RECENT_DAYS", 7, 1, 30))


def persona_context_budget() -> Dict[str, int]:
    return {
        "grok_summary_chars": _env_int("JAVSTORY_PERSONA_GROK_SUMMARY_CHARS", 400, 80, 1000),
        "per_product_tag_limit": _env_int("JAVSTORY_PERSONA_PER_PRODUCT_TAG_LIMIT", 16, 4, 40),
        "tag_counter_limit": _env_int("JAVSTORY_PERSONA_TAG_COUNTER_LIMIT", 15, 4, 40),
        "tone_counter_limit": _env_int("JAVSTORY_PERSONA_TONE_COUNTER_LIMIT", 8, 2, 24),
        "semantic_seed_limit": _env_int("JAVSTORY_PERSONA_SEMANTIC_SEED_LIMIT", 30, 4, 80),
        "semantic_top_k": _env_int("JAVSTORY_PERSONA_SEMANTIC_TOP_K", 5, 0, 20),
    }


def persona_prompt_budget() -> Dict[str, int]:
    return {
        "taste_axes": _env_int("JAVSTORY_PERSONA_PROMPT_TASTE_AXES", 6, 1, 12),
        "top_actors": _env_int("JAVSTORY_PERSONA_PROMPT_TOP_ACTORS", 5, 1, 12),
        "top_genres": _env_int("JAVSTORY_PERSONA_PROMPT_TOP_GENRES", 8, 1, 16),
        "recent_genres": _env_int("JAVSTORY_PERSONA_PROMPT_RECENT_GENRES", 5, 1, 12),
        "tag_counter": _env_int("JAVSTORY_PERSONA_PROMPT_TAG_COUNTER", 12, 2, 30),
        "tone_counter": _env_int("JAVSTORY_PERSONA_PROMPT_TONE_COUNTER", 6, 1, 20),
        "samples": _env_int("JAVSTORY_PERSONA_PROMPT_SAMPLES", 10, 1, 20),
        "grok_summary_chars": _env_int("JAVSTORY_PERSONA_PROMPT_GROK_SUMMARY_CHARS", 200, 80, 800),
        "sample_tags": _env_int("JAVSTORY_PERSONA_PROMPT_SAMPLE_TAGS", 6, 1, 16),
    }


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


def _extract_grok_product(
    pc: str,
    grok: Dict[str, Any],
    *,
    summary_chars: int = 400,
    item_limit: int = 16,
) -> Dict[str, Any]:
    tags: List[str] = []
    tones: List[str] = []
    for s in grok.get("scenes") or []:
        if not isinstance(s, dict):
            continue
        for t in s.get("key_tags") or []:
            if isinstance(t, str) and t.strip() and len(tags) < item_limit:
                tags.append(t.strip())
        tone = (s.get("tone") or "").strip()
        if tone and len(tones) < item_limit:
            tones.append(tone)
    summary = (grok.get("overall_summary") or grok.get("synopsis_short") or "").strip()
    return {
        "product_code": pc,
        "source": "grok",
        "overall_summary": summary[:summary_chars] if summary else "",
        "tags": tags,
        "tones": tones,
        "scene_count": len(grok.get("scenes") or []),
    }


def _extract_canonical_product(pc: str, state, *, item_limit: int = 16) -> Dict[str, Any]:
    tags: List[str] = []
    tones: List[str] = []
    labels: List[str] = []
    for s in state.scenes or []:
        for t in s.key_tags or []:
            if t and str(t).strip() and len(tags) < item_limit:
                tags.append(str(t).strip())
        if s.tone and str(s.tone).strip() and len(tones) < item_limit:
            tones.append(str(s.tone).strip())
        if s.scene_label and str(s.scene_label).strip() and len(labels) < 5:
            labels.append(str(s.scene_label).strip())
    return {
        "product_code": pc,
        "source": "canonical",
        "scene_count": len(state.scenes or []),
        "tags": tags,
        "tones": tones,
        "labels": labels,
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


_SEMANTIC_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "cache" / "semantic_profile_cache.json"
_SEMANTIC_CACHE_TTL = 6 * 3600  # 6시간


def _semantic_cache_key(seed_codes: List[str], model: str) -> str:
    raw = ",".join(sorted(seed_codes)) + "|" + model
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def _load_semantic_cache(key: str) -> Optional[Dict[str, Any]]:
    try:
        if not _SEMANTIC_CACHE_PATH.is_file():
            return None
        data = json.loads(_SEMANTIC_CACHE_PATH.read_text(encoding="utf-8"))
        if data.get("key") != key:
            return None
        if _time_module.time() - float(data.get("ts", 0)) > _SEMANTIC_CACHE_TTL:
            return None
        return data.get("profile")
    except Exception:
        return None


def _save_semantic_cache(key: str, profile: Dict[str, Any]) -> None:
    try:
        _SEMANTIC_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SEMANTIC_CACHE_PATH.write_text(
            json.dumps({"key": key, "ts": _time_module.time(), "profile": profile}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def _build_semantic_profile(seed_codes: List[str], exclude_codes: set[str]) -> Dict[str, Any]:
    budget = persona_context_budget()
    seed_limit = budget["semantic_seed_limit"]
    top_k = budget["semantic_top_k"]
    if top_k <= 0:
        return {}
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

    # 6시간 디스크 캐시 — 미시청 전체 임베딩 로드(수만 파일)가 병목이므로 재사용
    cache_key = _semantic_cache_key(seed_codes[:seed_limit], model)
    cached = _load_semantic_cache(cache_key)
    if cached is not None:
        print("[PersonaCtx] semantic_profile: 캐시 hit")
        return cached

    profile = build_user_profile_vector(model=model, seed_codes=seed_codes[:seed_limit])
    if not profile:
        result: Dict[str, Any] = {"enabled": True, "model": model, "seed_count": len(seed_codes), "nearest_unwatched": []}
        _save_semantic_cache(cache_key, result)
        return result

    nearest = []
    for item in rank_unwatched_by_vector(profile, model=model, exclude_codes=exclude_codes, top_k=top_k):
        nearest.append({
            "product_code": item.product_code,
            "score": round(float(item.score), 4),
            "reasons": list(item.match_reasons or []),
        })
    result = {
        "enabled": True,
        "model": model,
        "seed_count": min(len(seed_codes), seed_limit),
        "nearest_unwatched": nearest,
    }
    _save_semantic_cache(cache_key, result)
    return result


def _build_drift_hint(
    monthly: List[Dict[str, Any]],
    short_recent_genres: List[Dict[str, Any]],
    recent_genres: List[Dict[str, Any]],
    *,
    short_days: int,
    recent_days: int,
) -> str:
    if not monthly and not short_recent_genres and not recent_genres:
        return ""
    old_top: List[str] = []
    if len(monthly) >= 2:
        genres = monthly[-1].get("genres") or []
        old_top = [g.get("name", "") for g in genres[:2] if g.get("name")]
    short_top = [g.get("name", "") for g in (short_recent_genres or [])[:2] if g.get("name")]
    recent_top = [g.get("name", "") for g in (recent_genres or [])[:2] if g.get("name")]
    if short_top and recent_top and short_top[0] != recent_top[0]:
        return (
            f"최근 {short_days}일 취향은 '{short_top[0]}' 쪽으로 빠르게 기울고 있으며, "
            f"{recent_days}일 기준 선호('{recent_top[0]}')와 차이가 있습니다."
        )
    if not short_top and not recent_top:
        return ""
    focus_top = short_top or recent_top
    if old_top and focus_top[0] and focus_top[0] not in old_top:
        return f"최근 {short_days}일 취향은 '{focus_top[0]}' 장르 쪽으로 이동하는 경향이 있습니다."
    if focus_top:
        return f"최근 {short_days}일 자주 보는 장르: {', '.join(focus_top)}."
    return ""


def build_persona_context(*, max_products: int | None = None) -> Dict[str, Any]:
    """
    페르소나 합성용 구조화 컨텍스트.
    """
    import time as _time
    _t_total = _time.perf_counter()

    n = int(max_products or persona_sample_size())
    budget = persona_context_budget()
    recent_days = persona_recent_days()
    short_days = persona_short_recent_days()
    from javstory.config.app_config import similarity_excluded_genres_from_env

    excluded = similarity_excluded_genres_from_env()

    _t = _time.perf_counter()
    stats = get_library_stats()
    taste = compute_taste_vector()
    monthly = get_monthly_genre_trend(3)
    recent = compute_recent_trend(recent_days, excluded_genres=excluded)
    short_recent = compute_recent_trend(short_days, excluded_genres=excluded)
    print(f"[PersonaCtx] stats/trend: {_time.perf_counter()-_t:.1f}s")

    drift_hint = _build_drift_hint(
        monthly,
        short_recent.get("genres") or [],
        recent.get("genres") or [],
        short_days=short_days,
        recent_days=recent_days,
    )

    ctx: Dict[str, Any] = {
        "stats": stats,
        "taste_axes": taste.get("axes") or [],
        "top_actors": get_top_actors(5),
        "top_genres": get_top_genres(8, excluded=excluded),
        "top_actors_recent": short_recent.get("actors") or recent.get("actors") or [],
        "top_genres_recent": short_recent.get("genres") or recent.get("genres") or [],
        "monthly_genres": monthly,
        "recent_window": {
            "short_days": short_days,
            "days": recent_days,
        },
        "recent_trend": recent,
        "short_recent_trend": short_recent,
        "drift_hint": drift_hint,
        "samples": [],
        "sample_codes": [],
        "sample_groups": {},
        "excluded_genres": sorted(excluded),
        "semantic_profile": {},
        "coverage": {"grok": 0, "grok_errors": 0, "canonical": 0, "subtitle": 0},
        "context_budget": budget,
        "tag_counter": [],
        "tone_counter": [],
        "subtitle_profile": {},
    }

    try:
        from javstory.utils.actress_profile import get_favorite_actress_profiles
        ctx["favorite_actress_profiles"] = get_favorite_actress_profiles(10)
    except Exception:
        ctx["favorite_actress_profiles"] = []

    if not persona_deep_enabled():
        return ctx

    try:
        from javstory.translation.story_grok_module import load_cached_grok_json_flexible
    except Exception:
        load_cached_grok_json_flexible = None

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

    _t = _time.perf_counter()
    ctx["semantic_profile"] = _build_semantic_profile(positive_seed_codes, set(codes))
    print(f"[PersonaCtx] semantic_profile: {_time.perf_counter()-_t:.1f}s")

    _t = _time.perf_counter()
    meta_by_code = _watch_meta_by_codes(codes)
    print(f"[PersonaCtx] watch_meta_by_codes: {_time.perf_counter()-_t:.1f}s")
    tag_counter: Counter = Counter()
    tone_counter: Counter = Counter()
    cues_per_min_list: List[float] = []
    products: List[Dict[str, Any]] = []

    def _load_one(pc: str) -> Tuple[str, Dict[str, Any]]:
        """제품 코드 하나에 대한 Grok/canonical/자막 로드 (스레드 안전)."""
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

        grok = None
        if load_cached_grok_json_flexible is not None:
            try:
                grok = load_cached_grok_json_flexible(pc)
            except Exception as exc:
                entry["grok_error"] = exc.__class__.__name__
                entry["_grok_err"] = True
        if grok and grok.get("verification_ok") is not False and not grok.get("code_mismatch"):
            g = _extract_grok_product(
                pc,
                grok,
                summary_chars=budget["grok_summary_chars"],
                item_limit=budget["per_product_tag_limit"],
            )
            entry["grok"] = g
            entry["_grok_ok"] = True

        try:
            from javstory.library.paths import library_state_path
            from javstory.library.canonical.store import load_library_state

            sp = library_state_path(pc)
            if sp.is_file():
                state = load_library_state(sp)
                c = _extract_canonical_product(pc, state, item_limit=budget["per_product_tag_limit"])
                entry["canonical"] = c
                entry["_canonical_ok"] = True
        except Exception:
            pass

        dur = int(meta.get("total_duration") or meta.get("watch_duration") or 0)
        srt_paths = _find_srt_paths(pc, folder_path, meta)
        sm = _subtitle_metrics_for_paths(srt_paths, dur)
        if sm:
            entry["subtitle"] = sm

        return pc, entry

    # 병렬로 각 제품 코드 로드 (I/O 바운드 작업)
    worker_count = min(len(codes), 6)
    ordered: Dict[str, Dict[str, Any]] = {}
    _t = _time.perf_counter()
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = {pool.submit(_load_one, pc): pc for pc in codes}
        for fut in as_completed(futures):
            try:
                pc, entry = fut.result()
                ordered[pc] = entry
            except Exception:
                pass
    print(f"[PersonaCtx] parallel_load({len(codes)} codes, {worker_count} workers): {_time.perf_counter()-_t:.1f}s")

    # codes 순서를 유지하면서 집계
    for pc in codes:
        entry = ordered.get(pc)
        if entry is None:
            continue

        if entry.pop("_grok_err", False):
            ctx["coverage"]["grok_errors"] += 1
        if entry.pop("_grok_ok", False):
            ctx["coverage"]["grok"] += 1
            for t in (entry.get("grok") or {}).get("tags") or []:
                if not _is_excluded_tag(t, excluded):
                    tag_counter[t] += 1
            for t in (entry.get("grok") or {}).get("tones") or []:
                tone_counter[t] += 1
        if entry.pop("_canonical_ok", False):
            ctx["coverage"]["canonical"] += 1
            for t in (entry.get("canonical") or {}).get("tags") or []:
                if not _is_excluded_tag(t, excluded):
                    tag_counter[t] += 1
            for t in (entry.get("canonical") or {}).get("tones") or []:
                tone_counter[t] += 1
        if "subtitle" in entry:
            ctx["coverage"]["subtitle"] += 1
            cues_per_min_list.append(float((entry["subtitle"]).get("cues_per_min") or 0))

        if len(entry) > 1:
            products.append(entry)

    ctx["samples"] = products
    ctx["tag_counter"] = _filtered_counter(tag_counter, excluded, budget["tag_counter_limit"])
    ctx["tone_counter"] = [
        {"name": k, "count": v}
        for k, v in tone_counter.most_common(budget["tone_counter_limit"])
    ]

    if cues_per_min_list:
        avg = sum(cues_per_min_list) / len(cues_per_min_list)
        density = "높음" if avg >= 12 else ("보통" if avg >= 6 else "낮음")
        ctx["subtitle_profile"] = {
            "avg_cues_per_min": round(avg, 2),
            "dialogue_density": density,
            "sample_count": len(cues_per_min_list),
        }

    print(f"[PersonaCtx] TOTAL build_persona_context: {_time.perf_counter()-_t_total:.1f}s")
    return ctx
