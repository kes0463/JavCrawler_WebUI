"""시청 이어보기: 파일 경로 정규화 및 파트(파일)별 last_position JSON 병합."""

from __future__ import annotations

import json
from pathlib import Path


def normalize_watch_video_key(video_path: str) -> str:
    if not (video_path or "").strip():
        return ""
    try:
        return str(Path(video_path).resolve()).replace("\\", "/").lower()
    except Exception:
        return str(video_path).strip().replace("\\", "/").lower()


def last_position_ms_for_video(
    *,
    legacy_last_position: int,
    last_positions_json: str | None,
    video_path: str,
) -> int:
    """품번 단위 레거시 last_position + JSON 맵에서 video_path에 해당하는 ms."""
    key = normalize_watch_video_key(video_path)
    if key and last_positions_json:
        try:
            o = json.loads(last_positions_json)
            if isinstance(o, dict) and key in o:
                return int(o[key])
        except Exception:
            pass
    return int(legacy_last_position or 0)


def merge_last_positions_json(raw: str | None, key: str, position_ms: int) -> str:
    m: dict[str, int] = {}
    if raw:
        try:
            o = json.loads(raw)
            if isinstance(o, dict):
                for k, v in o.items():
                    ks = str(k).strip()
                    if ks and isinstance(v, (int, float)):
                        m[ks] = int(v)
        except Exception:
            m = {}
    if key:
        m[key] = int(position_ms)
    return json.dumps(m, ensure_ascii=False, separators=(",", ":"))
