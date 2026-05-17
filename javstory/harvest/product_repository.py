"""DB v2 P2 — products / video_files 듀얼라이트 (jav_metadata·L4와 동기화)."""

from __future__ import annotations

import datetime
import os
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session

from javstory.config.app_config import ENV_DB_V2_READ
from javstory.harvest.database import JAVMetadata, Product, VideoFile, get_db_session_ctx
from javstory.library.media_parts import build_video_part_refs


def normalize_sku(product_code: str) -> str:
    return (product_code or "").strip().upper()


def db_v2_read_enabled() -> bool:
    v = os.getenv(ENV_DB_V2_READ, "0").strip().lower()
    return v in ("1", "true", "yes", "on")


def _folder_path_from_db(sku: str) -> str | None:
    with get_db_session_ctx() as session:
        prod = session.query(Product).filter_by(sku=sku).first()
        if prod and (prod.folder_path or "").strip():
            return prod.folder_path
        row = session.query(JAVMetadata).filter_by(product_code=sku).first()
        if row and (row.folder_path or "").strip():
            return row.folder_path
    return None


def _paths_from_canonical(sku: str, folder_path: Path) -> list[Path]:
    try:
        from javstory.library.detail_persist import load_canonical_for_product
        from javstory.library.media_parts import part_refs_to_absolute_paths

        canon = load_canonical_for_product(sku)
        if canon.media and canon.media.parts:
            return [p for p in part_refs_to_absolute_paths(canon.media.parts, folder_path) if p.is_file()]
    except Exception:
        pass
    return []


def _paths_from_video_files(sku: str, folder_path: Path) -> list[Path]:
    with get_db_session_ctx() as session:
        prod = session.query(Product).filter_by(sku=sku).first()
        if not prod:
            return []
        root = folder_path.resolve()
        bind = (prod.folder_path or "").strip()
        if bind:
            try:
                root = Path(bind).resolve()
            except OSError:
                pass
        if not root.is_dir():
            return []
        rows = (
            session.query(VideoFile)
            .filter_by(product_id=prod.id)
            .order_by(VideoFile.part_order)
            .all()
        )
        out: list[Path] = []
        for vf in rows:
            rel = (vf.video_relpath or "").strip()
            if not rel:
                continue
            p = (root / rel).resolve()
            if p.is_file():
                out.append(p)
        return out


def resolve_video_paths_for_playback(
    product_code: str,
    folder_path: str | None = None,
) -> list[Path]:
    """
    재생·STT·자막 큐용 영상 경로 (읽기 SoT).
    L4 media.parts > L2 video_files (JAVSTORY_DB_V2_READ=1) > L1 video_discovery.
    """
    sku = normalize_sku(product_code)
    if not sku:
        return []
    fp = (folder_path or "").strip() or (_folder_path_from_db(sku) or "")
    root = Path(fp) if fp else None

    if root and root.is_dir():
        canon_paths = _paths_from_canonical(sku, root)
        if canon_paths:
            return canon_paths

    if db_v2_read_enabled() and root and root.is_dir():
        v2_paths = _paths_from_video_files(sku, root)
        if v2_paths:
            return v2_paths

    from javstory.library.video_discovery import find_all_video_paths_for_product

    return find_all_video_paths_for_product(sku, fp or None)


def resolve_primary_video_path(
    product_code: str,
    folder_path: str | None = None,
) -> Path | None:
    paths = resolve_video_paths_for_playback(product_code, folder_path)
    return paths[0] if paths else None


def sync_product_from_metadata_row(session: Session, row: JAVMetadata) -> Product | None:
    """jav_metadata 행에 대응하는 products 행 upsert."""
    if not row or not (row.product_code or "").strip():
        return None
    sku = normalize_sku(row.product_code)
    prod = session.query(Product).filter_by(sku=sku).one_or_none()
    now = datetime.datetime.now()
    if not prod:
        prod = Product(sku=sku, created_at=now)
        session.add(prod)
    prod.jav_metadata_id = row.id
    prod.folder_path = row.folder_path
    prod.updated_at = now
    session.flush()
    return prod


def set_folder_path(session: Session, product_code: str, folder_path: str | None) -> None:
    """jav_metadata.folder_path + products.folder_path 듀얼라이트."""
    sku = normalize_sku(product_code)
    row = session.query(JAVMetadata).filter_by(product_code=sku).first()
    if row:
        row.folder_path = folder_path
    prod = session.query(Product).filter_by(sku=sku).one_or_none()
    if row and not prod:
        prod = sync_product_from_metadata_row(session, row)
    elif prod:
        prod.folder_path = folder_path
        prod.updated_at = datetime.datetime.now()


def _file_fingerprint(path: Path) -> tuple[int | None, str | None]:
    try:
        if not path.is_file():
            return None, None
        st = path.stat()
        mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))
        return int(st.st_size), f"{mtime_ns}:{st.st_size}"
    except OSError:
        return None, None


