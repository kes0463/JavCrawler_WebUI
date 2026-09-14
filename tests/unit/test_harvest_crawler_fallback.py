"""Tests for hybrid crawler fallback logic."""

from javstory.harvest.crawler import _browser_chases_synopsis, _needs_fallback


def test_needs_fallback_when_synopsis_missing():
    # 기본(require_synopsis=False): synopsis 만 비어도 다음 소스로 넘어가지 않는다.
    assert _needs_fallback({
        "title": "STARS-001 Title",
        "cover_url": "https://example.com/poster.jpg",
        "synopsis": "",
    }) is False


def test_needs_fallback_synopsis_missing_when_required():
    # 값싼 HTTP 소스는 require_synopsis=True 로 synopsis 를 계속 보완한다.
    assert _needs_fallback({
        "title": "STARS-001 Title",
        "cover_url": "https://example.com/poster.jpg",
        "synopsis": "",
    }, require_synopsis=True) is True


def test_browser_chases_synopsis_env(monkeypatch):
    monkeypatch.delenv("JAVSTORY_HARVEST_BROWSER_FOR_SYNOPSIS", raising=False)
    assert _browser_chases_synopsis() is False
    monkeypatch.setenv("JAVSTORY_HARVEST_BROWSER_FOR_SYNOPSIS", "1")
    assert _browser_chases_synopsis() is True


def test_needs_fallback_complete_metadata():
    assert _needs_fallback({
        "title": "STARS-001 Title",
        "cover_url": "https://example.com/poster.jpg",
        "synopsis": "あらすじ本文",
    }) is False


def test_needs_fallback_boilerplate_title():
    assert _needs_fallback({
        "title": "123av.com — 새 도메인을 기억해 주세요",
        "cover_url": "https://example.com/poster.jpg",
        "synopsis": "",
    }) is True


def test_needs_fallback_missing_title():
    assert _needs_fallback({
        "title": "",
        "cover_url": "https://example.com/poster.jpg",
        "synopsis": "plot",
    }) is True
