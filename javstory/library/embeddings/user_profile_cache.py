"""Disk-backed cache for weighted user taste profile vectors."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import List, Optional, Sequence

from javstory.library.embeddings.pipeline import embeddings_ollama_model_from_env
from javstory.persona.library_search import normalize_product_code

_CACHE_DIR = Path("data/cache")
_CACHE_TTL_SEC = 6 * 3600


def _cache_path(cache_key: str, *, model: str) -> Path:
    safe = hashlib.sha256(f"{model}|{cache_key}".encode("utf-8")).hexdigest()[:24]
    return _CACHE_DIR / f"user_profile_vector_{safe}.json"


def _build_cache_key(seed_codes: Sequence[str], seed_weights: Sequence[float]) -> str:
    pairs = []
    for code, weight in zip(seed_codes, seed_weights):
        pc = normalize_product_code(str(code or ""))
        if not pc:
            continue
        pairs.append(f"{pc}:{round(float(weight or 0), 3)}")
    return "|".join(pairs)


def get_cached_weighted_user_profile_vector(
    seed_codes: Sequence[str],
    seed_weights: Sequence[float],
    *,
    model: str | None = None,
    ttl_sec: int = _CACHE_TTL_SEC,
) -> Optional[List[float]]:
    codes = [normalize_product_code(c) or "" for c in seed_codes]
    codes = [c for c in codes if c]
    if not codes:
        return None
    weights = list(seed_weights)
    if len(weights) != len(codes):
        weights = [1.0] * len(codes)
    m = (model or "").strip() or embeddings_ollama_model_from_env()
    key = _build_cache_key(codes, weights)
    path = _cache_path(key, model=m)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if float(payload.get("ts") or 0) + float(ttl_sec) < time.time():
            return None
        if str(payload.get("model") or "") != m:
            return None
        vector = payload.get("vector")
        if isinstance(vector, list) and vector:
            return [float(v) for v in vector]
    except Exception:
        return None
    return None


def store_weighted_user_profile_vector(
    seed_codes: Sequence[str],
    seed_weights: Sequence[float],
    vector: Sequence[float],
    *,
    model: str | None = None,
) -> None:
    codes = [normalize_product_code(c) or "" for c in seed_codes]
    codes = [c for c in codes if c]
    if not codes or not vector:
        return
    weights = list(seed_weights)
    if len(weights) != len(codes):
        weights = [1.0] * len(codes)
    m = (model or "").strip() or embeddings_ollama_model_from_env()
    key = _build_cache_key(codes, weights)
    path = _cache_path(key, model=m)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "ts": time.time(),
                    "model": m,
                    "seed_count": len(codes),
                    "vector": [float(v) for v in vector],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


def resolve_weighted_user_profile_vector(
    seed_codes: Sequence[str],
    seed_weights: Sequence[float],
    *,
    model: str | None = None,
) -> Optional[List[float]]:
    cached = get_cached_weighted_user_profile_vector(seed_codes, seed_weights, model=model)
    if cached is not None:
        return cached
    try:
        from javstory.library.embeddings.similarity import build_weighted_user_profile_vector

        vector = build_weighted_user_profile_vector(
            model=(model or embeddings_ollama_model_from_env()),
            seed_codes=[normalize_product_code(c) or "" for c in seed_codes if normalize_product_code(c)],
            seed_weights=list(seed_weights),
        )
    except Exception:
        return None
    if vector:
        store_weighted_user_profile_vector(seed_codes, seed_weights, vector, model=model)
    return vector
