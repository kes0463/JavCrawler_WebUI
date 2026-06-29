"""
123av.com 動画詳細ページ ( /ja/v/{product_id} ) から
품번·제목·説明·ポスター·女優·ジャンル·発売日·メーカーを HTML から抽出する。
"""
from __future__ import annotations

import os
import re
import time
import json
from dataclasses import asdict, dataclass, field
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

BASE_URL = "https://123av.com"
VIDEO_PATH_TEMPLATE = "/ja/v/{product_id}"
LOCALE_PATH_TEMPLATE = "/{locale}/v/{product_id}"
_SUPPORTED_LOCALES = ("ko", "ja")

# 레거시 DOM (page-video) + 2026 watch 레이아웃
SELECTORS = {
    "page_root": "#page-video",
    "title": "#page-video h1",
    "title_watch": "h1.watch__title",
    "player": "#player",
    "player_watch": ".player",
    "description": "#details .description.short p",
    "detail_item": "#details .detail-item",
    "watch_info": "dl.watch__info",
    "favourite": "button.btn-action.favourite[data-code]",
    "favourite_watch": "button.watch__save span",
}

# to_dict(한국어 키) 출력用 — 내부 dataclass 필드명은 그대로 둔다
# actresses → to_dict(한국어) 시 "여배우"에 이름만 문자열 리스트로 넣는다(링크는 .actresses 참고)
_OUTPUT_KEY_KO = {
    "code": "품번",
    "title": "제목",
    "description": "설명",
    "poster_url": "포스터",
    "genres": "장르",
    "release_date": "출시일",
    "maker": "메이커",
}

# to_text() 필드 출력 순서
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


@dataclass
class VideoInfo:
    code: str = ""
    title: str = ""
    title_ja: str = ""
    description: str = ""
    poster_url: str = ""
    actresses: List[Dict[str, str]] = field(
        default_factory=list
    )  # 내부: {"name", "href"} — to_dict 시 "이름", "링크"
    genres: List[str] = field(default_factory=list)
    release_date: str = ""
    maker: str = ""
    favourite_count: int = 0

    def to_dict(self, *, korean_keys: bool = True) -> Dict[str, Any]:
        raw = asdict(self)
        if not korean_keys:
            return raw
        out: Dict[str, Any] = {}
        for k, v in raw.items():
            if k == "actresses" and isinstance(v, list):
                names = []
                for item in v:
                    n = (item.get("name") or item.get("이름") or "").strip()
                    if n:
                        names.append(n)
                out["여배우"] = names
                continue
            out_key = _OUTPUT_KEY_KO.get(k, k)
            out[out_key] = v
        return out

    def to_text(self) -> str:
        """JSON 이 아닌, 라벨 + 값 형태의 일반 텍스트(한국어 키)."""
        d = self.to_dict(korean_keys=True)
        blocks: List[str] = []
        for key in _TEXT_FIELD_ORDER:
            if key not in d:
                continue
            value = d[key]
            if isinstance(value, list):
                if value and all(isinstance(x, str) for x in value):
                    text = ", ".join(value)
                else:
                    text = str(value) if value else ""
            else:
                text = "" if value is None else str(value)
            if key == "설명" and text:
                blocks.append(f"{key}:\n{text}")
            else:
                blocks.append(f"{key}: {text}")
        return "\n\n".join(blocks) + "\n" if blocks else "\n"


def _text(el: Any) -> str:
    if el is None:
        return ""
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True) or "").strip()


def _has_hangul(text: str) -> bool:
    return bool(re.search(r"[\uAC00-\uD7A3]", text or ""))


def _is_boilerplate_title(text: str) -> bool:
    """missav→123av 리다이렉트 안내·도메인 이전 문구는 작품 제목이 아님."""
    t = (text or "").strip()
    if not t:
        return True
    lower = t.casefold()
    needles = (
        "123av.com",
        "移転しました",
        "に移転",
        "으로 이적",
        "으로 이전",
        "이전했습니다",
        "새 도메인을 기억",
        "moved to 123av",
    )
    if any(n.casefold() in lower for n in needles):
        return True
    if re.match(r"^123av\.com\b", t, re.I) and "—" not in t and "-" not in t:
        return True
    return False


