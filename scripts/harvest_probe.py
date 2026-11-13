"""Harvest 수집 점검 도구 — 품번을 넣으면 사이트별 수집 결과를 나란히 보여준다.

사용:
    harvest_probe.bat                  (대화형: 품번 입력, 빈 줄이면 종료)
    harvest_probe.bat SNOS-334 SW-1051 (인자로 여러 개)
    harvest_probe.bat SNOS-334 --full  (사이트별 결과 + 실제 하베스트 병합 결과)
    harvest_probe.bat SNOS-334 --no-browser  (브라우저 단계 생략, 빠른 확인용)

- 사이트별 결과는 각 스크레이퍼를 직접 호출한 것이라 DB 를 쓰지 않는다(읽기/쓰기 없음).
- `--full` 은 실제 하베스트 순서(fetch_metadata_smart)로 병합한 결과다. DB 에 쓰지는 않지만
  배우명 정리 단계가 DB(배우 별명)를 읽는다. DB 가 없으면 단순 중복 제거로 대신한다.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

SYN_PREVIEW = 120
LIST_PREVIEW = 12


# ---------------------------------------------------------------- 사이트별 수집


def _site_123av(code: str, browser: bool) -> dict[str, Any]:
    from javstory.harvest.scrapers import av123_scraper as m

    i = m.fetch_video_info(code)
    return {
        "url": f"{m.BASE_URL}/ja/v/{code.lower()}",
        "code": i.code,
        "title": i.title,
        "title_ja": i.title_ja,
        "synopsis": i.description,
        "cover": i.poster_url,
        "actors": [a.get("name", "") if isinstance(a, dict) else str(a) for a in (i.actresses or [])],
        "genres": list(i.genres or []),
        "maker": i.maker,
        "release_date": i.release_date,
        "favourite": i.favourite_count,
    }


def _site_missav(code: str, browser: bool) -> dict[str, Any]:
    from javstory.harvest.scrapers import missav123_scraper as m

    i = m.fetch_video_info(code)
    return {
        "url": i.source_url,
        "code": i.code,
        "title": i.title,
        "synopsis": i.description,
        "cover": i.poster_url,
        "actors": list(i.actresses or []),
        "genres": list(i.genres or []),
        "maker": i.maker,
        "release_date": i.release_date,
    }


def _site_avwiki(code: str, browser: bool) -> dict[str, Any]:
    from javstory.harvest.scrapers import avwiki as m

    via = "http"
    try:
        i = m.fetch_work_info(code)
    except Exception as e:
        if not (browser and "403" in str(e)):
            raise
        via = "browser (403 우회)"
        i = m.fetch_work_info(code, use_playwright=True)
    return {
        "url": m.BASE_URL.rstrip("/") + m.WORK_PATH_TEMPLATE.format(product_id=code),
        "via": via,
        "code": i.code,
        "title": i.title,
        "synopsis": i.description,
        "cover": i.poster_url,
        "actors": list(i.actresses or []),
        "genres": list(i.genres or []),
        "maker": i.maker,
        "release_date": i.release_date,
    }


def _site_njav(code: str, browser: bool) -> dict[str, Any]:
    from javstory.harvest.scrapers import njavtv_scraper as m

    d = m.fetch_njavtv(code)
    note = ""
    if (d.get("error") or not d.get("title")) and browser:
        note = f"HTTP 실패({d.get('error') or '내용 없음'}) → 브라우저 재시도"
        d = m.fetch_njavtv(code, use_browser=True)
    if d.get("error") and not d.get("title"):
        raise RuntimeError(d["error"] + (f" / {note}" if note else ""))
    return {
        "url": d.get("final_url") or "",
        "via": d.get("via", "") + (f"  ({note})" if note else ""),
        "code": d.get("product_code", ""),
        "title": d.get("title", ""),
        "synopsis": d.get("synopsis", ""),
        "cover": d.get("cover_url", ""),
        "actors": list(d.get("actors") or []),
        "genres": list(d.get("genres") or []),
        "maker": d.get("maker", ""),
        "release_date": d.get("release_date", ""),
        "director": d.get("director", ""),
        "label": d.get("label", ""),
    }


def _site_avwikinet(code: str, browser: bool) -> dict[str, Any]:
    from javstory.harvest.scrapers import av_wiki_net_scraper as m

    i = m.fetch_actress_info(code)
    return {
        "url": i.source_url,
        "code": i.code,
        "title": i.title,
        "cover": i.cover_url,
        "actors": list(i.actresses or []),
        "maker": i.maker,
        "label": i.label,
        "release_date": i.release_date,
    }


SITES: list[tuple[str, Callable[[str, bool], dict[str, Any]]]] = [
    ("1. 123av", _site_123av),
    ("2. missav123", _site_missav),
    ("3. avwikidb", _site_avwiki),
    ("4. njavtv", _site_njav),
    ("5. av-wiki.net", _site_avwikinet),
]


# ---------------------------------------------------------------- 출력

FIELDS = [
    ("code", "품번"),
    ("title", "제목"),
    ("title_ja", "제목(ja)"),
    ("synopsis", "시놉시스"),
    ("cover", "커버"),
    ("actors", "배우"),
    ("genres", "장르"),
    ("maker", "메이커"),
    ("label", "레이블"),
    ("director", "감독"),
    ("release_date", "발매일"),
    ("favourite", "좋아요"),
]


def _pad(text: str, width: int) -> str:
    """한글·일본어(2칸 폭)를 감안해 왼쪽 정렬."""
    w = sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)
    return text + " " * max(0, width - w)


def _fmt(key: str, v: Any) -> str:
    if isinstance(v, list):
        if not v:
            return "(없음)"
        shown = ", ".join(str(x) for x in v[:LIST_PREVIEW])
        more = f" … 외 {len(v) - LIST_PREVIEW}" if len(v) > LIST_PREVIEW else ""
        return f"[{len(v)}] {shown}{more}"
    s = str(v if v is not None else "").strip()
    if not s:
        return "(없음)"
    s = s.replace("\r", " ").replace("\n", " ")
    if key == "synopsis" and len(s) > SYN_PREVIEW:
        return f"{s[:SYN_PREVIEW]}… ({len(s)}자)"
    return s


def _print_site(name: str, result: dict[str, Any] | None, err: str | None, secs: float) -> None:
    status = "OK" if result is not None else "실패"
    print(f"\n── {name}  [{status}, {secs:.1f}s]")
    if err:
        print(f"   오류: {err}")
        return
    assert result is not None
    if result.get("url"):
        print(f"   {_pad('URL', 9)}: {result['url']}")
    if result.get("via"):
        print(f"   {_pad('경로', 9)}: {result['via']}")
    for key, label in FIELDS:
        if key in result:
            print(f"   {_pad(label, 9)}: {_fmt(key, result[key])}")


def _run_site(fn: Callable[[str, bool], dict[str, Any]], code: str, browser: bool):
    t = time.time()
    try:
        return fn(code, browser), None, time.time() - t
    except Exception as e:
        msg = f"{type(e).__name__}: {e}".splitlines()[0]
        return None, msg[:300], time.time() - t


def _summary(code: str, results: dict[str, Any]) -> None:
    print(f"\n── 요약 ({code})")
    print("   " + "".join(_pad(h, w) for h, w in (('사이트', 16), ('제목', 6), ('시놉', 6), ('커버', 6), ('배우', 6), ('장르', 6))))
    for name, (res, err, _) in results.items():
        if res is None:
            print(f"   {_pad(name, 16)}실패")
            continue

        def mark(k: str) -> str:
            v = res.get(k)
            if k not in res:
                return "-"
            if isinstance(v, list):
                return str(len(v)) if v else "x"
            return "O" if str(v or "").strip() else "x"

        print(f"   {_pad(name, 16)}{mark('title'):<6}{mark('synopsis'):<6}{mark('cover'):<6}{mark('actors'):<6}{mark('genres'):<6}")
    print("   (O=있음, x=없음, 숫자=개수, -=이 사이트엔 없는 항목)")


def _full_chain(code: str) -> None:
    import javstory.utils.actress_profile as ap

    orig = ap.dedupe_crawled_actor_tokens

    def _safe(xs):
        try:
            return orig(xs)
        except Exception:
            return list(dict.fromkeys(x for x in xs if x))

    ap.dedupe_crawled_actor_tokens = _safe
    from javstory.harvest.crawler import HybridJavCrawler

    print(f"\n══ 실제 하베스트 병합 결과 ({code})")
    t = time.time()
    out = asyncio.run(HybridJavCrawler().fetch_metadata_smart(code))
    print(f"   {_pad('소요', 9)}: {time.time() - t:.1f}s")
    if not out:
        print("   결과 없음 (모든 소스 실패)")
        return
    print(f"   {_pad('사용 소스', 9)}: {', '.join(out.get('_sources_used') or [])}")
    for key, label in [
        ("title", "제목"), ("original_title", "원제"), ("synopsis", "시놉시스"), ("cover_url", "커버"),
        ("actors", "배우"), ("genres", "장르"), ("maker", "메이커"), ("release_date", "발매일"),
        ("favorite_score", "좋아요합"),
    ]:
        print(f"   {_pad(label, 9)}: {_fmt(key, out.get(key))}")


def probe(code: str, *, browser: bool, full: bool) -> None:
    code = code.strip().upper()
    print("\n" + "═" * 72)
    print(f" 품번 {code}  (브라우저 단계: {'사용' if browser else '생략'})")
    print("═" * 72)
    t = time.time()
    with ThreadPoolExecutor(max_workers=len(SITES)) as ex:
        futs = {name: ex.submit(_run_site, fn, code, browser) for name, fn in SITES}
        results = {name: f.result() for name, f in futs.items()}
    for name, (res, err, secs) in results.items():
        _print_site(name, res, err, secs)
    _summary(code, results)
    print(f"\n   전체 {time.time() - t:.1f}s (사이트 동시 조회)")
    if full:
        _full_chain(code)


def main() -> int:
    ap = argparse.ArgumentParser(description="사이트별 하베스트 수집 결과 점검")
    ap.add_argument("codes", nargs="*", help="품번 (없으면 대화형 입력)")
    ap.add_argument("--full", action="store_true", help="실제 하베스트 병합 결과도 표시")
    ap.add_argument("--no-browser", action="store_true", help="브라우저(Stealth) 단계 생략")
    ap.add_argument("--log", action="store_true", help="Scrapling 내부 로그 표시")
    args = ap.parse_args()
    if args.log:
        os.environ["JAVSTORY_SCRAPLING_LOG"] = "1"
    browser = not args.no_browser
    if not browser:
        os.environ["JAVSTORY_HARVEST_BROWSER_ON_RESET"] = "0"

    if args.codes:
        for c in args.codes:
            probe(c, browser=browser, full=args.full)
        return 0

    print("Harvest 수집 점검 — 품번을 입력하세요 (예: SNOS-334). 빈 줄 또는 q 로 종료.")
    print("  품번 뒤에 ' full' 을 붙이면 실제 하베스트 병합 결과도 표시합니다 (예: SNOS-334 full)")
    while True:
        try:
            line = input("\n품번> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line or line.lower() in ("q", "quit", "exit"):
            break
        parts = line.split()
        full = args.full or any(p.lower() in ("full", "--full") for p in parts[1:])
        try:
            probe(parts[0], browser=browser, full=full)
        except KeyboardInterrupt:
            print("\n(중단)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
