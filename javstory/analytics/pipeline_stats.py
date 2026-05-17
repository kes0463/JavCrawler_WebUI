"""파이프라인·수집 운영 지표 (로그·에러 디렉터리 집계)."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read_jsonl_events(days: int = 30) -> list[dict[str, Any]]:
    path = _PROJECT_ROOT / "logs" / "javstory.jsonl"
    if not path.is_file():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_raw = rec.get("ts") or ""
            try:
                ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
            if ts >= cutoff:
                out.append(rec)
    except OSError:
        pass
    return out


def get_pipeline_report(days: int = 30) -> Dict[str, Any]:
    """
    최근 N일 파이프라인·부트 이벤트 요약.
    """
    events = _read_jsonl_events(days=days)
    by_event: Counter = Counter()
    errors = 0
    for e in events:
        by_event[str(e.get("event") or "unknown")] += 1
        if str(e.get("level") or "").upper() in ("ERROR", "CRITICAL"):
            errors += 1

    error_dir = _PROJECT_ROOT / "data" / "error" / "04_ERROR"
    error_files = 0
    if error_dir.is_dir():
        try:
            error_files = sum(1 for p in error_dir.glob("*.json") if p.is_file())
        except OSError:
            error_files = 0

    return {
        "days": int(days),
        "total_events": len(events),
        "error_events": errors,
        "error_json_files": error_files,
        "by_event": dict(by_event.most_common(12)),
    }
