"""file_flag_cache 갱신 — 자막 생성 후 lamp_sub 반영."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


def test_refresh_flags_after_media_change_scans_ko_srt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from javstory.library import file_flag_scanner as scanner

    video = tmp_path / "ABW-001.mp4"
    video.write_bytes(b"x")
    (tmp_path / "ABW-001.ko.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n")

    monkeypatch.setattr(
        "javstory.library.video_discovery.guess_video_path_for_product_fast",
        lambda pc, folder: video,
    )
    monkeypatch.setattr(
        "javstory.library.paths.library_state_path",
        lambda pc: tmp_path / "missing.json",
    )
    monkeypatch.setattr(
        scanner,
        "_resolve_preview_path",
        lambda pc: None,
    )
    monkeypatch.setattr(
        "javstory.translation.story_grok_module.has_disk_grok_story_cache",
        lambda pc: False,
    )

    saved: list[dict] = []

    def _fake_upsert(db_path: str, rows: list[dict]) -> None:
        saved.extend(rows)

    monkeypatch.setattr(scanner, "_bulk_upsert", _fake_upsert)
    monkeypatch.setattr(scanner, "DB_PATH", str(tmp_path / "dummy.db"), raising=False)

    # DB 메타 없음 → video parent를 folder로 사용
    session = MagicMock()
    session.query.return_value.filter_by.return_value.first.return_value = None
    session_cm = MagicMock()
    monkeypatch.setattr(
        "javstory.harvest.database.get_db_session",
        lambda: session,
    )

    scanner.refresh_flags_after_media_change("ABW-001", video)

    assert len(saved) == 1
    assert saved[0]["product_code"] == "ABW-001"
    assert saved[0]["lamp_sub"] == 1


def test_repair_stale_lamp_stt_flags_sets_ja_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from javstory.library import file_flag_scanner as scanner

    video = tmp_path / "IPZZ-046.mp4"
    video.write_bytes(b"x")
    (tmp_path / "IPZZ-046.ja.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n")

    cache = MagicMock()
    cache.product_code = "IPZZ-046"
    cache.video_path = str(video)
    cache.lamp_stt = 0

    session = MagicMock()
    session.query.return_value.outerjoin.return_value.filter.return_value.all.return_value = [
        (cache, None),
    ]

    monkeypatch.setattr(
        "javstory.harvest.database.get_db_session",
        lambda: session,
    )
    monkeypatch.setattr(scanner, "_LAMP_STT_REPAIR_DONE", False)

    stats = scanner.repair_stale_lamp_stt_flags(force=True)
    assert stats["updated"] == 1
    assert cache.lamp_stt == 1
    session.commit.assert_called_once()
