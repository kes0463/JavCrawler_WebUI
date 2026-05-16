"""P3: resolve_video_paths_for_playback — L4 > L2 > L1."""

from __future__ import annotations

import importlib
from pathlib import Path

from javstory.library.canonical.schema import LibraryCanonical, MediaBinding, VideoPartRef
from javstory.library.canonical.store import save_library_state
from javstory.library.media_parts import build_video_part_refs
from javstory.library.paths import library_state_path


def _reload_db(monkeypatch, db_path: Path):
    import javstory.config.app_config as app_config

    monkeypatch.setattr(app_config, "DB_PATH", db_path)
    import javstory.harvest.database as dbmod

    importlib.reload(dbmod)
    return dbmod


def test_l4_parts_win_over_video_files(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "p3.db"
    dbmod = _reload_db(monkeypatch, db_path)
    dbmod.init_and_upgrade_db()

    bind = tmp_path / "SKU-100"
    bind.mkdir()
    p_canon = bind / "ordered.mp4"
    p_other = bind / "SKU-100_extra.mp4"
    p_canon.write_bytes(b"a")
    p_other.write_bytes(b"b")

    from javstory.harvest.product_repository import (
        resolve_video_paths_for_playback,
        set_folder_path,
        sync_product_from_metadata_row,
        sync_video_files,
    )

    with dbmod.get_db_session_ctx() as session:
        row = dbmod.JAVMetadata(product_code="SKU-100", folder_path=str(bind))
        session.add(row)
        session.flush()
        sync_product_from_metadata_row(session, row)
        set_folder_path(session, "SKU-100", str(bind))
        sync_video_files(session, "SKU-100", bind, [p_other, p_canon])
        session.commit()

    state = LibraryCanonical(
        product_code="SKU-100",
        media=MediaBinding(
            parts=[VideoPartRef(order=0, video_relpath="ordered.mp4")],
            primary_video_relpath="ordered.mp4",
        ),
    )
    ls = library_state_path("SKU-100", root=tmp_path / "lib")
    ls.parent.mkdir(parents=True, exist_ok=True)
    save_library_state(ls, state)

    _lib_root = tmp_path / "lib"

    def _ls(pc: str, root=None):
        return library_state_path(pc, root=_lib_root)

    monkeypatch.setattr("javstory.library.detail_persist.library_state_path", _ls)
    monkeypatch.setattr("javstory.library.paths.library_state_path", _ls)
    monkeypatch.setenv("JAVSTORY_DB_V2_READ", "1")

    paths = resolve_video_paths_for_playback("SKU-100", str(bind))
    assert len(paths) == 1
    assert paths[0].name == "ordered.mp4"


def test_v2_read_when_no_canonical(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "v2only.db"
    dbmod = _reload_db(monkeypatch, db_path)
    dbmod.init_and_upgrade_db()

    bind = tmp_path / "TST-200"
    bind.mkdir()
    p1 = bind / "TST-200_a.mp4"
    p2 = bind / "TST-200_b.mp4"
    p1.write_bytes(b"1")
    p2.write_bytes(b"2")

    from javstory.harvest.product_repository import (
        resolve_video_paths_for_playback,
        set_folder_path,
        sync_product_from_metadata_row,
        sync_video_files,
    )

    with dbmod.get_db_session_ctx() as session:
        row = dbmod.JAVMetadata(product_code="TST-200", folder_path=str(bind))
        session.add(row)
        session.flush()
        sync_product_from_metadata_row(session, row)
        set_folder_path(session, "TST-200", str(bind))
        sync_video_files(session, "TST-200", bind, [p2, p1])
        session.commit()

    monkeypatch.setenv("JAVSTORY_DB_V2_READ", "1")
    paths = resolve_video_paths_for_playback("TST-200")
    assert [x.name for x in paths] == ["TST-200_a.mp4", "TST-200_b.mp4"]


def test_library_data_delegates_to_resolver(tmp_path: Path, monkeypatch) -> None:
    from gui.library_data import find_all_video_paths_for_product

    bind = tmp_path / "bind"
    bind.mkdir()
    v = bind / "X-1.mp4"
    v.write_bytes(b"x")

    calls: list[str] = []

    def fake_resolve(pc: str, fp=None):
        calls.append(pc)
        return [v]

    monkeypatch.setattr(
        "javstory.harvest.product_repository.resolve_video_paths_for_playback",
        fake_resolve,
    )
    out = find_all_video_paths_for_product("X-1", str(bind))
    assert calls == ["X-1"]
    assert out == [v]
