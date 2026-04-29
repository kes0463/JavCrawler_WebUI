from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _stat_sig(path: Path) -> dict[str, Any]:
    try:
        st = path.stat()
        return {"size": int(st.st_size), "mtime_ns": int(st.st_mtime_ns)}
    except Exception:
        return {"size": None, "mtime_ns": None}


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        return


def is_up_to_date(*, meta_path: Path, inputs: dict[str, Path], params: dict[str, Any]) -> bool:
    """
    입력 파일 stat 시그니처 + 파라미터가 동일하면 up-to-date 로 간주.
    """
    meta = _read_json(meta_path)
    if not isinstance(meta, dict):
        return False
    if meta.get("params") != params:
        return False
    in_meta = meta.get("inputs")
    if not isinstance(in_meta, dict):
        return False
    for k, p in inputs.items():
        sig = _stat_sig(p)
        prev = in_meta.get(k)
        if not isinstance(prev, dict):
            return False
        if prev.get("size") != sig.get("size") or prev.get("mtime_ns") != sig.get("mtime_ns"):
            return False
    return True


def mark_up_to_date(*, meta_path: Path, inputs: dict[str, Path], params: dict[str, Any]) -> None:
    payload = {
        "version": 1,
        "params": params,
        "inputs": {k: _stat_sig(p) for k, p in inputs.items()},
    }
    _write_json_atomic(meta_path, payload)

