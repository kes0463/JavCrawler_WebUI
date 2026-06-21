"""Actress profile utilities for JAVSTORY.

- Folder creation and sanitization based on name_ko
- Image saving (profile + gallery) with resize
- Integration with actress_aliases and new DB columns
"""

from pathlib import Path
import re
import shutil
from datetime import datetime
from typing import Optional, Tuple, List
from PIL import Image, ImageOps
from PIL.Image import Resampling

from javstory.config.app_config import DATA_ROOT, E_DATA_ROOT
from javstory.harvest.database import get_db_session, get_db_session_ctx, Actress, ActressImage, ActressAlias


def actress_storage_root() -> Path:
    """배우 사진 저장 루트 — E:\\App\\JAVSTORY\\data (JAVSTORY_E_DATA_ROOT)."""
    return E_DATA_ROOT


def resolve_actress_media_path(path: str) -> str:
    """DB/상대 경로 → QML Image.source용 절대 경로."""
    if not path:
        return ""
    p = Path(path)
    if p.is_absolute():
        if p.is_file():
            return str(p.resolve())
    else:
        for root in (actress_storage_root(), DATA_ROOT):
            candidate = (root / p).resolve()
            if candidate.is_file():
                return str(candidate)
    if p.is_absolute():
        return str(p)
    return str((actress_storage_root() / p).resolve())


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def sanitize_folder_name(name: str) -> str:
    """Convert name_ko to safe folder name.
    - space -> _
    - remove invalid chars
    - max 50 chars
    """
    if not name:
        return "unknown_actress"

    name = name.strip()
    name = re.sub(r"[\s]+", "_", name)
    name = re.sub(r"[^a-zA-Z0-9_\u3131-\uD79D]", "", name)
    name = name[:50].strip("_")
    return name or "unknown_actress"


def get_actress_folder(name_ko: str, create: bool = True) -> Path:
    """Return Path to actress folder: {E_DATA_ROOT}/actress/{sanitized_name_ko}/"""
    safe_name = sanitize_folder_name(name_ko)
    folder = actress_storage_root() / "actress" / safe_name

    if create:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "profile").mkdir(exist_ok=True)
        (folder / "gallery").mkdir(exist_ok=True)

    return folder


def _rel_data_path(path: Path) -> str:
    path = path.resolve()
    for root in (actress_storage_root(), DATA_ROOT):
        try:
            return str(path.relative_to(root.resolve())).replace("\\", "/")
        except ValueError:
            continue
    return str(path).replace("\\", "/")


def _actress_folder_name(actress: Actress, actress_id: int) -> str:
    name = (actress.name_ko or actress.korean or "").strip()
    return sanitize_folder_name(name) if name else f"actress_{actress_id}"


def ensure_actress_media_dirs(actress: Actress, actress_id: int) -> tuple[Path, Path, Path]:
    """저장 시 E_DATA_ROOT/actress/{name_ko}/profile|gallery 자동 생성."""
    safe = _actress_folder_name(actress, actress_id)
    base = actress_storage_root() / "actress" / safe
    profile_dir = base / "profile"
    gallery_dir = base / "gallery"
    profile_dir.mkdir(parents=True, exist_ok=True)
    gallery_dir.mkdir(exist_ok=True)
    return base, profile_dir, gallery_dir


def find_actress_media_dirs(actress: Actress, actress_id: int) -> tuple[Path, Path, Path]:
    """읽기: E_DATA_ROOT/{name_ko} 우선, 비어 있으면 legacy actress_{id}."""
    safe = _actress_folder_name(actress, actress_id)
    primary = actress_storage_root() / "actress" / safe
    if _list_image_files(primary / "profile") or _list_image_files(primary / "gallery"):
        return primary, primary / "profile", primary / "gallery"

    for root in (actress_storage_root(), DATA_ROOT):
        legacy = root / "actress" / f"actress_{actress_id}"
        if _list_image_files(legacy / "profile") or _list_image_files(legacy / "gallery"):
            return legacy, legacy / "profile", legacy / "gallery"

    return primary, primary / "profile", primary / "gallery"


