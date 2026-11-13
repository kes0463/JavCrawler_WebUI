"""
하이브리드 크롤러 엔진 (Harvest/crawler.py): 
Scrapling(javstory.harvest.fetching) 기반 순수 데이터 추출 기능만 담당합니다.
DB 저장이나 번역 등 다른 레이어와는 완전히 격리되어 있습니다.
"""
from __future__ import annotations

import asyncio
import os
import re
import time
import sys
import unicodedata
from pathlib import Path
from typing import Any, Callable


_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from javstory.utils.common import log_ts

try:
    from javstory.harvest.scrapers import av123_scraper
except Exception:  # pragma: no cover
    av123_scraper = None  # type: ignore
try:
    from javstory.harvest.scrapers import missav123_scraper
except Exception:  # pragma: no cover
    missav123_scraper = None  # type: ignore
try:
    from javstory.harvest.scrapers import avwiki
except Exception:  # pragma: no cover
    avwiki = None  # type: ignore
try:
    from javstory.harvest.scrapers import av_wiki_net_scraper
except Exception:  # pragma: no cover
    av_wiki_net_scraper = None  # type: ignore
try:
    from javstory.harvest.scrapers import njavtv_scraper
except Exception:  # pragma: no cover
    njavtv_scraper = None  # type: ignore

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
    from javstory.utils.actress_profile import dedupe_crawled_actor_tokens

    raw_actors = dedupe_crawled_actor_tokens(raw_actors)
    
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
    from javstory.harvest.scrapers.av123_scraper import _is_boilerplate_title

    if not extra:
        return base
    base.setdefault("_sources_tried", [])
    base["_sources_tried"].append(source)
    field_sources: dict[str, str] = base.setdefault("_field_sources", {})

    def _empty_str(s: Any) -> bool:
        return not (isinstance(s, str) and s.strip())

    # 문자열 필드: 비어있으면 채움
    for k in ("title", "original_title", "synopsis", "cover_url", "release_date", "maker"):
        if _empty_str(base.get(k)) and isinstance(extra.get(k), str) and str(extra.get(k)).strip():
            val = str(extra.get(k)).strip()
            if k in ("title", "original_title") and _is_boilerplate_title(val):
                continue
            base[k] = val
            field_sources[k] = source

    # title이 채워졌는데 original_title이 비어있으면 동기화
    if _empty_str(base.get("original_title")) and isinstance(base.get("title"), str) and base["title"].strip():
        if not _is_boilerplate_title(base["title"]):
            base["original_title"] = base["title"].strip()

    # 리스트 필드: genres는 합집합, actors는 정규화 dedupe + 1차 소스 우선
    from javstory.utils.actress_profile import dedupe_crawled_actor_tokens

    genres_a = _ensure_list_str(base.get("genres"))
    genres_b = _ensure_list_str(extra.get("genres"))
    if genres_a or genres_b:
        seen_g: set[str] = set()
        merged_g: list[str] = []
        for x in genres_a + genres_b:
            if x and x not in seen_g:
                seen_g.add(x)
                merged_g.append(x)
        if merged_g:
            base["genres"] = merged_g
        if not genres_a and genres_b:
            field_sources["genres"] = source

    actors_a = dedupe_crawled_actor_tokens(_ensure_list_str(base.get("actors")))
    actors_b = dedupe_crawled_actor_tokens(_ensure_list_str(extra.get("actors")))
    if actors_a and actors_b:
        base["actors"] = dedupe_crawled_actor_tokens(actors_a + actors_b)
    elif actors_b:
        base["actors"] = actors_b
    elif actors_a:
        base["actors"] = actors_a
    if not actors_a and actors_b:
        field_sources["actors"] = source

    # favorite_score — 항상 합산 (비어있음 여부와 무관)
    base["favorite_score"] = int(base.get("favorite_score") or 0) + int(extra.get("favorite_score") or 0)
    for k, v in extra.items():
        if k.startswith("_fav_src_"):
            base[k] = int(v or 0)

    # 최종 URL / 소스
    if _empty_str(base.get("_final_url")) and isinstance(extra.get("_final_url"), str) and extra["_final_url"].strip():
        base["_final_url"] = extra["_final_url"].strip()
    base.setdefault("_sources_used", [])
    # 실제로 뭔가가 채워졌는지 정밀 비교까지는 무겁기 때문에, extra가 비어있지 않으면 사용으로 기록
    base["_sources_used"].append(source)
    return base


