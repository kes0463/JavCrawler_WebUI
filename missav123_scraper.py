"""
missav123.to 動画詳細ページ ( /ja/v/{product_id} ) から
품번·제목·설명·포스터·여배우·장르·출시일·메이커를 HTML から抽出する。

참고 샘플:
- `https://missav123.to/ja/v/jufe-449`
- `https://missav123.to/ja/v/dazd-264`
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

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


def parse_video_html(html: str, *, base_url: str = BASE_URL) -> MissavVideoInfo:
    soup = BeautifulSoup(html, "lxml")
    info = MissavVideoInfo()

    # title
    h1 = soup.select_one(SELECTORS["title"])
    if h1:
        info.title = _text(h1)

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

    # fallback code: try from title prefix "CODE - ..."
    if not info.code and info.title:
        m = re.match(r"^([A-Za-z0-9]+-\d+)\b", info.title)
        if m:
            info.code = m.group(1)

    return info


def fetch_video_info(
    product_id: str,
    *,
    base_url: str = BASE_URL,
    path_template: str = VIDEO_PATH_TEMPLATE,
    timeout: float = 30.0,
    session: Optional[requests.Session] = None,
) -> MissavVideoInfo:
    product_id = (product_id or "").strip()
    if not product_id:
        raise ValueError("product_id is empty")
    url = base_url.rstrip("/") + path_template.format(product_id=product_id)
    sess = session or requests.Session()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    }
    r = sess.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return parse_video_html(r.text, base_url=base_url)


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

