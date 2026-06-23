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
from javstory.harvest.database import get_db_session, get_db_session_ctx, Actress, ActressImage, ActressAlias, ActressWork


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
GALLERY_THUMB_SIZE = 256


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


def _gallery_thumb_path(full_path: Path) -> Path:
    return full_path.parent / "thumb" / full_path.name


def _write_gallery_thumb(full_path: Path, *, size: int = GALLERY_THUMB_SIZE) -> Optional[Path]:
    """gallery/ 원본 옆 gallery/thumb/ 에 썸네일 생성."""
    try:
        if not full_path.is_file():
            return None
        thumb_path = _gallery_thumb_path(full_path)
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(full_path) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((size, size), Resampling.LANCZOS)
            ext = full_path.suffix.lower()
            if ext == ".png":
                img.save(thumb_path, optimize=True)
            else:
                save_kwargs = {"quality": 85, "optimize": True}
                if ext not in (".jpg", ".jpeg"):
                    thumb_path = thumb_path.with_suffix(".jpg")
                img.convert("RGB").save(thumb_path, **save_kwargs)
        return thumb_path if thumb_path.is_file() else None
    except Exception as e:
        print(f"[ActressProfile] gallery thumb failed for {full_path}: {e}")
        return None


def _gallery_thumb_rel(full_path: Path) -> str:
    thumb = _gallery_thumb_path(full_path)
    if thumb.is_file():
        return _rel_data_path(thumb)
    return _rel_data_path(full_path)


def _gallery_entry_from_file(
    gf: Path,
    image_by_url: dict[str, ActressImage],
    sort_index: int,
) -> dict:
    rel = _rel_data_path(gf)
    row = image_by_url.get(rel)
    return {
        "image_id": int(row.image_id) if row else 0,
        "image_url": rel,
        "thumb_url": _gallery_thumb_rel(gf),
        "filename": gf.name,
        "sort_order": int(row.sort_order) if row else sort_index,
    }


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


def _normalize_image_url(url: str) -> str:
    return (url or "").replace("\\", "/")


def _resolve_profile_rel(
    actress: Actress,
    profile_dir: Path,
    profile_files: List[Path],
) -> str:
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
    return profile_rel


def _gallery_entries_from_files(
    gallery_files: List[Path],
    image_by_url: dict[str, ActressImage],
) -> tuple[List[dict], set[str]]:
    gallery_images: List[dict] = []
    valid_rels: set[str] = set()
    for i, gf in enumerate(gallery_files):
        rel = _rel_data_path(gf)
        valid_rels.add(rel)
        gallery_images.append(_gallery_entry_from_file(gf, image_by_url, i))
    return gallery_images, valid_rels


def _sync_actress_media_rows(
    session,
    actress: Actress,
    actress_id: int,
    profile_rel: str,
    gallery_files: List[Path],
    image_rows: List[ActressImage],
) -> List[dict]:
    """디스크 기준으로 ActressImage·profile_image_url 동기화 (쓰기 경로)."""
    image_by_url = {_normalize_image_url(r.image_url): r for r in image_rows}
    gallery_images: List[dict] = []
    valid_rels: set[str] = set()

    for i, gf in enumerate(gallery_files):
        rel = _rel_data_path(gf)
        valid_rels.add(rel)
        if not _gallery_thumb_path(gf).is_file():
            _write_gallery_thumb(gf)
        row = image_by_url.get(rel)
        if not row:
            row = ActressImage(
                actress_id=actress_id,
                image_url=rel,
                is_profile=False,
                sort_order=i,
            )
            session.add(row)
            session.flush()
            image_by_url[rel] = row
            image_rows.append(row)
        gallery_images.append(_gallery_entry_from_file(gf, image_by_url, i))

    for row in list(image_rows):
        url = _normalize_image_url(row.image_url)
        if url not in valid_rels or row.is_profile:
            session.delete(row)

    if profile_rel and profile_rel != (actress.profile_image_url or "").strip():
        actress.profile_image_url = profile_rel

    session.commit()
    return gallery_images


def load_actress_media(actress_id: int, *, sync_db: bool = False) -> dict:
    """profile/ · gallery/ 폴더에서 미디어 경로를 수집한다.

    sync_db=False(기본): 읽기 전용 — DB 일괄 조회, commit/insert/delete 없음.
    sync_db=True: 디스크와 actress_images·profile_image_url 동기화.
    """
    out = {"profile_image_url": "", "gallery_images": []}
    try:
        with get_db_session_ctx() as session:
            actress = session.query(Actress).filter_by(id=actress_id).first()
            if not actress:
                return out

            _, profile_dir, gallery_dir = find_actress_media_dirs(actress, actress_id)
            profile_files = _list_image_files(profile_dir)
            gallery_files = _list_image_files(gallery_dir)
            profile_rel = _resolve_profile_rel(actress, profile_dir, profile_files)

            image_rows = (
                session.query(ActressImage)
                .filter_by(actress_id=actress_id)
                .all()
            )
            image_by_url = {_normalize_image_url(r.image_url): r for r in image_rows}

            if sync_db:
                gallery_images = _sync_actress_media_rows(
                    session,
                    actress,
                    actress_id,
                    profile_rel,
                    gallery_files,
                    image_rows,
                )
            else:
                gallery_images, _ = _gallery_entries_from_files(
                    gallery_files, image_by_url
                )

            out["profile_image_url"] = profile_rel
            out["gallery_images"] = gallery_images
            return out
    except Exception as e:
        print(f"[ActressProfile] load_actress_media error: {e}")
        return out


