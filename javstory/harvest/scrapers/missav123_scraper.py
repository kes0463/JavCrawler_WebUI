"""
missav123.com 動画詳細ページ ( /ja/{product_id} ) から
품번·제목·설명·포스터·여배우·장르·출시일·메이커를 HTML から抽出する。

- 예전 주소 `missav123.to/ja/v/{id}` 는 123av.com 이전 안내 페이지만 내려주므로 쓰지 않는다.
- missav123.com 은 njavtv 와 같은 템플릿이라 파싱은 `njavtv_scraper.parse_njav_html` 을 공유한다.
- 이 사이트는 좋아요 수를 노출하지 않는다 → favourite_count 는 항상 0
  (coordinator 는 0 이면 DB 의 기존 사이트별 점수를 유지한다).

참고 샘플:
- `https://missav123.com/ja/snos-334`
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from javstory.harvest.fetching import http_get
from javstory.harvest.scrapers.av123_scraper import (
    _is_boilerplate_title,
    _normalize_scraped_title,
)
from javstory.harvest.scrapers.njavtv_scraper import parse_njav_html

BASE_URL = "https://missav123.com"
VIDEO_PATH_TEMPLATE = "/ja/{product_id}"

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


def _strip_code_prefix(title: str, code: str) -> str:
    t = _normalize_scraped_title(title, code)
    if code:
        t = re.sub(rf"^{re.escape(code)}\s+", "", t, flags=re.I).strip()
    return t


def parse_video_html(html: str, *, base_url: str = BASE_URL) -> MissavVideoInfo:
    d = parse_njav_html(html, base_url=base_url)
    info = MissavVideoInfo()
    raw_title = str(d.get("title") or "").strip()
    code = str(d.get("product_code") or "").strip()
    if not code and raw_title:
        m = re.match(r"^([A-Za-z0-9]+-[0-9]+)(?![0-9])", raw_title)
        if m:
            code = m.group(1)
    info.code = code.upper()
    title = _strip_code_prefix(raw_title, info.code)
    info.title = "" if _is_boilerplate_title(title) else title
    info.description = str(d.get("synopsis") or "").strip()
    info.poster_url = str(d.get("cover_url") or "").strip()
    info.actresses = [str(x) for x in (d.get("actors") or []) if str(x).strip()]
    info.genres = [str(x) for x in (d.get("genres") or []) if str(x).strip()]
    info.release_date = str(d.get("release_date") or "").strip()
    info.maker = str(d.get("maker") or "").strip()
    return info


def fetch_video_info(
    product_id: str,
    *,
    base_url: str = BASE_URL,
    path_template: str = VIDEO_PATH_TEMPLATE,
    timeout: float = 12.0,
    session=None,
) -> MissavVideoInfo:
    product_id = (product_id or "").strip()
    if not product_id:
        raise ValueError("product_id is empty")
    headers = {"Accept-Language": "ja,en-US;q=0.9,en;q=0.8"}
    last_exc: Optional[BaseException] = None
    candidates = _slug_candidates(product_id)
    if not candidates:
        raise ValueError("product_id is empty")

    for slug in candidates:
        url = base_url.rstrip("/") + path_template.format(product_id=slug)
        # 재시도·연결 리셋 폴백은 fetching.http_get 이 담당. 404/빈 페이지는 다음 슬러그로.
        try:
            r = http_get(url, headers=headers, timeout=timeout, session=session)
        except Exception as e:
            last_exc = e
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

