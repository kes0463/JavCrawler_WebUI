"""표지 로컬 경로 해석 및 다운로드 — core/image_handler·assets_handler 래핑."""

from __future__ import annotations

from pathlib import Path

from javstory.config import app_config


def _media_root() -> Path:
    """테스트에서 app_config.MEDIA_ROOT를 바꿀 수 있도록 런타임 조회."""
    return app_config.MEDIA_ROOT


def resolve_cover_path(product_code: str, cover_local_path: str | None = None) -> Path | None:
    """
    DB의 cover_local_path가 유효하면 우선.
    그다음 `data/media/{품번}/` 아래 cover.jpg → poster.jpg → thumb.jpg 순.
    """
    pc = (product_code or "").strip().upper()
    if not pc:
        return None
    if cover_local_path:
        p = Path(cover_local_path).expanduser()
        if p.is_file() and p.stat().st_size > 0:
            return p.resolve()
    base = _media_root() / pc
    for name in ("cover.jpg", "poster.jpg", "thumb.jpg"):
        cand = base / name
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
