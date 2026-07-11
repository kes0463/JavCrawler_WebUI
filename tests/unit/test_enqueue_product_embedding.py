"""Tests for harvest-time embedding enqueue helper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from javstory.library.embeddings.priority_queue import enqueue_product_embedding


def test_enqueue_product_embedding_noop_when_disabled():
    with patch(
        "javstory.library.embeddings.priority_queue.embeddings_enabled_from_env",
        return_value=False,
    ):
        assert enqueue_product_embedding("ABC-123") is False


def test_enqueue_product_embedding_uses_web_queue():
    mgr = MagicMock()
    mgr.enqueue.return_value = "emb-1"
    mod = MagicMock()
    mod.EmbeddingQueueController.instance.return_value = None
    with (
        patch(
            "javstory.library.embeddings.priority_queue.embeddings_enabled_from_env",
            return_value=True,
        ),
        patch.dict("sys.modules", {"gui.models.embedding_queue_model": mod}),
        patch(
            "javstory.library.embeddings.embedding_queue.embedding_queue_manager",
            mgr,
        ),
    ):
        assert enqueue_product_embedding("abc-123", force=True) is True
        mgr.enqueue.assert_called_once_with("ABC-123", force=True)


def test_enqueue_product_embedding_prefers_gui_queue():
    eq = MagicMock()
    mod = MagicMock()
    mod.EmbeddingQueueController.instance.return_value = eq
    with (
        patch(
            "javstory.library.embeddings.priority_queue.embeddings_enabled_from_env",
            return_value=True,
        ),
        patch(
            "javstory.library.embeddings.priority_queue.ensure_priority_embeddings_async"
        ) as ensure,
        patch.dict("sys.modules", {"gui.models.embedding_queue_model": mod}),
    ):
        assert enqueue_product_embedding("XYZ-9", force=True) is True
        eq.enqueue.assert_called_once_with("XYZ-9", force=True)
        ensure.assert_not_called()
