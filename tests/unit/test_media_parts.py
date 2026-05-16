"""media.parts 빌드·복원·canonical 동기화."""

from __future__ import annotations

from pathlib import Path

from javstory.library.canonical.schema import LibraryCanonical, VideoPartRef
from javstory.library.media_parts import (
    build_video_part_refs,
    part_refs_to_absolute_paths,
    sync_canonical_media_parts,
)


def test_build_video_part_refs_relative_paths_and_order(tmp_path: Path) -> None:
    root = tmp_path / "bind"
    root.mkdir()
    p2 = root / "work_PART2.mp4"
    p1 = root / "work_PART1.mp4"
    for p in (p1, p2):
        p.write_bytes(b"x")

    refs, primary = build_video_part_refs(root, [p2, p1])
    assert primary == "work_PART1.mp4"
    assert len(refs) == 2
    assert refs[0].order == 0
    assert refs[0].video_relpath == "work_PART1.mp4"
    assert refs[1].video_relpath == "work_PART2.mp4"


def test_part_refs_to_absolute_paths_respects_order(tmp_path: Path) -> None:
    root = tmp_path / "bind"
    root.mkdir()
    a = root / "a.mp4"
    b = root / "b.mp4"
    a.write_bytes(b"1")
    b.write_bytes(b"2")
    parts = [
        VideoPartRef(order=1, video_relpath="b.mp4"),
        VideoPartRef(order=0, video_relpath="a.mp4"),
    ]
    paths = part_refs_to_absolute_paths(parts, root)
    assert [p.name for p in paths] == ["a.mp4", "b.mp4"]


def test_sync_canonical_media_parts_updates_binding(tmp_path: Path) -> None:
    root = tmp_path / "SKU-100"
    root.mkdir()
    v1 = root / "SKU-100_A.mp4"
    v2 = root / "SKU-100_B.mp4"
    v1.write_bytes(b"a")
    v2.write_bytes(b"b")

    state = LibraryCanonical(product_code="SKU-100")
    out = sync_canonical_media_parts(state, folder_path=root, video_paths=[v2, v1])
    assert out.media.primary_video_relpath == "SKU-100_A.mp4"
    assert len(out.media.parts) == 2
    assert out.media.parts[1].video_relpath == "SKU-100_B.mp4"
