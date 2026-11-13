"""사이트별 수집 포인트 수정 회귀 테스트 (네트워크 없이, 축약 픽스처).

- missav123: missav123.com/ja/{slug} + njavtv 템플릿 파서 공유
- avwikidb: JSON-LD actor 의 남배우(/histrion/) 제외, 자동 요약 description 무시
- av-wiki.net: 직접 주소 우선, 검색 0건 조기 종료, 품번 일치 기사만 선택, lazyload 커버
"""

from __future__ import annotations

import json

from javstory.harvest import fetching
from javstory.harvest.scrapers import av_wiki_net_scraper as wn
from javstory.harvest.scrapers import avwiki
from javstory.harvest.scrapers import missav123_scraper as mv

# ---------------------------------------------------------------- missav123

MISSAV_HTML = """
<html><head><meta property="og:image" content="https://cdn.example/abc-123/cover-n.jpg"></head><body>
<h1 class="text-base text-nord6">ABC-123 テスト作品タイトル</h1>
<div class="mb-1 text-secondary break-all line-clamp-2">本文のあらすじ。</div>
<div class="space-y-2">
  <div class="text-secondary"><span>配信開始日:</span> <time>2026-08-07</time></div>
  <div class="text-secondary"><span>品番:</span> <span class="font-medium">ABC-123</span></div>
  <div class="text-secondary"><span>女優:</span> <a href="/a">女優A</a>, <a href="/b">女優B</a></div>
  <div class="text-secondary"><span>ジャンル:</span> <a href="/g">巨乳</a></div>
  <div class="text-secondary"><span>メーカー:</span> <a href="/ja/makers/m">メーカーM</a></div>
</div></body></html>
"""


def test_missav_uses_com_domain_and_flat_path():
    assert mv.BASE_URL == "https://missav123.com"
    assert mv.VIDEO_PATH_TEMPLATE.format(product_id="abc-123") == "/ja/abc-123"


def test_missav_parse_shares_njav_template_and_strips_code_prefix():
    i = mv.parse_video_html(MISSAV_HTML)
    assert i.code == "ABC-123"
    assert i.title == "テスト作品タイトル"
    assert i.description == "本文のあらすじ。"
    assert i.actresses == ["女優A", "女優B"]
    assert i.genres == ["巨乳"]
    assert i.maker == "メーカーM"
    assert i.release_date == "2026-08-07"
    assert i.poster_url == "https://cdn.example/abc-123/cover-n.jpg"
    assert i.favourite_count == 0


def test_missav_moved_notice_is_not_a_title():
    html = "<html><body><h1>123av.com に移転しました</h1></body></html>"
    assert mv.parse_video_html(html).title == ""


# ---------------------------------------------------------------- avwikidb


def _avwiki_html(actors, *, description, males=()):
    ld = {
        "@context": "https://schema.org",
        "@type": "Movie",
        "name": "ABC-123 作品",
        "description": description,
        "actor": actors,
        "identifier": [{"@type": "PropertyValue", "propertyID": "Code", "value": "ABC-123"}],
    }
    male_dd = "".join(f'<a href="/histrion/{n}/">{n}</a>' for n in males)
    return f"""<html><head><script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script></head>
    <body><dl><dt id="actresses">出演女優</dt><dd><a href="/actor/1/">女優A</a></dd>
    <dt id="histrion">出演男優</dt><dd>{male_dd}</dd></dl></body></html>"""


def test_avwiki_excludes_male_actors_by_url():
    html = _avwiki_html(
        [
            {"@type": "Person", "name": "女優A", "url": "https://avwikidb.com/actor/1/"},
            {"@type": "Person", "name": "女優B", "url": "https://avwikidb.com/actor/2/"},
            {"@type": "Person", "name": "男優X", "url": "https://avwikidb.com/histrion/9/"},
        ],
        description="",
    )
    assert avwiki.parse_work_html(html).actresses == ["女優A", "女優B"]


def test_avwiki_excludes_male_listed_in_body_even_without_url():
    html = _avwiki_html(
        [{"@type": "Person", "name": "女優A"}, {"@type": "Person", "name": "男優Y"}],
        description="",
        males=["男優Y"],
    )
    assert avwiki.parse_work_html(html).actresses == ["女優A"]


def test_avwiki_auto_summary_is_not_synopsis():
    auto = "出演女優 = 女優A｜ABC-123（abc00123） / メーカー / 2026年05月21日配信。画像20枚・一部視聴可。"
    html = _avwiki_html([{"@type": "Person", "name": "女優A"}], description=auto)
    assert avwiki.parse_work_html(html).description == ""


def test_avwiki_real_description_is_kept():
    html = _avwiki_html([{"@type": "Person", "name": "女優A"}], description="兄嫁が誘惑する物語。")
    assert avwiki.parse_work_html(html).description == "兄嫁が誘惑する物語。"


# ---------------------------------------------------------------- av-wiki.net

