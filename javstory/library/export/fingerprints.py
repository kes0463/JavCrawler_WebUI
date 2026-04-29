"""export 산출물 지문 — 외부 편집과의 동기화 검사용."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def file_fingerprint(path: Path | str) -> dict[str, str] | None:
    """파일이 없으면 None. { sha256, mtime_iso }."""
    p = Path(path)
    if not p.is_file():
        return None
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    mtime = p.stat().st_mtime
    mtime_iso = datetime.fromtimestamp(mtime, tz=timezone.utc).replace(microsecond=0).isoformat()
    return {"sha256": h.hexdigest(), "mtime_iso": mtime_iso}


def build_manifest_fingerprints(
    paths: dict[str, Path | str],
) -> dict[str, dict[str, str]]:
    """논리 키(relpath 등) -> 지문."""
    out: dict[str, dict[str, str]] = {}
    for key, p in paths.items():
        fp = file_fingerprint(p)
        if fp is not None:
            out[str(key)] = fp
    return out


def manifest_has_drift(
    stored: dict[str, dict[str, Any]],
    current_paths: dict[str, Path | str],
) -> list[str]:
    """
    저장된 file_fingerprints와 현재 디스크를 비교.
    불일치 키 목록 반환 (파일 없음·해시 불일치·mtime 불일치).
    """
    drift: list[str] = []
    for key, p in current_paths.items():
        sk = str(key)
        prev = stored.get(sk)
        now = file_fingerprint(p)
        if now is None:
            drift.append(sk)
            continue
        if not prev:
            drift.append(sk)
            continue
        if prev.get("sha256") != now.get("sha256"):
            drift.append(sk)
    return drift
