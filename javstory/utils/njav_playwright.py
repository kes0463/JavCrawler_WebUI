"""
njavtv.com Playwright 수집 로직 (crawl.py / hybrid 등에서 공용).

Locator 전략 (2026-03 안정 버전과 동일):
- 표지: div[style*="background-image"] → style에서 url() 정규식
- 제목: h1 첫 요소
- 시놉시스: div[class*="line-clamp"] 또는 div.mb-1.text-secondary.break-all
- 메타: 모든 div.text-secondary 순회, 내부 텍스트로 配信開始日/品番/女優/ジャンル/メーカー 매칭
"""
from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Any

_NJAV_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_COVER_STYLE_RE = re.compile(r"url\(['\"]?(.*?)['\"]?\)", re.I)

_CHALLENGE_FRAGMENTS = (
    "just a moment",
    "please wait",
    "checking your browser",
    "cloudflare",
    "attention required",
    "잠시",
    "기다리",
    "verify you are human",
)


def _safe_inner_text(loc: Any, timeout: float = 5_000) -> str:
    try:
        return loc.inner_text(timeout=timeout).strip()
    except Exception:
        return ""


def _title_placeholder(title: str) -> bool:
    s = (title or "").strip().lower()
    if len(s) < 4:
        return True
    for frag in _CHALLENGE_FRAGMENTS:
        if frag in s:
            return True
    if "njav" in s and ".com" in s and len(s) < 24:
        return True
    return False


def _click_age_gate(page: Any) -> None:
    for txt in ("18歳以上", "確認", "확인", "Enter", "Yes"):
        try:
            loc = page.get_by_text(txt, exact=False).first
            if loc.count() > 0:
                loc.click(timeout=2500)
                time.sleep(2)
                break
        except Exception:
            continue


def _extract_cover_url(page: Any) -> str | None:
    try:
        cover = page.locator('div[style*="background-image"]').first
        if cover.count() < 1:
            return None
        style = cover.get_attribute("style") or ""
        m = _COVER_STYLE_RE.search(style)
        if not m:
            return None
        u = m.group(1).strip().strip('"').strip("'").strip()
        return u or None
    except Exception:
        return None


def _extract_title(page: Any) -> str | None:
    try:
        h1 = page.locator("h1").first
        if h1.count() < 1:
            return None
        t = h1.inner_text(timeout=8_000).strip()
        if not t or _title_placeholder(t):
            return None
        return t
    except Exception:
        return None


def _extract_synopsis(page: Any) -> str | None:
    try:
        syn = page.locator(
            'div[class*="line-clamp"], div.mb-1.text-secondary.break-all'
        ).first
        if syn.count() < 1:
            return None
        st = syn.inner_text(timeout=8_000).strip()
        return st or None
    except Exception:
        return None


def _parse_text_secondary_blocks(page: Any) -> dict[str, Any]:
    """모든 div.text-secondary 를 스캔해 라벨 키워드로 필드 채움 (부분 실패 허용)."""
    out: dict[str, Any] = {}
    try:
        blocks = page.locator("div.text-secondary")
        n = blocks.count()
    except Exception:
        return out

    for i in range(n):
        try:
            block = blocks.nth(i)
            text = _safe_inner_text(block)
            if not text:
                continue
        except Exception:
            continue

        if "配信開始日" in text:
            try:
                tloc = block.locator("time").first
                if tloc.count() > 0:
                    v = _safe_inner_text(tloc)
                    if v:
                        out["release_date"] = v
            except Exception:
                pass

        if "品番" in text:
            try:
                sp = block.locator("span.font-medium").first
                if sp.count() > 0:
                    v = _safe_inner_text(sp)
                    if v:
                        out["product_code"] = v
                else:
                    for line in text.splitlines():
                        line = line.strip()
                        if "品番" in line and ":" in line:
                            rest = line.split(":", 1)[-1].strip()
                            if rest:
                                out["product_code"] = rest
                                break
            except Exception:
                pass

        if "女優" in text:
            try:
                names: list[str] = []
                for a in block.locator("a").all():
                    try:
                        nm = a.inner_text(timeout=3_000).strip()
                        if nm:
                            names.append(nm)
                    except Exception:
                        continue
                if names:
                    out["actors"] = names
            except Exception:
                pass

        if "ジャンル" in text:
            try:
                genres: list[str] = []
                for a in block.locator("a").all():
                    try:
                        g = a.inner_text(timeout=3_000).strip()
                        if g:
                            genres.append(g)
                    except Exception:
                        continue
                if genres:
                    out["genres"] = genres
            except Exception:
                pass

        if "メーカー" in text:
            try:
                preferred = block.locator('a[href*="makers"], a[href*="/maker/"]').first
                if preferred.count() > 0:
                    v = _safe_inner_text(preferred)
                    if v:
                        out["maker"] = v
                else:
                    fa = block.locator("a").first
                    if fa.count() > 0:
                        v = _safe_inner_text(fa)
                        if v:
                            out["maker"] = v
            except Exception:
                pass

    return out