def sync_video_files(
    session: Session,
    product_code: str,
    folder_path: str | Path,
    video_paths: list[Path],
) -> int:
    """품번의 video_files를 경로 목록으로 교체. 반환: 저장된 파트 수."""
    sku = normalize_sku(product_code)
    root = Path(folder_path)
    prod = session.query(Product).filter_by(sku=sku).one_or_none()
    if not prod:
        row = session.query(JAVMetadata).filter_by(product_code=sku).first()
        if not row:
            return 0
        prod = sync_product_from_metadata_row(session, row)
    session.query(VideoFile).filter_by(product_id=prod.id).delete(synchronize_session=False)
    if not root.is_dir() or not video_paths:
        session.flush()
        return 0
    refs, _ = build_video_part_refs(root, video_paths)
    now = datetime.datetime.now()
    for ref in refs:
        rel = (ref.video_relpath or "").replace("\\", "/")
        resolved = (root / rel).resolve() if rel else root
        size, fp = _file_fingerprint(resolved)
        session.add(
            VideoFile(
                product_id=prod.id,
                part_order=int(ref.order),
                video_relpath=rel,
                file_size=size,
                fingerprint=fp,
                created_at=now,
                updated_at=now,
            )
        )
    session.flush()
    return len(refs)


def clear_video_files_for_product(session: Session, product_code: str) -> None:
    sku = normalize_sku(product_code)
    prod = session.query(Product).filter_by(sku=sku).one_or_none()
    if prod:
        session.query(VideoFile).filter_by(product_id=prod.id).delete(
            synchronize_session=False
        )


def sync_video_files_standalone(
    product_code: str,
    folder_path: str | Path,
    video_paths: list[Path],
) -> int:
    with get_db_session_ctx() as session:
        n = sync_video_files(session, product_code, folder_path, video_paths)
        session.commit()
        return n


def sync_media_bundle(
    product_code: str,
    folder_path: str | Path,
    video_paths: list[Path],
) -> None:
    """L4 library_state media.parts + L2 video_files."""
    from javstory.library.media_parts import persist_media_parts_for_product

    pc = normalize_sku(product_code)
    root = Path(folder_path)
    paths = [p for p in video_paths if p.is_file()]
    if not pc or not root.is_dir() or not paths:
        return
    persist_media_parts_for_product(pc, root, paths)
    sync_video_files_standalone(pc, root, paths)


def get_video_absolute_paths(product_code: str) -> list[Path]:
    """`resolve_video_paths_for_playback` 별칭 (하위 호환)."""
    return resolve_video_paths_for_playback(product_code)


def _skip_boot_hydrate() -> bool:
    from javstory.config.app_config import ENV_SKIP_BOOT_HYDRATE

    v = os.getenv(ENV_SKIP_BOOT_HYDRATE, "0").strip().lower()
    return v in ("1", "true", "yes", "on")


def _hydrate_marker_path() -> Path:
    from javstory.config.app_config import PRODUCTS_V2_HYDRATE_MARKER

    return Path(PRODUCTS_V2_HYDRATE_MARKER)


def _write_hydrate_marker() -> None:
    p = _hydrate_marker_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("ok\n", encoding="utf-8")


def hydrate_all_products(
    session: Session,
    *,
    progress_every: int | None = None,
    log: Callable[[str], None] | None = None,
) -> tuple[int, int]:
    """jav_metadata 전체 -> products + (folder 있으면) video_files."""
    from javstory.config.app_config import HYDRATE_PROGRESS_EVERY
    from javstory.library.video_discovery import find_all_video_paths_for_product

    emit = log or print
    every = progress_every if progress_every is not None else HYDRATE_PROGRESS_EVERY
    rows = session.query(JAVMetadata).all()
    total = len(rows)
    if total == 0:
        return 0, 0
    emit(f"[DB] P2 hydrate: {total} works to process...")
    n_products = 0
    n_parts = 0
    for i, row in enumerate(rows, 1):
        sync_product_from_metadata_row(session, row)
        n_products += 1
        fp = (row.folder_path or "").strip()
        if fp:
            vps = find_all_video_paths_for_product(row.product_code, fp)
            if vps:
                n_parts += sync_video_files(session, row.product_code, fp, vps)
        if every > 0 and i % every == 0:
            emit(f"[DB] P2 hydrate progress: {i}/{total} products, {n_parts} video parts")
    return n_products, n_parts


def maybe_hydrate_products_v2() -> None:
    """products 비어 있고 jav_metadata 있으면 1회 backfill."""
    from javstory.harvest.database import is_db_read_only

    if is_db_read_only():
        print("[DB] P2 hydrate skipped: database read-only")
        return
    if _skip_boot_hydrate():
        from javstory.config.app_config import ENV_SKIP_BOOT_HYDRATE

        print(
            f"[DB] P2 hydrate skipped at boot ({ENV_SKIP_BOOT_HYDRATE}=1). "
            "Run: python tools/hydrate_products_v2.py"
        )
        return
    with get_db_session_ctx() as session:
        if session.query(Product).limit(1).first() is not None:
            return
        if session.query(JAVMetadata).limit(1).first() is None:
            return
        print("[DB] P2 hydrate: first run may take a while (disk scan per bound folder)...")
        n_products, n_parts = hydrate_all_products(session)
        session.commit()
        _write_hydrate_marker()
        print(f"[DB] P2 hydrate done: {n_products} products, {n_parts} video file parts")
