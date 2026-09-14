"""
av-wiki.net ("AV女優の名前が知りたい！") — 배우 식별 전문 블로그.

시놉시스/장르는 없음(구조상 존재하지 않음, 실측 확인됨) — 배우명·메이커·레이블·
발매일·커버 이미지 보완용 **최종 폴백** 전용. 특히 VR 레이블(MadonnaVR, kawaii* VR 등)
표기가 상세해 VR 작품 배우 식별에 강함.

URL 슬러그가 품번을 그대로 변환한 값이 아니라 워드프레스 퍼머링크라 품번→URL을
직접 유추할 수 없음(예: JUVR-141 → /juvr-141/, KAVR-146 → /kavr00146/). 대신
사이트 자체 검색(`?s={code}`)으로 기사 링크를 찾은 뒤 그 페이지를 파싱한다.

예)
- 검색: `https://av-wiki.net/?s=JUVR-141`
- 기사: `https://av-wiki.net/juvr-141/`
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

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

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


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


def find_article_url(html: str, *, base_url: str = BASE_URL) -> str:
    """검색 결과 HTML에서 첫 번째 실제 기사(작품 페이지) 퍼머링크를 찾는다."""
    soup = BeautifulSoup(html, "lxml")
    for article in soup.select("article"):
        for a in article.find_all("a", href=True):
            href = str(a.get("href") or "").strip()
            if _is_article_permalink(href, base_url=base_url):
                return href
    # article 태그가 없는 테마일 경우 페이지 전체에서 탐색(오탐 줄이려 첫 매치만)
    for a in soup.find_all("a", href=True):
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

    thumb_img = soup.select_one(".article-thumbnail img, article img")
    if thumb_img:
        src = str(thumb_img.get("src") or thumb_img.get("data-src") or "").strip()
        info.cover_url = _abs_url(src, base_url=base_url)

    return info


def fetch_actress_info(
    product_id: str,
    *,
    base_url: str = BASE_URL,
    search_path_template: str = SEARCH_PATH_TEMPLATE,
    timeout: float = 12.0,
    session: Optional[requests.Session] = None,
) -> AvWikiNetInfo:
    """품번으로 av-wiki.net을 검색해 기사 페이지를 찾아 파싱한다.

    시놉시스는 이 소스에 존재하지 않으므로 채워지지 않는다 — 배우/메이커/
    발매일/커버 보완용으로만 사용할 것.
    """
    product_id = (product_id or "").strip()
    if not product_id:
        raise ValueError("product_id is empty")

    sess = session or requests.Session()
    search_url = base_url.rstrip("/") + search_path_template.format(product_id=product_id)
    r = sess.get(search_url, headers=_HEADERS, timeout=timeout)
    r.raise_for_status()

    article_url = find_article_url(r.text, base_url=base_url)
    if not article_url:
        return AvWikiNetInfo(code=product_id.upper())

    r2 = sess.get(article_url, headers=_HEADERS, timeout=timeout)
    r2.raise_for_status()
    info = parse_article_html(r2.text, base_url=base_url)
    info.source_url = article_url

    # 오탐 방지: 검색이 무결과일 때 워드프레스는 사이드바의 "최근 글" 링크를 노출하고,
    # find_article_url 폴백이 그 링크(품번과 무관한 기사)를 잡을 수 있다. 파싱한 기사의
    # 품번이 요청 품번과 일치할 때만 신뢰하고, 아니면 배우 정보를 채우지 않는다.
    requested = _normalize_code(product_id)
    parsed = _normalize_code(info.code)
    if requested and parsed:
        if requested != parsed:
            return AvWikiNetInfo(code=product_id.upper(), source_url=article_url)
    elif requested and requested not in _normalize_code(r2.text):
        # 품번을 파싱하지 못한 경우, 본문에 품번이 등장하는지로 최소 검증한다.
        return AvWikiNetInfo(code=product_id.upper(), source_url=article_url)

    if not info.code:
        info.code = product_id.upper()
    return info
