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


def weighted_average_vectors(
    vectors: List[List[float]],
    weights: List[float],
) -> Optional[List[float]]:
    """Weighted mean of embedding vectors."""
    if not vectors or not weights or len(vectors) != len(weights):
        return average_vectors(vectors) if vectors else None
    dim = min(len(v) for v in vectors)
    if dim <= 0:
        return None
    out = [0.0] * dim
    total_w = 0.0
    for vec, weight in zip(vectors, weights):
        w = max(0.0, float(weight or 0))
        if w <= 0:
            continue
        total_w += w
        for i in range(dim):
            out[i] += float(vec[i]) * w
    if total_w <= 0:
        return average_vectors(vectors)
    inv = 1.0 / total_w
    return [x * inv for x in out]


def build_weighted_user_profile_vector(
    *,
    model: str,
    seed_codes: List[str],
    seed_weights: List[float],
) -> Optional[List[float]]:
    """Build a taste profile vector using per-seed weights (rating/liked/completion)."""
    vecs: List[List[float]] = []
    weights: List[float] = []
    for pc, weight in zip(seed_codes, seed_weights):
        v = _vector_for_product_code(pc, model=model)
        if v and float(weight or 0) > 0:
            vecs.append(v)
            weights.append(float(weight))
    return weighted_average_vectors(vecs, weights)


def build_negative_profile_vector(
    *,
    model: str,
    seed_codes: List[str],
    seed_weights: List[float] | None = None,
) -> Optional[List[float]]:
    """Average (optionally weighted) vector for disliked/low-rated works."""
    if seed_weights and len(seed_weights) == len(seed_codes):
        return build_weighted_user_profile_vector(
            model=model,
            seed_codes=seed_codes,
            seed_weights=seed_weights,
        )
    return build_user_profile_vector(model=model, seed_codes=seed_codes)


def _vector_distance_sq(a: List[float], b: List[float]) -> float:
    n = min(len(a), len(b))
    if n <= 0:
        return float("inf")
    return sum((float(a[i]) - float(b[i])) ** 2 for i in range(n))


def cluster_seed_vectors(
    seed_codes: List[str],
    *,
    model: str,
    k: int = 3,
    max_iters: int = 12,
) -> List[Tuple[List[str], List[float]]]:
    """Simple k-means over seed embeddings. Returns (codes_in_cluster, centroid) pairs."""
    items: List[Tuple[str, List[float]]] = []
    for pc in seed_codes:
        vec = _vector_for_product_code(pc, model=model)
        if vec:
            items.append((pc, vec))
    if len(items) < 2:
        if not items:
            return []
        return [([items[0][0]], items[0][1])]

    k = max(1, min(int(k or 3), len(items), 4))
    step = max(1, len(items) // k)
    centroids = [items[i * step][1][:] for i in range(k)]
    assignments: List[int] = [0] * len(items)

    for _ in range(max_iters):
        changed = False
        clusters: List[List[int]] = [[] for _ in range(k)]
        for idx, (_pc, vec) in enumerate(items):
            best_j = 0
            best_dist = float("inf")
            for j, centroid in enumerate(centroids):
                dist = _vector_distance_sq(vec, centroid)
                if dist < best_dist:
                    best_dist = dist
                    best_j = j
            if assignments[idx] != best_j:
                assignments[idx] = best_j
                changed = True
            clusters[best_j].append(idx)

        new_centroids: List[List[float]] = []
        for cluster_idxs in clusters:
            if not cluster_idxs:
                new_centroids.append(centroids[len(new_centroids)])
                continue
            cluster_vecs = [items[i][1] for i in cluster_idxs]
            centroid = average_vectors(cluster_vecs)
            new_centroids.append(centroid or items[cluster_idxs[0]][1])
        centroids = new_centroids
        if not changed:
            break

    out: List[Tuple[List[str], List[float]]] = []
    for j, centroid in enumerate(centroids):
        codes = [items[i][0] for i, assign in enumerate(assignments) if assign == j]
        if codes:
            out.append((codes, centroid))
    return out


def merge_round_robin_ranked(
    ranked_lists: List[List[SimilarResult]],
    *,
    limit: int,
) -> List[SimilarResult]:
    """Interleave cluster-ranked lists for diversity."""
    if not ranked_lists:
        return []
    if len(ranked_lists) == 1:
        return ranked_lists[0][:limit]

    merged: List[SimilarResult] = []
    seen: set[str] = set()
    max_len = max(len(lst) for lst in ranked_lists)
    for offset in range(max_len):
        for lst in ranked_lists:
            if offset >= len(lst):
                continue
            item = lst[offset]
            if item.product_code in seen:
                continue
            seen.add(item.product_code)
            merged.append(item)
            if len(merged) >= limit:
                return merged
    return merged


def rank_unwatched_with_contrast(
    positive_vec: List[float],
    negative_vec: List[float] | None,
    *,
    model: str,
    exclude_codes: set[str],
    top_k: int = 10,
    min_score: float = 0.35,
    neg_lambda: float = 0.3,
) -> List[SimilarResult]:
    """Rank unwatched works: score = sim(pos) - lambda * sim(neg)."""
    if not positive_vec:
        return []
    raw = rank_unwatched_by_vector(
        positive_vec,
        model=model,
        exclude_codes=exclude_codes,
        top_k=max(top_k * 4, 40),
        min_score=0.0,
    )
    if not negative_vec:
        return [r for r in raw if r.score >= min_score][:top_k]

    adjusted: List[SimilarResult] = []
    for item in raw:
        other_vec = _vector_for_product_code(item.product_code, model=model)
        if not other_vec:
            continue
        neg_sim = _cosine(negative_vec, other_vec)
        neg_penalty = neg_lambda * neg_sim if math.isfinite(neg_sim) else 0.0
        score = float(item.score) - neg_penalty
        if score >= min_score:
            reasons = list(item.match_reasons)
            if neg_penalty > 0.05:
                reasons.append("비선호 결 감점")
            adjusted.append(
                SimilarResult(
                    product_code=item.product_code,
                    score=score,
                    path=item.path,
                    match_reasons=reasons,
                )
            )
    adjusted.sort(key=lambda r: r.score, reverse=True)
    return adjusted[:top_k]


def vector_for_product_code(product_code: str, *, model: str) -> Optional[List[float]]:
    """Public wrapper for embedding lookup by product code."""
    return _vector_for_product_code(product_code, model=model)


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Public cosine similarity helper."""
    return _cosine(a, b)


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


