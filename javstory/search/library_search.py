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

# (timestamp, docs) — TTL 만료 시 재조회. 예전엔 무제한 캐시라 신규 하베스트·메타 수정이
# 웹서버 재시작 전까지 BM25/메타데이터 채널·임베딩 히트 제목에 반영 안 됐다.
_docs_cache: tuple[float, List["_LibraryDoc"]] | None = None
_docs_cache_lock = threading.Lock()
_docs_cache_version = 0
_DOCS_CACHE_TTL_SEC = 60.0
_DOCS_CACHE_TTL_ENV = "JAVSTORY_LIBRARY_SEARCH_DOCS_CACHE_TTL"
_embed_result_cache: dict[str, tuple[float, list, dict[str, Any]]] = {}
_embed_result_cache_lock = threading.Lock()
_EMBED_RESULT_CACHE_TTL_SEC = 600.0
_EMBED_RESULT_CACHE_MAX = 48

# BM25는 코퍼스 전체(전 작품) 토큰화 + IDF 계산 비용이 커서, docs 캐시가 갱신될 때만
# 다시 빌드한다. 키는 _docs_cache_version — id(docs)는 GC 후 메모리 주소가 재사용되면
# 다른 리스트끼리 충돌할 수 있어(드물지만 실제 버그) 명시적 카운터를 쓴다.
_bm25_index_cache: tuple[int, Any] | None = None
_bm25_index_cache_lock = threading.Lock()

try:
    from rank_bm25 import BM25Okapi
except ImportError:  # pragma: no cover - exercised only when optional dep is absent.
    BM25Okapi = None  # type: ignore[assignment]

from javstory.harvest.database import JAVMetadata, get_db_session_ctx
from javstory.library.embeddings.pipeline import (
    embeddings_enabled_from_env,
    embeddings_ollama_model_from_env,
    embed_texts,
)
from javstory.library.embeddings.query_format import (
    blend_embedding_lexical_score,
    concept_coverage,
    expand_query_concepts,
    format_search_query_for_embedding,
)
from javstory.library.embeddings.similarity import (
    _iter_embedding_payloads,
    max_doc_cosine,
    payload_doc_text_blob,
)

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


