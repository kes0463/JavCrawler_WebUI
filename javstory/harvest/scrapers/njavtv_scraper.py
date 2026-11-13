"""njavtv.com 상세 페이지 ( /ja/{slug} ) 수집.

요청은 `javstory.harvest.fetching` (Scrapling) 을 쓰고, 파싱은 BeautifulSoup 으로 한다.
njavtv 는 서버 렌더링이라 대부분 HTTP 요청만으로 제목·시놉시스·메타가 HTML 에 들어온다.
Cloudflare 챌린지 등으로 HTTP 가 막히면 `use_browser=True` (StealthyFetcher) 로 연다.

이전 구현(utils/njav_playwright.py 의 Playwright 로케이터, crawler.py 의 DrissionPage)을
대체한다. 두 구현의 셀렉터를 합쳐 하나의 HTML 파서(`parse_njav_html`)로 통일했다.
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from javstory.harvest.fetching import browser_get, http_get

BASE_URL = "https://njavtv.com"
_HEADERS = {"Accept-Language": "ja,en-US;q=0.9,en;q=0.8"}
_COVER_STYLE_RE = re.compile(r"url\(\s*(?:&quot;|['\"])?(.*?)(?:&quot;|['\"])?\s*\)", re.I)

_CHALLENGE_FRAGMENTS = (
    "just a moment",
    "please wait",
    "checking your browser",
    "cloudflare",
    "attention required",
    "verify you are human",
    "잠시",
    "기다리",
)

# 라벨 → 필드. 행 텍스트가 "라벨:" 로 시작할 때만 매칭(시놉시스 본문 속 단어 오탐 방지).
_LABELS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("product_code", ("品番",)),
    ("release_date", ("配信開始日", "発売日")),
    ("actors", ("女優", "出演者")),
    ("genres", ("ジャンル", "カテゴリー")),
    ("maker", ("メーカー", "ブランド")),
    ("director", ("監督",)),
    ("label", ("レーベル",)),
)


def njavtv_detail_urls(product_code: str) -> list[str]:
    """상세 URL 후보. 기본 슬러그가 404일 때 `-uncensored-leaked` 접미 경로를 쓴다."""
    slug = (product_code or "").strip().lower().replace("_", "-")
    slug = re.sub(r"-+", "-", slug.strip("-"))
    if not slug:
        return []
    primary = f"{BASE_URL}/ja/{slug}"
    suf = "-uncensored-leaked"
    if slug.endswith(suf):
        return [primary]
    return [primary, f"{BASE_URL}/ja/{slug}{suf}"]


def _text(el: Any) -> str:
    if el is None:
        return ""
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()


def title_looks_placeholder(title: Optional[str]) -> bool:
    s = (title or "").strip().lower()
    if len(s) < 4:
        return True
    if any(frag in s for frag in _CHALLENGE_FRAGMENTS):
        return True
    if "njav" in s and ".com" in s and len(s) < 24:
        return True
    return False


def _cover_from_style(style: str) -> str:
    m = _COVER_STYLE_RE.search(style or "")
    if not m:
        return ""
    return m.group(1).replace("&quot;", "").strip().strip('"').strip("'").strip()


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it and it not in seen:
            seen.add(it)
            out.append(it)
    return out


def _row_field(text: str) -> Optional[str]:
    head = text.split(":", 1)[0].split("：", 1)[0].strip() if (":" in text[:16] or "：" in text[:16]) else ""
    if not head:
        return None
    for field, labels in _LABELS:
        if any(head.startswith(lb) for lb in labels):
            return field
    return None


def _parse_meta_rows(soup: BeautifulSoup) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for row in soup.select("div.text-secondary"):
        if "break-all" in (row.get("class") or []):
            continue  # 시놉시스 블록
        text = _text(row)
        field = _row_field(text)
        if not field or field in out:
            continue
        links = [_text(a) for a in row.find_all("a")]
        links = [t for t in links if t]
        if field == "product_code":
            sp = row.select_one("span.font-medium")
            val = _text(sp) if sp else text.split(":", 1)[-1].strip()
            if val:
                out[field] = val
        elif field == "release_date":
            el = row.find("time") or row.select_one("span.font-medium")
            val = _text(el) if el else text.split(":", 1)[-1].strip()
            if val:
                out[field] = val
        elif field in ("actors", "genres"):
            if links:
                out[field] = _dedupe(links)
        elif field == "maker":
            pref = row.select_one('a[href*="makers"], a[href*="/maker/"]')
            val = _text(pref) if pref else (links[0] if links else "")
            if val:
                out[field] = val
        else:  # director / label
            if links:
                out[field] = links[0]
    return out


def _parse_head_meta(soup: BeautifulSoup, base_url: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    head = soup.find("head")
    if not head:
        return out

    def _content(**attrs: str) -> str:
        tag = head.find("meta", attrs=attrs)
        return (tag.get("content") or "").strip() if tag else ""

    og_img = _content(property="og:image") or _content(name="og:image")
    if og_img:
        out["cover_url"] = urljoin(base_url, og_img)
    title = _content(property="og:title") or _content(name="og:title")
    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()
    if title:
        out["title"] = title
    desc = (
        _content(name="description")
        or _content(property="og:description")
        or _content(name="twitter:description")
    )
    if desc:
        out["synopsis"] = desc
    actors = _dedupe(
        [(m.get("content") or "").strip() for m in head.find_all("meta", attrs={"property": "og:video:actor"})]
    )
    if actors:
        out["actors"] = actors
    rd = _content(property="og:video:release_date")
    if rd:
        out["release_date"] = rd
    return out


def parse_njav_html(html: str, *, base_url: str = BASE_URL) -> dict[str, Any]:
    """njavtv 상세 HTML → {title, synopsis, cover_url, product_code, release_date,
    actors, genres, maker, director, label}. 본문 값이 우선이고 빈 칸만 <head> 메타로 채운다."""
    data: dict[str, Any] = {}
    if not (html and html.strip()):
        return data
    soup = BeautifulSoup(html, "lxml")

    for sel in ("h1.text-nord6", "h1"):
        t = _text(soup.select_one(sel))
        if t and not title_looks_placeholder(t):
            data["title"] = t
            break

    for el in soup.select(
        'div.text-secondary.break-all, div[class*="line-clamp"], div.mb-1.text-secondary.break-all'
    ):
        st = el.get_text("\n", strip=True)
        if st:
            data["synopsis"] = st
            break

    for el in soup.select('.plyr__poster, div[style*="background-image"]'):
        cu = _cover_from_style(el.get("style") or "")
        if cu:
            data["cover_url"] = urljoin(base_url, cu)
            break

    data.update({k: v for k, v in _parse_meta_rows(soup).items() if k not in data})

    for k, v in _parse_head_meta(soup, base_url).items():
        cur = data.get(k)
        if not cur or (isinstance(cur, str) and not cur.strip()):
            if k == "title" and title_looks_placeholder(v):
                continue
            data[k] = v
    return data


def _page_action(page: Any) -> None:
    """브라우저 모드: 나이 확인 버튼과 '詳細' 탭을 눌러 숨은 메타가 DOM 에 들어오게 한다."""
    for txt in ("18歳以上", "確認", "확인", "Enter", "Yes"):
        try:
            loc = page.get_by_text(txt, exact=False).first
            if loc.count() > 0 and loc.is_visible():
                loc.click(timeout=2500)
                page.wait_for_timeout(1500)
                break
        except Exception:
            continue
    for txt in ("詳細", "Details"):
        try:
            loc = page.get_by_text(txt, exact=True).first
            if loc.count() > 0:
                loc.click(timeout=2500)
                page.wait_for_timeout(1000)
                break
        except Exception:
            continue


def _is_challenge(res: Any, parsed: dict[str, Any]) -> bool:
    if res.status_code in (403, 429, 503):
        return True
    low = (res.text or "")[:4000].lower()
    return ("just a moment" in low or "cf-chl" in low) and not parsed.get("title")


def fetch_njavtv(
    product_code: str,
    *,
    use_browser: bool = False,
    timeout: float = 15.0,
    browser_timeout: float = 45.0,
) -> dict[str, Any]:
    """품번으로 njavtv 상세를 수집. 실패는 예외 대신 `error` 키로 돌려준다.

    반환 키: parse_njav_html 의 필드 + `final_url`, `via`, (`error`).
    """
    code = (product_code or "").strip()
    data: dict[str, Any] = {"code_requested": code}
    urls = njavtv_detail_urls(code)
    if not urls:
        data["error"] = "empty product_code"
        return data

    for url in urls:
        try:
            if use_browser:
                res = browser_get(
                    url,
                    timeout=browser_timeout,
                    page_action=_page_action,
                    solve_cloudflare=True,
                )
            else:
                # HTTP 단계는 브라우저 폴백을 하지 않는다 — 브라우저는 crawler 가 별도 단계로 결정.
                res = http_get(url, headers=_HEADERS, timeout=timeout, browser_fallback=False)
        except Exception as e:
            data["error"] = f"{type(e).__name__}: {e}"
            return data
        if res.status_code == 404:
            continue
        parsed = parse_njav_html(res.text, base_url=BASE_URL)
        if _is_challenge(res, parsed):
            data["error"] = f"blocked: HTTP {res.status_code} (via {res.via})"
            return data
        data.update(parsed)
        data["final_url"] = res.url or url
        data["via"] = res.via
        return data

    data["error"] = "404: njavtv page not found"
    return data