def _is_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def _list_image_files(folder: Path) -> List[Path]:
    if not folder.is_dir():
        return []
    return sorted(
        (p for p in folder.iterdir() if _is_image_file(p)),
        key=lambda p: p.stat().st_mtime,
    )


def _actress_name_ko(actress: Actress, actress_id: int) -> str:
    return (actress.name_ko or actress.korean or "").strip() or f"actress_{actress_id}"


def _path_in_subdir(path: Path, subdir_name: str) -> bool:
    resolved = path.resolve()
    for root in (actress_storage_root(), DATA_ROOT):
        try:
            parts = resolved.relative_to(root.resolve()).parts
            if "actress" in parts and subdir_name in parts:
                return True
        except ValueError:
            continue
    return False


def _clear_folder_except(folder: Path, keep: Path | None = None) -> None:
    for p in _list_image_files(folder):
        if keep and p.resolve() == keep.resolve():
            continue
        try:
            p.unlink()
        except OSError:
            pass


def load_actress_media(actress_id: int) -> dict:
    """profile/ · gallery/ 폴더에서만 미디어 경로를 수집한다."""
    out = {"profile_image_url": "", "gallery_images": []}
    try:
        with get_db_session_ctx() as session:
            actress = session.query(Actress).filter_by(id=actress_id).first()
            if not actress:
                return out

            folder, profile_dir, gallery_dir = find_actress_media_dirs(actress, actress_id)

            profile_files = _list_image_files(profile_dir)
            gallery_files = _list_image_files(gallery_dir)

            profile_rel = ""
            db_url = (actress.profile_image_url or "").strip()
            if db_url:
                db_path = Path(db_url)
                if not db_path.is_absolute():
                    for root in (actress_storage_root(), DATA_ROOT):
                        candidate = (root / db_url).resolve()
                        if candidate.is_file():
                            db_path = candidate
                            break
                    else:
                        db_path = (actress_storage_root() / db_url).resolve()
                if db_path.is_file() and _path_in_subdir(db_path, "profile"):
                    profile_rel = _rel_data_path(db_path)

            if not profile_rel and profile_files:
                profile_rel = _rel_data_path(profile_files[-1])

            gallery_images: List[dict] = []
            valid_rels: set[str] = set()
            for i, gf in enumerate(gallery_files):
                rel = _rel_data_path(gf)
                valid_rels.add(rel)
                row = session.query(ActressImage).filter_by(
                    actress_id=actress_id, image_url=rel
                ).first()
                if not row:
                    row = ActressImage(
                        actress_id=actress_id,
                        image_url=rel,
                        is_profile=False,
                        sort_order=i,
                    )
                    session.add(row)
                    session.flush()
                gallery_images.append({
                    "image_id": row.image_id,
                    "image_url": rel,
                    "filename": gf.name,
                    "sort_order": i,
                })

            stale = session.query(ActressImage).filter_by(actress_id=actress_id).all()
            for row in stale:
                url = (row.image_url or "").replace("\\", "/")
                if url not in valid_rels or row.is_profile:
                    session.delete(row)

            if profile_rel and profile_rel != (actress.profile_image_url or "").strip():
                actress.profile_image_url = profile_rel

            session.commit()

            out["profile_image_url"] = profile_rel
            out["gallery_images"] = gallery_images
            return out
    except Exception as e:
        print(f"[ActressProfile] load_actress_media error: {e}")
        return out


