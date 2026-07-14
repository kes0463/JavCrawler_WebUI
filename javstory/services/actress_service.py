"""Actress profile service for WebAPI (mirrors gui/models/actress_model.py)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from javstory.harvest.database import (
    Actress,
    ActressAlias,
    ActressImage,
    WatchHistory,
    commit_with_retry,
    get_db_session_ctx,
)
from javstory.utils.actress_profile import (
    add_alias,
    aggregate_work_genres,
    batch_actress_work_counts,
    fetch_actress_library_works,
    load_actress_media,
    merge_actresses,
    promote_gallery_image_to_profile,
    rebuild_actress_works_for_actress,
    refresh_stale_metadata_actors_for_actress,
    resolve_actress_by_name,
    resolve_actress_media_path,
    save_actress_image,
    _format_debut_ym,
)

_SORT_KEYS = frozenset({"name", "works", "favorite", "score", "recent"})
_PROFILE_NAME_KEYS = frozenset({
    "name_ko", "name_ja", "name_en", "korean", "japanese", "romaji",
})
_DATE_FIELDS = frozenset({"birth_date", "debut_date", "last_watched"})
_INT_FIELDS = frozenset({"height", "bust", "waist", "hip"})
_FLOAT_FIELDS = frozenset({"user_score", "favorite_intensity"})


def _parse_profile_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value).strip()
    if not s:
        return None
    if len(s) >= 10 and s[4:5] == "-" and s[7:8] == "-":
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            pass
    if len(s) >= 7 and s[4:5] == "-":
        try:
            return date(int(s[:4]), int(s[5:7]), 1)
        except ValueError:
            pass
    return None


def _coerce_profile_field(key: str, value: Any) -> Any:
    if key in _DATE_FIELDS:
        return _parse_profile_date(value)
    if key in _INT_FIELDS:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if key in _FLOAT_FIELDS:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        s = value.strip()
        return s if s else None
    return value


def _apply_profile_updates(actress: Actress, data: dict) -> None:
    payload = dict(data) if data else {}
    for key, raw_value in payload.items():
        if not hasattr(actress, key) or key in ("id", "created_at", "updated_at"):
            continue
        setattr(actress, key, _coerce_profile_field(key, raw_value))
    if "name_ja" in payload:
        actress.japanese = actress.name_ja
    if "name_ko" in payload:
        actress.korean = actress.name_ko


def _media_url(path: str) -> str:
    p = (path or "").strip().replace("\\", "/")
    if not p:
        return ""
    from urllib.parse import quote

    return f"/api/actresses/media?path={quote(p, safe='')}"


def _effective_user_score(row: Actress) -> float:
    intensity = getattr(row, "favorite_intensity", None)
    manual = getattr(row, "user_score", None)
    if intensity is not None and float(intensity or 0) > 0:
        return float(intensity)
    if manual is not None and float(manual or 0) > 0:
        return float(manual)
    return 0.0


def _row_to_list_item(row: Actress, counts: dict | None = None) -> dict[str, Any]:
    wc = int(counts.get(row.id, 0) if counts else getattr(row, "work_count", 0) or 0)
    profile_path = resolve_actress_media_path(row.profile_image_url or "")
    return {
        "id": row.id,
        "name_ko": row.name_ko or row.korean or "",
        "name_ja": row.name_ja or row.japanese or "",
        "profile_image_url": _media_url(row.profile_image_url or "") if profile_path else "",
        "user_score": _effective_user_score(row),
        "is_favorite": bool(getattr(row, "is_favorite", False)),
        "genres": getattr(row, "genres", "") or "",
        "work_count": wc,
    }


def _apply_search_filter(qry, query: str):
    q = (query or "").strip()
    if not q:
        return qry
    like = f"%{q}%"
    alias_ids = (
        qry.session.query(ActressAlias.actress_id)
        .filter(ActressAlias.alias_name.ilike(like))
        .distinct()
    )
    return qry.filter(
        or_(
            Actress.name_ko.ilike(like),
            Actress.name_ja.ilike(like),
            Actress.japanese.ilike(like),
            Actress.name_en.ilike(like),
            Actress.korean.ilike(like),
            Actress.genres.ilike(like),
            Actress.id.in_(alias_ids),
        )
    )


def _work_count_sort_available(session) -> bool:
    try:
        row = (
            session.query(Actress.works_updated_at)
            .filter(Actress.works_updated_at.isnot(None))
            .limit(1)
            .first()
        )
        return row is not None
    except Exception:
        return False


def _apply_work_count_order(qry, ascending: bool):
    name_key = func.coalesce(Actress.name_ko, Actress.korean, "")
    if ascending:
        return qry.order_by(Actress.work_count.asc(), name_key.asc())
    return qry.order_by(Actress.work_count.desc(), name_key.asc())


def _actress_recent_key(row: Actress) -> tuple:
    updated = getattr(row, "updated_at", None)
    created = getattr(row, "created_at", None)
    ts = updated or created
    row_id = int(getattr(row, "id", 0) or 0)
    if ts is not None:
        return (ts, row_id)
    return (datetime.min, row_id)


def _order_actress_rows(session, rows: list[Actress], sort: str, ascending: bool) -> list[Actress]:
    rows = list(rows or [])
    reverse = not ascending
    if sort == "works":
        counts = batch_actress_work_counts(session, rows)
        rows.sort(
            key=lambda r: (counts.get(r.id, 0), (r.name_ko or r.korean or "")),
            reverse=reverse,
        )
        return rows
    if sort == "name":
        rows.sort(
            key=lambda r: (r.name_ko or r.korean or "", r.name_ja or r.japanese or ""),
            reverse=reverse,
        )
    elif sort == "favorite":
        rows.sort(
            key=lambda r: (bool(getattr(r, "is_favorite", False)), r.name_ko or r.korean or ""),
            reverse=reverse,
        )
    elif sort == "score":
        rows.sort(
            key=lambda r: (_effective_user_score(r), r.name_ko or r.korean or ""),
            reverse=reverse,
        )
    elif sort == "recent":
        rows.sort(key=_actress_recent_key, reverse=reverse)
    else:
        rows.sort(
            key=lambda r: (r.name_ko or r.korean or "", r.name_ja or r.japanese or ""),
            reverse=reverse,
        )
    return rows


def _profile_to_dict(row: Actress, media: dict, aliases: list) -> dict[str, Any]:
    profile_path = resolve_actress_media_path(media.get("profile_image_url") or row.profile_image_url or "")
    gallery = []
    for img in media.get("gallery_images") or []:
        rel = img.get("image_url") or ""
        thumb = img.get("thumb_url") or rel
        gallery.append({
            **img,
            "image_url": _media_url(rel) if rel else "",
            "thumb_url": _media_url(thumb) if thumb else "",
            "image_url_raw": rel,
        })
    return {
        "id": row.id,
        "name_ja": row.name_ja or row.japanese or "",
        "name_ko": row.name_ko or row.korean or "",
        "name_en": getattr(row, "name_en", "") or "",
        "romaji": getattr(row, "romaji", "") or "",
        "profile_image_url": _media_url(row.profile_image_url or "") if profile_path else "",
        "genres": getattr(row, "genres", "") or "",
        "user_score": float(getattr(row, "user_score", 0.0) or 0.0),
        "profile_text": getattr(row, "profile_text", "") or "",
        "birth_date": str(row.birth_date) if getattr(row, "birth_date", None) else "",
        "height": getattr(row, "height", 0) or 0,
        "bust": getattr(row, "bust", 0) or 0,
        "waist": getattr(row, "waist", 0) or 0,
        "hip": getattr(row, "hip", 0) or 0,
        "cup_size": getattr(row, "cup_size", "") or "",
        "debut_date": _format_debut_ym(getattr(row, "debut_date", None)),
        "debut_date_raw": str(row.debut_date) if getattr(row, "debut_date", None) else "",
        "agency": getattr(row, "agency", "") or "",
        "is_favorite": bool(getattr(row, "is_favorite", False)),
        "favorite_intensity": float(getattr(row, "favorite_intensity", 0.0) or 0.0),
        "memo": getattr(row, "memo", "") or "",
        "work_count": int(getattr(row, "work_count", 0) or 0),
        "aliases": aliases,
        "gallery_images": gallery,
    }


class ActressService:
    def list_actresses(
        self,
        *,
        q: str = "",
        sort: str = "name",
        ascending: bool = True,
        page: int = 1,
        per_page: int = 48,
    ) -> dict[str, Any]:
        sort = sort if sort in _SORT_KEYS else "name"
        page = max(1, int(page or 1))
        per_page = max(1, min(200, int(per_page or 48)))
        with get_db_session_ctx() as session:
            qry = session.query(Actress)
            qry = _apply_search_filter(qry, q)
            counts = None
            if sort == "works" and _work_count_sort_available(session):
                qry = _apply_work_count_order(qry, ascending)
                rows = qry.all()
            else:
                rows = qry.all()
                if sort == "works":
                    counts = batch_actress_work_counts(session, rows)
                rows = _order_actress_rows(session, rows, sort, ascending)
            if counts is None and sort == "works":
                counts = batch_actress_work_counts(session, rows)
            total = len(rows)
            start = (page - 1) * per_page
            page_rows = rows[start : start + per_page]
            return {
                "total": total,
                "page": page,
                "per_page": per_page,
                "items": [_row_to_list_item(r, counts) for r in page_rows],
            }

    def search_actresses(self, q: str = "", *, limit: int = 50) -> list[dict[str, Any]]:
        with get_db_session_ctx() as session:
            qry = session.query(Actress)
            qry = _apply_search_filter(qry, q)
            rows = qry.order_by(Actress.name_ko.asc().nullslast()).limit(limit).all()
            return [
                {
                    "id": r.id,
                    "name_ko": r.name_ko or r.korean or "",
                    "name_ja": r.name_ja or r.japanese or "",
                    "user_score": _effective_user_score(r),
                }
                for r in rows
            ]

    def resolve_id_by_name(self, name: str) -> int | None:
        aid = resolve_actress_by_name(name)
        return int(aid) if aid else None

    def get_profile(self, actress_id: int) -> dict[str, Any] | None:
        aid = int(actress_id or 0)
        if aid <= 0:
            return None
        with get_db_session_ctx() as session:
            row = session.query(Actress).filter_by(id=aid).first()
            if not row:
                return None
            media = load_actress_media(aid)
            aliases = [
                {
                    "alias_id": a.alias_id,
                    "alias_name": a.alias_name,
                    "alias_type": a.alias_type or "stage",
                    "is_primary": bool(a.is_primary),
                }
                for a in (row.aliases or [])
            ]
            synced = refresh_stale_metadata_actors_for_actress(session, aid)
            if synced:
                commit_with_retry(session)
            profile = _profile_to_dict(row, media, aliases)
            profile["library_refresh_pcs"] = synced
            return profile

    def get_works_bundle(self, actress_id: int) -> dict[str, Any]:
        aid = int(actress_id or 0)
        if aid <= 0:
            return {"works": [], "genres": []}
        with get_db_session_ctx() as session:
            actress = (
                session.query(Actress)
                .options(joinedload(Actress.aliases))
                .filter_by(id=aid)
                .first()
            )
            if not actress:
                return {"works": [], "genres": []}
            items = fetch_actress_library_works(session, actress)
            if items:
                from javstory.harvest.database import JAVMetadata
                from javstory.library.file_flag_scanner import load_flags_for_codes
                from javstory.services.library_service import LibraryService

                codes = [it["product_code"] for it in items]
                watch_rows = session.query(WatchHistory).filter(
                    WatchHistory.product_code.in_(codes)
                ).all()
                watch_by_pc: dict[str, WatchHistory] = {}
                for wh in watch_rows:
                    key = (wh.product_code or "").strip().upper()
                    if key:
                        watch_by_pc[key] = wh

                meta_rows = (
                    session.query(JAVMetadata)
                    .filter(JAVMetadata.product_code.in_(codes))
                    .all()
                )
                meta_by_pc = {
                    (r.product_code or "").strip().upper(): r
                    for r in meta_rows
                    if (r.product_code or "").strip()
                }
                flags_map = load_flags_for_codes(session, codes)
                lib = LibraryService()

                for it in items:
                    pc = (it.get("product_code") or "").strip().upper()
                    wh = watch_by_pc.get(pc)
                    it["user_rating"] = int(wh.rating or 0) if wh else 0
                    it["user_liked"] = bool(wh.liked) if wh else False
                    it["watch_later"] = bool(getattr(wh, "watch_later", False)) if wh else False
                    cp = it.get("cover_path") or it.get("coverPath") or ""
                    if cp:
                        it["cover_url"] = f"/api/library/cover/{it['product_code']}"

                    row = meta_by_pc.get(pc)
                    if row is not None:
                        folder = (getattr(row, "folder_path", None) or "").strip() or ""
                        it["folder_path"] = folder
                        cache = flags_map.get(pc) or flags_map.get(it["product_code"]) or {}
                        try:
                            flags = lib.media_flags_for(row, cache)
                            it["has_subtitle"] = bool(flags.get("has_subtitle"))
                            it["has_hardcoded_subtitle"] = bool(flags.get("has_hardcoded_subtitle"))
                            it["has_mosaic_removed"] = bool(flags.get("has_mosaic_removed"))
                            it["has_preview"] = bool(flags.get("has_preview"))
                            it["preview_media"] = flags.get("preview_media")
                        except Exception:
                            pass
            return {"works": items, "genres": aggregate_work_genres(items)}

    def create_actress(self, data: dict) -> int:
        with get_db_session_ctx() as session:
            actress = Actress(
                japanese=(data.get("name_ja") or data.get("name_ko") or "").strip(),
                korean=(data.get("name_ko") or "").strip() or None,
                name_ja=(data.get("name_ja") or "").strip() or None,
                name_ko=(data.get("name_ko") or "").strip() or None,
                name_en=(data.get("name_en") or "").strip() or None,
                genres=(data.get("genres") or "").strip() or None,
                profile_text=(data.get("profile_text") or "").strip() or None,
                user_score=float(data.get("user_score") or 0.0),
                memo=(data.get("memo") or "").strip() or None,
                needs_review=False,
            )
            session.add(actress)
            commit_with_retry(session)
            new_id = int(actress.id)
            primary = (data.get("name_ja") or data.get("name_ko") or "").strip()
            if primary:
                add_alias(new_id, primary, "stage", is_primary=True)
            return new_id

    def update_actress(self, actress_id: int, data: dict) -> bool:
        aid = int(actress_id or 0)
        if aid <= 0:
            return False
        with get_db_session_ctx() as session:
            row = session.query(Actress).filter_by(id=aid).first()
            if not row:
                return False
            payload = dict(data)
            _apply_profile_updates(row, payload)
            row.updated_at = datetime.now()
            commit_with_retry(session)
            if _PROFILE_NAME_KEYS & payload.keys():
                rebuild_actress_works_for_actress(session, aid, source="profile")
                commit_with_retry(session)
            return True

    def merge(self, keep_id: int, merge_id: int) -> tuple[bool, list[str]]:
        return merge_actresses(int(keep_id), int(merge_id))

    def add_alias(
        self,
        actress_id: int,
        alias_name: str,
        alias_type: str = "stage",
        *,
        is_primary: bool = False,
    ) -> bool:
        ok = add_alias(int(actress_id), alias_name, alias_type, is_primary)
        if ok:
            with get_db_session_ctx() as session:
                rebuild_actress_works_for_actress(session, int(actress_id), source="alias")
                commit_with_retry(session)
        return ok

    def remove_alias(self, actress_id: int, alias_id: int) -> bool:
        with get_db_session_ctx() as session:
            alias = session.query(ActressAlias).filter_by(alias_id=int(alias_id)).first()
            if not alias:
                return False
            session.delete(alias)
            commit_with_retry(session)
            rebuild_actress_works_for_actress(session, int(actress_id), source="alias")
            commit_with_retry(session)
            return True

    def add_image(self, actress_id: int, source_path: str, *, is_profile: bool = False) -> str:
        path = save_actress_image(
            actress_id=int(actress_id),
            source_path=source_path,
            is_profile=is_profile,
            sort_order=10,
        )
        return str(path or "")

    def set_profile_image(self, actress_id: int, image_id: int) -> bool:
        aid = int(actress_id)
        with get_db_session_ctx() as session:
            img = session.query(ActressImage).filter_by(
                image_id=int(image_id), actress_id=aid
            ).first()
            if not img:
                return False
            rel = img.image_url
        return bool(promote_gallery_image_to_profile(aid, rel))

    def resolve_media_file(self, path: str) -> str | None:
        resolved = resolve_actress_media_path(path)
        if resolved and __import__("pathlib").Path(resolved).is_file():
            return resolved
        return None
