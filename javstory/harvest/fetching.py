"""Harvest 공용 수집(요청/브라우저) 계층 — Scrapling 기반.

모든 스크레이퍼는 여기의 `http_get` / `browser_get` 만 호출하고, 돌려받은 HTML은 각자
BeautifulSoup 으로 파싱한다(파싱 로직은 이 모듈의 관심사가 아님).

- `http_get`: Scrapling `Fetcher` (curl_cffi 기반 브라우저 TLS 위장 + stealthy 헤더).
  curl 이 연결 리셋(`curl: (35)`)으로 실패하면 기존과 같이 일반 `requests` 로 한 번 더
  시도하고, 그래도 막히면 브라우저(`browser_get`)로 넘어간다. 일부 사이트는 curl 계열
  TLS 연결만 끊고 Chromium 연결은 통과시키기 때문이다.
- `browser_get`: Scrapling `StealthyFetcher` (patchright Chromium, Cloudflare 대응).

환경 변수
- `JAVSTORY_CURL_CFFI_DISABLED=1`  : Scrapling HTTP 대신 일반 `requests` 만 사용(기존 호환).
- `JAVSTORY_HARVEST_BROWSER_ON_RESET=0` : 연결 리셋 시 브라우저로 넘어가지 않음.
- `JAVSTORY_HARVEST_BROWSER_HEADLESS=0` : 브라우저 창을 띄움(디버깅용).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional
from urllib.parse import urlparse

import requests

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
_IMPERSONATE = "chrome131"

# 연결 리셋이 난 호스트는 한동안 curl/requests 를 건너뛰고 바로 브라우저로 간다.
# (123av 처럼 locale×slug 로 여러 번 요청하는 소스에서 매번 리셋을 기다리지 않도록)
_RESET_MEMORY_SECONDS = 600.0
_reset_hosts: dict[str, float] = {}
_reset_lock = threading.Lock()


def _quiet_scrapling_logger() -> None:
    """Scrapling 은 요청마다 INFO("Fetched (200) ...")와 재시도 ERROR 를 stdout 에 찍는다.
    실패 처리는 여기서 하고 하베스트 로그는 log_ts 로 남기므로 CRITICAL 만 통과시킨다.
    `JAVSTORY_SCRAPLING_LOG=1` 이면 그대로 둔다(디버깅용)."""
    if _env_flag("JAVSTORY_SCRAPLING_LOG", False):
        return
    logging.getLogger("scrapling").setLevel(logging.CRITICAL)


def _env_flag(name: str, default: bool) -> bool:
    raw = (os.environ.get(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


class FetchHTTPError(Exception):
    """HTTP 4xx/5xx 응답. 메시지에 상태 코드가 들어가므로 `"403" in str(e)` 판정이 유지된다."""

    def __init__(self, result: "FetchResult") -> None:
        super().__init__(f"HTTP {result.status_code} for url: {result.url} (via {result.via})")
        self.result = result
        self.status_code = result.status_code


@dataclass
class FetchResult:
    url: str
    status_code: int
    text: str
    via: str  # "scrapling" | "requests" | "browser"

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 400

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise FetchHTTPError(self)


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _is_connection_reset(exc: BaseException) -> bool:
    msg = str(exc).lower()
    if "curl:" in msg and ("(35)" in msg or "recv failure" in msg or "(56)" in msg):
        return True
    # DNS 실패·연결 거부·타임아웃은 브라우저로도 안 되므로 '리셋'만 잡는다.
    return isinstance(exc, ConnectionResetError) or (
        "connection was reset" in msg or "connectionreseterror" in msg or "10054" in msg
    )


def _remember_reset(host: str) -> None:
    if not host:
        return
    with _reset_lock:
        _reset_hosts[host] = time.monotonic()


def _host_recently_reset(host: str) -> bool:
    if not host:
        return False
    with _reset_lock:
        ts = _reset_hosts.get(host)
        if ts is None:
            return False
        if time.monotonic() - ts > _RESET_MEMORY_SECONDS:
            _reset_hosts.pop(host, None)
            return False
        return True


def _decode_body(body: bytes, encoding: Optional[str]) -> str:
    enc = (encoding or "").strip() or "utf-8"
    try:
        return body.decode(enc, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _from_scrapling(resp: Any, *, via: str, fallback_url: str) -> FetchResult:
    url = str(getattr(resp, "url", "") or fallback_url)
    status = int(getattr(resp, "status", 0) or 0)
    body = getattr(resp, "body", b"") or b""
    if isinstance(body, str):
        text = body
    else:
        text = _decode_body(body, getattr(resp, "encoding", None))
    return FetchResult(url=url, status_code=status, text=text, via=via)


def _requests_get(url: str, *, headers: Mapping[str, str], timeout: float) -> FetchResult:
    r = requests.get(url, headers=dict(headers), timeout=timeout, allow_redirects=True)
    r.encoding = r.apparent_encoding or "utf-8"
    return FetchResult(url=str(r.url), status_code=int(r.status_code), text=r.text, via="requests")


def _scrapling_get(url: str, *, headers: Mapping[str, str], timeout: float, retries: int) -> FetchResult:
    from scrapling.fetchers import Fetcher

    _quiet_scrapling_logger()
    resp = Fetcher.get(
        url,
        headers=dict(headers),
        timeout=timeout,
        impersonate=_IMPERSONATE,
        stealthy_headers=True,
        follow_redirects=True,
        retries=max(1, int(retries)),
        retry_delay=1,
    )
    return _from_scrapling(resp, via="scrapling", fallback_url=url)


def http_get(
    url: str,
    *,
    headers: Optional[Mapping[str, str]] = None,
    timeout: float = 12.0,
    retries: int = 2,
    browser_fallback: bool = True,
    browser_timeout: float = 30.0,
    session: Any = None,
) -> FetchResult:
    """HTML 페이지 GET. 4xx/5xx 는 예외가 아니라 `status_code` 로 돌려준다(전송 실패만 예외).

    전송 실패 순서: Scrapling(curl_cffi) → 연결 리셋이면 requests → 그래도 리셋이면 브라우저.
    `session` (requests.Session 호환)을 주면 그것만 사용한다(테스트/주입용, 기존 시그니처 호환).
    """
    hdrs: dict[str, str] = {"User-Agent": DEFAULT_UA}
    if headers:
        hdrs.update({k: v for k, v in headers.items() if v is not None})
    if session is not None:
        r = session.get(url, headers=hdrs, timeout=timeout)
        try:
            r.encoding = r.apparent_encoding or "utf-8"
        except Exception:
            pass
        return FetchResult(
            url=str(getattr(r, "url", url) or url),
            status_code=int(getattr(r, "status_code", 0) or 0),
            text=r.text,
            via="session",
        )
    host = _host(url)
    use_browser = browser_fallback and _env_flag("JAVSTORY_HARVEST_BROWSER_ON_RESET", True)

    if use_browser and _host_recently_reset(host):
        return browser_get(url, timeout=browser_timeout, locale=_locale_from_headers(hdrs))

    last_exc: Optional[BaseException] = None
    if not _env_flag("JAVSTORY_CURL_CFFI_DISABLED", False):
        try:
            return _scrapling_get(url, headers=hdrs, timeout=timeout, retries=retries)
        except Exception as e:
            last_exc = e
            if not _is_connection_reset(e):
                raise
    try:
        return _requests_get(url, headers=hdrs, timeout=timeout)
    except Exception as e:
        last_exc = e
        if not (use_browser and _is_connection_reset(e)):
            raise
    _remember_reset(host)
    try:
        return browser_get(url, timeout=browser_timeout, locale=_locale_from_headers(hdrs))
    except Exception:
        if last_exc is not None:
            raise last_exc
        raise


def _locale_from_headers(headers: Mapping[str, str]) -> str:
    al = (headers.get("Accept-Language") or "").split(",")[0].strip()
    return al or "ja-JP"


def browser_get(
    url: str,
    *,
    timeout: float = 45.0,
    page_action: Optional[Callable[[Any], Any]] = None,
    wait_selector: Optional[str] = None,
    headless: Optional[bool] = None,
    solve_cloudflare: bool = False,
    locale: str = "ja-JP",
) -> FetchResult:
    """Stealth Chromium 으로 페이지를 열고 최종 DOM HTML 을 돌려준다.

    `page_action(page)` 는 patchright(동기) Page 를 받아 나이 확인 클릭 등 상호작용을 한다.
    호출 스레드에 실행 중인 asyncio 루프가 없어야 한다(`asyncio.to_thread` 안에서 호출).
    """
    from scrapling.fetchers import StealthyFetcher

    _quiet_scrapling_logger()
    if headless is None:
        headless = _env_flag("JAVSTORY_HARVEST_BROWSER_HEADLESS", True)
    kwargs: dict[str, Any] = {
        "headless": headless,
        "timeout": int(max(5.0, float(timeout)) * 1000),
        "disable_resources": True,
        "block_webrtc": True,
        "locale": locale,
        "solve_cloudflare": solve_cloudflare,
        "retries": 1,
        # 동영상 사이트라 자동 재생/소리 방지 (기존 DrissionPage 옵션과 동일)
        "extra_flags": ["--autoplay-policy=user-gesture-required", "--mute-audio"],
    }
    if page_action is not None:
        kwargs["page_action"] = page_action
    if wait_selector:
        kwargs["wait_selector"] = wait_selector
    resp = StealthyFetcher.fetch(url, **kwargs)
    return _from_scrapling(resp, via="browser", fallback_url=url)


def reset_host_memory() -> None:
    """테스트용: 연결 리셋 기억을 비운다."""
    with _reset_lock:
        _reset_hosts.clear()
