"""structured_log — NDJSON boot_crash / pipeline_error."""

from __future__ import annotations

import json

import pytest


def test_log_event_appends_jsonl(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "javstory.utils.structured_log._PROJECT_ROOT",
        tmp_path,
    )
    from javstory.utils.structured_log import log_event, logs_dir

    log_event("INFO", "test_event", "hello", sku="ABC-001")
    path = logs_dir() / "javstory.jsonl"
    assert path.is_file()
    row = json.loads(path.read_text(encoding="utf-8").strip())
    assert row["event"] == "test_event"
    assert row["sku"] == "ABC-001"


def test_write_boot_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "javstory.utils.structured_log._PROJECT_ROOT",
        tmp_path,
    )
    from javstory.utils.structured_log import logs_dir, write_boot_crash

    try:
        raise RuntimeError("boom")
    except RuntimeError:
        txt = write_boot_crash()

    assert txt.name == "crash_report.txt"
    assert "boom" in txt.read_text(encoding="utf-8")
    lines = (logs_dir() / "javstory.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(lines[-1])["event"] == "boot_crash"