def sync_actress_media_db(actress_id: int) -> dict:
    """디스크 ↔ DB 강제 동기화 (이미지 추가·삭제 후 등)."""
    return load_actress_media(actress_id, sync_db=True)


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
            saved = target

        sync_actress_media_db(actress_id)
        return saved
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

        if not is_profile:
            _write_gallery_thumb(target_path)

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

        sync_actress_media_db(actress_id)
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
            rebuild_actress_works_for_actress(session, actress_id, source="alias")
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


def _actress_works_index_ready(session) -> bool:
    return session.query(ActressWork.actress_id).limit(1).first() is not None


def _build_actress_name_index(session) -> dict[str, list[int]]:
    """정규화 이름 → actress_id 목록 (1-pass 역인덱스)."""
    from sqlalchemy.orm import joinedload

    index: dict[str, list[int]] = {}
    rows = session.query(Actress).options(joinedload(Actress.aliases)).all()
    for row in rows:
        aid = int(row.id)
        for name in collect_actress_search_names(row):
            key = normalize_actor_name_key(name)
            if not key:
                continue
            bucket = index.setdefault(key, [])
            if aid not in bucket:
                bucket.append(aid)
    return index


def _metadata_row_to_work_item(row) -> dict:
    pc = (row.product_code or "").strip()
    return {
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
    }


def refresh_actress_work_count(session, actress_id: int) -> int:
    """actress_works 집계 → actresses.work_count 캐시 갱신."""
    from sqlalchemy import func

    aid = int(actress_id or 0)
    if aid <= 0:
        return 0
    count = (
        session.query(func.count(ActressWork.product_code))
        .filter(ActressWork.actress_id == aid)
        .scalar()
    ) or 0
    now = datetime.now()
    session.query(Actress).filter_by(id=aid).update(
        {"work_count": int(count), "works_updated_at": now},
        synchronize_session=False,
    )
    return int(count)


def refresh_actress_work_counts(session, actress_ids) -> None:
    """여러 배우 work_count 캐시 갱신."""
    ids = {int(i) for i in (actress_ids or []) if int(i or 0) > 0}
    for aid in ids:
        refresh_actress_work_count(session, aid)


def refresh_all_actress_work_counts(session) -> int:
    """전체 배우 work_count 캐시 백필 (actress_works GROUP BY)."""
    from sqlalchemy import func

    now = datetime.now()
    count_rows = (
        session.query(ActressWork.actress_id, func.count(ActressWork.product_code))
        .group_by(ActressWork.actress_id)
        .all()
    )
    count_map = {int(aid): int(cnt or 0) for aid, cnt in count_rows}
    updated = 0
    for (aid,) in session.query(Actress.id).all():
        aid = int(aid)
        session.query(Actress).filter_by(id=aid).update(
            {"work_count": count_map.get(aid, 0), "works_updated_at": now},
            synchronize_session=False,
        )
        updated += 1
    return updated


def sync_actress_works_for_product(session, product_code: str, *, source: str = "harvest") -> int:
    """품번 기준 actress_works 갱신 (harvest/resync)."""
    from javstory.harvest.database import JAVMetadata

    pc = (product_code or "").strip().upper()
    if not pc:
        return 0

    old_ids = {
        int(r[0])
        for r in session.query(ActressWork.actress_id).filter_by(product_code=pc).all()
    }
    session.query(ActressWork).filter_by(product_code=pc).delete(synchronize_session=False)
    row = session.query(JAVMetadata).filter_by(product_code=pc).first()
    if not row:
        refresh_actress_work_counts(session, old_ids)
        return 0

    tokens = parse_actor_tokens(
        row.actors_ko, row.actors_ja, row.actors, row.actors_romaji
    )
    if not tokens:
        refresh_actress_work_counts(session, old_ids)
        return 0

    name_index = _build_actress_name_index(session)
    now = datetime.now()
    added = 0
    linked: set[int] = set()

    for token in tokens:
        key = normalize_actor_name_key(token)
        if not key:
            continue
        for actress_id in name_index.get(key, []):
            if actress_id in linked:
                continue
            linked.add(actress_id)
            session.add(ActressWork(
                actress_id=actress_id,
                product_code=pc,
                match_source=source,
                matched_token=token,
                updated_at=now,
            ))
            added += 1
    refresh_actress_work_counts(session, old_ids | linked)
    return added


