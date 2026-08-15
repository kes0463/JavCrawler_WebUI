"""
임베딩 벡터 인덱스 (라이브러리 자연어 검색용).

JSON 전량 스캔 대신 L2 정규화 행렬 × 쿼리(내적=코사인)로 문서별 점수를 내고,
작품 단위 max로 집계한다. numpy만 사용(추가 의존성 없음).
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from javstory.library.embeddings.store import embeddings_cache_dir, read_embeddings_json

_INDEX_LOCK = threading.RLock()
_MEMORY: dict[str, "_AnnIndex"] = {}
_DIRTY: set[str] = set()

_ANN_ENABLED_ENV = "JAVSTORY_EMBEDDING_ANN_ENABLED"


def ann_enabled_from_env(default: bool = True) -> bool:
    raw = (os.environ.get(_ANN_ENABLED_ENV, "") or "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def _model_key(model: str) -> str:
    return re.sub(r"[^\w\-.]", "_", (model or "").strip(), flags=re.ASCII) or "model"


def ann_index_dir() -> Path:
    d = embeddings_cache_dir() / "ann"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _paths_for_model(model: str) -> tuple[Path, Path]:
    key = _model_key(model)
    base = ann_index_dir() / key
    return base.with_suffix(".npy"), base.with_suffix(".meta.json")


def _payload_files_for_model(model: str) -> list[Path]:
    key = _model_key(model)
    d = embeddings_cache_dir()
    return sorted(p for p in d.glob(f"*__{key}.json") if p.is_file())


def _source_signature(model: str) -> dict[str, Any]:
    matched: list[tuple[str, float, int]] = []
    for p in _payload_files_for_model(model):
        try:
            st = p.stat()
            matched.append((p.name, st.st_mtime, st.st_size))
        except OSError:
            continue
    matched.sort()
    return {
        "model": model,
        "file_count": len(matched),
        "files": matched[:5000],
    }


def _l2_normalize(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return (mat / norms).astype(np.float32, copy=False)


@dataclass
class _AnnIndex:
    model: str
    dim: int
    vectors: np.ndarray  # [N, D] float32 L2-normalized
    product_codes: list[str]  # length N
    text_by_code: dict[str, str]
    signature: dict[str, Any]
    built_at: float

    @property
    def doc_count(self) -> int:
        return int(self.vectors.shape[0]) if self.vectors is not None else 0

    @property
    def product_count(self) -> int:
        return len(self.text_by_code)


def invalidate_embedding_ann_index(model: str | None = None) -> None:
    """임베딩 저장·모델 변경 시 호출. model=None이면 전부 무효화."""
    with _INDEX_LOCK:
        if model is None:
            _MEMORY.clear()
            try:
                for meta in ann_index_dir().glob("*.meta.json"):
                    _DIRTY.add(meta.stem)
            except Exception:
                pass
            return
        key = _model_key(model)
        _MEMORY.pop(key, None)
        _DIRTY.add(key)


def _load_text_blob(payload: dict[str, Any]) -> str:
    from javstory.library.embeddings.similarity import payload_doc_text_blob

    return payload_doc_text_blob(payload)


def build_embedding_ann_index(model: str, *, force: bool = False) -> _AnnIndex | None:
    """캐시 JSON을 스캔해 행렬 인덱스를 빌드·디스크 저장."""
    m = (model or "").strip()
    if not m:
        return None
    key = _model_key(m)
    sig = _source_signature(m)

    with _INDEX_LOCK:
        cached = _MEMORY.get(key)
        if (
            not force
            and cached is not None
            and key not in _DIRTY
            and cached.signature.get("file_count") == sig.get("file_count")
            and cached.signature.get("files") == sig.get("files")
        ):
            return cached

    rows: list[np.ndarray] = []
    codes: list[str] = []
    text_by_code: dict[str, str] = {}
    dim: int | None = None

    for p in _payload_files_for_model(m):
        try:
            payload = read_embeddings_json(p)
        except Exception:
            continue
        payload_model = str(payload.get("model") or "").strip()
        if payload_model and payload_model != m:
            continue
        pc = str(payload.get("product_code") or "").strip().upper()
        if not pc:
            continue
        text_by_code[pc] = _load_text_blob(payload)
        for d in payload.get("docs") or []:
            if not isinstance(d, dict):
                continue
            emb = d.get("embedding")
            if not isinstance(emb, list) or not emb:
                continue
            vec = np.asarray(emb, dtype=np.float32)
            if vec.ndim != 1 or vec.size == 0:
                continue
            if dim is None:
                dim = int(vec.size)
            if int(vec.size) != dim:
                continue
            rows.append(vec)
            codes.append(pc)

    if not rows or dim is None:
        with _INDEX_LOCK:
            _DIRTY.discard(key)
            _MEMORY.pop(key, None)
        return None

    mat = _l2_normalize(np.stack(rows, axis=0))
    index = _AnnIndex(
        model=m,
        dim=dim,
        vectors=mat,
        product_codes=codes,
        text_by_code=text_by_code,
        signature=sig,
        built_at=time.time(),
    )

    npy_path, meta_path = _paths_for_model(m)
    try:
        np.save(npy_path, mat)
        meta_path.write_text(
            json.dumps(
                {
                    "model": m,
                    "dim": dim,
                    "product_codes": codes,
                    "text_by_code": text_by_code,
                    "signature": sig,
                    "built_at": index.built_at,
                    "doc_count": len(codes),
                    "product_count": len(text_by_code),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass

    with _INDEX_LOCK:
        _MEMORY[key] = index
        _DIRTY.discard(key)
    return index


def _try_load_disk(model: str, sig: dict[str, Any]) -> _AnnIndex | None:
    npy_path, meta_path = _paths_for_model(model)
    if not npy_path.is_file() or not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(meta, dict):
            return None
        if meta.get("signature") != sig:
            return None
        if str(meta.get("model") or "").strip() != model:
            return None
        mat = np.load(npy_path)
        if not isinstance(mat, np.ndarray) or mat.ndim != 2:
            return None
        codes = meta.get("product_codes") or []
        if not isinstance(codes, list) or len(codes) != mat.shape[0]:
            return None
        text_by_code = meta.get("text_by_code") or {}
        if not isinstance(text_by_code, dict):
            text_by_code = {}
        return _AnnIndex(
            model=model,
            dim=int(mat.shape[1]),
            vectors=mat.astype(np.float32, copy=False),
            product_codes=[str(c).strip().upper() for c in codes],
            text_by_code={str(k).strip().upper(): str(v or "") for k, v in text_by_code.items()},
            signature=dict(meta.get("signature") or {}),
            built_at=float(meta.get("built_at") or 0.0),
        )
    except Exception:
        return None


def get_embedding_ann_index(model: str, *, rebuild_if_missing: bool = True) -> _AnnIndex | None:
    if not ann_enabled_from_env():
        return None
    m = (model or "").strip()
    if not m:
        return None
    key = _model_key(m)
    sig = _source_signature(m)

    with _INDEX_LOCK:
        dirty = key in _DIRTY
        cached = _MEMORY.get(key)
        if (
            cached is not None
            and not dirty
            and cached.signature.get("file_count") == sig.get("file_count")
            and cached.signature.get("files") == sig.get("files")
        ):
            return cached

    if not dirty:
        disk = _try_load_disk(m, sig)
        if disk is not None:
            with _INDEX_LOCK:
                _MEMORY[key] = disk
                _DIRTY.discard(key)
            return disk

    if not rebuild_if_missing:
        return None
    return build_embedding_ann_index(m, force=True)


def search_ann_max_cosine(
    query_vec: list[float] | np.ndarray,
    *,
    model: str,
    min_cosine: float | None = None,
) -> tuple[list[tuple[str, float]], dict[str, str]]:
    """
    작품별 max-doc 코사인 점수 목록(내림차순)과 텍스트 블롭.
    인덱스가 없으면 ([], {}).
    """
    index = get_embedding_ann_index(model)
    if index is None or index.doc_count <= 0:
        return [], {}
    q = np.asarray(query_vec, dtype=np.float32).reshape(-1)
    if q.size != index.dim:
        return [], {}
    qn = float(np.linalg.norm(q))
    if qn <= 1e-12:
        return [], {}
    q = (q / qn).astype(np.float32, copy=False)
    scores = index.vectors @ q  # [N]
    best: dict[str, float] = {}
    for pc, score in zip(index.product_codes, scores):
        s = float(score)
        prev = best.get(pc)
        if prev is None or s > prev:
            best[pc] = s
    items = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
    if min_cosine is not None:
        thr = float(min_cosine)
        items = [(pc, s) for pc, s in items if s >= thr]
    return items, dict(index.text_by_code)


def ann_index_stats(model: str) -> dict[str, Any]:
    index = get_embedding_ann_index(model, rebuild_if_missing=False)
    if index is None:
        return {"enabled": ann_enabled_from_env(), "ready": False, "model": model}
    return {
        "enabled": ann_enabled_from_env(),
        "ready": True,
        "model": index.model,
        "dim": index.dim,
        "doc_count": index.doc_count,
        "product_count": index.product_count,
        "built_at": index.built_at,
    }


__all__ = [
    "ann_enabled_from_env",
    "ann_index_dir",
    "ann_index_stats",
    "build_embedding_ann_index",
    "get_embedding_ann_index",
    "invalidate_embedding_ann_index",
    "search_ann_max_cosine",
]
