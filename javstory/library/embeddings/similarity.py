"""
Embeddings similarity utilities.

Purpose:
- Make the embeddings cache immediately useful (semantic "similar works" lookup)
- Keep it dependency-free (no numpy/faiss)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from javstory.library.embeddings.store import embeddings_cache_dir, read_embeddings_json


@dataclass(frozen=True)
class SimilarResult:
    product_code: str
    score: float
    path: Path
    match_reasons: List[str]  # 구체적으로 어떤 부분이 유사한지 (Grok, Meta 등)


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return float("-inf")
    n = min(len(a), len(b))
    if n <= 0:
        return float("-inf")

    dot = 0.0
    na = 0.0
    nb = 0.0
    for i in range(n):
        xa = float(a[i])
        xb = float(b[i])
        dot += xa * xb
        na += xa * xa
        nb += xb * xb
    if na <= 0.0 or nb <= 0.0:
        return float("-inf")
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _get_vec_by_kind(payload: Dict[str, Any], kind: str) -> Optional[List[float]]:
    for d in payload.get("docs") or []:
        if d.get("kind") == kind:
            emb = d.get("embedding")
            if isinstance(emb, list) and emb:
                return [float(x) for x in emb]
    return None


def _pick_representative_vector(payload: Dict[str, Any]) -> Optional[List[float]]:
    """
    [고도화] Grok 스토리 문맥에 높은 가중치를 부여하여 대표 벡터를 생성합니다.
    Grok(70%) + Meta(30%) 비율로 혼합하여 문맥적 유사성 판단력을 극대화합니다.
    """
    docs = payload.get("docs") or []
    if not isinstance(docs, list) or not docs:
        return None

    grok_vec = _get_vec_by_kind(payload, "grok_story")
    meta_vec = _get_vec_by_kind(payload, "meta_canonical")
    
    others: List[List[float]] = []
    if not grok_vec or not meta_vec:
        for d in docs:
            if d.get("kind") not in ("grok_story", "meta_canonical"):
                emb = d.get("embedding")
                if isinstance(emb, list) and emb:
                    others.append([float(x) for x in emb])

    # 1. Grok + Meta 혼합 (가장 이상적)
    if grok_vec and meta_vec:
        dim = min(len(grok_vec), len(meta_vec))
        return [(grok_vec[i] * 0.7 + meta_vec[i] * 0.3) for i in range(dim)]
    
    # 2. 둘 중 하나만 있는 경우
    if grok_vec: return grok_vec
    if meta_vec: return meta_vec

    # 3. 둘 다 없는 경우 전체 평균
    if not others:
        return None
    
    dim = min(len(v) for v in others)
    out = [0.0] * dim
    for v in others:
        for i in range(dim):
            out[i] += v[i]
    inv = 1.0 / float(len(others))
    return [x * inv for x in out]


def _iter_embedding_payloads(*, model: str | None = None) -> Iterable[Tuple[Path, Dict[str, Any]]]:
    d = embeddings_cache_dir()
    for p in sorted(d.glob("*.json")):
        try:
            payload = read_embeddings_json(p)
            if model:
                m = str(payload.get("model") or "").strip()
                if m != model:
                    continue
            yield p, payload
        except Exception:
            continue


def find_similar_products(
    query_product_code: str,
    *,
    model: str,
    top_k: int = 10,
    min_score: float = 0.35,
) -> List[SimilarResult]:
    pc = (query_product_code or "").strip().upper()
    if not pc:
        return []
    top_k = max(1, min(50, int(top_k or 10)))

    query_payload: Optional[Dict[str, Any]] = None
    query_vec: Optional[List[float]] = None
    for p, payload in _iter_embedding_payloads(model=model):
        if str(payload.get("product_code") or "").strip().upper() == pc:
            query_payload = payload
            query_vec = _pick_representative_vector(payload)
            break

    if not query_vec or not query_payload:
        return []

    q_grok = _get_vec_by_kind(query_payload, "grok_story")
    q_meta = _get_vec_by_kind(query_payload, "meta_canonical")

    out: List[SimilarResult] = []
    for p, payload in _iter_embedding_payloads(model=model):
        other_pc = str(payload.get("product_code") or "").strip().upper()
        if not other_pc or other_pc == pc:
            continue
        
        other_vec = _pick_representative_vector(payload)
        if not other_vec:
            continue
        
        score = _cosine(query_vec, other_vec)
        if math.isfinite(score) and score >= min_score:
            match_reasons = []
            
            # [고도화] 문서 종류별 개별 비교를 통한 상세 이유 도출
            o_grok = _get_vec_by_kind(payload, "grok_story")
            o_meta = _get_vec_by_kind(payload, "meta_canonical")
            
            if q_grok and o_grok:
                g_score = _cosine(q_grok, o_grok)
                if g_score > 0.85: match_reasons.append("스토리 구성/전개")
            
            if q_meta and o_meta:
                m_score = _cosine(q_meta, o_meta)
                if m_score > 0.85: match_reasons.append("작품 배경/설정")

            out.append(SimilarResult(product_code=other_pc, score=float(score), path=p, match_reasons=match_reasons))

    out.sort(key=lambda r: r.score, reverse=True)
    return out[:top_k]


def _vector_for_product_code(product_code: str, *, model: str) -> Optional[List[float]]:
    pc = (product_code or "").strip().upper()
    if not pc:
        return None
    for _p, payload in _iter_embedding_payloads(model=model):
        if str(payload.get("product_code") or "").strip().upper() == pc:
            return _pick_representative_vector(payload)
    return None


def average_vectors(vectors: List[List[float]]) -> Optional[List[float]]:
    if not vectors:
        return None
    dim = min(len(v) for v in vectors)
    if dim <= 0:
        return None
    out = [0.0] * dim
    for v in vectors:
        for i in range(dim):
            out[i] += float(v[i])
    inv = 1.0 / float(len(vectors))
    return [x * inv for x in out]


def build_user_profile_vector(*, model: str, seed_codes: List[str]) -> Optional[List[float]]:
    """시청·좋아요 작품 임베딩의 평균 벡터."""
    vecs: List[List[float]] = []
    for pc in seed_codes:
        v = _vector_for_product_code(pc, model=model)
        if v:
            vecs.append(v)
    return average_vectors(vecs)


def rank_unwatched_by_vector(
    profile_vec: List[float],
    *,
    model: str,
    exclude_codes: set[str],
    top_k: int = 10,
    min_score: float = 0.35,
) -> List[SimilarResult]:
    if not profile_vec:
        return []
    out: List[SimilarResult] = []
    for p, payload in _iter_embedding_payloads(model=model):
        other_pc = str(payload.get("product_code") or "").strip().upper()
        if not other_pc or other_pc in exclude_codes:
            continue
        other_vec = _pick_representative_vector(payload)
        if not other_vec:
            continue
        score = _cosine(profile_vec, other_vec)
        if math.isfinite(score) and score >= min_score:
            out.append(SimilarResult(product_code=other_pc, score=float(score), path=p, match_reasons=["취향 프로필 유사"]))
    out.sort(key=lambda r: r.score, reverse=True)
    return out[:top_k]


