"""라이브러리 상세 화면 데이터 조립(QML LibraryDetailObject용 dict)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from javstory.harvest.product_repository import resolve_video_paths_for_playback


class LibraryDetailService:
    @staticmethod
    def find_summary(all_summaries: list[Any], product_code: str) -> Any | None:
        s = next((x for x in all_summaries if x.product_code == product_code), None)
        if s:
            return s
        try:
            from javstory.utils.product_code import strip_split_suffixes

            base = strip_split_suffixes((product_code or "").strip().upper()) or (
                product_code or ""
            ).strip().upper()
            return next(
                (
                    x
                    for x in all_summaries
                    if strip_split_suffixes((x.product_code or "").strip().upper()) == base
                ),
                None,
            )
        except Exception:
            return None

    @classmethod
    def build_detail_data(
        cls,
        summary: Any,
        *,
        favorite_delta_days: int = 0,
    ) -> dict[str, Any]:
        s = summary
        fp_bind = getattr(s, "folder_path", None) or ""
        data: dict[str, Any] = {
            "product_code": s.product_code,
            "title_ko": s.title_ko,
            "title_ja": s.title_ja,
            "actors_ko": s.actors_ko,
            "maker_ko": s.maker_ko,
            "release_date": s.release_date,
            "synopsis_ko": s.synopsis_ko,
            "genres_ko": s.genres_ko,
            "cover_path": s.cover_effective_path or s.cover_local_path or "",
            "scene_count": s.scene_count,
            "pipeline_stage": s.pipeline_stage,
            "has_canonical": s.has_canonical,
            "overall_summary": s.overall_summary_preview,
            "still_paths": [],
            "video_path": "",
            "video_paths": [],
            "grok_json": "",
            "grok_scenes_json": "[]",
            "grok_verified": False,
            "grok_mismatch_reason": "",
            "is_hardcoded": s.is_hardcoded,
            "is_mopa": getattr(s, "is_mopa", False),
            "has_ja_srt": s.has_ja_srt,
            "has_ko_srt": s.has_ko_srt,
            "lamp_hardcoded": s.lamp_hardcoded,
            "lamp_mopa": getattr(s, "lamp_mopa", False),
            "folder_path": fp_bind,
            "digest_path": "",
            "highlight_path": "",
            "watch_count": 0,
            "watch_duration": 0,
            "last_position": 0,
            "user_rating": 0,
            "user_liked": False,
            "watch_later": False,
            "watch_later_added_iso": "",
            "favorite_score": int(getattr(s, "favorite_score", 0) or 0),
            "favorite_site_delta": 0,
            "favorite_site_delta_days": 0,
            "has_favorite_site_delta": False,
        }

        cls._merge_library_state(s, data)
        cls._merge_grok_cache(s, data)
        cls._merge_stills_and_digest(s, data)
        cls._merge_highlight(s, data)
        cls._merge_video_paths(s, fp_bind, data)
        cls._merge_watch_history(s, data)
        cls._merge_favorite_delta(s, data, favorite_delta_days)
        return data

    @staticmethod
    def _merge_library_state(s: Any, data: dict[str, Any]) -> None:
        try:
            from javstory.library.paths import library_state_path

            p = library_state_path(s.product_code)
            if not p.is_file():
                return
            d = json.loads(p.read_text(encoding="utf-8"))
            data["grok_json"] = json.dumps(
                d.get("story_context", {}), ensure_ascii=False, indent=2
            )
            stills: list[str] = []
            for sc in d.get("scenes") or []:
                if isinstance(sc, dict):
                    for sp in sc.get("still_paths") or []:
                        stills.append(str(sp))
            data["still_paths"] = stills
        except Exception:
            pass

    @staticmethod
    def _merge_grok_cache(s: Any, data: dict[str, Any]) -> None:
        try:
            from javstory.config.app_config import library_story_context_batch_tier
            from javstory.translation.story_grok_module import load_cached_grok_json_flexible

            gj = load_cached_grok_json_flexible(
                s.product_code, library_story_context_batch_tier()
            )
            if not isinstance(gj, dict) or not gj:
                return
            data["grok_verified"] = bool(
                gj.get("verification_ok") is True and gj.get("code_mismatch") is not True
            )
            data["grok_mismatch_reason"] = str(gj.get("mismatch_reason") or "")
            grok_scenes = []
            for sc in gj.get("scenes") or []:
                if isinstance(sc, dict):
                    grok_scenes.append(
                        {
                            "time_range": sc.get("time_range", ""),
                            "scene_label": sc.get("scene_label", ""),
                            "scene_summary": sc.get("scene_summary", ""),
                        }
                    )
            data["grok_scenes_json"] = json.dumps(grok_scenes, ensure_ascii=False)
        except Exception:
            pass

    @staticmethod
    def _merge_stills_and_digest(s: Any, data: dict[str, Any]) -> None:
        stills_set: set[str] = set()
        if data.get("still_paths"):
            for p in data["still_paths"]:
                stills_set.add(str(Path(p).resolve()))
        try:
            from javstory.config.app_config import DATA_ROOT, E_DATA_ROOT, E_MEDIA_ROOT

            media_dir = Path(E_MEDIA_ROOT) / s.product_code
            legacy_e_flat_dir = Path(E_DATA_ROOT) / s.product_code
            legacy_e_media_dir = Path(E_DATA_ROOT) / "media" / s.product_code
            legacy_media_dir = Path(DATA_ROOT) / "media" / s.product_code
            base = next(
                (b for b in (media_dir, legacy_e_flat_dir, legacy_e_media_dir, legacy_media_dir) if b.is_dir()),
                None,
            )
            if base is None:
                return
            snap_dir = base / "Snapshots"
            exts = ["*.jpg", "*.jpeg", "*.png", "*.webp"]
            found: list[Path] = []
            if snap_dir.is_dir():
                for ext in exts:
                    found.extend(snap_dir.glob(ext))
            else:
                for ext in exts:
                    found.extend(base.glob(ext))
            exclude = {
                "cover.jpg",
                "poster.jpg",
                "thumb.jpg",
                "cover.png",
                "poster.png",
                "cover.webp",
                "poster.webp",
            }
            for f in found:
                if f.name.lower() not in exclude:
                    stills_set.add(str(f.resolve()))
            digest_file = base / "Digest" / "digest.mp4"
            if not digest_file.exists():
                digest_file = snap_dir / "digest.mp4"
            if not digest_file.exists():
                digest_file = base / "digest.mp4"
            if digest_file.is_file():
                data["digest_path"] = str(digest_file.resolve())
            data["still_paths"] = sorted(stills_set)
        except Exception:
            pass

    @staticmethod
    def _merge_highlight(s: Any, data: dict[str, Any]) -> None:
        try:
            pc = (s.product_code or "").strip().upper()
            if not pc:
                return
            from javstory.config.app_config import DATA_ROOT, E_DATA_ROOT, E_MEDIA_ROOT

            highlight_dir = Path(E_MEDIA_ROOT) / pc / "Highlight"
            for alt in (
                Path(E_DATA_ROOT) / pc / "Highlight",
                Path(E_DATA_ROOT) / "media" / pc / "Highlight",
                Path(DATA_ROOT) / "media" / pc / "Highlight",
            ):
                if not highlight_dir.is_dir() and alt.is_dir():
                    highlight_dir = alt
            for cand in (
                highlight_dir / "highlight.mp4",
                highlight_dir / "FINAL_HIGHLIGHT_840x640.mp4",
            ):
                if cand.is_file():
                    data["highlight_path"] = str(cand.resolve())
                    return
            if highlight_dir.is_dir():
                mp4s = sorted(highlight_dir.glob("*.mp4"))
                if mp4s and mp4s[0].is_file():
                    data["highlight_path"] = str(mp4s[0].resolve())
        except Exception:
            pass

    @staticmethod
    def _merge_video_paths(s: Any, fp_bind: str, data: dict[str, Any]) -> None:
        try:
            from javstory.library.multipart.detect import sort_video_parts

            sorted_paths = sort_video_parts(
                resolve_video_paths_for_playback(s.product_code, fp_bind or None)
            )
            data["video_paths"] = [str(p.resolve()) for p in sorted_paths]
            if data["video_paths"]:
                data["video_path"] = data["video_paths"][0]
        except Exception:
            data["video_paths"] = data.get("video_paths") or []

    @staticmethod
    def _merge_watch_history(s: Any, data: dict[str, Any]) -> None:
        try:
            from gui.watch_resume import last_position_ms_for_video
            from javstory.harvest.database import WatchHistory, get_db_session_ctx
            from javstory.utils.product_code import strip_split_suffixes

            with get_db_session_ctx() as sess:
                wh = sess.query(WatchHistory).filter_by(product_code=s.product_code).first()
                if not wh:
                    base = strip_split_suffixes((s.product_code or "").strip().upper()) or s.product_code
                    if base and base != s.product_code:
                        wh = sess.query(WatchHistory).filter_by(product_code=base).first()
                if not wh:
                    return
                data["watch_count"] = int(wh.session_count or 0)
                data["watch_duration"] = int(wh.watch_duration or 0)
                data["last_position"] = last_position_ms_for_video(
                    legacy_last_position=int(wh.last_position or 0),
                    last_positions_json=getattr(wh, "last_positions_json", None),
                    video_path=data.get("video_path") or "",
                )
                data["user_rating"] = int(wh.rating or 0)
                data["user_liked"] = bool(wh.liked)
                data["watch_later"] = bool(getattr(wh, "watch_later", False))
                added_at = getattr(wh, "watch_later_added_at", None)
                if added_at:
                    try:
                        data["watch_later_added_iso"] = added_at.replace(microsecond=0).isoformat(sep=" ")
                    except Exception:
                        data["watch_later_added_iso"] = ""
        except Exception:
            pass

    @staticmethod
    def _merge_favorite_delta(
        s: Any, data: dict[str, Any], favorite_delta_days: int
    ) -> None:
        fav_row = int(data.get("favorite_score") or 0)
        fd_days = int(favorite_delta_days or 0)
        if fd_days <= 0:
            return
        try:
            from javstory.harvest.database import favorite_score_delta_one

            delta = favorite_score_delta_one(
                str(s.product_code or ""),
                fd_days,
                fallback_score=fav_row,
            )
            data["favorite_site_delta_days"] = fd_days
            if delta is not None:
                data["favorite_site_delta"] = int(delta)
                data["has_favorite_site_delta"] = True
            else:
                data["favorite_site_delta"] = 0
                data["has_favorite_site_delta"] = False
        except Exception:
            data["favorite_site_delta"] = 0
            data["favorite_site_delta_days"] = fd_days
            data["has_favorite_site_delta"] = False