def rebuild_actress_works_for_actress(session, actress_id: int, *, source: str = "scan") -> int:
    """단일 배우의 actress_works 전체 재구축 (이름·별명·합치기 후).

    jav_metadata 전체를 한 번에 메모리에 올리지 않고 ID 청크 단위로 스캔해
    UI·DB 락 점유 시간을 줄인다.
    """
    from sqlalchemy.orm import joinedload
    from javstory.harvest.database import JAVMetadata

    actress = (
        session.query(Actress)
        .options(joinedload(Actress.aliases))
        .filter_by(id=actress_id)
        .first()
    )
    if not actress:
        return 0

    names = collect_actress_search_names(actress)
    session.query(ActressWork).filter_by(actress_id=actress_id).delete(synchronize_session=False)
    if not names:
        refresh_actress_work_count(session, actress_id)
        session.commit()
        return 0

    search_keys = {
        normalize_actor_name_key(n)
        for n in names
        if normalize_actor_name_key(n)
    }
    now = datetime.now()
    added = 0
    last_id = 0
    chunk_size = 200

    while True:
        ids = [
            r[0]
            for r in session.query(JAVMetadata.id)
            .filter(JAVMetadata.id > last_id)
            .order_by(JAVMetadata.id.asc())
            .limit(chunk_size)
            .all()
        ]
        if not ids:
            break
        last_id = int(ids[-1] or last_id)

        for mid in ids:
            row = session.query(JAVMetadata).filter_by(id=mid).first()
            if not row:
                continue
            if not metadata_row_matches_actress(row, names):
                continue
            pc = (row.product_code or "").strip().upper()
            if not pc:
                continue
            matched_token = ""
            for token in parse_actor_tokens(
                row.actors_ko, row.actors_ja, row.actors, row.actors_romaji
            ):
                if normalize_actor_name_key(token) in search_keys:
                    matched_token = token
                    break
            session.add(ActressWork(
                actress_id=int(actress_id),
                product_code=pc,
                match_source=source,
                matched_token=matched_token,
                updated_at=now,
            ))
            added += 1
        session.commit()

    refresh_actress_work_count(session, actress_id)
    session.commit()
    return added


def rebuild_all_actress_works(session, *, source: str = "scan") -> int:
    """전체 jav_metadata 스캔으로 actress_works 백필."""
    from javstory.harvest.database import JAVMetadata

    session.query(ActressWork).delete(synchronize_session=False)
    name_index = _build_actress_name_index(session)
    now = datetime.now()
    total = 0

    for row in session.query(JAVMetadata).all():
        pc = (row.product_code or "").strip().upper()
        if not pc:
            continue
        tokens = parse_actor_tokens(
            row.actors_ko, row.actors_ja, row.actors, row.actors_romaji
        )
        if not tokens:
            continue
        linked: set[int] = set()
        for token in tokens:
            key = normalize_actor_name_key(token)
            if not key:
                continue
            for actress_id in name_index.get(key, []):
                if actress_id in linked:
                    continue
                linked.add(actress_id)
                session.add(ActressWork(
                    actress_id=actress_id,
                    product_code=pc,
                    match_source=source,
                    matched_token=token,
                    updated_at=now,
                ))
                total += 1
    refresh_all_actress_work_counts(session)
    return total


def _batch_actress_work_counts_legacy(session, actress_rows: list) -> dict[int, int]:
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


def _batch_actress_work_counts_indexed(session, actress_rows: list) -> dict[int, int]:
    from sqlalchemy import func

    if not actress_rows:
        return {}
    actress_ids = [int(r.id) for r in actress_rows]
    counts = {aid: 0 for aid in actress_ids}
    rows = (
        session.query(ActressWork.actress_id, func.count(ActressWork.product_code))
        .filter(ActressWork.actress_id.in_(actress_ids))
        .group_by(ActressWork.actress_id)
        .all()
    )
    for aid, cnt in rows:
        counts[int(aid)] = int(cnt or 0)
    return counts


def batch_actress_work_counts(session, actress_rows: list) -> dict[int, int]:
    """배우별 라이브러리 출연 작품 수."""
    if _actress_works_index_ready(session):
        return _batch_actress_work_counts_indexed(session, actress_rows)
    return _batch_actress_work_counts_legacy(session, actress_rows)


def _fetch_actress_library_works_legacy(session, actress, max_items: int = 500) -> List[dict]:
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