ARTICLE_HTML = """<html><body><article>
<h1 class="entry-title">作品タイトル<span class="entry-subtitle">メーカーM - {code}</span></h1>
<div class="article-thumbnail"><img class="lazyload" src="data:image/gif;base64,R0lGOD" data-src="https://img.example/{code}.jpg"></div>
<dl class="dltable"><dt>メーカー</dt><dd>メーカーM</dd><dt>AV女優名</dt><dd><a href="/av-actress/a/">女優A</a><a href="/av-actress/b/">女優B</a></dd>
<dt>配信開始日</dt><dd>2026-08-07</dd></dl></article></body></html>"""

SERIES_HTML = """<html><body><h1>AV女優名 by シリーズ</h1><p>ABC-123 ほか</p></body></html>"""

NO_RESULT_HTML = """<html><body><main>検索ワード：xyz-999 0件 検索ワードに一致する記事は見つかりませんでした。
<a href="https://av-wiki.net/fanza-shirouto/">カテゴリ</a></main></body></html>"""

SEARCH_HTML = """<html><body><main>検索ワード：KAVR-146 1件
<article><a href="https://av-wiki.net/mgstage/x/series-id-1/">シリーズ</a>
<a href="https://av-wiki.net/fanza-shirouto/">カテゴリ</a>
<a href="https://av-wiki.net/kavr00146/">続きを読む</a></article></main></body></html>"""


def test_find_article_returns_empty_on_zero_results():
    assert wn.find_article_url(NO_RESULT_HTML, product_id="XYZ-999") == ""


def test_find_article_picks_code_matching_slug_not_series_or_category():
    assert wn.find_article_url(SEARCH_HTML, product_id="KAVR-146") == "https://av-wiki.net/kavr00146/"


def test_find_article_rejects_unrelated_links():
    assert wn.find_article_url(SEARCH_HTML, product_id="ABC-123") == ""


def test_parse_article_prefers_lazyload_data_src():
    i = wn.parse_article_html(ARTICLE_HTML.format(code="ABC-123"))
    assert i.cover_url == "https://img.example/ABC-123.jpg"
    assert i.actresses == ["女優A", "女優B"]
    assert i.code == "ABC-123"


class _Resp:
    def __init__(self, url, status, text):
        self.url, self.status_code, self.text = url, status, text
        self.apparent_encoding = "utf-8"
        self.encoding = None


class _Sess:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url, headers=None, timeout=None):
        self.calls.append(url)
        status, text = self.pages.get(url, (404, ""))
        return _Resp(url, status, text)


def test_fetch_direct_url_hits_in_one_request():
    sess = _Sess({"https://av-wiki.net/abc-123/": (200, ARTICLE_HTML.format(code="ABC-123"))})
    i = wn.fetch_actress_info("ABC-123", session=sess)
    assert sess.calls == ["https://av-wiki.net/abc-123/"]
    assert i.actresses == ["女優A", "女優B"]


def test_fetch_falls_back_to_search_for_nonstandard_slug():
    sess = _Sess(
        {
            "https://av-wiki.net/?s=KAVR-146": (200, SEARCH_HTML),
            "https://av-wiki.net/kavr00146/": (200, ARTICLE_HTML.format(code="KAVR-146")),
        }
    )
    i = wn.fetch_actress_info("KAVR-146", session=sess)
    assert sess.calls[-1] == "https://av-wiki.net/kavr00146/"
    assert i.source_url == "https://av-wiki.net/kavr00146/"
    assert i.actresses == ["女優A", "女優B"]


def test_fetch_rejects_series_page_without_actresses():
    sess = _Sess({"https://av-wiki.net/abc-123/": (200, SERIES_HTML), "https://av-wiki.net/?s=ABC-123": (200, NO_RESULT_HTML)})
    i = wn.fetch_actress_info("ABC-123", session=sess)
    assert i.actresses == []


def test_fetch_rejects_article_for_other_code():
    sess = _Sess(
        {
            "https://av-wiki.net/abc-123/": (200, ARTICLE_HTML.format(code="ZZZ-999")),
            "https://av-wiki.net/?s=ABC-123": (200, NO_RESULT_HTML),
        }
    )
    assert wn.fetch_actress_info("ABC-123", session=sess).actresses == []


def test_session_result_type():
    # 세션 주입 경로가 FetchResult 로 정규화되는지(위 테스트들의 전제)
    res = fetching.http_get("https://av-wiki.net/x/", session=_Sess({}))
    assert (res.status_code, res.via) == (404, "session")


# ---------------------------------------------------------------- 표기 폭 정규화


def test_normalize_name_width_halfwidth_kana_to_fullwidth():
    from javstory.harvest.crawler import _normalize_name_width

    out = {
        "actors": ["佐野ﾅﾂ", "松本ｲﾁｶ", "佐野ナツ", "水谷心音（藤崎りお）"],
        "genres": ["中出ｼ", "ﾍﾞｽﾄ･総集編", "ｱｸﾒ･ｵｰｶﾞｽﾞﾑ", "OL", "Ol"],
        "maker": "ﾀﾞｽｯ!",
        "title": "ﾀｲﾄﾙ",  # 제목은 대상 아님
    }
    _normalize_name_width(out)
    # 정규화 후 같아진 '佐野ナツ' 는 하나로 합쳐짐, 전각 괄호는 반각으로
    assert out["actors"] == ["佐野ナツ", "松本イチカ", "水谷心音(藤崎りお)"]
    # 대소문자(OL/Ol)는 건드리지 않음
    assert out["genres"] == ["中出シ", "ベスト・総集編", "アクメ・オーガズム", "OL", "Ol"]
    assert out["maker"] == "ダスッ!"
    assert out["title"] == "ﾀｲﾄﾙ"