async def scrape_njavtv_playwright_async(
    product_code: str,
    *,
    entry_url: str | None = None,
    headless: bool = True,
    slow_mo: int = 0,
    settle_seconds: float | None = None,
    goto_timeout_ms: int = 60_000,
    include_page_html: bool = False,
) -> dict[str, Any]:
    """
    asyncio 환경(예: QThread 내 이벤트 루프)에서 사용. sync_playwright + 루프 충돌을 피한다.
    """
    from playwright.async_api import async_playwright

    code = product_code.strip()
    slug = code.lower().replace("_", "-")
    url = (entry_url or "").strip() or f"https://njavtv.com/ja/{slug}"
    if settle_seconds is None:
        settle_seconds = float(os.getenv("JAVSTORY_NJAV_SETTLE_SECONDS", "7"))

    data: dict[str, Any] = {"code_requested": code}

    async def _click_age_gate_async(page: Any) -> None:
        for txt in ("18歳以上", "確認", "확인", "Enter", "Yes"):
            try:
                loc = page.get_by_text(txt, exact=False).first
                if await loc.count() > 0:
                    await loc.click(timeout=2500)
                    await asyncio.sleep(2)
                    break
            except Exception:
                continue

    async def _extract_cover_url_async(page: Any) -> str | None:
        try:
            cover = page.locator('div[style*="background-image"]').first
            if await cover.count() < 1:
                return None
            style = await cover.get_attribute("style") or ""
            m = _COVER_STYLE_RE.search(style)
            if not m:
                return None
            u = m.group(1).strip().strip('"').strip("'").strip()
            return u or None
        except Exception:
            return None

    async def _extract_title_async(page: Any) -> str | None:
        try:
            h1 = page.locator("h1").first
            if await h1.count() < 1:
                return None
            t = (await h1.inner_text(timeout=8_000)).strip()
            if not t or _title_placeholder(t):
                return None
            return t
        except Exception:
            return None

    async def _extract_synopsis_async(page: Any) -> str | None:
        try:
            syn = page.locator(
                'div[class*="line-clamp"], div.mb-1.text-secondary.break-all'
            ).first
            if await syn.count() < 1:
                return None
            st = (await syn.inner_text(timeout=8_000)).strip()
            return st or None
        except Exception:
            return None

    async def _parse_text_secondary_blocks_async(page: Any) -> dict[str, Any]:
        out: dict[str, Any] = {}
        try:
            blocks = page.locator("div.text-secondary")
            n = await blocks.count()
        except Exception:
            return out

        for i in range(n):
            try:
                block = blocks.nth(i)
                text = (await block.inner_text(timeout=5_000)).strip()
                if not text:
                    continue
            except Exception:
                continue

            if "配信開始日" in text:
                try:
                    tloc = block.locator("time").first
                    if await tloc.count() > 0:
                        v = (await tloc.inner_text(timeout=5_000)).strip()
                        if v:
                            out["release_date"] = v
                except Exception:
                    pass

            if "品番" in text:
                try:
                    sp = block.locator("span.font-medium").first
                    if await sp.count() > 0:
                        v = (await sp.inner_text(timeout=5_000)).strip()
                        if v:
                            out["product_code"] = v
                    else:
                        for line in text.splitlines():
                            line = line.strip()
                            if "品番" in line and ":" in line:
                                rest = line.split(":", 1)[-1].strip()
                                if rest:
                                    out["product_code"] = rest
                                    break
                except Exception:
                    pass

            if "女優" in text:
                try:
                    names: list[str] = []
                    for a in await block.locator("a").all():
                        try:
                            nm = (await a.inner_text(timeout=3_000)).strip()
                            if nm:
                                names.append(nm)
                        except Exception:
                            continue
                    if names:
                        out["actors"] = names
                except Exception:
                    pass

            if "ジャンル" in text:
                try:
                    genres: list[str] = []
                    for a in await block.locator("a").all():
                        try:
                            g = (await a.inner_text(timeout=3_000)).strip()
                            if g:
                                genres.append(g)
                        except Exception:
                            continue
                    if genres:
                        out["genres"] = genres
                except Exception:
                    pass

            if "メーカー" in text:
                try:
                    preferred = block.locator('a[href*="makers"], a[href*="/maker/"]').first
                    if await preferred.count() > 0:
                        v = (await preferred.inner_text(timeout=5_000)).strip()
                        if v:
                            out["maker"] = v
                    else:
                        fa = block.locator("a").first
                        if await fa.count() > 0:
                            v = (await fa.inner_text(timeout=5_000)).strip()
                            if v:
                                out["maker"] = v
                except Exception:
                    pass

        return out

    try:
        browser = None
        context = None
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless, slow_mo=slow_mo)
            context = await browser.new_context(
                user_agent=_NJAV_UA,
                locale="ja-JP",
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()
            try:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=goto_timeout_ms)
                except Exception as e:
                    data["error"] = f"goto: {e}"
                    return data

                try:
                    await asyncio.sleep(settle_seconds)
                    await _click_age_gate_async(page)
                    await asyncio.sleep(1.0)
                except Exception:
                    pass

                try:
                    data["final_url"] = page.url or url
                except Exception:
                    data["final_url"] = url

                cu = await _extract_cover_url_async(page)
                if cu:
                    data["cover_url"] = cu

                tt = await _extract_title_async(page)
                if tt:
                    data["title"] = tt

                sy = await _extract_synopsis_async(page)
                if sy:
                    data["synopsis"] = sy

                meta = await _parse_text_secondary_blocks_async(page)
                for k, v in meta.items():
                    data[k] = v

                if include_page_html:
                    try:
                        data["_page_html"] = await page.content()
                    except Exception:
                        data["_page_html"] = ""
            finally:
                try:
                    if context:
                        await context.close()
                except Exception:
                    pass
                try:
                    if browser:
                        await browser.close()
                except Exception:
                    pass
    except Exception as e:
        data.setdefault("error", str(e))

    return data