def _normalize_scraped_title(raw: str, code: str = "") -> str:
    """`SNOS-275 — 제목 — 123AV` 형태를 정리."""
    title = (raw or "").strip()
    if not title:
        return ""
    title = re.sub(r"\s*—\s*123AV\s*$", "", title, flags=re.I).strip()
    title = re.sub(r"\s*-\s*123AV\s*$", "", title, flags=re.I).strip()
    code_key = (code or "").strip().upper()
    if code_key:
        prefix = re.compile(
            rf"^{re.escape(code_key)}\s*(?:—|-)\s*",
            re.I,
        )
        title = prefix.sub("", title).strip()
    else:
        m = re.match(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*\s*(?:—|-)\s*(.+)$", title)
        if m:
            title = m.group(1).strip()
    return title


def _title_from_soup(soup: BeautifulSoup) -> str:
    candidates: List[str] = []
    for sel in (
        SELECTORS["title_watch"],
        SELECTORS["title"],
        "#video-info h1.title",
    ):
        el = soup.select_one(sel)
        if el:
            candidates.append(_text(el))
    og = soup.find("meta", property="og:title")
    if og and (og.get("content") or "").strip():
        candidates.append((og.get("content") or "").strip())
    if soup.title and soup.title.string:
        candidates.append(soup.title.string.strip())
    for el in soup.select("h1"):
        t = _text(el)
        if t:
            candidates.append(t)
    for cand in candidates:
        if cand and not _is_boilerplate_title(cand):
            return cand
    return ""


def _poster_from_soup(soup: BeautifulSoup, *, base_url: str) -> str:
    player = soup.select_one(SELECTORS["player"])
    if player:
        poster = (player.get("data-poster") or "").strip()
        if poster:
            return urljoin(base_url, poster) if poster.startswith("/") else poster
    watch_player = soup.select_one(SELECTORS["player_watch"])
    if watch_player:
        style = watch_player.get("style") or ""
        m = re.search(r"background-image\s*:\s*url\(['\"]?([^'\"()]+)['\"]?\)", style, re.I)
        if m:
            poster = m.group(1).strip()
            return urljoin(base_url, poster) if poster.startswith("/") else poster
    og = soup.find("meta", property="og:image")
    if og and (og.get("content") or "").strip():
        poster = (og.get("content") or "").strip()
        return urljoin(base_url, poster) if poster.startswith("/") else poster
    return ""


def _favourite_count_from_soup(soup: BeautifulSoup) -> int:
    for sel in (SELECTORS["favourite_watch"], "button.btn-action.favourite[data-code] span"):
        span = soup.select_one(sel)
        if not span:
            continue
        raw = span.get_text(strip=True).replace(",", "").replace(".", "")
        if not raw:
            continue
        try:
            return int(raw)
        except (ValueError, TypeError):
            continue
    return 0


def _code_from_soup(soup: BeautifulSoup) -> str:
    btn = soup.select_one(SELECTORS["favourite"])
    if btn:
        code = (btn.get("data-code") or "").strip()
        if code:
            return code
    return ""


def _parse_watch_info_dl(soup: BeautifulSoup, info: VideoInfo) -> None:
    dl = soup.select_one(SELECTORS["watch_info"])
    if not dl:
        return
    label_map = {
        "コード": "code", "코드": "code",
        "リリース日": "release_date", "発売日": "release_date", "출시일": "release_date",
        "女優": "actresses", "出演者": "actresses", "출연진": "actresses",
        "ジャンル": "genres", "장르": "genres",
        "メーカー": "maker", "제작사": "maker",
    }
    for row in dl.select(".watch__info-row"):
        dt = row.find("dt")
        dd = row.find("dd")
        if not dt or not dd:
            continue
        label = _text(dt).rstrip("：:").strip()
        field = label_map.get(label)
        if field == "code":
            t = _text(dd)
            if t and not info.code:
                info.code = t
        elif field == "release_date":
            info.release_date = _text(dd)
        elif field == "actresses":
            from javstory.utils.actress_profile import strip_actor_parenthetical_alias

            actresses: List[Dict[str, str]] = []
            for a in dd.find_all("a", href=True):
                href = (a.get("href") or "").strip()
                if "actresses" not in href:
                    continue
                name = _text(a)
                if name:
                    actresses.append({"name": strip_actor_parenthetical_alias(name), "href": href})
            if actresses:
                info.actresses = actresses
        elif field == "genres":
            genres: List[str] = []
            for a in dd.find_all("a", href=True):
                t = _text(a)
                if t:
                    genres.append(t)
            if genres:
                info.genres = genres
        elif field == "maker":
            maker = _parse_maker(dd)
            if maker:
                info.maker = maker


def _iter_detail_rows(soup: BeautifulSoup) -> List[Any]:
    node = soup.select_one(SELECTORS["detail_item"])
    if not node:
        return []
    return node.find_all("div", recursive=False)


def _row_label_and_value_container(row: Any) -> tuple[str, Any]:
    spans = row.find_all("span", recursive=False)
    if len(spans) < 2:
        return "", None
    label = _text(spans[0]).rstrip("：:").strip()
    value_node = spans[1]
    return label, value_node


def _parse_actresses(value_node: Any) -> List[Dict[str, str]]:
    from javstory.utils.actress_profile import strip_actor_parenthetical_alias

    out: List[Dict[str, str]] = []
    if not value_node:
        return out
    for a in value_node.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if "actresses" not in href:
            continue
        name = _text(a)
        if name:
            out.append({"name": strip_actor_parenthetical_alias(name), "href": href})
    return out


def _parse_genre_span(value_node: Any) -> List[str]:
    if not value_node:
        return []
    genre = value_node.find("span", class_="genre")
    target = genre or value_node
    names: List[str] = []
    for a in target.find_all("a", href=True):
        t = _text(a)
        if t:
            names.append(t)
    return names


def _parse_maker(value_node: Any) -> str:
    if not value_node:
        return ""
    a = value_node.find("a", href=re.compile(r"^makers/"))
    if a:
        return _text(a)
    return _text(value_node)


def _code_from_favourite(soup: BeautifulSoup) -> str:
    code = _code_from_soup(soup)
    if code:
        return code
    btn = soup.select_one(SELECTORS["favourite"])
    if not btn:
        return ""
    return (btn.get("data-code") or "").strip()


def _favourite_count_from_button(soup: BeautifulSoup) -> int:
    return _favourite_count_from_soup(soup)


def _slug_candidates(product_id: str) -> List[str]:
    """
    상세 URL 경로는 품번 슬러그인데, 무수정/리크 등은 `-uncensored-leaked` 접미가 붙는다.
    예: /ja/v/vrtm-131-uncensored-leaked (기본 vrtm-131 만으로는 404·빈 페이지)
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


def _detail_has_content(info: VideoInfo) -> bool:
    title = str(getattr(info, "title", "") or "").strip()
    code = str(getattr(info, "code", "") or "").strip()
    return bool(title or code)


def _merge_locale_pages(info_ja: VideoInfo, info_ko: VideoInfo) -> VideoInfo:
    """ja/ko 페이지 파싱 결과 병합 — 표시 제목은 한국어 우선."""
    base = info_ja if info_ja.code or info_ja.actresses else info_ko
    other = info_ko if base is info_ja else info_ja
    merged = VideoInfo(
        code=base.code or other.code,
        description=base.description or other.description,
        poster_url=base.poster_url or other.poster_url,
        actresses=_merge_actress_lists(base.actresses, other.actresses),
        genres=base.genres or other.genres,
        release_date=base.release_date or other.release_date,
        maker=base.maker or other.maker,
        favourite_count=max(base.favourite_count, other.favourite_count),
    )
    title_ja_raw = info_ja.title_ja or info_ja.title or ""
    title_ko_raw = info_ko.title or ""
    merged.title_ja = title_ja_raw
    if _has_hangul(title_ko_raw):
        merged.title = title_ko_raw
    else:
        merged.title = title_ja_raw or title_ko_raw
    return merged


def _actress_href_key(item: dict[str, str]) -> str:
    href = (item.get("href") or "").strip().rstrip("/").lower()
    if "/actresses/" in href:
        return href.split("/actresses/", 1)[-1].split("?")[0]
    if href:
        return href
    return (item.get("name") or "").strip().lower()


def _merge_actress_lists(
    primary: List[Dict[str, str]],
    secondary: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """ja/ko 배우 목록 — href 기준 합집합, 동일 인물은 한글 표기 우선."""
    merged: dict[str, Dict[str, str]] = {}
    order: List[str] = []
    for item in (primary or []) + (secondary or []):
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue
        key = _actress_href_key(item)
        if not key:
            continue
        if key not in merged:
            merged[key] = {"name": name, "href": (item.get("href") or "").strip()}
            order.append(key)
            continue
        existing = merged[key]
        if _has_hangul(name) and not _has_hangul(existing.get("name") or ""):
            merged[key] = {
                "name": name,
                "href": existing.get("href") or item.get("href") or "",
            }
    return [merged[k] for k in order]


def parse_video_html(
    html: str,
    *,
    base_url: str = BASE_URL,
    locale: str = "",
) -> VideoInfo:
    soup = BeautifulSoup(html, "lxml")
    info = VideoInfo()

    raw_title = _title_from_soup(soup)
    info.poster_url = _poster_from_soup(soup, base_url=base_url)

    desc = soup.select_one(SELECTORS["description"])
    if desc:
        info.description = _text(desc)

    info.code = _code_from_favourite(soup)
    info.favourite_count = _favourite_count_from_button(soup)

    _parse_watch_info_dl(soup, info)

    for row in _iter_detail_rows(soup):
        label, value_node = _row_label_and_value_container(row)
        if not label or value_node is None:
            continue
        if label in ("コード",):
            t = _text(value_node)
            if t and not info.code:
                info.code = t
        if label in ("リリース日", "発売日"):
            info.release_date = _text(value_node)
        if label in ("女優",):
            parsed = _parse_actresses(value_node)
            if parsed:
                info.actresses = parsed
        if label in ("ジャンル",):
            parsed = _parse_genre_span(value_node)
            if parsed:
                info.genres = parsed
        if label in ("メーカー",):
            maker = _parse_maker(value_node)
            if maker:
                info.maker = maker

    norm = _normalize_scraped_title(raw_title, info.code)
    if _is_boilerplate_title(norm):
        norm = ""
    info.title = norm
    loc = (locale or "").lower()
    if loc == "ja" or (loc != "ko" and not _has_hangul(norm)):
        info.title_ja = norm

    return info


def _http_get(
    url: str,
    *,
    headers: dict,
    timeout: float,
    session=None,
    disable_cffi: bool,
) -> Optional[Any]:
    max_tries = 3
    backoffs = (0.0, 0.8, 1.6)
    last_exc: Optional[BaseException] = None
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
            return r
        except Exception as e:
            last_exc = e
            msg = str(e)
            is_curl_reset = ("curl:" in msg.lower()) and ("(35)" in msg or "recv failure" in msg.lower())
            if is_curl_reset and (_USE_CFFI and (session is None)) and (not disable_cffi):
                try:
                    sess = requests.Session()
                    r = sess.get(url, headers=headers, timeout=timeout)
                    r.encoding = r.apparent_encoding or "utf-8"
                    return r
                except Exception as e2:
                    last_exc = e2
            continue
    if last_exc is not None:
        raise last_exc
    return None


def fetch_video_info(
    product_id: str,
    *,
    base_url: str = BASE_URL,
    path_template: str = VIDEO_PATH_TEMPLATE,
    timeout: float = 30.0,
    session=None,
) -> VideoInfo:
    product_id = product_id.strip()
    if not product_id:
        raise ValueError("product_id is empty")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9,ja;q=0.8,en;q=0.7",
    }
    last_exc: Optional[BaseException] = None
    candidates = _slug_candidates(product_id)
    if not candidates:
        raise ValueError("product_id is empty")

    disable_cffi = (os.environ.get("JAVSTORY_CURL_CFFI_DISABLED", "") or "").strip().lower() in (
        "1", "true", "yes", "on",
    )

    for slug in candidates:
        info_ja: Optional[VideoInfo] = None
        info_ko: Optional[VideoInfo] = None
        for locale in _SUPPORTED_LOCALES:
            path = LOCALE_PATH_TEMPLATE.format(locale=locale, product_id=slug)
            url = base_url.rstrip("/") + path
            try:
                r = _http_get(url, headers=headers, timeout=timeout, session=session, disable_cffi=disable_cffi)
            except Exception as e:
                last_exc = e
                continue
            if r is None or r.status_code == 404:
                continue
            try:
                r.raise_for_status()
            except Exception as e:
                last_exc = e
                continue
            try:
                parsed = parse_video_html(r.text, base_url=base_url, locale=locale)
            except Exception as e:
                last_exc = e
                continue
            if locale == "ja":
                info_ja = parsed
            else:
                info_ko = parsed

        merged: Optional[VideoInfo] = None
        if info_ja and info_ko:
            merged = _merge_locale_pages(info_ja, info_ko)
        elif info_ja:
            merged = info_ja
        elif info_ko:
            merged = info_ko

        if merged and _detail_has_content(merged):
            return merged

    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"123av: 유효한 상세 페이지 없음 ({product_id!r})")


if __name__ == "__main__":
    import sys
    from pathlib import Path

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    for name in ("test_dazd-264.txt", "test_cjod-515.txt"):
        p = Path(__file__).resolve().parent / name
        if not p.exists():
            continue
        data = parse_video_html(p.read_text(encoding="utf-8"))
        print("===", name, "===")
        print(data.to_text(), end="")
