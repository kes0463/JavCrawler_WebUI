"""discover_snapshot_paths 단위 테스트."""

from __future__ import annotations

from pathlib import Path

from javstory.library.snapshots import discover_snapshot_paths


def test_discover_snapshots_from_snapshots_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "javstory.library.snapshots.E_MEDIA_ROOT",
        tmp_path / "media",
    )
    monkeypatch.setattr("javstory.library.snapshots.E_DATA_ROOT", tmp_path / "edata")
    monkeypatch.setattr("javstory.library.snapshots.DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(
        "javstory.library.snapshots.work_library_dir",
        lambda pc: tmp_path / "library" / pc,
    )
    monkeypatch.setattr(
        "javstory.library.snapshots.library_state_path",
        lambda pc: tmp_path / "library" / pc / "library_state.json",
    )

    snap_dir = tmp_path / "media" / "ABC-123" / "Snapshots"
    snap_dir.mkdir(parents=True)
    (snap_dir / "snapshot_001.jpg").write_bytes(b"jpeg")
    (snap_dir / "snapshot_002.jpg").write_bytes(b"jpeg")
    (snap_dir / "cover.jpg").write_bytes(b"jpeg")

    paths = discover_snapshot_paths("ABC-123")
    assert len(paths) == 2
    assert paths[0].name == "snapshot_001.jpg"


def test_discover_snapshots_from_bound_folder(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "javstory.library.snapshots.E_MEDIA_ROOT",
        tmp_path / "media",
    )
    monkeypatch.setattr("javstory.library.snapshots.E_DATA_ROOT", tmp_path / "edata")
    monkeypatch.setattr("javstory.library.snapshots.DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(
        "javstory.library.snapshots.work_library_dir",
        lambda pc: tmp_path / "library" / pc,
    )
    monkeypatch.setattr(
        "javstory.library.snapshots.library_state_path",
        lambda pc: tmp_path / "library" / pc / "library_state.json",
    )

    bound = tmp_path / "bound" / "ABC-123"
    snap = bound / "Snapshots"
    snap.mkdir(parents=True)
    (snap / "shot.png").write_bytes(b"png")

    paths = discover_snapshot_paths("ABC-123", folder_path=str(bound))
    assert len(paths) == 1
    assert paths[0].name == "shot.png"
