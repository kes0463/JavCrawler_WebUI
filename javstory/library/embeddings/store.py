"""
Embedding store on disk (JSON).

Path: data/cache/embeddings/{product_code}.json  (default)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from javstory.config.app_config import DATA_ROOT


def embeddings_cache_dir() -> Path:
    d = DATA_ROOT / "cache" / "embeddings"
    d.mkdir(parents=True, exist_ok=True)
    return d


def embeddings_cache_path(product_code: str, *, model: str) -> Path:
    pc = re.sub(r"[^\w\-.]", "_", (product_code or "").strip().upper(), flags=re.ASCII) or "UNKNOWN"
    m = re.sub(r"[^\w\-.]", "_", (model or "").strip(), flags=re.ASCII) or "model"
    return embeddings_cache_dir() / f"{pc}__{m}.json"


def write_embeddings_json(path: Path | str, payload: Dict[str, Any], *, indent: int = 2) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=indent), encoding="utf-8")
    return p


def read_embeddings_json(path: Path | str) -> Dict[str, Any]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("embeddings json is not an object")
    return data

