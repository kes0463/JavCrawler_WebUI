from __future__ import annotations

import numpy as np


def test_cache_manager_singleton_and_embedding_cache():
    from javstory.utils.cache_manager import CacheManager, cache_manager

    other = CacheManager()
    assert other is cache_manager

    cache_manager.reset()
    stored = cache_manager.set_embedding("hello", [1, 2, 3])
    loaded = cache_manager.get_embedding("hello")

    assert isinstance(stored, np.ndarray)
    assert loaded is stored
    assert np.array_equal(loaded, np.array([1.0, 2.0, 3.0]))


def test_cache_manager_search_cache_and_stats():
    from javstory.utils.cache_manager import cache_manager

    cache_manager.reset()
    assert cache_manager.get_search_results("query") is None
    cache_manager.set_search_results("query", [{"id": "A"}])

    assert cache_manager.get_search_results("query") == [{"id": "A"}]
    stats = cache_manager.get_stats()
    assert stats["search_hits"] == 1
    assert stats["search_misses"] == 1
    assert stats["search_hit_rate"] == 0.5


def test_cache_manager_lru_and_invalidation():
    from javstory.utils.cache_manager import cache_manager

    cache_manager.reset()
    old_embedding_size = cache_manager.embedding_max_size
    old_search_size = cache_manager.search_max_size
    cache_manager.embedding_max_size = 2
    cache_manager.search_max_size = 2
    try:
        cache_manager.set_embedding("a", [1])
        cache_manager.set_embedding("b", [2])
        cache_manager.get_embedding("a")
        cache_manager.set_embedding("c", [3])

        assert cache_manager.get_embedding("a") is not None
        assert cache_manager.get_embedding("b") is None

        cache_manager.set_search_results("alpha", [1])
        cache_manager.set_search_results("beta", [2])
        cache_manager.invalidate_by_prefix(cache_manager.make_key("alpha")[:8])
        assert cache_manager.get_search_results("alpha") is None
        assert cache_manager.get_search_results("beta") == [2]

        cache_manager.invalidate_search_cache()
        assert cache_manager.get_search_results("beta") is None
    finally:
        cache_manager.embedding_max_size = old_embedding_size
        cache_manager.search_max_size = old_search_size
        cache_manager.reset()


def test_cache_manager_compat_import():
    from javstory.utils.cache_manager import cache_manager as canonical
    from utils.cache_manager import cache_manager as compat

    assert compat is canonical


def test_cache_manager_accepts_prehashed_embedding_key():
    import hashlib

    from javstory.utils.cache_manager import cache_manager

    cache_manager.reset()
    text_hash = hashlib.md5("hello".encode()).hexdigest()
    cache_manager.set_embedding(text_hash, [1, 2])

    assert cache_manager.get_embedding(text_hash) is not None
    assert list(cache_manager.embedding_cache.keys()) == [text_hash]
