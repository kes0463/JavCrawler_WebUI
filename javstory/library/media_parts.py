"""canonical `media.parts` ↔ 로컬 분할 영상 경로 동기화."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from javstory.library.canonical.schema import LibraryCanonical, MediaBinding, VideoPartRef
from javstory.library.multipart.detect import sort_video_parts


def build_video_part_refs(
    folder_path: Path,
    video_paths: list[Path],
) -> tuple[list[VideoPartRef], str | None]:
    """바인딩 폴더 기준 상대 경로로 `VideoPartRef` 목록과 primary relpath를 만든다."""
    root = folder_path.resolve()
    sorted_paths = sort_video_parts([p.resolve() for p in video_paths if p.is_file()])
    refs: list[VideoPartRef] = []
    primary: str | None = None
    for i, p in enumerate(sorted_paths):
        try:
            rel = p.relative_to(root)
            relpath = str(rel).replace("\\", "/")
        except ValueError:
            relpath = p.name
        if i == 0:
            primary = relpath
        refs.append(VideoPartRef(order=i, video_relpath=relpath))
    return refs, primary


def part_refs_to_absolute_paths(parts: list[VideoPartRef], folder_path: Path) -> list[Path]:
    """canonical parts 순서대로 절대 경로 복원(존재하는 파일만)."""
    root = folder_path.resolve()
    ordered = sorted(parts, key=lambda x: int(x.order))
    out: list[Path] = []
    for pr in ordered:
        rel = (pr.video_relpath or "").strip()
        if not rel:
            continue
        p = (root / rel).resolve()
        if p.is_file():
            out.append(p)
    return out


def sync_canonical_media_parts(
    state: LibraryCanonical,
    *,
    folder_path: str | Path,
    video_paths: list[Path] | None = None,
) -> LibraryCanonical:
    """`media.parts`·`primary_video_relpath`를 폴더 내 영상 목록과 맞춘다."""
    root = Path(folder_path)
    if not root.is_dir():
        return state
    paths = list(video_paths or [])
    if not paths:
        return state
    refs, primary = build_video_part_refs(root, paths)
    if not refs:
        return state
    media = state.media if state.media is not None else MediaBinding()
    media = replace(
        media,
        parts=refs,
        primary_video_relpath=primary,
    )
    return replace(state, media=media)


def persist_media_parts_for_product(
    product_code: str,
    folder_path: str | Path,
    video_paths: list[Path] | None = None,
) -> None:
    """library_state.json에 분할 파트 목록을 기록한다."""
    from javstory.library.canonical.store import load_library_state, save_library_state
    from javstory.library.detail_persist import load_canonical_for_product
    from javstory.library.paths import library_state_path

    pc = (product_code or "").strip().upper()
    if not pc:
        return
    root = Path(folder_path)
    if not root.is_dir():
        return

    paths = list(video_paths or [])
    if not paths:
        return

    ls_path = library_state_path(pc)
    if ls_path.is_file():
        state = load_library_state(ls_path)
    else:
        state = load_canonical_for_product(pc)
    state.product_code = pc
    state = sync_canonical_media_parts(state, folder_path=root, video_paths=paths)
    ls_path.parent.mkdir(parents=True, exist_ok=True)
    save_library_state(ls_path, state)
