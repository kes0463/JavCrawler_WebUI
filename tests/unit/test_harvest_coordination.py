"""Tests for Harvest ↔ embedding coordination."""

from __future__ import annotations

from unittest.mock import patch

from javstory.library.embeddings import harvest_coordination as hc
from javstory.library.embeddings.priority_queue import enqueue_product_embedding


def test_begin_end_harvest_session_defers_embeddings(monkeypatch):
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_PAUSE_DURING_HARVEST", "1")
    hc._harvest_session_count = 0
    hc._harvest_paused = False
    hc._deferred_codes.clear()

    with patch.object(hc, "_maybe_stop_embeddings_server"):
        hc.begin_harvest_session()
    assert hc.is_embedding_harvest_paused() is True

    with patch(
        "javstory.library.embeddings.priority_queue.embeddings_enabled_from_env",
        return_value=True,
    ):
        assert enqueue_product_embedding("ABC-123") is True
    assert hc.deferred_embedding_count() == 1

    with (
        patch(
            "javstory.library.embeddings.pipeline.embeddings_enabled_from_env",
            return_value=True,
        ),
        patch.object(hc, "_enqueue_product_embedding_now", return_value=True) as flush_mock,
        patch.object(hc, "_maybe_stop_translation_server") as stop_chat,
        patch.object(hc, "_maybe_start_embeddings_server") as start_embed,
        patch.object(hc, "_embedding_queue_has_pending", return_value=False),
    ):
        n = hc.end_harvest_session()
    assert n == 1
    flush_mock.assert_called_once_with("ABC-123")
    stop_chat.assert_called_once()
    start_embed.assert_called_once()
    assert hc.is_embedding_harvest_paused() is False
    assert hc.deferred_embedding_count() == 0


def test_end_harvest_stops_chat_before_embeddings_even_without_deferred(monkeypatch):
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_PAUSE_DURING_HARVEST", "1")
    hc._harvest_session_count = 0
    hc._harvest_paused = False
    hc._deferred_codes.clear()

    with patch.object(hc, "_maybe_stop_embeddings_server"):
        hc.begin_harvest_session()

    order: list[str] = []

    def _stop(*_a, **_k):
        order.append("stop_chat")

    def _start(*_a, **_k):
        order.append("start_embed")

    with (
        patch.object(hc, "_maybe_stop_translation_server", side_effect=_stop),
        patch.object(hc, "_maybe_start_embeddings_server", side_effect=_start),
        patch.object(hc, "_embedding_queue_has_pending", return_value=True),
    ):
        assert hc.end_harvest_session() == 0
    assert order == ["stop_chat", "start_embed"]


def test_nested_harvest_sessions(monkeypatch):
    monkeypatch.setenv("JAVSTORY_EMBEDDINGS_PAUSE_DURING_HARVEST", "1")
    hc._harvest_session_count = 0
    hc._harvest_paused = False
    hc._deferred_codes.clear()

    with patch.object(hc, "_maybe_stop_embeddings_server"):
        hc.begin_harvest_session()
        hc.begin_harvest_session()
    with (
        patch.object(hc, "_maybe_stop_translation_server"),
        patch.object(hc, "_maybe_start_embeddings_server"),
        patch.object(hc, "_embedding_queue_has_pending", return_value=False),
    ):
        hc.end_harvest_session()
        assert hc.is_embedding_harvest_paused() is True
        hc.end_harvest_session()
    assert hc.is_embedding_harvest_paused() is False