def _browser_chases_synopsis() -> bool:
    """njavtv 브라우저 단계(건당 수 초~수십 초)를 synopsis만 누락일 때도 돌릴지.

    기본 켜짐 — 값싼 소스(123av/missav123/avwiki) 3곳이 다 synopsis를 못 주면
    njavtv까지 가서 채운다(단계별 재시도는 추가하지 않음 — 각 단계는 여전히 1회만
    시도). `JAVSTORY_HARVEST_BROWSER_FOR_SYNOPSIS=0` 으로 예전(title/cover만 있으면
    synopsis 없어도 그냥 저장하는, 더 빠른) 동작으로 되돌릴 수 있다.
    """
    raw = (os.environ.get("JAVSTORY_HARVEST_BROWSER_FOR_SYNOPSIS", "") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    return True


def _needs_fallback(d: dict[str, Any], *, require_synopsis: bool = False) -> bool:
    """title·cover(·synopsis) 중 하나라도 없거나 제목이 리다이렉트 안내 문구일 때 다음 소스 시도.

    기본은 title/cover 만 본다 — synopsis 는 있으면 좋은 선택 필드라, 그것만
    비었다고 다음 소스(특히 수 분짜리 브라우저 단계)로 넘어가지 않는다.
    값싼 HTTP 소스(missav/avwiki)는 호출부에서 `require_synopsis=True` 로
    synopsis·favorite_score 를 계속 보완한다.
    `_merge_empty_only` 가 필드 단위로 빈 값만 채우므로 이미 채워진
    title/cover/actors 등은 다음 소스로 덮어써지지 않는다.
    """
    from javstory.harvest.scrapers.av123_scraper import _is_boilerplate_title

    title = str(d.get("title") or "").strip()
    cover = str(d.get("cover_url") or "").strip()
    synopsis = str(d.get("synopsis") or "").strip()
    if (not title) or (not cover) or title == "제목 없음" or cover == "이미지 누락":
        return True
    if require_synopsis and not synopsis:
        return True
    if _is_boilerplate_title(title):
        return True
    return False


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
    from javstory.utils.actress_profile import dedupe_crawled_actor_tokens

    actresses = dedupe_crawled_actor_tokens(actresses)
    poster = str(getattr(info, "poster_url", "") or "").strip()
    fav = int(getattr(info, "favourite_count", 0) or 0)
    return {
        "title": str(getattr(info, "title", "") or "").strip(),
        "original_title": str(getattr(info, "title_ja", "") or getattr(info, "title", "") or "").strip(),
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
    from javstory.utils.actress_profile import dedupe_crawled_actor_tokens

    actors = dedupe_crawled_actor_tokens(_ensure_list_str(getattr(info, "actresses", None)))
    return {
        "title": str(getattr(info, "title", "") or "").strip(),
        "original_title": str(getattr(info, "title", "") or "").strip(),
        "synopsis": str(getattr(info, "description", "") or "").strip(),
        "cover_url": str(getattr(info, "poster_url", "") or "").strip(),
        "actors": actors,
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
    from javstory.utils.actress_profile import dedupe_crawled_actor_tokens

    actors = dedupe_crawled_actor_tokens(_ensure_list_str(getattr(info, "actresses", None)))
    return {
        "title": str(getattr(info, "title", "") or "").strip(),
        "original_title": str(getattr(info, "title", "") or "").strip(),
        "synopsis": str(getattr(info, "description", "") or "").strip(),
        "cover_url": str(getattr(info, "poster_url", "") or "").strip(),
        "actors": actors,
        "genres": _ensure_list_str(getattr(info, "genres", None)),
        "release_date": str(getattr(info, "release_date", "") or "").strip(),
        "maker": str(getattr(info, "maker", "") or "").strip(),
        "_source": "avwiki_pw" if use_playwright else "avwiki",
    }

def _needs_actress_fallback(d: dict[str, Any]) -> bool:
    """av-wiki.net(5순위, 최종 폴백)을 시도할지 — 배우 식별 전문 사이트라 시놉시스가
    없으므로, synopsis 누락만으로는 트리거하지 않고 배우 정보가 비어있을 때만 시도한다.
    """
    actors = _ensure_list_str(d.get("actors"))
    if not actors:
        return True
    title = str(d.get("title") or "").strip()
    cover = str(d.get("cover_url") or "").strip()
    return (not title) or (not cover)


def _scrape_avwikinet(product_code: str) -> dict[str, Any]:
    if av_wiki_net_scraper is None:
        return {}
    info = av_wiki_net_scraper.fetch_actress_info(product_code)
    from javstory.utils.actress_profile import dedupe_crawled_actor_tokens

    actors = dedupe_crawled_actor_tokens([a for a in (info.actresses or []) if a])
    return {
        # av-wiki.net 제목은 "{작품 요약}...에 출연한 AV여배우는 누구? 이름은?" 형식의
        # 블로그 헤드라인이라 작품 제목으로 부적합 — title/synopsis는 채우지 않음.
        "cover_url": str(info.cover_url or "").strip(),
        "actors": actors,
        "release_date": str(info.release_date or "").strip(),
        "maker": str(info.maker or "").strip(),
        "_source": "avwikinet",
    }


_WIDTH_NORMALIZED_KEYS = ("actors", "genres", "maker")


def _nfkc(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip()


def _normalize_name_width(out: dict[str, Any]) -> None:
    """배우·장르·메이커 표기를 NFKC 로 통일한다(반각 가나 → 전각, 전각 영숫자·괄호 → 반각).

    123av(ja)는 DMM 원문 그대로 `佐野ﾅﾂ`·`中出ｼ`·`ﾀﾞｽｯ!` 같은 반각 가나를 주고 다른 소스는
    전각이라, 정규화하지 않으면 같은 배우/장르/메이커가 DB 에 별도 행으로 갈라진다.
    정규화 후 같아진 항목은 순서를 유지하며 합친다. (대소문자 `OL`/`Ol` 은 건드리지 않음)
    """
    for key in _WIDTH_NORMALIZED_KEYS:
        v = out.get(key)
        if isinstance(v, str):
            out[key] = _nfkc(v)
        elif isinstance(v, list):
            seen: set[str] = set()
            items: list[str] = []
            for x in v:
                n = _nfkc(str(x))
                if n and n not in seen:
                    seen.add(n)
                    items.append(n)
            out[key] = items


def _scrape_njavtv(product_code: str, use_browser: bool = False) -> dict[str, Any]:
    """njavtv 수집 → DB 저장용 dict. 내용이 없으면 {} (상위 `_merge_empty_only` 가 무시)."""
    if njavtv_scraper is None:
        return {}
    raw = njavtv_scraper.fetch_njavtv(product_code, use_browser=use_browser)
    if raw.get("error"):
        log_ts(f"[Hybrid] njavtv({'browser' if use_browser else 'http'}) 실패: {raw['error']}")
    if not _raw_has_any_content(raw):
        return {}
    out = _scrape_dict_for_db(raw, product_code)
    out["_final_url"] = raw.get("final_url")
    return out


class HybridJavCrawler:
    def __init__(self) -> None:
        pass

    async def fetch_metadata_smart(
        self,
        product_code: str,
        *,
        progress_cb: Callable[[str, int], None] | None = None,
    ) -> dict[str, Any]:
        code = product_code.upper()
        out: dict[str, Any] = {"_sources_tried": [], "_sources_used": []}

        def _stage(msg: str, pct: int = 25) -> None:
            log_ts(msg)
            if progress_cb:
                try:
                    progress_cb(msg, pct)
                except Exception:
                    pass

        # 1) 123av
        _stage(f"[Hybrid] 1순위(123av): HTTP 수집 시도: {code}", 26)
        try:
            d = await asyncio.wait_for(asyncio.to_thread(_scrape_123av, code), timeout=60.0)
            out = _merge_empty_only(out, d, source="123av")
        except Exception:
            pass

        # 2) missav123 — 값싼 HTTP라 synopsis·favorite_score 보완까지 계속 시도
        if _needs_fallback(out, require_synopsis=True):
            _stage(f"[Hybrid] 2순위(missav123): HTTP 수집 시도: {code}", 28)
            try:
                d = await asyncio.wait_for(asyncio.to_thread(_scrape_missav123, code), timeout=45.0)
                out = _merge_empty_only(out, d, source="missav123")
            except Exception:
                pass

        # 3) avwiki (아마추어 보루 / 403 시 브라우저) — 값싼 HTTP라 synopsis 도 계속 시도
        if _needs_fallback(out, require_synopsis=True):
            _stage(f"[Hybrid] 3순위(avwiki): HTTP 수집 시도: {code}", 30)
            try:
                d = await asyncio.wait_for(
                    asyncio.to_thread(_scrape_avwiki, code, False), timeout=25.0
                )
                out = _merge_empty_only(out, d, source="avwiki")
            except Exception as e:
                if "403" in str(e):
                    try:
                        _stage(f"[Hybrid] 3순위(avwiki): 403 감지 → 브라우저 우회 시도: {code}", 31)
                        d2 = await asyncio.wait_for(
                            asyncio.to_thread(_scrape_avwiki, code, True), timeout=60.0
                        )
                        out = _merge_empty_only(out, d2, source="avwiki_pw")
                    except Exception:
                        pass

        # 4) njavtv — 서버 렌더링이라 HTTP(Scrapling)로 대부분 끝난다. 값싸므로 synopsis
        #    보완까지 시도. 막히면(Cloudflare 등) 브라우저(StealthyFetcher)로 한 번 더.
        #  - 브라우저 단계는 건당 수 초~수십 초. title/cover 가 이미 있으면(=synopsis 만 누락)
        #    _browser_chases_synopsis() 설정을 따른다.
        if _needs_fallback(out, require_synopsis=True):
            _stage(f"[Hybrid] 4순위(njavtv): HTTP 수집 시도: {code}", 33)
            try:
                d = await asyncio.wait_for(asyncio.to_thread(_scrape_njavtv, code, False), timeout=30.0)
                out = _merge_empty_only(out, d, source="njavtv")
            except Exception:
                pass

        if _needs_fallback(out, require_synopsis=_browser_chases_synopsis()):
            _stage(f"[Hybrid] 4순위(njavtv): 브라우저(Stealth) 수집 시도: {code}", 35)
            try:
                d = await asyncio.wait_for(asyncio.to_thread(_scrape_njavtv, code, True), timeout=100.0)
                out = _merge_empty_only(out, d, source="njavtv_browser")
            except Exception:
                pass

        # 5) av-wiki.net (배우 식별 전문 — 최종 폴백, 시놉시스 없음)
        if _needs_actress_fallback(out):
            _stage(f"[Hybrid] 5순위(av-wiki.net): 배우/커버 보완 시도: {code}", 39)
            try:
                d = await asyncio.wait_for(asyncio.to_thread(_scrape_avwikinet, code), timeout=30.0)
                out = _merge_empty_only(out, d, source="avwikinet")
            except Exception:
                pass

        # 최소 결과 검증: title/synopsis/cover_url 중 하나라도 있어야 성공으로 취급
        if not _raw_has_any_content(out):
            return {}
        out.setdefault("_source", "fallback_chain")
        _normalize_name_width(out)
        if out.get("actors"):
            from javstory.utils.actress_profile import dedupe_crawled_actor_tokens

            out["actors"] = dedupe_crawled_actor_tokens(_ensure_list_str(out.get("actors")))
        return out
