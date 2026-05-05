"""
하이브리드 크롤러 엔진 (Harvest/crawler.py): 
Playwright와 DrissionPage를 이용한 순수 데이터 추출 기능만 담당합니다.
DB 저장이나 번역 등 다른 레이어와는 완전히 격리되어 있습니다.
"""
from __future__ import annotations

import asyncio
import re
import socket
import time
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests
from DrissionPage import ChromiumPage, ChromiumOptions
import tempfile
import shutil

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from javstory.utils.njav_playwright import njavtv_detail_urls, scrape_njavtv_playwright_async
from javstory.utils.common import log_ts

# 폴백 스크레이퍼(순서: 123av -> missav123 -> avwiki -> njavtv)
# - 루트에 있는 단독 스크립트들이지만, _ROOT를 sys.path에 추가했기 때문에 import 가능
try:
    import av123_scraper  # type: ignore
except Exception:  # pragma: no cover
    av123_scraper = None  # type: ignore
try:
    import missav123_scraper  # type: ignore
except Exception:  # pragma: no cover
    missav123_scraper = None  # type: ignore
try:
    import avwiki  # type: ignore
except Exception:  # pragma: no cover
    avwiki = None  # type: ignore

# njavtv.com 정밀 셀렉터 (nth-child 체인 금지)
NJAV_TITLE_SELECTORS = ("css:h1.text-nord6", "tag:h1")
NJAV_SYNOPSIS_SELECTORS = ("css:div.text-secondary.break-all", "css:div.break-all.text-secondary", "tag:div@class=break-all")
NJAV_COVER_SELECTOR = ".plyr__poster"

LABELS_TO_PROBE = {
    "product_code": "品番",
    "release_date": "配信開始日",
    "actors": "女優",
    "genres": "ジャンル",
    "maker": "メーカー"
}

_MAKER_HREF_MARKERS = ("/makers/", "/maker/")
_NJAV_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_PLACEHOLDER_TITLE_LOWER = frozenset(
    {"njavtv.com", "njavtv", "njav", "njav tv", "just a moment...", "attention required"}
)

# 에러 페이지(title) 시그니처 — 정상 메타로 저장되면 안 됨
_ERROR_TITLE_PATTERNS = (
    r"\b503\b",
    r"service unavailable",
    r"bad gateway",
    r"gateway timeout",
    r"temporarily unavailable",
    r"too many requests",
    r"access denied",
    r"forbidden",
    r"cloudflare",
    r"just a moment",
    r"attention required",
    r"서비스\s*이용\s*불가",
    r"일시적(으로)?\s*사용\s*불가",
)

def _tcp_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _slug_for_url(product_code: str | None) -> str:
    if not product_code: return ""
    return product_code.strip().lower().replace("_", "-")

def _njav_path_is_dm_detail(href: str) -> bool:
    try:
        parts = [p for p in urlparse(href).path.split("/") if p]
        if len(parts) < 3: return False
        return parts[0].lower().startswith("dm") and parts[1] == "ja"
    except: return False

def _curl_resolve_njav_http_redirect(entry_url: str) -> str | None:
    try:
        r = curl_requests.get(
            entry_url, headers={"User-Agent": _NJAV_UA},
            timeout=30, impersonate="chrome120", allow_redirects=True,
        )
        u = str(r.url).strip()
        if u and "njavtv.com" in u.lower() and _njav_path_is_dm_detail(u):
            return u
    except: pass
    return None

def _wait_njav_detail_url(page: Any, *, slug: str, max_wait: float) -> str:
    deadline = time.time() + max_wait
    slug_l = _slug_for_url(slug)
    while time.time() < deadline:
        href = (_page_location_href(page) or (getattr(page, "url", None) or "").strip() or "")
        if href and _njav_path_is_dm_detail(href):
            if slug_l:
                parts = [p for p in urlparse(href).path.split("/") if p]
                tail = (parts[-1] if parts else "").lower().replace("_", "-")
                if tail == slug_l or tail.replace("-", "") == slug_l.replace("-", ""):
                    return href
            else: return href
        time.sleep(0.35)
    return (_page_location_href(page) or (getattr(page, "url", None) or "").strip() or "")

