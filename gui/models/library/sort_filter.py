"""라이브러리 그리드 필터·정렬·품번 병합."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gui.models.library.search import (
    build_watch_feedback_by_base,
    match_summary,
    parse_search_expr,
    preview_path_for,
    release_month_key,
)


@dataclass
class ListRebuildOptions:
    all_summaries: list[Any]
    search_query: str = ""
    filter_mode: int = 0
    month_filter: str = ""
    unknown_only: bool = False
    sort_mode: int = 0
    favorite_delta_days: int = 0
    preview_path_cache: dict[str, str] = field(default_factory=dict)


class LibrarySortFilter:
    @staticmethod
    def base_product_code(pc: str) -> str:
        try:
            from javstory.utils.product_code import strip_split_suffixes

            u = (pc or "").strip().upper()
            return strip_split_suffixes(u) or u
        except Exception:
            return (pc or "").strip().upper()

    @classmethod
    def rebuild(cls, opts: ListRebuildOptions) -> list[dict]:
        genre_groups, genre_excludes, text_terms = parse_search_expr(opts.search_query or "")
        has_query = bool(genre_groups or genre_excludes or text_terms)
        fm = opts.filter_mode
        mf = (opts.month_filter or "").strip()
        if opts.unknown_only:
            mf = "unknown"

        filtered: list[Any] = []
        for s in opts.all_summaries:
            if fm == 1 and not getattr(s, "has_canonical", False):
                continue
            if fm == 2 and getattr(s, "has_canonical", False):
                continue
            if fm == 3 and not getattr(s, "folder_path", None):
                continue
            if fm == 4 and not (
                getattr(s, "has_ko_srt", False) or getattr(s, "has_ja_srt", False)
            ):
                continue
            if mf:
                rk = release_month_key(getattr(s, "release_date", "") or "")
                if rk != mf:
                    continue
            if has_query and not match_summary(s, genre_groups, genre_excludes, text_terms):
                continue
            filtered.append(s)

        groups: dict[str, list[Any]] = {}
        for s in filtered:
            k = cls.base_product_code(getattr(s, "product_code", "") or "")
            groups.setdefault(k, []).append(s)

        stage_rank = {"none": 0, "harvest": 1, "transcription": 2, "translation": 3, "canonical": 4}

        def pick_rep(lst: list[Any]) -> Any:
            def score(x: Any) -> tuple:
                has_cover = 1 if (
                    getattr(x, "cover_effective_path", None) or getattr(x, "cover_local_path", None)
                ) else 0
                upd = getattr(x, "updated_at_iso", "") or ""
                return (has_cover, upd)

            return max(lst, key=score)

        try:
            from javstory.config.app_config import DATA_ROOT, E_MEDIA_ROOT

            e_root = Path(E_MEDIA_ROOT)
            legacy_root = Path(DATA_ROOT) / "media"
        except Exception:
            e_root = None
            legacy_root = None

        cache = opts.preview_path_cache

        def preview_path_cached(base_pc: str) -> str:
            key = (base_pc or "").strip().upper()
            if not key:
                return ""
            hit = cache.get(key)
            if hit is not None:
                return hit
            v = preview_path_for(key, e_root, legacy_root)
            cache[key] = v
            return v

        watch_map = build_watch_feedback_by_base()
        mode = opts.sort_mode
        eff_delta_days = int(opts.favorite_delta_days or 0)
        if eff_delta_days <= 0 and mode in (11, 12):
            eff_delta_days = 7

        deltas_map: dict[str, int | None] = {}
        if eff_delta_days > 0:
            try:
                from javstory.harvest.database import favorite_score_deltas_for_period

                meta_by_code: dict[str, int] = {}
                for s2 in filtered:
                    pc2 = (getattr(s2, "product_code", "") or "").strip().upper()
                    if pc2:
                        meta_by_code[pc2] = int(getattr(s2, "favorite_score", 0) or 0)
                deltas_map = favorite_score_deltas_for_period(
                    meta_scores_by_code=meta_by_code,
                    period_days=eff_delta_days,
                )
            except Exception:
                deltas_map = {}

        merged_items: list[dict] = []
        for base_pc, lst in groups.items():
            rep = pick_rep(lst)
            max_scene = max((getattr(x, "scene_count", 0) or 0) for x in lst) if lst else 0
            max_stage = "none"
            for x in lst:
                st = getattr(x, "pipeline_stage", "none") or "none"
                if stage_rank.get(st, 0) > stage_rank.get(max_stage, 0):
                    max_stage = st

            part_pcs: list[str] = []
            for x in lst:
                pcp = (getattr(x, "product_code", "") or "").strip().upper()
                if pcp and pcp not in part_pcs:
                    part_pcs.append(pcp)

            fd_acc: list[int] = []
            if eff_delta_days > 0 and deltas_map:
                for pcp in part_pcs:
                    dv = deltas_map.get(pcp)
                    if dv is not None:
                        fd_acc.append(int(dv))
            favorite_delta = sum(fd_acc) if fd_acc else None

            wm = watch_map.get(base_pc) or {}
            merged_items.append(
                {
                    "product_code": base_pc,
                    "title_ko": getattr(rep, "title_ko", "") or "",
                    "title_ja": getattr(rep, "title_ja", "") or "",
                    "actors_ko": getattr(rep, "actors_ko", "") or "",
                    "cover_path": getattr(rep, "cover_effective_path", None)
                    or getattr(rep, "cover_local_path", None)
                    or "",
                    "preview_path": preview_path_cached(base_pc),
                    "scene_count": max_scene,
                    "pipeline_stage": max_stage,
                    "release_date": getattr(rep, "release_date", "") or "",
                    "has_canonical": any(bool(getattr(x, "has_canonical", False)) for x in lst),
                    "part_count": len(lst),
                    "is_hardcoded": any(bool(getattr(x, "is_hardcoded", False)) for x in lst),
                    "has_ja_srt": any(bool(getattr(x, "has_ja_srt", False)) for x in lst),
                    "has_ko_srt": any(bool(getattr(x, "has_ko_srt", False)) for x in lst),
                    "lamp_hardcoded": any(bool(getattr(x, "lamp_hardcoded", False)) for x in lst),
                    "lamp_mopa": any(bool(getattr(x, "lamp_mopa", False)) for x in lst),
                    "updated_at_iso": max(
                        (getattr(x, "updated_at_iso", "") or "" for x in lst), default=""
                    ),
                    "favorite_score": sum(int(getattr(x, "favorite_score", 0) or 0) for x in lst),
                    "favorite_delta": favorite_delta,
                    "user_rating": int(wm.get("rating") or 0),
                    "user_liked": bool(wm.get("liked")),
                    "watch_later": bool(wm.get("watch_later")),
                    "watch_later_added_iso": str(wm.get("watch_later_added_iso") or ""),
                    "user_feedback_iso": str(wm.get("feedback_iso") or ""),
                    "has_story_context": any(
                        bool(getattr(x, "has_story_context", False)) for x in lst
                    ),
                }
            )

        if fm == 5:
            merged_items = [
                it
                for it in merged_items
                if int(it.get("user_rating") or 0) > 0 or bool(it.get("user_liked"))
            ]
        if fm == 6:
            merged_items = [it for it in merged_items if bool(it.get("user_liked"))]
        if fm == 7:
            merged_items = [it for it in merged_items if bool(it.get("has_story_context"))]
        if fm == 8:
            merged_items = [it for it in merged_items if bool(it.get("watch_later"))]

        cls._sort_merged_items(merged_items, mode)
        return merged_items

    @staticmethod
    def _sort_merged_items(merged_items: list[dict], mode: int) -> None:
        if mode == 0:
            merged_items.sort(key=lambda it: it.get("product_code", ""))
        elif mode == 1:
            merged_items.sort(key=lambda it: it.get("release_date", ""), reverse=True)
        elif mode == 2:
            merged_items.sort(key=lambda it: it.get("release_date", ""))
        elif mode == 3:
            merged_items.sort(key=lambda it: int(it.get("scene_count") or 0), reverse=True)
        elif mode == 4:
            merged_items.sort(key=lambda it: it.get("updated_at_iso", ""), reverse=True)
        elif mode == 5:
            merged_items.sort(key=lambda it: it.get("actors_ko", "") or "\uffff")
        elif mode == 6:
            merged_items.sort(key=lambda it: it.get("actors_ko", "") or "\uffff", reverse=True)
        elif mode == 7:
            merged_items.sort(
                key=lambda it: (
                    0
                    if (
                        it.get("has_ko_srt")
                        or it.get("has_ja_srt")
                        or it.get("lamp_hardcoded")
                    )
                    else 1,
                    it.get("product_code", ""),
                )
            )
        elif mode == 8:
            merged_items.sort(
                key=lambda it: (0 if it.get("lamp_mopa") else 1, it.get("product_code", ""))
            )
        elif mode == 9:
            merged_items.sort(key=lambda it: int(it.get("favorite_score") or 0), reverse=True)
        elif mode == 10:
            merged_items.sort(key=lambda it: int(it.get("favorite_score") or 0))
        elif mode == 11:
            merged_items.sort(
                key=lambda it: (
                    (0, int(it.get("favorite_delta") or 0))
                    if it.get("favorite_delta") is not None
                    else (-1, 0)
                ),
                reverse=True,
            )
        elif mode == 12:
            merged_items.sort(
                key=lambda it: (
                    (0, int(it.get("favorite_delta") or 0))
                    if it.get("favorite_delta") is not None
                    else (1, 0)
                ),
            )
        elif mode == 13:
            merged_items.sort(
                key=lambda it: (
                    0 if int(it.get("user_rating") or 0) > 0 else 1,
                    -int(it.get("user_rating") or 0),
                    it.get("product_code", ""),
                ),
            )
        elif mode == 14:
            merged_items.sort(
                key=lambda it: (
                    bool(it.get("watch_later")),
                    str(it.get("watch_later_added_iso") or ""),
                    it.get("product_code", ""),
                ),
                reverse=True,
            )