def _fetch_actress_library_works_indexed(session, actress, max_items: int = 500) -> List[dict]:
    from javstory.harvest.database import JAVMetadata

    aid = int(getattr(actress, "id", 0) or 0)
    if aid <= 0:
        return []

    rows = (
        session.query(JAVMetadata)
        .join(ActressWork, ActressWork.product_code == JAVMetadata.product_code)
        .filter(ActressWork.actress_id == aid)
        .order_by(JAVMetadata.release_date.desc())
        .limit(max_items)
        .all()
    )
    return [_metadata_row_to_work_item(row) for row in rows]


def fetch_actress_library_works(session, actress, max_items: int = 500) -> List[dict]:
    """배우 출연작 목록 — actress_works 인덱스 우선, 없으면 레거시 스캔."""
    if _actress_works_index_ready(session):
        return _fetch_actress_library_works_indexed(session, actress, max_items)
    return _fetch_actress_library_works_legacy(session, actress, max_items)


def verify_actress_works_backfill(
    session,
    *,
    sample_limit: int | None = None,
) -> dict:
    """백필 검증 — 레거시 스캔 vs actress_works·work_count 캐시.

    Returns:
        dict: checked, count_mismatches, works_mismatches, cache_mismatches, ok
    """
    from sqlalchemy.orm import joinedload

    qry = session.query(Actress).options(joinedload(Actress.aliases)).order_by(Actress.id.asc())
    if sample_limit is not None and int(sample_limit) > 0:
        qry = qry.limit(int(sample_limit))
    rows = qry.all()
    if not rows:
        return {
            "checked": 0,
            "count_mismatches": [],
            "works_mismatches": [],
            "cache_mismatches": [],
            "ok": True,
        }

    actress_ids = [int(r.id) for r in rows]
    id_set = set(actress_ids)

    indexed_pcs_by_aid: dict[int, set[str]] = {aid: set() for aid in actress_ids}
    for aid, pc in session.query(ActressWork.actress_id, ActressWork.product_code).filter(
        ActressWork.actress_id.in_(actress_ids)
    ).all():
        aid = int(aid)
        if aid not in id_set:
            continue
        code = (pc or "").strip().upper()
        if code:
            indexed_pcs_by_aid[aid].add(code)

    legacy_pcs_by_aid: dict[int, set[str]] = {aid: set() for aid in actress_ids}
    name_to_ids: dict[str, set[int]] = {}
    for row in rows:
        aid = int(row.id)
        for name in collect_actress_search_names(row):
            key = normalize_actor_name_key(name)
            if not key:
                continue
            name_to_ids.setdefault(key, set()).add(aid)

    from javstory.harvest.database import JAVMetadata

    for meta in session.query(JAVMetadata).all():
        pc = (meta.product_code or "").strip().upper()
        if not pc:
            continue
        matched: set[int] = set()
        for token in parse_actor_tokens(
            meta.actors_ko, meta.actors_ja, meta.actors, meta.actors_romaji
        ):
            key = normalize_actor_name_key(token)
            if not key:
                continue
            matched.update(name_to_ids.get(key, set()))
        for aid in matched:
            if aid in legacy_pcs_by_aid:
                legacy_pcs_by_aid[aid].add(pc)

    count_mismatches: list[dict] = []
    works_mismatches: list[dict] = []
    cache_mismatches: list[dict] = []

    for row in rows:
        aid = int(row.id)
        legacy_cnt = len(legacy_pcs_by_aid.get(aid, set()))
        indexed_cnt = len(indexed_pcs_by_aid.get(aid, set()))
        cached_cnt = int(getattr(row, "work_count", 0) or 0)

        if legacy_cnt != indexed_cnt:
            count_mismatches.append({
                "actress_id": aid,
                "legacy": legacy_cnt,
                "indexed": indexed_cnt,
            })

        if cached_cnt != indexed_cnt:
            cache_mismatches.append({
                "actress_id": aid,
                "cached": cached_cnt,
                "indexed": indexed_cnt,
            })

        legacy_pcs = legacy_pcs_by_aid.get(aid, set())
        indexed_pcs = indexed_pcs_by_aid.get(aid, set())
        if legacy_pcs != indexed_pcs:
            works_mismatches.append({
                "actress_id": aid,
                "legacy_only": sorted(legacy_pcs - indexed_pcs)[:5],
                "indexed_only": sorted(indexed_pcs - legacy_pcs)[:5],
                "legacy_total": len(legacy_pcs),
                "indexed_total": len(indexed_pcs),
            })

    ok = not count_mismatches and not works_mismatches and not cache_mismatches
    return {
        "checked": len(rows),
        "count_mismatches": count_mismatches,
        "works_mismatches": works_mismatches,
        "cache_mismatches": cache_mismatches,
        "ok": ok,
    }


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
            rebuild_actress_works_for_actress(session, keep_id, source="merge")
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
                "id":                 row.id,
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
                "work_count":         int(getattr(row, "work_count", 0) or 0),
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
