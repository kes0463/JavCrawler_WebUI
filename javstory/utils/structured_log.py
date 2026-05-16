"""구조화 로그 — `logs/javstory.jsonl` (NDJSON, UTF-8).

부트 크래시: `crash_report.txt`(사람용) + jsonl `boot_crash`.
파이프라인 실패: `data/error/04_ERROR/*.json` + jsonl `pipeline_error`.
"""

from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def logs_dir() -> Path:
    d = _PROJECT_ROOT / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_event(
    level: str,
    event: str,
    message: str = "",
    *,
    exc: BaseException | None = None,
    **data: Any,
) -> None:
    """한 줄 JSON 이벤트를 append (실패해도 앱 동작은 유지)."""
    record: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level.upper(),
        "event": event,
        "message": message,
        "platform": sys.platform,
    }
    if exc is not None:
        record["exception_type"] = type(exc).__name__
        record["exception"] = str(exc)
    if data:
        record.update(data)
    try:
        path = logs_dir() / "javstory.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def write_boot_crash() -> Path:
    """`logs/crash_report.txt` + jsonl `boot_crash`. 호출 전에 예외가 발생한 상태여야 함."""
    text = traceback.format_exc()
    log_dir = logs_dir()
    txt_path = log_dir / "crash_report.txt"
    try:
        txt_path.write_text(text, encoding="utf-8")
    except Exception:
        pass
    log_event(
        "CRITICAL",
        "boot_crash",
        "Uncaught exception during application startup",
        traceback=text,
    )
    return txt_path
