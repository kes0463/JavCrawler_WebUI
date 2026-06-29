"""Tests for hybrid crawler fallback logic."""

from javstory.harvest.crawler import _needs_fallback


def test_needs_fallback_when_synopsis_missing():
    assert _needs_fallback({
        "title": "STARS-001 Title",
        "cover_url": "https://example.com/poster.jpg",
        "synopsis": "",
    }) is True


def test_needs_fallback_complete_metadata():
    assert _needs_fallback({
        "title": "STARS-001 Title",
        "cover_url": "https://example.com/poster.jpg",
        "synopsis": "あらすじ本文",
    }) is False


def test_needs_fallback_missing_title():
    assert _needs_fallback({
        "title": "",
        "cover_url": "https://example.com/poster.jpg",
        "synopsis": "plot",
    }) is True