def promote_gallery_image_to_profile(actress_id: int, image_url: str) -> Optional[Path]:
    """gallery/ 이미지를 profile/로 복사해 대표 사진으로 지정."""
    try:
        src = Path(image_url)
        if not src.is_file():
            for root in (actress_storage_root(), DATA_ROOT):
                candidate = (root / image_url).resolve() if not Path(image_url).is_absolute() else src
                if candidate.is_file():
                    src = candidate
                    break
        if not src.is_file():
            return None
        if not _path_in_subdir(src, "gallery"):
            return None

        with get_db_session_ctx() as session:
            actress = session.query(Actress).filter_by(id=actress_id).first()
            if not actress:
                return None

            _, profile_dir, _ = ensure_actress_media_dirs(actress, actress_id)

            ext = src.suffix.lower() or ".jpg"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target = profile_dir / f"{timestamp}_{src.stem}{ext}"

            with Image.open(src) as img:
                img = ImageOps.exif_transpose(img)
                img.thumbnail((800, 1200), Resampling.LANCZOS)
                img.save(target, quality=95, optimize=True)

            _clear_folder_except(profile_dir, keep=target)
            rel = _rel_data_path(target)
            actress.profile_image_url = rel
            actress.updated_at = datetime.now()
            session.commit()
            return target
    except Exception as e:
        print(f"[ActressProfile] promote_gallery_image_to_profile error: {e}")
        return None

def save_actress_image(
    actress_id: int,
    source_path: Path | str,
    is_profile: bool = False,
    caption: str = "",
    sort_order: int = 0,
    resize_profile: Tuple[int, int] = (800, 1200),
    max_gallery_size: int = 1200,
) -> Optional[Path]:
    """Save image to profile/ or gallery/ and update DB."""
    try:
        source_path = Path(source_path)
        if source_path.as_posix().startswith("file:"):
            from PySide6.QtCore import QUrl
            local = QUrl(str(source_path)).toLocalFile()
            if local:
                source_path = Path(local)
        if not source_path.exists():
            print(f"[ActressProfile] source not found: {source_path}")
            return None

        session = get_db_session()
        try:
            actress = session.query(Actress).filter_by(id=actress_id).first()
            if not actress:
                return None
        finally:
            session.close()

        _, profile_dir, gallery_dir = ensure_actress_media_dirs(actress, actress_id)
        subdir = profile_dir if is_profile else gallery_dir

        ext = source_path.suffix.lower() or ".jpg"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{source_path.stem}{ext}"
        target_path = subdir / filename

        with Image.open(source_path) as img:
            img = ImageOps.exif_transpose(img)
            if is_profile:
                img.thumbnail(resize_profile, Resampling.LANCZOS)
            elif max(img.size) > max_gallery_size:
                img.thumbnail((max_gallery_size, max_gallery_size), Resampling.LANCZOS)
            img.save(target_path, quality=95, optimize=True)

        rel = _rel_data_path(target_path)

        session = get_db_session()
        try:
            actress = session.query(Actress).filter_by(id=actress_id).first()
            if not actress:
                return None

            if is_profile:
                _clear_folder_except(subdir, keep=target_path)
                actress.profile_image_url = rel
                actress.updated_at = datetime.now()
            else:
                session.add(ActressImage(
                    actress_id=actress_id,
                    image_url=rel,
                    is_profile=False,
                    sort_order=sort_order,
                    caption=caption or "",
                ))
            session.commit()
        finally:
            session.close()

        return target_path

    except Exception as e:
        print(f"[ActressProfile] Failed to save image {source_path}: {e}")
        return None


def add_alias(actress_id: int, alias_name: str, alias_type: str = "stage", is_primary: bool = False) -> bool:
    """Add alias to actress_aliases table."""
    try:
        session = get_db_session()
        try:
            alias = ActressAlias(
                actress_id=actress_id,
                alias_name=alias_name.strip(),
                alias_type=alias_type,
                is_primary=is_primary,
            )
            session.add(alias)
            session.commit()
            return True
        finally:
            session.close()
    except Exception as e:
        print(f"[ActressProfile] Failed to add alias: {e}")
        return False


def _format_debut_ym(value) -> str:
    """Date/datetime/str → YYYY-MM 표시."""
    if not value:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m")
    s = str(value).strip()
    if len(s) >= 7 and s[4:5] == "-":
        return s[:7]
    return s


def parse_actor_tokens(*values: Optional[str]) -> List[str]:
    """actors_ko/ja/romaji CSV → 개별 배우 이름 토큰."""
    tokens: List[str] = []
    seen: set[str] = set()
    for val in values:
        raw = (val or "").strip()
        if not raw:
            continue
        for part in raw.split(","):
            token = part.strip()
            if not token:
                continue
            key = token.casefold()
            if key in seen:
                continue
            seen.add(key)
            tokens.append(token)
    return tokens


