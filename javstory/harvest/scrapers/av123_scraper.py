"""
123av.com 動画詳細ページ ( /ja/v/{product_id} ) から
품번·제목·説明·ポスター·女優·ジャンル·発売日·メーカーを HTML から抽出する。
"""
from __future__ import annotations

import os
import re
import time
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

# テストスナップと同じ DOM（ page-video 配下 ）
SELECTORS = {
    "page_root": "#page-video",
    "title": "#page-video h1",
    "player": "#player",
    "description": "#details .description.short p",
    "detail_item": "#details .detail-item",
    "favourite": "button.btn-action.favourite[data-code]",
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
    out: List[Dict[str, str]] = []
    if not value_node:
        return out
    for a in value_node.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if "actresses" not in href:
            continue
        name = _text(a)
        if name:
            out.append({"name": name, "href": href})
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
    btn = soup.select_one(SELECTORS["favourite"])
    if not btn:
        return ""
    return (btn.get("data-code") or "").strip()


def _favourite_count_from_button(soup: BeautifulSoup) -> int:
    span = soup.select_one("button.btn-action.favourite[data-code] span")
    if not span:
        return 0
    try:
        return int(span.get_text(strip=True).replace(",", "").replace(".", "") or 0)
    except (ValueError, TypeError):
        return 0


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


def parse_video_html(
    html: str,
    *,
    base_url: str = BASE_URL,
) -> VideoInfo:
    soup = BeautifulSoup(html, "lxml")
    info = VideoInfo()
    h1 = soup.select_one(SELECTORS["title"])
    if h1:
        info.title = _text(h1)

    player = soup.select_one(SELECTORS["player"])
    if player:
        info.poster_url = (player.get("data-poster") or "").strip()
        if info.poster_url and info.poster_url.startswith("/"):
            info.poster_url = urljoin(base_url, info.poster_url)

    desc = soup.select_one(SELECTORS["description"])
    if desc:
        info.description = _text(desc)

    info.code = _code_from_favourite(soup)
    info.favourite_count = _favourite_count_from_button(soup)

    for row in _iter_detail_rows(soup):
        label, value_node = _row_label_and_value_container(row)
        if not label or value_node is None:
            continue
        if label in ("コード",):
            t = _text(value_node)
            if t and not info.code:
                info.code = t
        if label in ("リリース日",):
            info.release_date = _text(value_node)
        if label in ("女優",):
            info.actresses = _parse_actresses(value_node)
        if label in ("ジャンル",):
            info.genres = _parse_genre_span(value_node)
        if label in ("メーカー",):
            info.maker = _parse_maker(value_node)

    return info


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
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    }
    last_exc: Optional[BaseException] = None
    candidates = _slug_candidates(product_id)
    if not candidates:
        raise ValueError("product_id is empty")

    for slug in candidates:
        path = path_template.format(product_id=slug)
        url = base_url.rstrip("/") + path
        # 네트워크/WAF 환경에서 curl_cffi가 curl(35)로 자주 죽는 케이스가 있어
        # - 짧은 재시도
        # - curl_cffi 실패 시 requests로 폴백
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
                # curl_cffi 경로에서 리셋이 나면 requests로 1회 즉시 폴백
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
        if _detail_has_content(info):
            return info
        # For redirect/empty pages, continue to next slug (including siro2735)

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
