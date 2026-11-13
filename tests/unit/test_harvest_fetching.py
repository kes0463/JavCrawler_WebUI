"""javstory.harvest.fetching — Scrapling 요청 계층의 폴백 순서 (네트워크 없이)."""

from __future__ import annotations

import pytest

from javstory.harvest import fetching as f


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    f.reset_host_memory()
    for k in ("JAVSTORY_CURL_CFFI_DISABLED", "JAVSTORY_HARVEST_BROWSER_ON_RESET"):
        monkeypatch.delenv(k, raising=False)
    yield
    f.reset_host_memory()


def _ok(url: str, via: str) -> f.FetchResult:
    return f.FetchResult(url=url, status_code=200, text="<html>ok</html>", via=via)


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[str] = []


def _install(monkeypatch, *, scrapling=None, req=None, browser=None) -> _Recorder:
    rec = _Recorder()

    def mk(name, behavior):
        def _fn(url, **kw):
            rec.calls.append(name)
            if isinstance(behavior, BaseException):
                raise behavior
            return _ok(url, name)

        return _fn

    monkeypatch.setattr(f, "_scrapling_get", mk("scrapling", scrapling))
    monkeypatch.setattr(f, "_requests_get", mk("requests", req))
    monkeypatch.setattr(f, "browser_get", mk("browser", browser))
    return rec


RESET = Exception("Failed to perform, curl: (35) Recv failure: Connection was reset.")


def test_scrapling_success_is_used_directly(monkeypatch):
    rec = _install(monkeypatch)
    res = f.http_get("https://a.example/x")
    assert res.via == "scrapling"
    assert rec.calls == ["scrapling"]


def test_reset_falls_back_to_requests_then_browser(monkeypatch):
    rec = _install(monkeypatch, scrapling=RESET, req=ConnectionResetError(10054, "reset"))
    res = f.http_get("https://a.example/x")
    assert res.via == "browser"
    assert rec.calls == ["scrapling", "requests", "browser"]


def test_reset_host_is_remembered_and_goes_straight_to_browser(monkeypatch):
    rec = _install(monkeypatch, scrapling=RESET, req=ConnectionResetError(10054, "reset"))
    f.http_get("https://a.example/1")
    rec.calls.clear()
    f.http_get("https://a.example/2")
    assert rec.calls == ["browser"]
    # 다른 호스트는 영향 없음
    rec.calls.clear()
    f.http_get("https://b.example/1")
    assert rec.calls[0] == "scrapling"


def test_reset_then_requests_success(monkeypatch):
    rec = _install(monkeypatch, scrapling=RESET)
    res = f.http_get("https://a.example/x")
    assert res.via == "requests"
    assert rec.calls == ["scrapling", "requests"]


def test_non_reset_error_is_raised_without_fallback(monkeypatch):
    rec = _install(monkeypatch, scrapling=TimeoutError("timed out"))
    with pytest.raises(TimeoutError):
        f.http_get("https://a.example/x")
    assert rec.calls == ["scrapling"]


def test_browser_fallback_can_be_disabled(monkeypatch):
    rec = _install(monkeypatch, scrapling=RESET, req=ConnectionResetError(10054, "reset"))
    with pytest.raises(ConnectionResetError):
        f.http_get("https://a.example/x", browser_fallback=False)
    assert "browser" not in rec.calls

    monkeypatch.setenv("JAVSTORY_HARVEST_BROWSER_ON_RESET", "0")
    rec.calls.clear()
    with pytest.raises(ConnectionResetError):
        f.http_get("https://a.example/y")
    assert "browser" not in rec.calls


def test_curl_disabled_env_uses_requests_only(monkeypatch):
    monkeypatch.setenv("JAVSTORY_CURL_CFFI_DISABLED", "1")
    rec = _install(monkeypatch)
    res = f.http_get("https://a.example/x")
    assert res.via == "requests"
    assert rec.calls == ["requests"]


def test_session_injection_bypasses_scrapling(monkeypatch):
    rec = _install(monkeypatch)

    class _Resp:
        url = "https://a.example/final"
        status_code = 404
        text = "nf"
        apparent_encoding = "utf-8"
        encoding = None

    class _Sess:
        def get(self, url, headers=None, timeout=None):
            return _Resp()

    res = f.http_get("https://a.example/x", session=_Sess())
    assert rec.calls == []
    assert (res.status_code, res.via, res.url) == (404, "session", "https://a.example/final")


def test_raise_for_status_message_keeps_status_code():
    res = f.FetchResult(url="https://a.example/x", status_code=403, text="", via="scrapling")
    with pytest.raises(f.FetchHTTPError) as ei:
        res.raise_for_status()
    # crawler 는 `"403" in str(e)` 로 브라우저 우회를 결정한다
    assert "403" in str(ei.value)
    assert ei.value.status_code == 403
    f.FetchResult(url="u", status_code=200, text="", via="x").raise_for_status()


def test_decode_body_falls_back_on_unknown_encoding():
    assert f._decode_body("日本".encode("utf-8"), "no-such-codec") == "日本"