def normalize_actor_name_key(name: str) -> str:
    return (name or "").strip().casefold()


def actress_names_match_tokens(search_names: List[str], actor_tokens: List[str]) -> bool:
    """검색 이름과 작품 배우 토큰이 정확히 일치하는지 (부분 문자열 제외)."""
    search_keys = {
        normalize_actor_name_key(n)
        for n in (search_names or [])
        if normalize_actor_name_key(n)
    }
    if not search_keys:
        return False
    for token in actor_tokens or []:
        if normalize_actor_name_key(token) in search_keys:
            return True
    return False


def metadata_row_matches_actress(row, search_names: List[str]) -> bool:
    """JAVMetadata 행의 배우 목록에 해당 프로필 이름이 포함되는지."""
    tokens = parse_actor_tokens(
        getattr(row, "actors_ko", None),
        getattr(row, "actors_ja", None),
        getattr(row, "actors", None),
        getattr(row, "actors_romaji", None),
    )
    return actress_names_match_tokens(search_names, tokens)


def batch_actress_work_counts(session, actress_rows: list) -> dict[int, int]:
    """배우별 라이브러리 출연 작품 수 (품번 dedupe, 역인덱스 1-pass).

    메타데이터 전체 × 배우 전체 이중 루프 대신, 이름→배우ID 역인덱스로
    메타데이터를 한 번만 순회한다.
    """
    from javstory.harvest.database import JAVMetadata

    if not actress_rows:
        return {}

    name_to_ids: dict[str, set[int]] = {}
    actress_ids: list[int] = []
    for row in actress_rows:
        aid = row.id
        actress_ids.append(aid)
        for name in collect_actress_search_names(row):
            key = normalize_actor_name_key(name)
            if not key:
                continue
            name_to_ids.setdefault(key, set()).add(aid)

    counts = {aid: 0 for aid in actress_ids}
    seen: dict[int, set[str]] = {aid: set() for aid in actress_ids}

    meta_rows = session.query(
        JAVMetadata.product_code,
        JAVMetadata.actors_ko,
        JAVMetadata.actors_ja,
        JAVMetadata.actors,
        JAVMetadata.actors_romaji,
    ).all()

    for product_code, actors_ko, actors_ja, actors, actors_romaji in meta_rows:
        pc = (product_code or "").strip()
        if not pc:
            continue
        token_keys = {
            normalize_actor_name_key(t)
            for t in parse_actor_tokens(actors_ko, actors_ja, actors, actors_romaji)
        }
        token_keys.discard("")
        if not token_keys:
            continue

        matched: set[int] = set()
        for tk in token_keys:
            ids = name_to_ids.get(tk)
            if ids:
                matched.update(ids)
        if not matched:
            continue

        for aid in matched:
            if pc in seen[aid]:
                continue
            seen[aid].add(pc)
            counts[aid] += 1

    return counts


def fetch_actress_library_works(session, actress, max_items: int = 500) -> List[dict]:
    """배우 출연작 목록 — 정확 토큰 매칭, release_date 내림차순.

    ILIKE 선필터+상한(50) 방식은 합치기 후 이름·작품이 늘면
    흡수된 배우 작품이 후보 풀/상위 N에서 빠질 수 있어 전체 스캔한다.
    """
    from javstory.harvest.database import JAVMetadata

    names = collect_actress_search_names(actress)
    if not names:
        return []

    meta_rows = (
        session.query(JAVMetadata)
        .order_by(JAVMetadata.release_date.desc())
        .all()
    )

    seen: set[str] = set()
    items: List[dict] = []
    for row in meta_rows:
        if not metadata_row_matches_actress(row, names):
            continue
        pc = (row.product_code or "").strip()
        if not pc or pc in seen:
            continue
        seen.add(pc)
        items.append({
            "product_code": pc,
            "title_ko": row.title_ko or row.title or "",
            "titleKo": row.title_ko or row.title or "",
            "actors_ko": row.actors_ko or "",
            "actorsKo": row.actors_ko or "",
            "genres_ko": row.genres_ko or row.genres or "",
            "cover_path": row.cover_image_local_path or row.cover_image_url or "",
            "coverPath": row.cover_image_local_path or row.cover_image_url or "",
            "release_date": row.release_date or "",
            "scene_count": 0,
            "user_rating": 0,
            "userRating": 0,
            "user_liked": False,
            "favorite_score": int(getattr(row, "favorite_score", 0) or 0),
        })
        if len(items) >= max_items:
            break
    return items