def _embedding_min_score_from_env(default: float = 0.36) -> float:
    raw = (os.environ.get(_EMBED_MIN_SCORE_ENV, "") or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return min(0.95, max(0.05, value))


def _embedding_relative_ratio_from_env(default: float = 0.84) -> float:
    raw = (os.environ.get(_EMBED_REL_RATIO_ENV, "") or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return min(0.99, max(0.05, value))


def _embedding_max_gap_from_env(default: float = 0.10) -> float:
    """1등 대비 허용 점수 하락폭. 작을수록 상위 유사도만 유지."""
    raw = (os.environ.get(_EMBED_MAX_GAP_ENV, "") or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return min(0.5, max(0.01, value))


def embedding_search_thresholds_from_env() -> dict[str, float]:
    """Settings/API용 자연어 검색 컷오프 스냅샷."""
    return {
        "search_min_score": round(_embedding_min_score_from_env(), 4),
        "search_relative_ratio": round(_embedding_relative_ratio_from_env(), 4),
        "search_max_gap": round(_embedding_max_gap_from_env(), 4),
    }

def _docs_cache_ttl() -> float:
    raw = (os.environ.get(_DOCS_CACHE_TTL_ENV, "") or "").strip()
    if not raw:
        return _DOCS_CACHE_TTL_SEC
    try:
        return max(5.0, float(raw))
    except ValueError:
        return _DOCS_CACHE_TTL_SEC


def invalidate_library_docs_cache() -> None:
    """라이브러리 메타데이터 변경(수정 등) 시 호출 — BM25/메타데이터 검색용 문서 캐시를 즉시 비운다.

    TTL(기본 60초)이 안전망 역할을 하므로 모든 변경 경로에서 호출하지 않아도 결국은
    반영되지만, 수동 편집처럼 호출 지점이 명확한 곳은 즉시 반영하는 게 낫다.
    """
    global _docs_cache, _docs_cache_version
    with _docs_cache_lock:
        _docs_cache = None
        _docs_cache_version += 1


def _get_bm25_ranker(docs: Sequence["_LibraryDoc"], *, version: int) -> Any:
    """docs 캐시 세대(version) 단위로 BM25 인덱스를 캐시.

    토큰화 + IDF 계산은 코퍼스 전체 크기에 비례해 비싸다. docs 캐시가 갱신될 때만
    (버전이 바뀔 때만) 재빌드한다.
    """
    global _bm25_index_cache
    with _bm25_index_cache_lock:
        if _bm25_index_cache is not None and _bm25_index_cache[0] == version:
            return _bm25_index_cache[1]

    tokenized_docs = [_tokenize(doc.text) for doc in docs]
    ranker = BM25Okapi(tokenized_docs) if BM25Okapi is not None else _FallbackBM25(tokenized_docs)

    with _bm25_index_cache_lock:
        _bm25_index_cache = (version, ranker)
    return ranker


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
    # v2: e5 instruct + max-doc + concept coverage
    raw = (
        f"v2|{model}|{min_score:.4f}|{relative_ratio:.4f}|{max_gap:.4f}|"
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

    mid = scores[len(scores) // 2]
    # 상위가 코퍼스와 거의 안 갈라지면(평탄 분포) 강하게 자른다
    discrimination = top - mid
    effective_ratio = relative_ratio
    effective_gap = max_gap
    if discrimination < 0.08:
        effective_ratio = max(effective_ratio, 0.90)
        effective_gap = min(effective_gap, 0.05)
    elif discrimination < 0.12:
        effective_ratio = max(effective_ratio, 0.87)
        effective_gap = min(effective_gap, 0.07)

    mean = sum(scores) / len(scores)
    var = sum((s - mean) ** 2 for s in scores) / len(scores)
    std = math.sqrt(var)
    dist_floor = mean + max(0.05, 0.9 * std)
    floor = max(
        min_score,
        top * effective_ratio,
        top - effective_gap,
        dist_floor,
    )
    floor = min(floor, top)

    selected = [item for item in scored if float(item.raw_score) >= floor]
    if len(selected) <= 1:
        return selected

    cut: List[_SearchResult] = [selected[0]]
    cliff = max(0.018, top * 0.04)
    tight = top * effective_ratio
    for prev, cur in zip(selected, selected[1:]):
        drop = float(prev.raw_score) - float(cur.raw_score)
        if drop >= cliff and float(cur.raw_score) < tight:
            break
        if (top - float(cur.raw_score)) > effective_gap:
            break
        cut.append(cur)
    # 평탄 분포면 상위 소수만
    if discrimination < 0.08:
        return cut[:12]
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

    def search_embedding_union_bm25(
        self,
        query: str,
        *,
        bm25_top_k: int = 40,
        min_score: float | None = None,
        relative_ratio: float | None = None,
        max_gap: float | None = None,
    ) -> list:
        """
        라이브러리 UI용: 임베딩 고유사도 밴드를 유지한 채 BM25 히트를 뒤에 덧붙인다.
        RRF로 점수를 섞지 않아 시맨틱 top 밴드가 희석되지 않는다.
        """
        q = (query or "").strip()
        if not q:
            return []
        emb_hits = self.search_by_embedding(
            q,
            min_score=min_score,
            relative_ratio=relative_ratio,
            max_gap=max_gap,
        )
        emb_diag = dict(self.last_embedding_diag or {})
        bm25_top = max(1, min(200, int(bm25_top_k or 40)))
        bm25_hits: list[dict[str, Any]] = []
        docs = self._load_docs()
        if docs:
            for item in self._search_bm25(q, docs, top_k=bm25_top):
                pid = str(item.id or "").strip().upper()
                if not pid:
                    continue
                bm25_hits.append(
                    {
                        "id": pid,
                        "title": item.title,
                        "score": round(float(item.raw_score), 6),
                        "source": "bm25",
                    }
                )

        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for hit in emb_hits:
            pid = str(hit.get("id") or "").strip().upper()
            if not pid or pid in seen:
                continue
            seen.add(pid)
            merged.append(
                {
                    "id": pid,
                    "title": hit.get("title") or pid,
                    "score": float(hit.get("score") or 0),
                    "source": "embedding",
                }
            )
        for hit in bm25_hits:
            pid = str(hit.get("id") or "").strip().upper()
            if not pid or pid in seen:
                continue
            seen.add(pid)
            merged.append(hit)

        self.last_embedding_diag = {
            **emb_diag,
            "embedding_n": len(emb_hits),
            "bm25_n": len(bm25_hits),
            "union_n": len(merged),
        }
        return merged

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
        global _docs_cache, _docs_cache_version
        now = time.time()
        ttl = _docs_cache_ttl()
        with _docs_cache_lock:
            if _docs_cache is not None:
                ts, docs = _docs_cache
                if now - ts < ttl:
                    return docs
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
            _docs_cache = (now, docs)
            _docs_cache_version += 1
            return docs

    def _search_bm25(self, query: str, docs: Sequence[_LibraryDoc], *, top_k: int) -> List[_SearchResult]:
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []
        with _docs_cache_lock:
            version = _docs_cache_version
        ranker = _get_bm25_ranker(docs, version=version)
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
        embed_input = format_search_query_for_embedding(query, model=model)
        try:
            vecs = asyncio.run(embed_texts([embed_input], model=model))
            query_vec = vecs[0] if vecs else None
            embed_err = None
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                vecs = loop.run_until_complete(embed_texts([embed_input], model=model))
                query_vec = vecs[0] if vecs else None
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
            from javstory.library.embeddings.pipeline import embeddings_backend_from_env

            backend = embeddings_backend_from_env()
            try:
                if backend == "ollama":
                    from javstory.llm.ollama_serve import ollama_base_url
                    endpoint = ollama_base_url()
                else:
                    from javstory.llm.llamacpp_embeddings import embeddings_llamacpp_base_url
                    endpoint = embeddings_llamacpp_base_url()
            except Exception:
                endpoint = "llama-server" if backend != "ollama" else "http://localhost:11434"
            self.last_embedding_diag = {
                "status": "query_failed",
                "backend": backend,
                "endpoint": endpoint,
                "model": model,
                "error": (embed_err or "")[:300],
                "url": endpoint,
            }
            return []

        title_by_code = {doc.product_code: doc.title for doc in docs}
        concepts = expand_query_concepts(query)
        concept_n = len(concepts)
        results: List[_SearchResult] = []
        ann_used = False
        try:
            from javstory.library.embeddings.ann_index import (
                ann_enabled_from_env,
                search_ann_max_cosine,
            )

            if ann_enabled_from_env():
                ann_hits, text_by_code = search_ann_max_cosine(query_vec, model=model)
                if ann_hits:
                    ann_used = True
                    for pc, cosine in ann_hits:
                        if not math.isfinite(cosine):
                            continue
                        blob = text_by_code.get(pc, "") if concepts else ""
                        cov = concept_coverage(blob, concepts) if concepts else 0.0
                        score = blend_embedding_lexical_score(cosine, cov, concept_n=concept_n)
                        if math.isfinite(score):
                            results.append(
                                _SearchResult(pc, title_by_code.get(pc, pc), "embedding", float(score))
                            )
        except Exception:
            ann_used = False
            results = []

        if not ann_used:
            for _path, payload in _iter_embedding_payloads(model=model):
                pc = str(payload.get("product_code") or "").strip().upper()
                if not pc:
                    continue
                cosine = max_doc_cosine(query_vec, payload)
                if not math.isfinite(cosine):
                    continue
                cov = concept_coverage(payload_doc_text_blob(payload), concepts) if concepts else 0.0
                score = blend_embedding_lexical_score(cosine, cov, concept_n=concept_n)
                if math.isfinite(score):
                    results.append(_SearchResult(pc, title_by_code.get(pc, pc), "embedding", float(score)))
        results.sort(key=lambda item: item.raw_score, reverse=True)
        out = results if top_k is None else results[: max(1, int(top_k))]
        self.last_embedding_diag = {
            "status": "ok",
            "model": model,
            "query_format": "e5_instruct" if embed_input != query else "raw",
            "concept_n": concept_n,
            "returned_n": len(out),
            "scored_n": len(results),
            "ann_used": ann_used,
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


__all__ = [
    "HybridLibrarySearch",
    "clear_embed_search_cache",
    "embedding_search_thresholds_from_env",
    "invalidate_library_docs_cache",
]
