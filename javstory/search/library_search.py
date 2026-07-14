"""Hybrid library search with Reciprocal Rank Fusion."""

from __future__ import annotations

import asyncio
import hashlib
import math
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Iterable, List, Sequence

_docs_cache: List["_LibraryDoc"] | None = None
_docs_cache_lock = threading.Lock()
_embed_result_cache: dict[str, tuple[float, list, dict[str, Any]]] = {}
_embed_result_cache_lock = threading.Lock()
_EMBED_RESULT_CACHE_TTL_SEC = 600.0
_EMBED_RESULT_CACHE_MAX = 48

try:
    from rank_bm25 import BM25Okapi
except ImportError:  # pragma: no cover - exercised only when optional dep is absent.
    BM25Okapi = None  # type: ignore[assignment]

from javstory.harvest.database import JAVMetadata, get_db_session_ctx
from javstory.library.embeddings.pipeline import (
    embeddings_enabled_from_env,
    embeddings_ollama_model_from_env,
)
from javstory.library.embeddings.similarity import _cosine, _iter_embedding_payloads, _pick_representative_vector
from javstory.llm.ollama_embeddings import ollama_embed_text

_DEFAULT_WEIGHTS = (0.3, 0.5, 0.2)
_WEIGHTS_ENV = "JAVSTORY_HYBRID_SEARCH_WEIGHTS"
_EMBED_MIN_SCORE_ENV = "JAVSTORY_EMBEDDING_SEARCH_MIN_SCORE"
_EMBED_REL_RATIO_ENV = "JAVSTORY_EMBEDDING_SEARCH_RELATIVE_RATIO"
_EMBED_MAX_GAP_ENV = "JAVSTORY_EMBEDDING_SEARCH_MAX_GAP"
_TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣ぁ-んァ-ン一-龥]{2,}")


@dataclass(frozen=True)
class _LibraryDoc:
    product_code: str
    title: str
    text: str
    metadata_text: str


@dataclass(frozen=True)
class _SearchResult:
    id: str
    title: str
    source: str
    raw_score: float = 0.0


class _FallbackBM25:
    """Small lexical ranker used only when rank_bm25 is not installed."""

    def __init__(self, corpus: Sequence[Sequence[str]]):
        self.corpus = [list(doc) for doc in corpus]

    def get_scores(self, query_tokens: Sequence[str]) -> List[float]:
        q = set(query_tokens)
        if not q:
            return [0.0 for _ in self.corpus]
        return [float(sum(1 for token in doc if token in q)) for doc in self.corpus]


def _tokenize(text: str) -> List[str]:
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(text or "")]


def _split_csv(text: str | None) -> List[str]:
    if not text:
        return []
    return [item.strip() for item in text.replace("、", ",").split(",") if item.strip()]


def _title(row: JAVMetadata) -> str:
    return (
        row.title_ko
        or row.title_ja
        or row.original_title
        or row.title_en
        or row.product_code
        or ""
    )


def _metadata_text(row: JAVMetadata) -> str:
    fields = [
        row.actors_ko,
        row.actors_ja,
        row.actors,
        row.genres_ko,
        row.genres_ja,
        row.genres,
        row.maker_ko,
        row.maker_ja,
        row.maker,
    ]
    return " ".join(str(value or "") for value in fields)


def _doc_text(row: JAVMetadata) -> str:
    fields = [
        row.product_code,
        row.title_ko,
        row.title_ja,
        row.title_en,
        row.original_title,
        row.synopsis_ko,
        row.synopsis_ja,
        row.synopsis,
        _metadata_text(row),
    ]
    return " ".join(str(value or "") for value in fields)


def _weights_from_env(default: tuple[float, float, float] = _DEFAULT_WEIGHTS) -> tuple[float, float, float]:
    raw = (os.environ.get(_WEIGHTS_ENV, "") or "").strip()
    if not raw:
        return default
    try:
        parts = [float(part.strip()) for part in raw.split(",")]
    except ValueError:
        return default
    if len(parts) != 3 or any(part < 0 for part in parts):
        return default
    total = sum(parts)
    if total <= 0:
        return default
    return (parts[0] / total, parts[1] / total, parts[2] / total)