def collect_actress_search_names(actress: Actress) -> List[str]:
    """작품 매칭용 이름 후보 (본명 + 별명)."""
    names: List[str] = []
    for val in (
        actress.name_ja, actress.japanese,
        actress.name_ko, actress.korean,
        actress.name_en, actress.romaji,
    ):
        v = (val or "").strip()
        if v and v not in names:
            names.append(v)
    for alias in actress.aliases or []:
        v = (alias.alias_name or "").strip()
        if v and v not in names:
            names.append(v)
    return names


def aggregate_work_genres(works: List[dict]) -> List[str]:
    """작품 genres_ko 집계 → 빈도 내림차순 장르 이름."""
    counts: dict[str, int] = {}
    for w in works:
        raw = (w.get("genres_ko") or "").strip()
        for g in raw.split(","):
            g = g.strip()
            if g:
                counts[g] = counts.get(g, 0) + 1
    return [name for name, _ in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]


def _ensure_alias(session, actress_id: int, alias_name: str, alias_type: str = "other") -> None:
    name = (alias_name or "").strip()
    if not name:
        return
    exists = session.query(ActressAlias).filter_by(
        actress_id=actress_id, alias_name=name
    ).first()
    if exists:
        return
    session.add(ActressAlias(
        actress_id=actress_id,
        alias_name=name,
        alias_type=alias_type,
        is_primary=False,
    ))


def _fill_if_empty(keep: Actress, merge: Actress, attr: str) -> None:
    if not hasattr(keep, attr) or not hasattr(merge, attr):
        return
    keep_val = getattr(keep, attr, None)
    merge_val = getattr(merge, attr, None)
    if keep_val in (None, "", 0) and merge_val not in (None, "", 0):
        setattr(keep, attr, merge_val)


def merge_actresses(keep_id: int, merge_id: int) -> bool:
    """keep_id 프로필에 merge_id를 흡수 후 merge 행 삭제."""
    if keep_id <= 0 or merge_id <= 0 or keep_id == merge_id:
        return False
    try:
        with get_db_session_ctx() as session:
            from sqlalchemy.orm import joinedload

            keep = session.query(Actress).filter_by(id=keep_id).first()
            merge = (
                session.query(Actress)
                .options(joinedload(Actress.aliases))
                .filter_by(id=merge_id)
                .first()
            )
            if not keep or not merge:
                return False

            merge_search_names = collect_actress_search_names(merge)

            session.query(ActressImage).filter_by(actress_id=merge_id).update(
                {"actress_id": keep_id}
            )

            for name in merge_search_names:
                _ensure_alias(session, keep_id, name, "other")

            for alias in session.query(ActressAlias).filter_by(actress_id=merge_id).all():
                session.delete(alias)

            for attr in (
                "name_ja", "name_ko", "name_en", "korean", "romaji",
                "profile_image_url", "profile_text", "genres", "memo", "agency", "cup_size",
                "birth_date", "debut_date", "height", "bust", "waist", "hip",
                "user_score", "favorite_intensity", "strong_reaction_count", "watch_count",
                "last_watched",
            ):
                _fill_if_empty(keep, merge, attr)

            if not keep.japanese and merge.japanese:
                keep.japanese = merge.japanese
            elif merge.japanese and merge.japanese != keep.japanese:
                _ensure_alias(session, keep_id, merge.japanese, "old")

            keep.is_favorite = bool(getattr(keep, "is_favorite", False) or getattr(merge, "is_favorite", False))
            ki = float(getattr(keep, "favorite_intensity") or 0.0)
            mi = float(getattr(merge, "favorite_intensity") or 0.0)
            keep.favorite_intensity = max(ki, mi) if (ki or mi) else None
            keep.updated_at = datetime.now()
            session.delete(merge)
            session.commit()
            return True
    except Exception as e:
        print(f"[ActressProfile] merge_actresses failed: {e}")
        return False


