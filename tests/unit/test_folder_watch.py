"""javstory.folder_watch 단위 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from javstory.folder_watch import candidates as cand_mod
from javstory.folder_watch import inbox as inbox_mod
from javstory.folder_watch import paused as paused_mod
from javstory.folder_watch.service import FolderWatchBackgroundService


@pytest.fixture
def inbox_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "folder_binding_inbox.json"
    monkeypatch.setattr(inbox_mod, "_INBOX_PATH", path)
    return path


@pytest.fixture
def paused_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "folder_watch_paused.json"
    monkeypatch.setattr(paused_mod, "_PAUSED_FILE", path)
    paused_mod.invalidate_cache()
    return path


def test_inbox_upsert_remove_and_lookup(inbox_path: Path) -> None:
    assert inbox_mod.load_inbox() == []

    inbox_mod.upsert_inbox_item("stars-001", r"D:\old\STARS-001", [r"E:\new\STARS-001"])
    items = inbox_mod.load_inbox()
    assert len(items) == 1
    assert items[0].product_code == "STARS-001"
    assert items[0].old_path == r"D:\old\STARS-001"
    assert items[0].candidates == [r"E:\new\STARS-001"]

    inbox_mod.upsert_inbox_item("STARS-001", r"D:\old\STARS-001", [r"F:\alt"])
    assert len(inbox_mod.load_inbox()) == 1
    assert inbox_mod.load_inbox()[0].candidates == [r"F:\alt"]

    assert inbox_mod.inbox_contains("stars-001") is True
    item = inbox_mod.get_inbox_item("STARS-001")
    assert item is not None
    assert item.product_code == "STARS-001"

    inbox_mod.remove_inbox_item("STARS-001")
    assert inbox_mod.load_inbox() == []
    assert inbox_mod.inbox_contains("STARS-001") is False
    assert inbox_mod.get_inbox_item("STARS-001") is None


def test_inbox_clear(inbox_path: Path) -> None:
    inbox_mod.upsert_inbox_item("A-001", "/a", [])
    inbox_mod.upsert_inbox_item("B-002", "/b", [])
    inbox_mod.clear_inbox()
    assert inbox_mod.load_inbox() == []


def test_paused_pause_resume(paused_path: Path) -> None:
    assert paused_mod.load_paused_product_codes() == set()
    assert paused_mod.is_monitoring_paused("ipx-123") is False

    paused_mod.pause_monitoring("ipx-123")
    assert paused_mod.is_monitoring_paused("IPX-123") is True
    assert "IPX-123" in paused_mod.load_paused_product_codes()

    paused_mod.resume_monitoring("IPX-123")
    assert paused_mod.is_monitoring_paused("IPX-123") is False


def test_rank_candidates_by_old_path() -> None:
    old = r"E:\Media\JAV\STARS-001"
    cands = [
        r"F:\backup\STARS-001",
        r"E:\Media\JAV\STARS-001-moved",
        r"E:\Media\other\STARS-001",
    ]
    ranked = cand_mod._rank_candidates_by_old_path(old, cands)
    assert ranked[0] == r"E:\Media\JAV\STARS-001-moved"


def test_verify_bindings_skips_existing_and_paused(
    paused_path: Path,
    inbox_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = FolderWatchBackgroundService()
    existing = tmp_path_dir = Path(__file__).resolve().parent
    missing = tmp_path_dir / "nonexistent-folder-watch-test"

    svc._paths = {"OK-001": str(existing), "MISS-001": str(missing)}
    paused_mod.pause_monitoring("MISS-001")

    monkeypatch.setattr(
        "javstory.folder_watch.service.search_folder_candidates",
        lambda *_a, **_k: [r"Z:\found"],
    )
    monkeypatch.setattr(
        "javstory.folder_watch.service.upsert_inbox_item",
        lambda pc, old, cands: inbox_mod.upsert_inbox_item(pc, old, cands),
    )

    svc.verify_bindings()
    svc.verify_bindings()

    assert inbox_mod.inbox_contains("OK-001") is False
    assert inbox_mod.inbox_contains("MISS-001") is False
    assert "OK-001" not in svc._broken_notified


def test_verify_bindings_queues_missing_folder(
    inbox_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = FolderWatchBackgroundService()
    missing = Path(__file__).resolve().parent / "folder-watch-missing-dir"
    svc._paths = {"LOST-001": str(missing)}

    monkeypatch.setattr(
        "javstory.folder_watch.service.search_folder_candidates",
        lambda *_a, **_k: [r"G:\LOST-001"],
    )
    monkeypatch.setattr(
        "javstory.folder_watch.service.upsert_inbox_item",
        lambda pc, old, cands: inbox_mod.upsert_inbox_item(pc, old, cands),
    )

    svc.verify_bindings()
    import time

    deadline = time.time() + 3.0
    while time.time() < deadline:
        if inbox_mod.inbox_contains("LOST-001"):
            break
        time.sleep(0.05)

    assert inbox_mod.inbox_contains("LOST-001") is True
    item = inbox_mod.get_inbox_item("LOST-001")
    assert item is not None
    assert item.candidates == [r"G:\LOST-001"]
