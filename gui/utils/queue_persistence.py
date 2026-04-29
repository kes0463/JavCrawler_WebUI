"""백그라운드 큐(번역·하이라이트·프리뷰·몽타주·모자이크) 디스크 영속화."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from javstory.config.app_config import E_DATA_ROOT

SCHEMA_V = 1


def _state_dir() -> Path:
    return Path(E_DATA_ROOT) / "queue_state"


def _path(name: str) -> Path:
    n = (name or "").strip().lower().replace("..", "").replace("/", "_").replace("\\", "_")
    if not n:
        raise ValueError("queue persistence name required")
    return _state_dir() / f"{n}.json"


def load_queue_state(name: str) -> Optional[Dict[str, Any]]:
    p = _path(name)
    if not p.is_file():
        return None
    try:
        raw = p.read_text(encoding="utf-8")
        if not raw.strip():
            return None
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if "items" not in data and int(data.get("v", 0) or 0) != SCHEMA_V:
        return None
    return data


def save_queue_state(name: str, payload: Dict[str, Any]) -> None:
    p = _path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    out = {**payload, "v": SCHEMA_V}
    tmp = p.with_suffix(p.suffix + ".tmp")
    s = json.dumps(out, ensure_ascii=False, indent=0)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(s)
    os.replace(tmp, p)


def clear_queue_state(name: str) -> None:
    try:
        p = _path(name)
        if p.is_file():
            p.unlink()
    except Exception:
        pass
