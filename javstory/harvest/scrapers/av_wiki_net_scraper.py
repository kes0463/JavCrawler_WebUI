"""
av-wiki.net ("AV女優の名前が知りたい！") — 배우 식별 전문 블로그.

시놉시스/장르는 없음(구조상 존재하지 않음, 실측 확인됨) — 배우명·메이커·레이블·
발매일·커버 이미지 보완용 **최종 폴백** 전용. 특히 VR 레이블(MadonnaVR, kawaii* VR 등)
표기가 상세해 VR 작품 배우 식별에 강함.

URL 슬러그는 워드프레스 퍼머링크라 대부분 `/{품번 소문자}/` 지만 항상 그렇지는 않다
(예: JUVR-141 → /juvr-141/, KAVR-146 → /kavr00146/). 그래서 직접 주소를 먼저 열고,
안 되면 사이트 자체 검색(`?s={code}`)에서 품번이 일치하는 기사만 골라 파싱한다.

예)
- 검색: `https://av-wiki.net/?s=JUVR-141`
- 기사: `https://av-wiki.net/juvr-141/`
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from javstory.harvest.fetching import http_get

BASE_URL = "https://av-wiki.net"
SEARCH_PATH_TEMPLATE = "/?s={product_id}"

# 기사 본문이 아닌 카테고리/태그성 av-wiki.net 링크 — 검색 결과에서 실제 기사
# 퍼머링크를 골라낼 때 이 프리픽스는 제외한다.
_NON_ARTICLE_PATH_PREFIXES = (
    "/av-actress/",
    "/fanza-video/",
    "/author/",
    "/tag/",
    "/category/",
    "/page/",
)

_HEADERS = {"Accept-Language": "ja,en-US;q=0.9,en;q=0.8"}


def _text(el: Any) -> str:
    if el is None:
        return ""
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True) or "").strip()


def _normalize_code(code: str) -> str:
    """품번 비교용 정규화: 대문자화 + 영숫자만 남기고 + 숫자 구간의 선행 0 제거.

    'KAVR-146', 'KAVR00146', 'kavr 146' 이 모두 'KAVR146' 으로 수렴한다.
    """
    s = re.sub(r"[^A-Za-z0-9]", "", (code or "")).upper()
    return re.sub(r"\d+", lambda m: str(int(m.group())), s)


def _abs_url(url: str, *, base_url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    return urljoin(base_url, url)


def _is_article_permalink(href: str, *, base_url: str) -> bool:
    if not href or base_url not in href:
        return False
    path = urlparse(href).path or ""
    if path in ("", "/"):
        return False
    if any(path.startswith(p) for p in _NON_ARTICLE_PATH_PREFIXES):
        return False
    return True


_NO_RESULT_RE = re.compile(r"(?<!\d)0件|一致する(?:記事|投稿)は見つかりませんでした|一致する投稿がありませんでした")


def _search_has_no_results(soup: BeautifulSoup) -> bool:
    main = soup.select_one("main") or soup
    return bool(_NO_RESULT_RE.search(_text(main)[:600]))


def _slug_matches_code(href: str, code_key: str) -> bool:
    """퍼머링크 마지막 경로 조각이 품번과 같은지 (`/kavr00146/` == KAVR-146)."""
    parts = [p for p in (urlparse(href).path or "").split("/") if p]
    return bool(parts) and len(parts) == 1 and _normalize_code(parts[0]) == code_key


def find_article_url(html: str, *, base_url: str = BASE_URL, product_id: str = "") -> str:
    """검색 결과 HTML에서 요청 품번의 기사 퍼머링크를 찾는다.

    검색 결과 페이지에는 시리즈/카테고리/페이지 링크와 사이드바 "최근 글"이 섞여 있어
    첫 링크를 고르면 엉뚱한 페이지가 잡힌다. 그래서
    - 검색 결과가 0건이면 바로 "" 를 돌려주고,
    - `product_id` 가 있으면 퍼머링크(1단 경로) 또는 링크 텍스트가 품번과 일치하는 것만 고른다.
    `product_id` 없이 부르면 예전처럼 <article> 안 첫 퍼머링크(호환용).
    """
    soup = BeautifulSoup(html, "lxml")
    if _search_has_no_results(soup):
        return ""
    code_key = _normalize_code(product_id)
    anchors = [a for art in soup.select("article") for a in art.find_all("a", href=True)]
    anchors += soup.find_all("a", href=True)
    if code_key:
        for a in anchors:
            href = str(a.get("href") or "").strip()
            if _is_article_permalink(href, base_url=base_url) and _slug_matches_code(href, code_key):
                return href
        for a in anchors:
            href = str(a.get("href") or "").strip()
            if not _is_article_permalink(href, base_url=base_url):
                continue
            if len([p for p in (urlparse(href).path or "").split("/") if p]) != 1:
                continue  # /mgstage/…/series-id-…/ 같은 다단 경로는 기사가 아님
            if code_key in _normalize_code(_text(a)):
                return href
        return ""
    for a in anchors:
        href = str(a.get("href") or "").strip()
        if _is_article_permalink(href, base_url=base_url):
            return href
    return ""


def _dl_dt_dd_map(soup: BeautifulSoup) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for dl in soup.select("dl.dltable, dl"):
        dts = dl.find_all("dt")
        for dt in dts:
            dd = dt.find_next_sibling("dd")
            if dd is None:
                continue
            key = _text(dt)
            if key and key not in out:
                out[key] = _text(dd)
    return out


@dataclass
class AvWikiNetInfo:
    code: str = ""
    title: str = ""
    maker: str = ""
    label: str = ""
    actresses: List[str] = field(default_factory=list)
    release_date: str = ""
    cover_url: str = ""
    source_url: str = ""


def parse_article_html(html: str, *, base_url: str = BASE_URL) -> AvWikiNetInfo:
    soup = BeautifulSoup(html, "lxml")
    info = AvWikiNetInfo()

    h1 = soup.select_one("h1.entry-title") or soup.find("h1")
    if h1:
        subtitle = h1.select_one(".entry-subtitle")
        subtitle_text = _text(subtitle)
        if subtitle:
            subtitle.extract()
        info.title = _text(h1)
        # subtitle 형식: "{메이커} - {품번}"
        m = re.search(r"-\s*([A-Za-z0-9]+-?\d+)\s*$", subtitle_text)
        if m:
            info.code = m.group(1).strip()

    dlmap = _dl_dt_dd_map(soup)
    info.maker = info.maker or dlmap.get("メーカー", "").strip()
    info.label = dlmap.get("レーベル", "").strip()
    if not info.code:
        info.code = dlmap.get("メーカー品番", "").strip()
    info.release_date = dlmap.get("配信開始日", "").strip()

    # AV女優名 dd 안에 배우별 <a> 태그가 여러 개 있을 수 있음(공연작)
    for dt in soup.find_all("dt"):
        if _text(dt) == "AV女優名":
            dd = dt.find_next_sibling("dd")
            if dd:
                names = [_text(a) for a in dd.find_all("a")]
                names = [n for n in names if n]
                info.actresses = names or ([_text(dd)] if _text(dd) else [])
            break

    # 지연 로딩 이미지는 src 가 1px data: GIF 이고 실제 주소는 data-src 에 있다.
    thumb_img = soup.select_one(".article-thumbnail img, article img")
    if thumb_img:
        cands = [str(thumb_img.get(k) or "").strip() for k in ("data-src", "src")]
        src = next((c for c in cands if c and not c.startswith("data:")), "")
        info.cover_url = _abs_url(src, base_url=base_url) if src else ""

    return info


def fetch_actress_info(
    product_id: str,
    *,
    base_url: str = BASE_URL,
    search_path_template: str = SEARCH_PATH_TEMPLATE,
    timeout: float = 12.0,
    session: Any = None,
) -> AvWikiNetInfo:
    """품번으로 av-wiki.net 기사 페이지를 찾아 파싱한다.

    1) 대부분 기사 주소가 `/{품번 소문자}/` 라 먼저 직접 연다(요청 1회로 끝).
    2) 404 이거나 다른 작품이면 사이트 검색(`?s={code}`)에서 품번이 일치하는 기사만 고른다
       (`KAVR-146 → /kavr00146/` 처럼 슬러그가 다른 경우 대비).

    시놉시스는 이 소스에 존재하지 않으므로 채워지지 않는다 — 배우/메이커/
    발매일/커버 보완용으로만 사용할 것.
    """
    product_id = (product_id or "").strip()
    if not product_id:
        raise ValueError("product_id is empty")
    requested = _normalize_code(product_id)
    empty = AvWikiNetInfo(code=product_id.upper())

    def _load(url: str) -> Optional[AvWikiNetInfo]:
        r = http_get(url, headers=_HEADERS, timeout=timeout, session=session)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        info = parse_article_html(r.text, base_url=base_url)
        info.source_url = str(r.url or url)
        # 오탐 방지: 파싱한 기사의 품번이 요청 품번과 일치할 때만 신뢰한다. 품번을 못
        # 읽었으면 배우가 있고 본문에 품번이 나올 때만 인정(시리즈/카테고리 페이지 배제).
        parsed = _normalize_code(info.code)
        if parsed:
            if parsed != requested:
                return None
        elif not (info.actresses and requested in _normalize_code(r.text)):
            return None
        if not info.code:
            info.code = product_id.upper()
        return info

    slug = re.sub(r"[^a-z0-9-]", "", product_id.lower())
    if slug:
        direct = _load(base_url.rstrip("/") + f"/{slug}/")
        if direct is not None:
            return direct

    search_url = base_url.rstrip("/") + search_path_template.format(product_id=product_id)
    r = http_get(search_url, headers=_HEADERS, timeout=timeout, session=session)
    r.raise_for_status()
    article_url = find_article_url(r.text, base_url=base_url, product_id=product_id)
    if not article_url or article_url.rstrip("/").endswith(f"/{slug}"):
        return empty  # 0건 / 일치 기사 없음 / 이미 시도한 직접 주소
    return _load(article_url) or AvWikiNetInfo(code=product_id.upper(), source_url=article_url)