def _title_looks_placeholder(title: str | None) -> bool:
    s = (title or "").strip().lower()
    if len(s) < 4: return True
    if s in _PLACEHOLDER_TITLE_LOWER: return True
    if "njav" in s and ".com" in s and len(s) < 24: return True
    try:
        if any(re.search(pat, s, flags=re.IGNORECASE) for pat in _ERROR_TITLE_PATTERNS):
            return True
    except Exception:
        pass
    return False

def _norm_product_code(val: str | None) -> str:
    if not val or not isinstance(val, str): return ""
    return re.sub(r"\s+", "", val.strip()).upper()

def _extract_njav_head_meta(html: str, base_url: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not (html and html.strip()): return out
    soup = BeautifulSoup(html, "html.parser")
    head = soup.find("head")
    if not head: return out
    def _content(sel: dict[str, str]) -> str | None:
        tag = head.find("meta", attrs=sel)
        return (tag.get("content") or "").strip() if tag and (tag.get("content") or "").strip() else None
    
    og_img = _content({"property": "og:image"}) or _content({"name": "og:image"})
    if og_img: out["cover_url"] = urljoin(base_url, og_img)
    title = _content({"property": "og:title"}) or _content({"name": "og:title"})
    if title: out["title"] = title
    if not out.get("title") and soup.title and soup.title.string:
        out["title"] = soup.title.string.strip()
    desc = _content({"name": "description"}) or _content({"property": "og:description"}) or _content({"name": "twitter:description"})
    if desc: out["synopsis"] = desc
    actors = []
    for m in head.find_all("meta", attrs={"property": "og:video:actor"}):
        c = (m.get("content") or "").strip()
        if c and c not in actors: actors.append(c)
    if actors: out["actors"] = actors
    rd = _content({"property": "og:video:release_date"})
    if rd: out["release_date"] = rd
    return out

def _merge_njav_body_head(body: dict[str, Any], head: dict[str, Any]) -> dict[str, Any]:
    merged = dict(body)
    if not head: return merged
    if not (merged.get("cover_url") or "").strip() and head.get("cover_url"): merged["cover_url"] = head["cover_url"]
    if not (merged.get("title") or "").strip() and head.get("title"): merged["title"] = head["title"]
    if not (merged.get("synopsis") or "").strip() and head.get("synopsis"): merged["synopsis"] = head["synopsis"]
    b_actors = merged.get("actors")
    if not (isinstance(b_actors, list) and b_actors) and not (isinstance(b_actors, str) and b_actors.strip()) and head.get("actors"):
        merged["actors"] = head["actors"]
    _rd = merged.get("release_date")
    if not (isinstance(_rd, str) and _rd.strip()) and head.get("release_date"): merged["release_date"] = head["release_date"]
    return merged

def _page_location_href(page: Any) -> str | None:
    try:
        u = page.run_js("return location.href")
        if isinstance(u, str) and u.startswith("http"): return u.strip()
    except: pass
    return None

def _print_scraped_preview(data: dict[str, Any]) -> None:
    print("[Hybrid] --- 수집 결과 ---")
    order = [("final_url", "최종 URL"), ("title", "제목"), ("product_code", "품번"), ("release_date", "출시일"), ("maker", "메이커"), ("actors", "배우"), ("genres", "장르"), ("synopsis", "시놉시스"), ("cover_url", "표지 URL")]
    for key, label in order:
        v = data.get("_final_url") or data.get("final_url") if key == "final_url" else data.get(key)
        if v is None or v == "" or v == []:
            print(f"  {label}: (없음)")
            continue
        if isinstance(v, list):
            preview = ", ".join(str(x) for x in v[:12])
            if len(v) > 12: preview += f" … 외 {len(v) - 12}명"
            print(f"  {label}: {preview}")
        elif isinstance(v, str) and len(v) > 200 and key == "synopsis":
            print(f"  {label}: {v[:200]}…")
        else: print(f"  {label}: {v}")
    print("[Hybrid] ------------------")

def _raw_has_any_content(raw: dict[str, Any]) -> bool:
    if not raw: return False
    # 단순 요청 정보나 URL 외에 실제 데이터가 있는지 확인
    #
    # 중요: njavtv는 404/에러 페이지에서도 head meta description(사이트 공용 소개 문구)이 내려올 수 있어
    # synopsis만 채워진 상태를 "성공"으로 판정하면 안 된다.
    title = str(raw.get("title") or "").strip()
    cover = str(raw.get("cover_url") or "").strip()
    actors = raw.get("actors")
    genres = raw.get("genres")
    synopsis = str(raw.get("synopsis") or "").strip()

    def _has_list(v: Any) -> bool:
        return isinstance(v, list) and any(str(x).strip() for x in v)

    # njavtv 404에서 흔한 Not Found 타이틀 (일본어)
    notfound_titles = {"見つかりません", "見つかりませんでした", "ページが見つかりません", "ページが見つかりませんでした"}

    def _cover_looks_placeholder(u: str) -> bool:
        s = (u or "").strip().lower()
        if not s:
            return True
        if s in ("이미지 누락",):
            return True
        # 사이트 로고/파비콘류는 표지로 취급하면 안 됨
        if "logo" in s and ("njavtv" in s or "missav" in s):
            return True
        if s.endswith("/favicon.ico") or "favicon" in s:
            return True
        if "logo-square" in s:
            return True
        return False

    has_title = (
        bool(title)
        and (not _title_looks_placeholder(title))
        and title != "제목 없음"
        and title not in notfound_titles
    )
    has_cover = bool(cover) and (not _cover_looks_placeholder(cover))
    has_actors = _has_list(actors)
    has_genres = _has_list(genres)

    # synopsis는 단독 근거로 삼지 않는다(404 공용 문구 오인 방지)
    if has_title or has_cover or has_actors or has_genres:
        return True

    if synopsis:
        # njavtv 404에서 자주 보이는 공용 소개 문구(일부 포함)면 데이터 없음으로 처리
        generic_frags = (
            "オンラインで無料ハイビジョンAV映画",
            "ダウンロード不要",
            "10万本以上の動画",
            "毎日更新",
            "広告が表示されない",
            "シリアル番号",
            "女優、またはシリーズ名で動画を検索",
        )
        if any(frag in synopsis for frag in generic_frags):
            return False

    # 여기까지 왔으면 실질 콘텐츠가 없다고 판단
    return False

def _scrape_dict_for_db(raw: dict[str, Any], product_code: str) -> dict[str, Any]:
    code = product_code.upper()
    title = (raw.get("title") or "").strip()
    if not title or _title_looks_placeholder(title): title = "제목 없음"
    
    # [수정] actors, genres는 리스트 타입을 유지해야 리졸버에서 글자 단위로 쪼개지지 않음
    raw_actors = raw.get("actors")
    if isinstance(raw_actors, str): raw_actors = [a.strip() for a in raw_actors.split(",") if a.strip()]
    elif not isinstance(raw_actors, list): raw_actors = []
    
    raw_genres = raw.get("genres")
    if isinstance(raw_genres, str): raw_genres = [g.strip() for g in raw_genres.split(",") if g.strip()]
    elif not isinstance(raw_genres, list): raw_genres = []
    
    cover_url = (raw.get("cover_url") or "").strip()
    if not cover_url: cover_url = "이미지 누락"
    
    def _to_str(v: Any) -> str:
        if isinstance(v, list): return ", ".join(str(x) for x in v)
        return str(v).strip() if v else ""

    return {
        "title": title, 
        "original_title": title, # 크롤링 원문 타이틀 보존
        "actors": raw_actors,    # 리스트 유지
        "genres": raw_genres,    # 리스트 유지
        "maker": _to_str(raw.get("maker")), 
        "release_date": _to_str(raw.get("release_date")), 
        "synopsis": (raw.get("synopsis") or "").strip(),
        "cover_url": cover_url, 
        "_source": "njavtv_scrape", 
        "_final_url": raw.get("_final_url"),
    }


def _ensure_list_str(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        out: list[str] = []
        for x in v:
            s = str(x).strip()
            if s:
                out.append(s)
        return out
    if isinstance(v, str):
        # 콤마 구분 문자열 폴백
        return [s.strip() for s in v.split(",") if s.strip()]
    return []


def _merge_empty_only(base: dict[str, Any], extra: dict[str, Any], *, source: str) -> dict[str, Any]:
    """
    base에 비어있는 필드만 extra로 채움.
    - actors/genres는 합집합(중복 제거, 순서 보존)
    - title이 들어오면 original_title도 채울 수 있도록 유지
    """
    if not extra:
        return base
    base.setdefault("_sources_tried", [])
    base["_sources_tried"].append(source)

    def _empty_str(s: Any) -> bool:
        return not (isinstance(s, str) and s.strip())

    # 문자열 필드: 비어있으면 채움
    for k in ("title", "original_title", "synopsis", "cover_url", "release_date", "maker"):
        if _empty_str(base.get(k)) and isinstance(extra.get(k), str) and str(extra.get(k)).strip():
            base[k] = str(extra.get(k)).strip()

    # title이 채워졌는데 original_title이 비어있으면 동기화
    if _empty_str(base.get("original_title")) and isinstance(base.get("title"), str) and base["title"].strip():
        base["original_title"] = base["title"].strip()

    # 리스트 필드: 합집합
    for k in ("actors", "genres"):
        a = _ensure_list_str(base.get(k))
        b = _ensure_list_str(extra.get(k))
        seen: set[str] = set()
        merged: list[str] = []
        for x in a + b:
            if x and x not in seen:
                seen.add(x)
                merged.append(x)
        if merged:
            base[k] = merged

    # favorite_score — 항상 합산 (비어있음 여부와 무관)
    base["favorite_score"] = int(base.get("favorite_score") or 0) + int(extra.get("favorite_score") or 0)
    for k, v in extra.items():
        if k.startswith("_fav_src_"):
            base[k] = int(v or 0)

    # 디버그용: 최종 URL / 소스
    if _empty_str(base.get("_final_url")) and isinstance(extra.get("_final_url"), str) and extra["_final_url"].strip():
        base["_final_url"] = extra["_final_url"].strip()
    base.setdefault("_sources_used", [])
    # 실제로 뭔가가 채워졌는지 정밀 비교까지는 무겁기 때문에, extra가 비어있지 않으면 사용으로 기록
    base["_sources_used"].append(source)
    return base


def _needs_fallback(d: dict[str, Any]) -> bool:
    """없음/부족 판정: title 또는 cover_url이 없으면 폴백."""
    title = str(d.get("title") or "").strip()
    cover = str(d.get("cover_url") or "").strip()
    return (not title) or (not cover) or title == "제목 없음" or cover == "이미지 누락"


def _scrape_123av(product_code: str) -> dict[str, Any]:
    if av123_scraper is None:
        return {}
    info = av123_scraper.fetch_video_info(product_code)
    # VideoInfo: actresses는 [{"name","href"}], genres는 [str]
    actresses = []
    try:
        for a in (getattr(info, "actresses", None) or []):
            if isinstance(a, dict):
                nm = str(a.get("name") or "").strip()
                if nm:
                    actresses.append(nm)
            elif isinstance(a, str) and a.strip():
                actresses.append(a.strip())
    except Exception:
        actresses = []
    poster = str(getattr(info, "poster_url", "") or "").strip()
    fav = int(getattr(info, "favourite_count", 0) or 0)
    return {
        "title": str(getattr(info, "title", "") or "").strip(),
        "original_title": str(getattr(info, "title", "") or "").strip(),
        "synopsis": str(getattr(info, "description", "") or "").strip(),
        "cover_url": poster,
        "actors": actresses,
        "genres": _ensure_list_str(getattr(info, "genres", None)),
        "release_date": str(getattr(info, "release_date", "") or "").strip(),
        "maker": str(getattr(info, "maker", "") or "").strip(),
        "favorite_score": fav,
        "_fav_src_123av": fav,
        "_source": "123av",
    }


def _scrape_missav123(product_code: str) -> dict[str, Any]:
    if missav123_scraper is None:
        return {}
    info = missav123_scraper.fetch_video_info(product_code)
    fav = int(getattr(info, "favourite_count", 0) or 0)
    return {
        "title": str(getattr(info, "title", "") or "").strip(),
        "original_title": str(getattr(info, "title", "") or "").strip(),
        "synopsis": str(getattr(info, "description", "") or "").strip(),
        "cover_url": str(getattr(info, "poster_url", "") or "").strip(),
        "actors": _ensure_list_str(getattr(info, "actresses", None)),
        "genres": _ensure_list_str(getattr(info, "genres", None)),
        "release_date": str(getattr(info, "release_date", "") or "").strip(),
        "maker": str(getattr(info, "maker", "") or "").strip(),
        "favorite_score": fav,
        "_fav_src_missav123": fav,
        "_source": "missav123",
    }


def _scrape_avwiki(product_code: str, *, use_playwright: bool = False) -> dict[str, Any]:
    if avwiki is None:
        return {}
    info = avwiki.fetch_work_info(product_code, use_playwright=use_playwright)
    return {
        "title": str(getattr(info, "title", "") or "").strip(),
        "original_title": str(getattr(info, "title", "") or "").strip(),
        "synopsis": str(getattr(info, "description", "") or "").strip(),
        "cover_url": str(getattr(info, "poster_url", "") or "").strip(),
        "actors": _ensure_list_str(getattr(info, "actresses", None)),
        "genres": _ensure_list_str(getattr(info, "genres", None)),
        "release_date": str(getattr(info, "release_date", "") or "").strip(),
        "maker": str(getattr(info, "maker", "") or "").strip(),
        "_source": "avwiki_pw" if use_playwright else "avwiki",
    }

class HybridJavCrawler:
    def __init__(self) -> None:
        pass

    def get_local_page_data(self, url: str, expected_product_code: str | None = None, force_visible: bool = False) -> dict[str, Any]:
        log_ts(f"[Hybrid] 요청 URL: {url} (Visible: {force_visible})")
        # [개선] 동영상 자동 재생 방지 및 음소거 설정
        co = ChromiumOptions().set_argument('--no-sandbox')
        co.set_argument('--autoplay-policy=user-gesture-required') 
        co.set_argument('--mute-audio')                            
        
        # [핵심] 병렬 실행 충돌 방지: OS가 할당한 실제 포트 사용(set_local_port(0)은 127.0.0.1:0으로 남는 경우가 있음)
        co.set_local_port(_tcp_free_port())
        
        slug = expected_product_code or f"tmp_{int(time.time())}"
        # 각 품번별로 독립된 임시 사용자 데이터 경로 할당 (잠금 에러 방지)
        tmp_user_dir = Path(tempfile.gettempdir()) / f"javstory_dp_{slug}"
        if tmp_user_dir.exists():
            try: shutil.rmtree(tmp_user_dir, ignore_errors=True)
            except: pass
        co.set_user_data_path(str(tmp_user_dir))

        if force_visible:
            co.set_paths(browser_path=None) # 시스템 기본 브라우저 사용 시도
            co.headless(False)
        else:
            co.headless(True)

        page = None
        data: dict[str, Any] = {}
        slug = expected_product_code or ""
        try:
            page = ChromiumPage(co)
            try: browser_pid = page.process_id
            except: pass
            
            # 유저 에이전트 및 핑거프린트 노출 최소화
            page.set.user_agent(_NJAV_UA)
            
            open_url = url
            http_final = _curl_resolve_njav_http_redirect(url)
            if http_final: open_url = http_final
            
            page.get(open_url)
            
            # Cloudflare 대기 레이턴시 증가
            for _ in range(5):
                if any(term in (page.title or "") for term in ["Access Denied", "403 Forbidden", "Attention Required", "Cloudflare", "Just a moment"]):
                    log_ts(f"[Hybrid] 보안 확인 중... 대기 ({_ + 1}/5)")
                    time.sleep(5)
                else: break
            href = _page_location_href(page) or (page.url or "").strip() or open_url
            final_url = href or open_url
            for _ in range(2):
                if ("Just a moment" in page.title or "잠시만 기다려" in page.title) and not page.ele('tag:h1'): time.sleep(5)
                else: break
            for s in ['text:18歳以上', 'text:확인', 'text:Enter', 'text:Yes']:
                btn = page.ele(s, timeout=1)
                if btn: btn.click(); time.sleep(2); break
            final_url = _wait_njav_detail_url(page, slug=slug, max_wait=22.0) or final_url
            
            # [개선] 상세 정보(詳細) 탭 활성화 시도 (탭이 숨겨져 있어도 텍스트 추출을 보장하기 위함)
            for tab_text in ['text:詳細', 'text:Details', 'tag:span@text=詳細']:
                tab = page.ele(tab_text, timeout=2)
                if tab:
                    try: 
                        tab.click(by_js=True)
                        time.sleep(1.5)
                        log_ts("[Hybrid] 상세 정보 탭 활성화 완료")
                        break
                    except: pass
            for sel in NJAV_TITLE_SELECTORS:
                ele = page.ele(sel, timeout=1)
                if ele and (ele.text or "").strip() and not _title_looks_placeholder(ele.text.strip()):
                    data["title"] = ele.text.strip(); break
            for sel in NJAV_SYNOPSIS_SELECTORS:
                ele = page.ele(sel, timeout=1)
                if ele and (ele.text or "").strip(): data["synopsis"] = ele.text.strip(); break
            poster = page.ele(NJAV_COVER_SELECTOR, timeout=2)
            if poster:
                m = re.search(r'url\(["\']?(.+?)["\']?\)', poster.attr('style') or "")
                if m: data["cover_url"] = m.group(1).replace("&quot;", "").strip('"').strip("'")
            # [개선] 상세 정보 영역(div.space-y-2)의 하위 로우(div.text-secondary)들만 독립적으로 루프하며 추출
            meta_container = page.ele('css:div.space-y-2', timeout=3)
            if meta_container:
                meta_rows = meta_container.eles('css:div.text-secondary')
                for row in meta_rows:
                    row_text = row.text or ""
                    
                    # 1. 품번 (品番) - span.font-medium에서 정확히 추출
                    if "品番" in row_text:
                        code_val = row.ele('css:span.font-medium', timeout=1)
                        if code_val: data["product_code"] = code_val.text.strip()
                    
                    # 2. 출시일 (配信開始日) - time 또는 span.font-medium에서 추출
                    elif "配信開始" in row_text or "発売日" in row_text:
                        rd_val = row.ele('tag:time') or row.ele('css:span.font-medium')
                        if rd_val: data["release_date"] = rd_val.text.strip()

                    # 3. 여배우 (女優) - 모든 a 태그를 리스트로 수집 (다수 대응) + 괄호 제거(예외 처리)
                    elif "女優" in row_text or "出演자" in row_text or "出演者" in row_text:
                        raw_actors = [a.text.strip() for a in row.eles('tag:a') if a.text.strip()]
                        # [개선] 괄호 및 괄호 내부 텍스트 제거 (예: 水谷心音（藤崎りお） -> 水谷心音)
                        actors = []
                        for ra in raw_actors:
                            clean_name = re.sub(r'[\(（].*?[\)）]', '', ra).strip()
                            if clean_name: actors.append(clean_name)
                        if actors: data["actors"] = actors

                    # 4. 장르 (ジャンル) - 모든 a 태그를 리스트로 수집 (누락 방지)
                    elif "ジャンル" in row_text or "カテゴリー" in row_text:
                        genres = [a.text.strip() for a in row.eles('tag:a') if a.text.strip()]
                        if genres: data["genres"] = genres

                    # 5. 메이커 (メーカー) - 첫 번째 a 태그 추출
                    elif "メーカー" in row_text or "브랜드" in row_text or "ブランド" in row_text:
                        maker_link = row.ele('tag:a')
                        if maker_link: data["maker"] = maker_link.text.strip()
                    
                    # 6. 감독 (監督) / 레이블 (レー벨) 등 추가 정보
                    elif "監督" in row_text:
                        director_val = row.ele('tag:a')
                        if director_val: data["director"] = director_val.text.strip()
                    elif "レーベル" in row_text:
                        label_val = row.ele('tag:a')
                        if label_val: data["label"] = label_val.text.strip()

            # [디버그] 추출된 핵심 필드 로그 남기기
            for k in ["product_code", "actors", "genres", "maker"]:
                if data.get(k): log_ts(f"[Hybrid] 정밀 라벨 발견: {k} -> {data[k]}")
            final_url = _page_location_href(page) or final_url
            data = _merge_njav_body_head(data, _extract_njav_head_meta(page.html or "", final_url))
            data["_final_url"] = final_url
            _print_scraped_preview(data)
            return data
        except Exception as e:
            msg = str(e).encode('utf-8', 'replace').decode('utf-8', 'replace')
            print(f"[Hybrid] 추출 중 에러: {msg}")
            return {}
        finally: 
            try: 
                if page:
                    page.quit()
            except: pass
            
            # [강력 조치] 프로세스 잔류 방지 (특히 Headless 모드 좀비 방어)
            if browser_pid:
                try:
                    import psutil
                    proc = psutil.Process(browser_pid)
                    if proc.is_running():
                        proc.kill() # 확실한 종료
                        log_ts(f"[Hybrid] 브라우저 프로세스(PID:{browser_pid}) 강제 종료 완료")
                except: pass

            # 작업 종료 후 임시 폴더 삭제 시도 (용량 관리)
            if 'tmp_user_dir' in locals() and tmp_user_dir.exists():
                try: shutil.rmtree(tmp_user_dir, ignore_errors=True)
                except: pass

    async def fetch_metadata_smart(self, product_code: str) -> dict[str, Any]:
        code = product_code.upper()
        out: dict[str, Any] = {"_sources_tried": [], "_sources_used": []}

        # 1) 123av
        log_ts(f"[Hybrid] 1순위(123av): requests 수집 시도: {code}")
        try:
            d = await asyncio.to_thread(_scrape_123av, code)
            out = _merge_empty_only(out, d, source="123av")
        except Exception:
            pass

        # 2) missav123
        if _needs_fallback(out):
            log_ts(f"[Hybrid] 2순위(missav123): requests 수집 시도: {code}")
            try:
                d = await asyncio.to_thread(_scrape_missav123, code)
                out = _merge_empty_only(out, d, source="missav123")
            except Exception:
                pass

        # 3) avwiki (아마추어 보루 / 403 시 Playwright)
        if _needs_fallback(out):
            log_ts(f"[Hybrid] 3순위(avwiki): requests 수집 시도: {code}")
            try:
                d = await asyncio.to_thread(_scrape_avwiki, code, False)
                out = _merge_empty_only(out, d, source="avwiki")
            except Exception as e:
                if "403" in str(e):
                    try:
                        log_ts(f"[Hybrid] 3순위(avwiki): 403 감지 → Playwright 우회 시도: {code}")
                        d2 = await asyncio.to_thread(_scrape_avwiki, code, True)
                        out = _merge_empty_only(out, d2, source="avwiki_pw")
                    except Exception:
                        pass

        # 4) njavtv (Playwright -> DrissionPage -> 재시도)
        if _needs_fallback(out):
            log_ts(f"[Hybrid] 4순위(njavtv): Playwright(Headless) 수집 시도: {code}")
            raw = await scrape_njavtv_playwright_async(code)
            if _raw_has_any_content(raw):
                nj = _scrape_dict_for_db(raw, code)
                nj["_final_url"] = raw.get("_final_url") or raw.get("final_url")
                out = _merge_empty_only(out, nj, source="njavtv")

        if _needs_fallback(out):
            log_ts(f"[Hybrid] 4순위(njavtv): DrissionPage(Headless) 정밀 수집 시도: {code}")
            for nj_url in njavtv_detail_urls(code):
                raw2 = await asyncio.to_thread(
                    self.get_local_page_data,
                    nj_url,
                    code,
                    False,
                )
                if _raw_has_any_content(raw2):
                    nj2 = _scrape_dict_for_db(raw2, code)
                    nj2["_final_url"] = raw2.get("_final_url") or raw2.get("final_url")
                    out = _merge_empty_only(out, nj2, source="njavtv_dp")
                    break

        if _needs_fallback(out):
            log_ts(f"[Hybrid] 4순위(njavtv): 최종 재시도(Headless) : {code}")
            await asyncio.sleep(4)
            for nj_url in njavtv_detail_urls(code):
                raw3 = await asyncio.to_thread(
                    self.get_local_page_data,
                    nj_url,
                    code,
                    False,
                )
                if _raw_has_any_content(raw3):
                    nj3 = _scrape_dict_for_db(raw3, code)
                    nj3["_final_url"] = raw3.get("_final_url") or raw3.get("final_url")
                    out = _merge_empty_only(out, nj3, source="njavtv_dp_retry")
                    break

        # 최소 결과 검증: title/synopsis/cover_url 중 하나라도 있어야 성공으로 취급
        if not _raw_has_any_content(out):
            return {}
        out.setdefault("_source", "fallback_chain")
        return out
