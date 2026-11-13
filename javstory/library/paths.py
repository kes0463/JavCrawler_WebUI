"""라이브러리 루트 경로 — %LOCALAPPDATA%\\JAVSTORY\\Library\\ 및 JAVSTORY_LIBRARY_ROOT."""

from __future__ import annotations

import os
import re
from pathlib import Path

_ENV_LIBRARY_ROOT = "JAVSTORY_LIBRARY_ROOT"
_SAFE_CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def require_safe_code(code: str) -> str:
    """품번을 폴더 이름으로 쓰기 전 검사 — URL 의 `..\\` 등으로 미디어 루트 밖을 가리키지 못하게."""
    if not _SAFE_CODE.fullmatch(code or ""):
        raise ValueError(f"잘못된 품번: {code!r}")
    return code


def default_library_root() -> Path:
    """Windows 기본: %LOCALAPPDATA%\\JAVSTORY\\Library\\"""
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "JAVSTORY" / "Library"
    return Path.home() / ".javstory" / "Library"


def library_root() -> Path:
    """환경변수 JAVSTORY_LIBRARY_ROOT가 있으면 그 경로, 없으면 default_library_root()."""
    override = os.environ.get(_ENV_LIBRARY_ROOT, "").strip()
    if override:
        return Path(override).expanduser()
    return default_library_root()


def work_library_dir(product_code: str, *, root: Path | None = None) -> Path:
    """품번별 작품 폴더: {library_root}/{품번}/"""
    code = (product_code or "").strip().upper().replace(" ", "")
    if not code:
        raise ValueError("product_code가 비어 있습니다.")
    base = root if root is not None else library_root()
    return base / require_safe_code(code)


def library_state_path(product_code: str, *, root: Path | None = None) -> Path:
    """canonical 단일 파일 경로: {work}/library_state.json"""
    return work_library_dir(product_code, root=root) / "library_state.json"


def stills_dir(product_code: str, *, root: Path | None = None) -> Path:
    return work_library_dir(product_code, root=root) / "stills"