def test_fetch_metadata_smart_normalizes_width(monkeypatch):
    import asyncio

    from javstory.harvest import crawler
    import javstory.utils.actress_profile as ap

    monkeypatch.setattr(ap, "dedupe_crawled_actor_tokens", lambda xs: list(dict.fromkeys(xs)))
    monkeypatch.setattr(
        crawler,
        "_scrape_123av",
        lambda code: {
            "title": "作品", "synopsis": "あらすじ", "cover_url": "https://img.example/c.jpg",
            "actors": ["佐野ﾅﾂ"], "genres": ["中出ｼ"], "maker": "ﾀﾞｽｯ!", "_source": "123av",
        },
    )
    monkeypatch.setattr(crawler, "_scrape_avwikinet", lambda code: {})
    out = asyncio.run(crawler.HybridJavCrawler().fetch_metadata_smart("ABC-123"))
    assert out["actors"] == ["佐野ナツ"]
    assert out["genres"] == ["中出シ"]
    assert out["maker"] == "ダスッ!"


# ---------------------------------------------------------------- 다른 판본으로 넘어가지 않기


def _flaky_get(errors_for, pages):
    calls: list[str] = []

    def _get(url, **kw):
        calls.append(url)
        if url in errors_for:
            raise ConnectionResetError(10054, "reset")
        status, text = pages.get(url, (404, ""))
        return fetching.FetchResult(url=url, status_code=status, text=text, via="scrapling")

    return _get, calls


def test_missav_transport_error_does_not_fall_through_to_leaked_variant(monkeypatch):
    import pytest

    leaked = "https://missav123.com/ja/abc-123-uncensored-leaked"
    get, calls = _flaky_get({"https://missav123.com/ja/abc-123"}, {leaked: (200, MISSAV_HTML)})
    monkeypatch.setattr(mv, "http_get", get)
    with pytest.raises(ConnectionResetError):
        mv.fetch_video_info("ABC-123")
    assert leaked not in calls


def test_missav_404_does_try_next_variant_and_records_url(monkeypatch):
    leaked = "https://missav123.com/ja/abc-123-uncensored-leaked"
    get, calls = _flaky_get(set(), {leaked: (200, MISSAV_HTML)})
    monkeypatch.setattr(mv, "http_get", get)
    i = mv.fetch_video_info("ABC-123")
    assert calls[:2] == ["https://missav123.com/ja/abc-123", leaked]
    assert i.source_url == leaked


def test_123av_transport_error_does_not_fall_through(monkeypatch):
    import pytest
    from javstory.harvest.scrapers import av123_scraper as a

    base = "https://123av.com"
    errs = {f"{base}/ja/v/abc-123", f"{base}/ko/v/abc-123"}
    get, calls = _flaky_get(errs, {})
    monkeypatch.setattr(a, "http_get", get)
    with pytest.raises(ConnectionResetError):
        a.fetch_video_info("ABC-123")
    assert not any("uncensored" in c for c in calls)


# ---------------------------------------------------------------- 123av 좋아요 수


def _save_button(count_attr: str, label: str) -> str:
    xdata = f"save({{ type: 'title', id: 1, preload: true, {count_attr} saveLabel: '保存' }})" if count_attr else ""
    attr = f' x-data="{xdata}"' if xdata else ""
    return f'<html><body><button class="watch__save" type="button"{attr}><span x-text="followLabel">{label}</span></button></body></html>'


def test_123av_favourite_reads_exact_count_over_1000():
    from bs4 import BeautifulSoup
    from javstory.harvest.scrapers import av123_scraper as a

    soup = BeautifulSoup(_save_button("count: 1716,", "1.7K"), "lxml")
    assert a._favourite_count_from_soup(soup) == 1716


def test_123av_favourite_falls_back_to_abbreviated_label():
    from bs4 import BeautifulSoup
    from javstory.harvest.scrapers import av123_scraper as a

    assert a._favourite_count_from_soup(BeautifulSoup(_save_button("", "1.7K"), "lxml")) == 1700
    assert a._favourite_count_from_soup(BeautifulSoup(_save_button("", "77"), "lxml")) == 77
    assert a._favourite_count_from_soup(BeautifulSoup(_save_button("", "1,234"), "lxml")) == 1234


def test_parse_count_label_variants():
    from javstory.harvest.scrapers import av123_scraper as a

    assert [a._parse_count_label(x) for x in ("0", "999", "1.7K", "12k", "2.3M", "1.2万", "x", "")] == [
        0, 999, 1700, 12000, 2300000, 12000, None, None,
    ]