def _embedding_min_score_from_env(default: float = 0.28) -> float:
    raw = (os.environ.get(_EMBED_MIN_SCORE_ENV, "") or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _embedding_relative_ratio_from_env(default: float = 0.74) -> float:
    raw = (os.environ.get(_EMBED_REL_RATIO_ENV, "") or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return min(0.99, max(0.05, value))


def _embedding_max_gap_from_env(default: float = 0.12) -> float:
    """1등 대비 허용 점수 하락폭. 작을수록 상위 유사도만 유지."""
    raw = (os.environ.get(_EMBED_MAX_GAP_ENV, "") or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return min(0.5, max(0.01, value))


def _embed_result_cache_ttl() -> float:
    raw = (os.environ.get("JAVSTORY_EMBEDDING_SEARCH_CACHE_TTL", "") or "").strip()
    if not raw:
        return _EMBED_RESULT_CACHE_TTL_SEC
    try:
        return max(30.0, float(raw))
    except ValueError:
        return _EMBED_RESULT_CACHE_TTL_SEC


def _embed_search_cache_key(
    query: str,
    *,
    model: str,
    min_score: float,
    relative_ratio: float,
    max_gap: float,
) -> str:
    raw = (
        f"{model}|{min_score:.4f}|{relative_ratio:.4f}|{max_gap:.4f}|"
        f"{(query or '').strip()}"
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _get_cached_embed_search(key: str) -> tuple[list, dict[str, Any]] | None:
    now = time.time()
    ttl = _embed_result_cache_ttl()
    with _embed_result_cache_lock:
        hit = _embed_result_cache.get(key)
        if not hit:
            return None
        ts, results, diag = hit
        if now - ts > ttl:
            _embed_result_cache.pop(key, None)
            return None
        return list(results), dict(diag)


def _store_cached_embed_search(key: str, results: list, diag: dict[str, Any]) -> None:
    with _embed_result_cache_lock:
        if len(_embed_result_cache) >= _EMBED_RESULT_CACHE_MAX:
            oldest = min(_embed_result_cache.items(), key=lambda item: item[1][0])[0]
            _embed_result_cache.pop(oldest, None)
        _embed_result_cache[key] = (time.time(), list(results), dict(diag))


def clear_embed_search_cache() -> None:
    with _embed_result_cache_lock:
        _embed_result_cache.clear()


def _filter_relevant_embedding_hits(
    ranked: Sequence[_SearchResult],
    *,
    min_score: float,
    relative_ratio: float,
    max_gap: float,
) -> List[_SearchResult]:
    """1등에 가까운 고유사도만 남긴다. 아래로 갈수록 내용이 멀어지는 히트는 자른다."""
    scored = [
        item
        for item in ranked
        if math.isfinite(float(item.raw_score))
    ]
    if not scored:
        return []

    scores = [float(item.raw_score) for item in scored]
    top = scores[0]
    if top < min_score:
        return []

    mean = sum(scores) / len(scores)
    var = sum((s - mean) ** 2 for s in scores) / len(scores)
    std = math.sqrt(var)
    # 코퍼스 평균대는 버리되, 관련 밴드는 이전보다 넓게
    dist_floor = mean + max(0.04, 0.75 * std)
    floor = max(
        min_score,
        top * relative_ratio,
        top - max_gap,
        dist_floor,
    )
    floor = min(floor, top)

    selected = [item for item in scored if float(item.raw_score) >= floor]
    if len(selected) <= 1:
        return selected

    # 큰 급락에서만 절단 (작은 점수 차이는 허용)
    cut: List[_SearchResult] = [selected[0]]
    cliff = max(0.028, top * 0.055)
    tight = top * relative_ratio
    for prev, cur in zip(selected, selected[1:]):
        drop = float(prev.raw_score) - float(cur.raw_score)
        if drop >= cliff and float(cur.raw_score) < tight:
            break
        if (top - float(cur.raw_score)) > max_gap:
            break
        cut.append(cur)
    return cut


class HybridLibrarySearch:
    """BM25 + embedding + metadata search fused with RRF."""

    def __init__(
        self,
        *,
        weights: tuple[float, float, float] | None = None,
        top_k: int = 20,
        fusion_k: int = 60,
    ) -> None:
        self.weights = weights or _weights_from_env()
        self.top_k = max(1, min(1000, int(top_k or 20)))
        self.fusion_k = max(1, int(fusion_k or 60))
        self.last_embedding_diag: dict[str, Any] = {}

    def search_by_embedding(
        self,
        query: str,
        *,
        min_score: float | None = None,
        relative_ratio: float | None = None,
        max_gap: float | None = None,
    ) -> list:
        """임베딩 유사도만으로 검색. 1등에 가까운 고유사도만 반환."""
        q = (query or "").strip()
        if not q:
            return []
        threshold = float(min_score) if min_score is not None else _embedding_min_score_from_env()
        ratio = (
            float(relative_ratio)
            if relative_ratio is not None
            else _embedding_relative_ratio_from_env()
        )
        gap = float(max_gap) if max_gap is not None else _embedding_max_gap_from_env()
        model = embeddings_ollama_model_from_env()
        cache_key = _embed_search_cache_key(
            q,
            model=model,
            min_score=threshold,
            relative_ratio=ratio,
            max_gap=gap,
        )
        cached = _get_cached_embed_search(cache_key)
        if cached is not None:
            results, diag = cached
            self.last_embedding_diag = {**diag, "cache_hit": True}
            return results

        docs = self._load_docs()
        if not docs:
            return []
        ranked = self._search_embedding(q, docs, top_k=None)
        selected = _filter_relevant_embedding_hits(
            ranked,
            min_score=threshold,
            relative_ratio=ratio,
            max_gap=gap,
        )
        results = [
            {
                "id": item.id,
                "title": item.title,
                "score": round(float(item.raw_score), 6),
                "source": "embedding",
            }
            for item in selected
        ]
        diag = {
            **dict(self.last_embedding_diag or {}),
            "selected_n": len(selected),
            "min_score": threshold,
            "relative_ratio": ratio,
            "max_gap": gap,
            "cache_hit": False,
        }
        self.last_embedding_diag = diag
        if str(diag.get("status") or "") == "ok" or results:
            _store_cached_embed_search(cache_key, results, diag)
        return results

    def search_with_fusion(
        self,
        query: str,
        weights: tuple[float, float, float] | None = None,
    ) -> list:
        """Search three rankers and return top-k RRF-fused results."""
        q = (query or "").strip()
        if not q:
            return []
        active_weights = weights or self.weights or _weights_from_env()
        docs = self._load_docs()
        if not docs:
            return []

        rankers = (
            self._search_bm25,
            self._search_embedding,
            self._search_metadata,
        )
        ranked_lists = []
        for idx, ranker in enumerate(rankers):
            if idx < len(active_weights) and float(active_weights[idx]) <= 0:
                ranked_lists.append([])
                continue
            ranked = ranker(q, docs, top_k=self.top_k)
            ranked_lists.append(ranked)
        fused = self._fuse_results(ranked_lists, active_weights)
        return [
            {
                "id": item.id,
                "title": item.title,
                "score": round(score, 6),
                "source": item.source,
            }
            for item, score in fused[: self.top_k]
        ]

    def _load_docs(self) -> List[_LibraryDoc]:
        global _docs_cache
        with _docs_cache_lock:
            if _docs_cache is not None:
                return _docs_cache
        with get_db_session_ctx() as session:
            rows = session.query(JAVMetadata).all()
            docs = [
                _LibraryDoc(
                    product_code=str(row.product_code or "").strip().upper(),
                    title=_title(row),
                    text=_doc_text(row),
                    metadata_text=_metadata_text(row),
                )
                for row in rows
                if str(row.product_code or "").strip()
            ]
        with _docs_cache_lock:
            _docs_cache = docs
            return docs

    def _search_bm25(self, query: str, docs: Sequence[_LibraryDoc], *, top_k: int) -> List[_SearchResult]:
        tokenized_docs = [_tokenize(doc.text) for doc in docs]
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []
        ranker = BM25Okapi(tokenized_docs) if BM25Okapi is not None else _FallbackBM25(tokenized_docs)
        scores = ranker.get_scores(query_tokens)
        ranked = sorted(
            zip(docs, scores),
            key=lambda item: float(item[1]),
            reverse=True,
        )
        return [
            _SearchResult(doc.product_code, doc.title, "bm25", float(score))
            for doc, score in ranked[:top_k]
            if float(score) > 0
        ]

    def _search_embedding(
        self,
        query: str,
        docs: Sequence[_LibraryDoc],
        *,
        top_k: int | None,
    ) -> List[_SearchResult]:
        self.last_embedding_diag = {}
        if not embeddings_enabled_from_env():
            self.last_embedding_diag = {"status": "disabled"}
            return []
        model = embeddings_ollama_model_from_env()
        try:
            query_vec = asyncio.run(ollama_embed_text(text=query, model=model, timeout_sec=60.0))
            embed_err = None
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                query_vec = loop.run_until_complete(ollama_embed_text(text=query, model=model, timeout_sec=60.0))
                embed_err = None
            except Exception as e:
                query_vec = None
                embed_err = f"{type(e).__name__}:{e}"
            finally:
                loop.close()
        except Exception as e:
            query_vec = None
            embed_err = f"{type(e).__name__}:{e}"

        if query_vec is None:
            try:
                from javstory.llm.ollama_serve import ollama_base_url

                _ollama_url = ollama_base_url()
            except Exception:
                _ollama_url = "http://localhost:11434"
            self.last_embedding_diag = {
                "status": "query_failed",
                "model": model,
                "error": (embed_err or "")[:300],
                "url": _ollama_url,
            }
            return []

        title_by_code = {doc.product_code: doc.title for doc in docs}
        results: List[_SearchResult] = []
        for _path, payload in _iter_embedding_payloads(model=model):
            pc = str(payload.get("product_code") or "").strip().upper()
            if not pc:
                continue
            vec = _pick_representative_vector(payload)
            score = _cosine(query_vec, vec or [])
            if math.isfinite(score):
                results.append(_SearchResult(pc, title_by_code.get(pc, pc), "embedding", float(score)))
        results.sort(key=lambda item: item.raw_score, reverse=True)
        out = results if top_k is None else results[: max(1, int(top_k))]
        self.last_embedding_diag = {
            "status": "ok",
            "model": model,
            "returned_n": len(out),
            "scored_n": len(results),
        }
        return out

    def _search_metadata(self, query: str, docs: Sequence[_LibraryDoc], *, top_k: int) -> List[_SearchResult]:
        terms = _tokenize(query)
        if not terms:
            return []
        scored: List[tuple[_LibraryDoc, float]] = []
        for doc in docs:
            metadata_tokens = set(_tokenize(doc.metadata_text))
            if not metadata_tokens:
                continue
            score = sum(1.0 for term in terms if term in metadata_tokens)
            if score:
                scored.append((doc, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return [
            _SearchResult(doc.product_code, doc.title, "metadata", float(score))
            for doc, score in scored[:top_k]
        ]

    def _fuse_results(
        self,
        ranked_lists: Sequence[Sequence[_SearchResult]],
        weights: tuple[float, float, float],
    ) -> List[tuple[_SearchResult, float]]:
        scores: dict[str, float] = {}
        items: dict[str, _SearchResult] = {}
        source_sets: dict[str, set[str]] = {}
        for list_idx, ranked in enumerate(ranked_lists):
            weight = float(weights[list_idx]) if list_idx < len(weights) else 0.0
            for rank, item in enumerate(ranked):
                if not item.id:
                    continue
                scores[item.id] = scores.get(item.id, 0.0) + weight / (self.fusion_k + rank + 1)
                if item.id not in items:
                    items[item.id] = item
                source_sets.setdefault(item.id, set()).add(item.source)

        fused = [
            (
                _SearchResult(
                    item.id,
                    item.title,
                    "+".join(sorted(source_sets.get(item.id, {item.source}))),
                    item.raw_score,
                ),
                score,
            )
            for item_id, score in scores.items()
            for item in [items[item_id]]
        ]
        fused.sort(key=lambda item: item[1], reverse=True)
        return fused


__all__ = ["HybridLibrarySearch", "clear_embed_search_cache"]
