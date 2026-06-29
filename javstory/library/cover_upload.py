"""라이브러리 작품 표지 — 로컬 파일 저장·DB 반영."""

from __future__ import annotations

import shutil
from pathlib import Path

_ALLOWED_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})


def save_cover_image(product_code: str, source_path: str | Path) -> Path:
    """업로드/임시 파일을 미디어 루트 `{품번}/poster.jpg` 등으로 복사."""
    from javstory.utils.image_handler import ImageHandler

    pc = (product_code or "").strip().upper()
    if not pc:
        raise ValueError("품번이 필요합니다.")

    src = Path(source_path)
    if not src.is_file():
        raise ValueError("이미지 파일을 찾을 수 없습니다.")

    ext = src.suffix.lower()
    if ext not in _ALLOWED_SUFFIXES:
        raise ValueError("지원 형식: JPG, PNG, WEBP, GIF")

    handler = ImageHandler()
    p_dir = handler.get_product_dir(pc)
    poster = p_dir / "poster.jpg"
    cover = p_dir / "cover.jpg"
    thumb = p_dir / "thumb.jpg"

    shutil.copy2(src, poster)
    shutil.copy2(src, cover)
    shutil.copy2(src, thumb)

    return poster.resolve()


def persist_cover_paths(product_code: str, poster_path: str | Path) -> str:
    """jav_metadata + file_flag_cache에 표지 경로 반영."""
    import datetime

    from javstory.harvest.database import JAVMetadata, commit_with_retry, get_db_session_ctx
    from javstory.library.file_flag_scanner import upsert_one_flag

    pc = (product_code or "").strip().upper()
    poster = Path(poster_path).resolve()
    thumb = poster.parent / "thumb.jpg"
    local = str(poster)

    with get_db_session_ctx() as db:
        row = db.query(JAVMetadata).filter_by(product_code=pc).first()
        if not row:
            raise ValueError(f"DB에 품번 {pc}가 없습니다.")
        row.cover_image_local_path = local
        if thumb.is_file():
            row.thumb_image_local_path = str(thumb.resolve())
        row.updated_at = datetime.datetime.now()
        folder_path = row.folder_path
        is_hardcoded = bool(row.is_hardcoded)
        commit_with_retry(db)

    upsert_one_flag(pc, folder_path, is_hardcoded)
    return local
