"""
missav123.to 動画詳細ページ ( /ja/v/{product_id} ) から
품번·제목·설명·포스터·여배우·장르·출시일·메이커를 HTML から抽出する。

참고 샘플:
- `https://missav123.to/ja/v/jufe-449`
- `https://missav123.to/ja/v/dazd-264`
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

try:
    from curl_cffi import requests as _cffi_requests
    _USE_CFFI = True
except ImportError:
    import requests as _cffi_requests  # type: ignore[no-redef]
    _USE_CFFI = False

import requests
from bs4 import BeautifulSoup

from javstory.harvest.scrapers.av123_scraper import (
    _is_boilerplate_title,
    _normalize_scraped_title,
    _title_from_soup,
)

BASE_URL = "https://missav123.to"
VIDEO_PATH_TEMPLATE = "/ja/v/{product_id}"

SELECTORS = {
    "player": "#player",  # d-tag
    "title": "#video-info h1.title",
    "desc": "#video-details .desc .content",
    "details_meta": "#video-details .meta",
}

_TEXT_FIELD_ORDER = [
    "품번",
    "제목",
    "설명",
    "포스터",
    "여배우",
    "장르",
    "출시일",
    "메이커",
]


def _text(el: Any) -> str:
    if el is None:
        return ""
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True) or "").strip()


def _norm_label(label: str) -> str:
    # ex) "コード:" / "発売日:" / "ジャンル:" / "女優:" / "メーカー:"
    return (label or "").strip().rstrip("：:").strip()


def _abs_url(href: str, *, base_url: str) -> str:
    href = (href or "").strip()
    if not href:
        return ""
    return urljoin(base_url, href)


@dataclass
class MissavVideoInfo:
    code: str = ""
    title: str = ""
    description: str = ""
    poster_url: str = ""
    actresses: List[str] = field(default_factory=list)
    genres: List[str] = field(default_factory=list)
    release_date: str = ""
    maker: str = ""
    favourite_count: int = 0

    def to_text(self) -> str:
        blocks: List[str] = []

        def add_line(k: str, v: str) -> None:
            blocks.append(f"{k}: {v}".rstrip())

        def add_block(k: str, v: str) -> None:
            blocks.append(f"{k}:\n{v}".rstrip())

        # keep order stable
        d: Dict[str, Any] = {
            "품번": self.code,
            "제목": self.title,
            "설명": self.description,
            "포스터": self.poster_url,
            "여배우": ", ".join([a for a in self.actresses if a]),
            "장르": ", ".join([g for g in self.genres if g]),
            "출시일": self.release_date,
            "메이커": self.maker,
        }

        for key in _TEXT_FIELD_ORDER:
            if key not in d:
                continue
            val = "" if d[key] is None else str(d[key])
            if key == "설명" and val:
                add_block(key, val)
            else:
                add_line(key, val)

        return "\n\n".join(blocks) + ("\n" if blocks else "")


def _favourite_count_missav(soup: BeautifulSoup) -> int:
    # 1차: #video-info d-tag.actions[favorites] 어트리뷰트 (현행 DOM)
    actions = soup.select_one("#video-info d-tag.actions[favorites]")
    if actions:
        val = (actions.get("favorites") or "").strip()
        if val:
            try:
                return int(val.replace(",", ""))
            except (ValueError, TypeError):
                pass

    # 2차: d-tag.actions[favorites] (id 없이도 탐색)
    for dtag in soup.select("d-tag.actions[favorites]"):
        val = (dtag.get("favorites") or "").strip()
        if val:
            try:
                return int(val.replace(",", ""))
            except (ValueError, TypeError):
                pass

    # 3차: 구버전 DOM — 버튼 텍스트 fallback
    for btn in soup.select("div.act button.btn, div.addtolist button, button.btn"):
        icon = btn.select_one(".fa-heart, .fa-thumbs-up")
        if not icon:
            continue
        text = btn.get_text(separator=" ", strip=True)
        m = re.search(r"\d[\d,]*", text)
        if m:
            try:
                return int(m.group(0).replace(",", ""))
            except (ValueError, TypeError):
                pass
    return 0


def _slug_candidates(product_id: str) -> List[str]:
    """
    상세 URL이 품번만이 아니라 `-uncensored-leaked` 등 접미를 붙는 경우가 있다.
    (123av / missav123 동일 패턴) — `vrtm-131` 대신 `vrtm-131-uncensored-leaked` 가 실제 경로.
    """
    raw = (product_id or "").strip().lower()
    raw = re.sub(r"\s+", "-", raw)
    slug = re.sub(r"-+", "-", raw.strip("-"))
    if not slug:
        return []
    out: List[str] = []
    seen: set[str] = set()

    def add(x: str) -> None:
        if x and x not in seen:
            seen.add(x)
            out.append(x)

    add(slug)
    # SIRO-2735 등 일부 SIRO 시리즈는 siro2735 (하이픈 없이) 형태로도 존재
    if "-" in slug and slug.startswith(("siro-", "siro")):
        no_hyphen = slug.replace("-", "", 1)  # siro-2735 -> siro2735
        add(no_hyphen)
    for suf in ("-uncensored-leaked", "-uncensored", "-leaked", "-censored"):
        if not slug.endswith(suf):
            add(slug + suf)
            if "-" in slug and slug.startswith(("siro-", "siro")):
                add(no_hyphen + suf)
    return out


def _missav_detail_has_content(info: MissavVideoInfo) -> bool:
    title = str(getattr(info, "title", "") or "").strip()
    code = str(getattr(info, "code", "") or "").strip()
    if title and _is_boilerplate_title(title):
        title = ""
    return bool(title or code)


def parse_video_html(html: str, *, base_url: str = BASE_URL) -> MissavVideoInfo:
    soup = BeautifulSoup(html, "lxml")
    info = MissavVideoInfo()

    raw_title = _title_from_soup(soup)
    if raw_title:
        m = re.match(r"^([A-Za-z0-9]+-\d+)\b", raw_title)
        if m and not info.code:
            info.code = m.group(1)
    info.title = _normalize_scraped_title(raw_title, info.code)
    if _is_boilerplate_title(info.title):
        info.title = ""

    # player attrs: code / cover
    player = soup.select_one(SELECTORS["player"])
    if player:
        info.code = (player.get("code") or "").strip() or info.code
        cover = (player.get("cover") or "").strip()
        if cover:
            info.poster_url = _abs_url(cover, base_url=base_url)

    # description
    desc = soup.select_one(SELECTORS["desc"])
    if desc:
        info.description = _text(desc)

    # details meta rows: <div><label>発売日:</label> <span>...</span></div>
    meta = soup.select_one(SELECTORS["details_meta"])
    if meta:
        for row in meta.find_all("div", recursive=False):
            label_el = row.find("label")
            label = _norm_label(_text(label_el))
            if not label:
                continue

            if label in ("コード",):
                span = row.find("span")
                t = _text(span)
                if t:
                    info.code = t
                continue

            if label in ("発売日",):
                span = row.find("span")
                info.release_date = _text(span)
                continue

            if label in ("女優",):
                actresses: List[str] = []
                for a in row.find_all("a", href=True):
                    name = _text(a)
                    if name:
                        actresses.append(name)
                info.actresses = actresses
                continue

            if label in ("ジャンル",):
                genres: List[str] = []
                for a in row.find_all("a", href=True):
                    t = _text(a)
                    if t:
                        genres.append(t)
                info.genres = genres
                continue

            if label in ("メーカー",):
                a = row.find("a", href=True)
                info.maker = _text(a) if a else _text(row)
                continue

    # fallback code: try from title prefix "CODE - ..." or redirect title
    if not info.code and info.title:
        m = re.match(r"^([A-Za-z0-9]+-\d+)\b", info.title)
        if m:
            info.code = m.group(1)
        else:
            # For redirect pages like "SIRO-2735 — ..."
            m2 = re.search(r"(SIRO|siro)-?(\d+)", info.title, re.I)
            if m2:
                info.code = f"SIRO-{m2.group(2)}"

    # If title was updated from redirect, try to set code from it too
    if not info.code and info.title and "SIRO" in info.title.upper():
        m3 = re.search(r"SIRO-?(\d+)", info.title, re.I)
        if m3:
            info.code = f"SIRO-{m3.group(1)}"

    info.favourite_count = _favourite_count_missav(soup)
    return info


def fetch_video_info(
    product_id: str,
    *,
    base_url: str = BASE_URL,
    path_template: str = VIDEO_PATH_TEMPLATE,
    timeout: float = 30.0,
    session=None,
) -> MissavVideoInfo:
    product_id = (product_id or "").strip()
    if not product_id:
        raise ValueError("product_id is empty")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    }
    last_exc: Optional[BaseException] = None
    candidates = _slug_candidates(product_id)
    if not candidates:
        raise ValueError("product_id is empty")

    for slug in candidates:
        url = base_url.rstrip("/") + path_template.format(product_id=slug)
        max_tries = 3
        backoffs = (0.0, 0.8, 1.6)
        disable_cffi = (os.environ.get("JAVSTORY_CURL_CFFI_DISABLED", "") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

        r = None
        for i in range(max_tries):
            if i > 0:
                try:
                    time.sleep(backoffs[min(i, len(backoffs) - 1)])
                except Exception:
                    pass
            try:
                if _USE_CFFI and (session is None) and (not disable_cffi):
                    r = _cffi_requests.get(
                        url,
                        headers=headers,
                        timeout=timeout,
                        impersonate="chrome131",
                    )
                else:
                    sess = session or requests.Session()
                    r = sess.get(url, headers=headers, timeout=timeout)
                    r.encoding = r.apparent_encoding or "utf-8"
                break
            except Exception as e:
                last_exc = e
                msg = str(e)
                is_curl_reset = ("curl:" in msg.lower()) and ("(35)" in msg or "recv failure" in msg.lower())
                if is_curl_reset and (_USE_CFFI and (session is None)) and (not disable_cffi):
                    try:
                        sess = requests.Session()
                        r = sess.get(url, headers=headers, timeout=timeout)
                        r.encoding = r.apparent_encoding or "utf-8"
                        break
                    except Exception as e2:
                        last_exc = e2
                continue

        if r is None:
            continue
        if r.status_code == 404:
            continue
        try:
            r.raise_for_status()
        except Exception as e:
            last_exc = e
            continue
        try:
            info = parse_video_html(r.text, base_url=base_url)
        except Exception as e:
            last_exc = e
            continue
        if _missav_detail_has_content(info):
            return info

    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"missav123: 유효한 상세 페이지 없음 ({product_id!r})")


if __name__ == "__main__":
    import sys

    # windows console mojibake 방지
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    pid = sys.argv[1].strip() if len(sys.argv) > 1 else "jufe-449"
    data = fetch_video_info(pid)
    print(data.to_text(), end="")