def get_favorite_actress_profiles(limit: int = 10) -> List[dict]:
    """즐겨찾기/관심도 상위 배우 프로필 요약."""
    try:
        with get_db_session_ctx() as session:
            rows = (
                session.query(Actress)
                .filter(
                    (Actress.is_favorite == True) |
                    (Actress.favorite_intensity.isnot(None))
                )
                .order_by(
                    Actress.is_favorite.desc(),
                    Actress.favorite_intensity.desc().nullslast(),
                    Actress.user_score.desc().nullslast(),
                )
                .limit(max(1, limit))
                .all()
            )
            out = []
            for r in rows:
                out.append({
                    "id": r.id,
                    "name": r.name_ko or r.korean or r.name_ja or r.japanese or "",
                    "name_ja": r.name_ja or r.japanese or "",
                    "genres": r.genres or "",
                    "memo": (r.memo or "")[:200],
                    "user_score": r.user_score or 0.0,
                    "favorite_intensity": r.favorite_intensity or 0.0,
                    "is_favorite": bool(r.is_favorite),
                })
            return out
    except Exception as e:
        print(f"[ActressProfile] get_favorite_actress_profiles error: {e}")
        return []


def get_actress_context_by_name(name: str) -> dict:
    """이름/별명으로 배우 컨텍스트 조회."""
    aid = resolve_actress_by_name(name)
    return get_actress_context(aid) if aid else {}


def get_actress_context(actress_id: int) -> dict:
    """Persona Chat / 추천 시스템용 배우 컨텍스트 반환.

    반환 키:
        name, name_ja, name_en, genres, memo, profile_text,
        user_score, favorite_intensity, is_favorite, aliases
    """
    try:
        with get_db_session_ctx() as session:
            row = session.query(Actress).filter_by(id=actress_id).first()
            if not row:
                return {}
            aliases = [a.alias_name for a in (row.aliases or [])]
            return {
                "name":               row.name_ko or row.korean or "",
                "name_ja":            row.name_ja or row.japanese or "",
                "name_en":            row.name_en or "",
                "romaji":             row.romaji or "",
                "genres":             row.genres or "",
                "memo":               row.memo or "",
                "profile_text":       row.profile_text or "",
                "user_score":         row.user_score or 0.0,
                "favorite_intensity": row.favorite_intensity or 0.0,
                "is_favorite":        bool(row.is_favorite),
                "aliases":            aliases,
                "agency":             row.agency or "",
            }
    except Exception as e:
        print(f"[ActressProfile] get_actress_context error: {e}")
        return {}


def resolve_actress_by_name(name: str) -> Optional[int]:
    """이름(한/일/영/별명)으로 actress_id 반환. 없으면 None."""
    if not name or not name.strip():
        return None
    q = name.strip()
    try:
        with get_db_session_ctx() as session:
            # 정확히 일치하는 행 먼저 탐색
            row = session.query(Actress).filter(
                (Actress.name_ko == q) |
                (Actress.korean == q) |
                (Actress.name_ja == q) |
                (Actress.japanese == q) |
                (Actress.name_en == q) |
                (Actress.romaji == q)
            ).first()
            if row:
                return row.id

            # 별명 테이블 탐색
            alias = session.query(ActressAlias).filter_by(alias_name=q).first()
            if alias:
                return alias.actress_id
    except Exception:
        pass
    return None


# Extend existing resolver (called from next step)
def extend_actress_resolver():
    """Future extension point for alias-aware resolution."""
    pass


if __name__ == "__main__":
    # Simple test
    print("Sanitize test:", sanitize_folder_name("미야무라 레이  (新垣 結衣)"))
    folder = get_actress_folder("Test Actress", create=False)
    print("Folder:", folder)
