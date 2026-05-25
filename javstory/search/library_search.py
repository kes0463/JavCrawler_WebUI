"""Hybrid library search with Reciprocal Rank Fusion."""

from __future__ import annotations

import asyncio
import math
import os
import re
from dataclasses import dataclass
from typing import Any, Iterable, List, Sequence

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
        self.top_k = max(1, min(50, int(top_k or 20)))
        self.fusion_k = max(1, int(fusion_k or 60))

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

        ranked_lists = [
            self._search_bm25(q, docs, top_k=self.top_k),
            self._search_embedding(q, docs, top_k=self.top_k),
            self._search_metadata(q, docs, top_k=self.top_k),
        ]
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
        with get_db_session_ctx() as session:
            rows = session.query(JAVMetadata).all()
            return [
                _LibraryDoc(
                    product_code=str(row.product_code or "").strip().upper(),
                    title=_title(row),
                    text=_doc_text(row),
                    metadata_text=_metadata_text(row),
                )
                for row in rows
                if str(row.product_code or "").strip()
            ]

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

    def _search_embedding(self, query: str, docs: Sequence[_LibraryDoc], *, top_k: int) -> List[_SearchResult]:
        if not embeddings_enabled_from_env():
            return []
        model = embeddings_ollama_model_from_env()
        try:
            query_vec = asyncio.run(ollama_embed_text(text=query, model=model, timeout_sec=60.0))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                query_vec = loop.run_until_complete(ollama_embed_text(text=query, model=model, timeout_sec=60.0))
            finally:
                loop.close()
        except Exception:
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
        return results[:top_k]

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


__all__ = ["HybridLibrarySearch"]
