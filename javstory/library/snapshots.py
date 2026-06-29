"""작품 스냅샷(스틸) 이미지 경로 탐색."""

from __future__ import annotations

import json
from pathlib import Path

from javstory.config.app_config import DATA_ROOT, E_DATA_ROOT, E_MEDIA_ROOT, MEDIA_ROOT
from javstory.library.paths import library_state_path, work_library_dir

_COVER_NAMES = frozenset({
    "cover.jpg",
    "poster.jpg",
    "thumb.jpg",
    "cover.png",
    "poster.png",
    "cover.webp",
    "poster.webp",
})
_IMAGE_EXTS = ("*.jpg", "*.jpeg", "*.png", "*.webp")


def _media_bases(product_code: str) -> list[Path]:
    pc = (product_code or "").strip().upper()
    bases: list[Path] = []
    seen: set[str] = set()

    def _add(p: Path) -> None:
        try:
            key = str(p.resolve()).lower()
        except OSError:
            key = str(p).lower()
        if key in seen:
            return
        seen.add(key)
        if p.is_dir():
            bases.append(p)

    for base in (
        Path(E_MEDIA_ROOT) / pc,
        Path(E_DATA_ROOT) / pc,
        Path(E_DATA_ROOT) / "media" / pc,
        Path(DATA_ROOT) / "media" / pc,
        work_library_dir(pc),
    ):
        _add(base)
    return bases


def _collect_images_from_dir(directory: Path, *, recursive: bool = False) -> list[Path]:
    found: list[Path] = []
    try:
        if not directory.is_dir():
            return found
        if recursive:
            for ext in _IMAGE_EXTS:
                found.extend(directory.rglob(ext.lstrip("*")))
        else:
            for ext in _IMAGE_EXTS:
                found.extend(directory.glob(ext))
    except OSError:
        return found
    return found


def _canonical_scene_stills(product_code: str) -> list[Path]:
    pc = (product_code or "").strip().upper()
    if not pc:
        return []
    out: list[Path] = []
    try:
        state_path = library_state_path(pc)
        work = work_library_dir(pc)
        if not state_path.is_file():
            return out
        data = json.loads(state_path.read_text(encoding="utf-8"))
        for scene in data.get("scenes") or []:
            if not isinstance(scene, dict):
                continue
            for raw in scene.get("still_paths") or []:
                rel = Path(str(raw))
                cand = rel if rel.is_absolute() else (work / rel)
                if cand.is_file():
                    out.append(cand.resolve())
    except Exception:
        pass
    return out


def discover_snapshot_paths(
    product_code: str,
    *,
    folder_path: str | None = None,
) -> list[Path]:
    """스냅샷·씬 스틸 이미지 절대 경로 목록(정렬)."""
    stills: dict[str, Path] = {}

    def _add(path: Path) -> None:
        try:
            resolved = path.resolve()
        except OSError:
            return
        if not resolved.is_file():
            return
        if resolved.name.lower() in _COVER_NAMES:
            return
        stills[str(resolved).lower()] = resolved

    for p in _canonical_scene_stills(product_code):
        _add(p)

    for base in _media_bases(product_code):
        snap_dir = base / "Snapshots"
        if snap_dir.is_dir():
            for f in _collect_images_from_dir(snap_dir):
                _add(f)
        else:
            for f in _collect_images_from_dir(base, recursive=False):
                _add(f)
        stills_dir = base / "stills"
        if stills_dir.is_dir():
            for f in _collect_images_from_dir(stills_dir, recursive=True):
                _add(f)

    bound = (folder_path or "").strip()
    if bound:
        root = Path(bound)
        if root.is_dir():
            snap_dir = root / "Snapshots"
            if snap_dir.is_dir():
                for f in _collect_images_from_dir(snap_dir):
                    _add(f)

    return sorted(stills.values(), key=lambda p: p.name.lower())
