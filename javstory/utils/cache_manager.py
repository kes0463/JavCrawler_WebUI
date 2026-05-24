"""In-memory LRU caches for embeddings and search results."""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from threading import RLock
from typing import Any, List

import numpy as np

_MD5_RE = __import__("re").compile(r"^[a-fA-F0-9]{32}$")


class CacheManager:
    """Singleton cache manager with separate embedding/search LRU caches."""

    _instance: "CacheManager | None" = None
    _instance_lock = RLock()

    def __new__(cls, *args: Any, **kwargs: Any) -> "CacheManager":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, *, embedding_max_size: int = 512, search_max_size: int = 256) -> None:
        if getattr(self, "_initialized", False):
            return
        self.embedding_max_size = max(1, int(embedding_max_size or 512))
        self.search_max_size = max(1, int(search_max_size or 256))
        self.embedding_cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self.search_cache: OrderedDict[str, List[Any]] = OrderedDict()
        self._lock = RLock()
        self._embedding_hits = 0
        self._embedding_misses = 0
        self._search_hits = 0
        self._search_misses = 0
        self._initialized = True

    @staticmethod
    def make_key(text: str) -> str:
        """Return an MD5 hash key for text."""
        return hashlib.md5(str(text or "").encode("utf-8")).hexdigest()

    @classmethod
    def _resolve_key(cls, text_or_hash: str) -> str:
        raw = str(text_or_hash or "")
        return raw.lower() if _MD5_RE.fullmatch(raw) else cls.make_key(raw)

    def get_embedding(self, text: str) -> np.ndarray | None:
        key = self._resolve_key(text)
        with self._lock:
            value = self.embedding_cache.get(key)
            if value is None:
                self._embedding_misses += 1
                return None
            self.embedding_cache.move_to_end(key)
            self._embedding_hits += 1
            return value

    def set_embedding(self, text: str, vector: Any) -> np.ndarray:
        key = self._resolve_key(text)
        arr = np.asarray(vector, dtype=float)
        with self._lock:
            self.embedding_cache[key] = arr
            self.embedding_cache.move_to_end(key)
            self._trim_lru(self.embedding_cache, self.embedding_max_size)
        return arr

    def get_search_results(self, query: str) -> List[Any] | None:
        key = self.make_key(query)
        with self._lock:
            value = self.search_cache.get(key)
            if value is None:
                self._search_misses += 1
                return None
            self.search_cache.move_to_end(key)
            self._search_hits += 1
            return list(value)

    def set_search_results(self, query: str, results: List[Any]) -> List[Any]:
        key = self.make_key(query)
        value = list(results or [])
        with self._lock:
            self.search_cache[key] = value
            self.search_cache.move_to_end(key)
            self._trim_lru(self.search_cache, self.search_max_size)
        return value

    def invalidate_search_cache(self) -> None:
        """Clear all cached search results."""
        with self._lock:
            self.search_cache.clear()

    def invalidate_by_prefix(self, prefix: str) -> None:
        """Delete cache entries whose MD5 keys start with prefix."""
        raw_prefix = str(prefix or "")
        if not raw_prefix:
            return
        with self._lock:
            for cache in (self.embedding_cache, self.search_cache):
                for key in [key for key in cache if key.startswith(raw_prefix)]:
                    del cache[key]

    def get_stats(self) -> dict:
        """Return cache sizes and hit-rate statistics."""
        with self._lock:
            embedding_total = self._embedding_hits + self._embedding_misses
            search_total = self._search_hits + self._search_misses
            total_hits = self._embedding_hits + self._search_hits
            total_requests = embedding_total + search_total
            return {
                "embedding_cache_size": len(self.embedding_cache),
                "embedding_cache_max_size": self.embedding_max_size,
                "search_cache_size": len(self.search_cache),
                "search_cache_max_size": self.search_max_size,
                "embedding_hits": self._embedding_hits,
                "embedding_misses": self._embedding_misses,
                "embedding_hit_rate": self._hit_rate(self._embedding_hits, embedding_total),
                "search_hits": self._search_hits,
                "search_misses": self._search_misses,
                "search_hit_rate": self._hit_rate(self._search_hits, search_total),
                "hit_rate": self._hit_rate(total_hits, total_requests),
            }

    def reset(self) -> None:
        """Clear both caches and counters. Intended for tests and manual reset."""
        with self._lock:
            self.embedding_cache.clear()
            self.search_cache.clear()
            self._embedding_hits = 0
            self._embedding_misses = 0
            self._search_hits = 0
            self._search_misses = 0

    @staticmethod
    def _trim_lru(cache: OrderedDict[str, Any], max_size: int) -> None:
        while len(cache) > max_size:
            cache.popitem(last=False)

    @staticmethod
    def _hit_rate(hits: int, total: int) -> float:
        if total <= 0:
            return 0.0
        return round(float(hits) / float(total), 4)


cache_manager = CacheManager()


__all__ = ["CacheManager", "cache_manager"]
