"""
avwikidb.com 작품 페이지 ( /work/{품번}/ ) 에서
품번·제목·설명·포스터·여배우·장르·출시일·메이커를 HTML から抽出する.

예)
- `https://avwikidb.com/work/SW-1051/`

중요:
- avwikidb.com 은 환경에 따라 `requests`로 접근 시 403(봇 차단)이 발생할 수 있습니다.
- 그 경우 Playwright 우회 옵션을 사용하세요.
  - 실행: `python .\avwiki.py --pw SW-1051`
  - (최초 1회) 설치:
    - `pip install playwright`
    - `python -m playwright install chromium`
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://avwikidb.com"
WORK_PATH_TEMPLATE = "/work/{product_id}/"

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


def _abs_url(url: str, *, base_url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    return urljoin(base_url, url)


def _iter_ld_json(soup: BeautifulSoup) -> Iterable[Dict[str, Any]]:
    for tag in soup.select('script[type="application/ld+json"]'):
        raw = tag.string or tag.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    yield item
            continue
        if isinstance(data, dict):
            yield data


def _pick_movie_ld(soup: BeautifulSoup) -> Dict[str, Any]:
    for obj in _iter_ld_json(soup):
        if obj.get("@type") == "Movie":
            return obj
    return {}


def _pick_code_from_movie_ld(movie: Dict[str, Any]) -> str:
    ident = movie.get("identifier")
    if isinstance(ident, list):
        for it in ident:
            if not isinstance(it, dict):
                continue
            if (it.get("propertyID") or "").lower() == "code":
                return str(it.get("value") or "").strip()
    return ""


def _pick_poster_from_movie_ld(movie: Dict[str, Any]) -> str:
    img = movie.get("image")
    if isinstance(img, list) and img:
        return str(img[0]).strip()
    if isinstance(img, str):
        return img.strip()
    return ""


def _pick_actor_names_from_movie_ld(movie: Dict[str, Any]) -> List[str]:
    actor = movie.get("actor")
    out: List[str] = []
    if isinstance(actor, list):
        for it in actor:
            if isinstance(it, dict):
                name = str(it.get("name") or "").strip()
                if name:
                    out.append(name)
            elif isinstance(it, str) and it.strip():
                out.append(it.strip())
    elif isinstance(actor, dict):
        name = str(actor.get("name") or "").strip()
        if name:
            out.append(name)
    return out


def _pick_genres_from_movie_ld(movie: Dict[str, Any]) -> List[str]:
    g = movie.get("genre")
    if isinstance(g, list):
        return [str(x).strip() for x in g if str(x).strip()]
    if isinstance(g, str) and g.strip():
        return [g.strip()]
    return []


def _pick_maker_from_movie_ld(movie: Dict[str, Any]) -> str:
    pc = movie.get("productionCompany")
    if isinstance(pc, dict):
        return str(pc.get("name") or "").strip()
    if isinstance(pc, str):
        return pc.strip()
    return ""


def _pick_release_date_from_movie_ld(movie: Dict[str, Any]) -> str:
    dp = str(movie.get("datePublished") or "").strip()
    if not dp:
        return ""
    # 2026-05-21T00:00:00.000Z → 2026-05-21
    return dp.split("T", 1)[0]


def _dl_dt_dd_map(soup: BeautifulSoup) -> Dict[str, str]:
    """
    본문에 <dl><dt>품번</dt><dd>SW-1051</dd> 같은 형태가 있어서
    ld+json 누락 시 백업용으로 사용.
    """
    out: Dict[str, str] = {}
    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt", recursive=False)
        dds = dl.find_all("dd", recursive=False)
        if not dts or not dds:
            continue
        for dt, dd in zip(dts, dds):
            k = _text(dt)
            v = _text(dd)
            if k and v and k not in out:
                out[k] = v
    return out


def _pick_description_from_body(soup: BeautifulSoup) -> str:
    # "作品内容" 블록
    # <dt class="pb-1.5">作品内容</dt> <dd ...><div ...>...</div></dd>
    for dl in soup.find_all("dl"):
        dt = dl.find("dt")
        if not dt:
            continue
        if _text(dt) == "作品内容":
            dd = dl.find("dd")
            if dd:
                return _text(dd)
    return ""


def _pick_actresses_from_cards(soup: BeautifulSoup) -> List[str]:
    # <dt id="actresses">出演女優</dt> 아래 카드 링크 텍스트
    node = soup.select_one("#actresses")
    if not node:
        return []
    dd = node.find_next("dd")
    if not dd:
        return []
    names: List[str] = []
    for a in dd.find_all("a", href=True):
        t = _text(a)
        if t:
            names.append(t)
    return names


def _pick_genres_from_body(soup: BeautifulSoup) -> List[str]:
    # 장르가 있으면 "シチュエーション" 등에서 <span class="...">企画</span> 형태
    names: List[str] = []
    for dt in soup.find_all("dt"):
        if _text(dt) in ("シチュエーション", "ジャンル"):
            dd = dt.find_next("dd")
            if not dd:
                continue
            for s in dd.find_all("span"):
                t = _text(s)
                if t:
                    names.append(t)
    return names


@dataclass
class AvwikiInfo:
    code: str = ""
    title: str = ""
    description: str = ""
    poster_url: str = ""
    actresses: List[str] = field(default_factory=list)
    genres: List[str] = field(default_factory=list)
    release_date: str = ""
    maker: str = ""

    def to_text(self) -> str:
        d: Dict[str, Any] = {
            "품번": self.code,
            "제목": self.title,
            "설명": self.description,
            "포스터": self.poster_url,
            "여배우": ", ".join([x for x in self.actresses if x]),
            "장르": ", ".join([x for x in self.genres if x]),
            "출시일": self.release_date,
            "메이커": self.maker,
        }
        blocks: List[str] = []
        for k in _TEXT_FIELD_ORDER:
            v = "" if d.get(k) is None else str(d.get(k, ""))
            if k == "설명" and v:
                blocks.append(f"{k}:\n{v}".rstrip())
            else:
                blocks.append(f"{k}: {v}".rstrip())
        return "\n\n".join(blocks) + "\n"


def parse_work_html(html: str, *, base_url: str = BASE_URL) -> AvwikiInfo:
    soup = BeautifulSoup(html, "lxml")
    info = AvwikiInfo()

    movie = _pick_movie_ld(soup)
    if movie:
        info.title = str(movie.get("name") or "").strip()
        info.description = str(movie.get("description") or "").strip()
        info.poster_url = _abs_url(_pick_poster_from_movie_ld(movie), base_url=base_url)
        info.actresses = _pick_actor_names_from_movie_ld(movie)
        info.genres = _pick_genres_from_movie_ld(movie)
        info.maker = _pick_maker_from_movie_ld(movie)
        info.release_date = _pick_release_date_from_movie_ld(movie)
        info.code = _pick_code_from_movie_ld(movie)

    # fallback: h1
    if not info.title:
        h1 = soup.find("h1")
        info.title = _text(h1)

    # fallback: poster from main image
    if not info.poster_url:
        img = soup.select_one("article img, main img")
        if img and img.get("src"):
            info.poster_url = _abs_url(str(img.get("src")), base_url=base_url)

    # fallback: code/maker/date from dl
    dlmap = _dl_dt_dd_map(soup)
    if not info.code:
        info.code = dlmap.get("品番", "").strip()
    if not info.maker:
        info.maker = dlmap.get("メーカー", "").strip()
    if not info.release_date:
        # "2026年05月21日" → "2026-05-21"
        dt = dlmap.get("配信開始日", "").strip()
        m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", dt)
        if m:
            y, mo, da = m.group(1), int(m.group(2)), int(m.group(3))
            info.release_date = f"{y}-{mo:02d}-{da:02d}"

    # fallback: description from body
    if not info.description:
        info.description = _pick_description_from_body(soup)

    # fallback: actresses from cards
    if not info.actresses:
        info.actresses = _pick_actresses_from_cards(soup)

    # fallback: genres from body
    if not info.genres:
        info.genres = _pick_genres_from_body(soup)

    return info


def fetch_work_info(
    product_id: str,
    *,
    base_url: str = BASE_URL,
    path_template: str = WORK_PATH_TEMPLATE,
    timeout: float = 30.0,
    session: Optional[requests.Session] = None,
    use_playwright: bool = False,
    playwright_headless: bool = True,
    playwright_wait_ms: int = 1500,
) -> AvwikiInfo:
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
    if use_playwright:
        html = _fetch_html_with_playwright(
            url, headless=playwright_headless, wait_ms=playwright_wait_ms
        )
        return parse_work_html(html, base_url=base_url)

    r = sess.get(url, headers=headers, timeout=timeout)
    try:
        r.raise_for_status()
    except requests.HTTPError as e:
        # avwikidb.com は環境によって 403(Cloudflare等)が返ることがある
        # その場合は fetch を諦め、保存した HTML 스냅샷을 parse_work_html 로 처리하도록 유도한다.
        if r.status_code == 403:
            raise requests.HTTPError(
                f"{e}\n"
                f"- 이 사이트는 403(봇 차단)으로 막히는 경우가 많아서 `requests`로는 불가할 수 있습니다.\n"
                f"- 해결 1) 브라우저에서 HTML 저장 후: `python avwiki.py --html SW-1051.html`\n"
                f"- 해결 2) Playwright로 브라우저 우회: `python avwiki.py --pw SW-1051`\n"
                f"  (설치: `pip install playwright` 후 `python -m playwright install chromium`)\n"
            ) from e
        raise requests.HTTPError(
            f"{e}\n"
            f"- 직접 접속이 403이면, 브라우저에서 페이지 HTML을 저장한 뒤\n"
            f"  `python avwiki.py --html SW-1051.html` 로 파싱하세요.\n"
            f"- 또는 네트워크/봇 차단 정책을 확인하세요."
        ) from e
    r.encoding = r.apparent_encoding or "utf-8"
    return parse_work_html(r.text, base_url=base_url)


def _fetch_html_with_playwright(url: str, *, headless: bool, wait_ms: int) -> str:
    """
    Cloudflare/봇차단(403) 우회용. Playwright가 설치되어 있을 때만 동작.

    - headless=False 로 실행하면 브라우저 창이 떠서, 만약 사람 확인(체크/캡차)이 나오면 직접 통과 가능.
    - wait_ms 는 페이지 로딩 후 추가 대기 시간.
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Playwright가 설치되어 있지 않습니다. 아래 순서로 설치 후 다시 시도하세요.\n"
            "1) pip install playwright\n"
            "2) python -m playwright install chromium\n"
        ) from e

    wait_ms = max(0, int(wait_ms))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        if wait_ms:
            page.wait_for_timeout(wait_ms)
        html = page.content()
        context.close()
        browser.close()
        return html


if __name__ == "__main__":
    import sys

    # Windows 콘솔 깨짐 방지(가능한 경우)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    args = [a for a in sys.argv[1:] if a.strip()]
    if len(args) >= 2 and args[0] == "--pw":
        code = args[1].strip()
        data = fetch_work_info(code, use_playwright=True)
        print(data.to_text(), end="")
    elif len(args) >= 2 and args[0] == "--pw-headful":
        code = args[1].strip()
        # headful은 사람이 확인할 수 있도록 더 길게 대기
        data = fetch_work_info(
            code, use_playwright=True, playwright_headless=False, playwright_wait_ms=8000
        )
        print(data.to_text(), end="")
    elif len(args) >= 2 and args[0] == "--html":
        path = args[1]
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        data = parse_work_html(html)
        print(data.to_text(), end="")
    else:
        code = args[0].strip() if args else "SW-1051"
        data = fetch_work_info(code)
        print(data.to_text(), end="")