def scrape_njavtv_playwright(
    product_code: str,
    *,
    entry_url: str | None = None,
    headless: bool = True,
    slow_mo: int = 0,
    settle_seconds: float | None = None,
    goto_timeout_ms: int = 60_000,
    include_page_html: bool = False,
) -> dict[str, Any]:
    """
    njavtv 한 페이지 크롤. 키: cover_url, title, synopsis, release_date, product_code,
    actors, genres, maker, final_url. 내부용: _page_html (옵션).
    """
    from playwright.sync_api import sync_playwright

    code = product_code.strip()
    slug = code.lower().replace("_", "-")
    url = (entry_url or "").strip() or f"https://njavtv.com/ja/{slug}"
    if settle_seconds is None:
        settle_seconds = float(os.getenv("JAVSTORY_NJAV_SETTLE_SECONDS", "7"))

    data: dict[str, Any] = {"code_requested": code}

    browser = None
    context = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
            context = browser.new_context(
                user_agent=_NJAV_UA,
                locale="ja-JP",
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()
            try:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=goto_timeout_ms)
                except Exception as e:
                    data["error"] = f"goto: {e}"
                    return data

                try:
                    time.sleep(settle_seconds)
                    _click_age_gate(page)
                    time.sleep(1.0)
                except Exception:
                    pass

                try:
                    data["final_url"] = page.url or url
                except Exception:
                    data["final_url"] = url

                cu = _extract_cover_url(page)
                if cu:
                    data["cover_url"] = cu

                tt = _extract_title(page)
                if tt:
                    data["title"] = tt

                sy = _extract_synopsis(page)
                if sy:
                    data["synopsis"] = sy

                meta = _parse_text_secondary_blocks(page)
                for k, v in meta.items():
                    data[k] = v

                if include_page_html:
                    try:
                        data["_page_html"] = page.content()
                    except Exception:
                        data["_page_html"] = ""
            finally:
                try:
                    if context:
                        context.close()
                except Exception:
                    pass
                try:
                    if browser:
                        browser.close()
                except Exception:
                    pass
    except Exception as e:
        data.setdefault("error", str(e))

    return data


def public_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """저장/출력용: 언더스코어 키 제거."""
    return {k: v for k, v in raw.items() if not str(k).startswith("_")}
