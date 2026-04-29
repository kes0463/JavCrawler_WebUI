"""library_state.json 로드·저장 (원자적 쓰기)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from javstory.library.canonical.schema import LibraryCanonical


def load_library_state(path: Path | str) -> LibraryCanonical:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(p)
    raw = p.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"library_state가 객체가 아닙니다: {p}")
    return LibraryCanonical.from_json_dict(data)


def save_library_state(path: Path | str, state: LibraryCanonical, *, indent: int = 2) -> None:
    p = Path(path)
    state.touch()
    payload = state.to_json_dict()
    _atomic_write_json(p, payload, indent=indent)


def _atomic_write_json(path: Path, obj: dict[str, Any], *, indent: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=indent)
    fd, tmp = tempfile.mkstemp(
        suffix=".json",
        prefix=path.name + ".",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
