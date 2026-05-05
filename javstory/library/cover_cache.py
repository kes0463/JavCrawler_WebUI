"""표지 로컬 경로 해석 및 다운로드 — core/image_handler·assets_handler 래핑."""

from __future__ import annotations

import os
from pathlib import Path

from javstory.config import app_config


def _cover_search_roots() -> list[Path]:
    """
    표지 파일 탐색 루트(중복 경로 제거).
    - JAVSTORY_MEDIA_ROOT: 설정에서 지정한 미디어 루트
    - E_MEDIA_ROOT: data/works (품번 폴더 직하에 cover.jpg 두는 경우)
    - MEDIA_ROOT: 레거시 data/media/{품번}/
    """
    roots: list[Path] = []
    seen: set[str] = set()

    def add(p: Path | None) -> None:
        if p is None:
            return
        try:
            rp = Path(p).expanduser().resolve()
        except Exception:
            rp = Path(p).expanduser()
        key = str(rp).lower()
        if key in seen:
            return
        seen.add(key)
        roots.append(rp)

    env = (os.environ.get("JAVSTORY_MEDIA_ROOT") or "").strip()
    if env:
        add(Path(env))
    try:
        add(getattr(app_config, "E_MEDIA_ROOT", None))
    except Exception:
        pass
    add(app_config.MEDIA_ROOT)
    return roots


def resolve_cover_path(product_code: str, cover_local_path: str | None = None) -> Path | None:
    """
    DB의 cover_local_path가 유효하면 우선.
    그다음 각 미디어 루트 아래 `{품번}/cover.jpg` → `poster.jpg` → `thumb.jpg` 순으로 탐색.
    (`works/{품번}/cover.jpg` 는 E_MEDIA_ROOT·JAVSTORY_MEDIA_ROOT 쪽에 해당)
    """
    pc = (product_code or "").strip().upper()
    if not pc:
        return None
    if cover_local_path:
        p = Path(cover_local_path).expanduser()
        if p.is_file() and p.stat().st_size > 0:
            return p.resolve()
    names = ("cover.jpg", "poster.jpg", "thumb.jpg")
    for root in _cover_search_roots():
        for name in names:
            cand = root / pc / name
            if cand.is_file() and cand.stat().st_size > 0:
                return cand.resolve()
    return None


def cover_needs_download(
    product_code: str,
    cover_url: str | None,
    cover_local_path: str | None = None,
) -> bool:
    """로컬 표지가 없고 URL이 있으면 True."""
    if resolve_cover_path(product_code, cover_local_path):
        return False
    url = (cover_url or "").strip()
    if not url or url == "이미지 누락":
        return False
    return True


async def ensure_cover_cached(product_code: str, cover_url: str) -> Path | None:
    """httpx 비동기 다운로드 — cover.jpg 저장."""
    if not cover_needs_download(product_code, cover_url):
        return resolve_cover_path(product_code)
    from javstory.utils.assets_handler import MetadataAssetsHandler

    handler = MetadataAssetsHandler()
    path = await handler.download_cover_image(cover_url, product_code)
    if path:
        return Path(path).resolve()
    return resolve_cover_path(product_code)


def ensure_cover_cached_sync(product_code: str, cover_url: str) -> Path | None:
    """동기: ImageHandler로 poster/thumb 채운 뒤 resolve."""
    if not cover_needs_download(product_code, cover_url):
        return resolve_cover_path(product_code)
    from javstory.utils.image_handler import ImageHandler

    ImageHandler().process_jav_assets(product_code, cover_url)
    return resolve_cover_path(product_code)
