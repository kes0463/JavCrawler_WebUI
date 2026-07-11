"""Tests for manual Grok story generation service."""

from __future__ import annotations

from unittest.mock import patch

from javstory.services.grok_story_service import start_grok_story_generation


def test_start_grok_story_empty_codes():
    out = start_grok_story_generation([])
    assert out["ok"] is False
    assert out["queued"] == 0


def test_start_grok_story_skips_existing_without_force():
    with (
        patch(
            "javstory.services.grok_story_service.has_disk_grok_story_cache",
            return_value=True,
        ),
        patch(
            "javstory.services.grok_story_service.threading.Thread"
        ) as thread_cls,
    ):
        out = start_grok_story_generation(["ABC-123"], force=False)
        assert out["ok"] is True
        assert out["queued"] == 0
        assert out["skipped"] == 1
        thread_cls.assert_not_called()


def test_start_grok_story_queues_when_missing():
    with (
        patch(
            "javstory.services.grok_story_service.has_disk_grok_story_cache",
            return_value=False,
        ),
        patch(
            "javstory.services.grok_story_service.threading.Thread"
        ) as thread_cls,
    ):
        out = start_grok_story_generation(["abc-123"], force=False)
        assert out["ok"] is True
        assert out["queued"] == 1
        thread_cls.assert_called_once()
    # Mocked thread never clears running set — reset for other tests.
    from javstory.services import grok_story_service as svc

    with svc._LOCK:
        svc._RUNNING.clear()
