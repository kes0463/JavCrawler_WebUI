"""njavtv HTML 파서 / fetch_njavtv 흐름 (네트워크 없이)."""

from __future__ import annotations

from javstory.harvest import fetching
from javstory.harvest.scrapers import njavtv_scraper as nj

# 실제 njavtv 상세 페이지의 메타 영역 구조를 축약한 픽스처
DETAIL_HTML = """
<html><head>
<title>ABC-123 テスト作品 - 女優A</title>
<meta property="og:image" content="https://cdn.example/abc-123/cover-n.jpg">
<meta property="og:title" content="ABC-123 テスト作品 - 女優A">
<meta name="description" content="ヘッドの説明文">
<meta property="og:video:actor" content="女優A">
</head><body>
<h1 class="text-base text-nord6">ABC-123 テスト作品 - 女優A</h1>
<div class="mb-1 text-secondary break-all line-clamp-2">
  本文のあらすじです。女優: という単語が入っていても行として扱わない。
</div>
<div class="space-y-2">
  <div class="text-secondary"><span>配信開始日:</span> <time datetime="2025-10-24">2025-10-24</time></div>
  <div class="text-secondary"><span>品番:</span> <span class="font-medium">ABC-123</span></div>
  <div class="text-secondary"><span>女優:</span> <a href="/ja/actresses/a">女優A</a>, <a href="/ja/actresses/b">女優B</a>, <a href="/ja/actresses/a">女優A</a></div>
  <div class="text-secondary"><span>ジャンル:</span> <a href="/g/1">美少女</a>, <a href="/g/2">ハイビジョン</a></div>
  <div class="text-secondary"><span>メーカー:</span> <a href="/ja/makers/x">メーカーX</a></div>
  <div class="text-secondary"><span>監督:</span> <a href="/ja/directors/d">監督D</a></div>
  <div class="text-secondary"><span>レーベル:</span> <a href="/ja/labels/l">レーベルL</a></div>
</div>
</body></html>
"""


def test_parse_body_fields():
    d = nj.parse_njav_html(DETAIL_HTML)
    assert d["title"] == "ABC-123 テスト作品 - 女優A"
    assert d["synopsis"].startswith("本文のあらすじ")
    assert d["release_date"] == "2025-10-24"
    assert d["product_code"] == "ABC-123"
    assert d["actors"] == ["女優A", "女優B"]  # 중복 제거, 시놉시스 속 '女優:' 무시
    assert d["genres"] == ["美少女", "ハイビジョン"]
    assert d["maker"] == "メーカーX"
    assert d["director"] == "監督D"
    assert d["label"] == "レーベルL"
    # 본문에 커버가 없으면 og:image 로 채움
    assert d["cover_url"] == "https://cdn.example/abc-123/cover-n.jpg"


def test_body_cover_style_wins_over_og_image():
    html = DETAIL_HTML.replace(
        "<h1", '<div class="plyr__poster" style="background-image: url(&quot;https://cdn.example/p.jpg&quot;);"></div><h1'
    )
    assert nj.parse_njav_html(html)["cover_url"] == "https://cdn.example/p.jpg"


def test_head_meta_fills_only_missing():
    html = """<html><head><meta property="og:title" content="XYZ-001 作品">
    <meta name="description" content="説明"><meta property="og:video:actor" content="女優Z">
    <meta property="og:video:release_date" content="2024-01-02"></head><body></body></html>"""
    d = nj.parse_njav_html(html)
    assert d == {
        "title": "XYZ-001 作品",
        "synopsis": "説明",
        "actors": ["女優Z"],
        "release_date": "2024-01-02",
    }


def test_challenge_title_is_not_used():
    html = "<html><head><title>Just a moment...</title></head><body><h1>Just a moment...</h1></body></html>"
    assert "title" not in nj.parse_njav_html(html)


def test_detail_urls():
    assert nj.njavtv_detail_urls("ABC_123") == [
        "https://njavtv.com/ja/abc-123",
        "https://njavtv.com/ja/abc-123-uncensored-leaked",
    ]
    assert nj.njavtv_detail_urls("abc-123-uncensored-leaked") == [
        "https://njavtv.com/ja/abc-123-uncensored-leaked"
    ]
    assert nj.njavtv_detail_urls("  ") == []


def _fake_get(responses):
    calls: list[str] = []

    def _get(url, **kw):
        calls.append(url)
        status, text = responses[len(calls) - 1]
        return fetching.FetchResult(url=url, status_code=status, text=text, via="scrapling")

    return _get, calls


def test_fetch_404_tries_uncensored_slug(monkeypatch):
    get, calls = _fake_get([(404, ""), (200, DETAIL_HTML)])
    monkeypatch.setattr(nj, "http_get", get)
    d = nj.fetch_njavtv("ABC-123")
    assert calls[1].endswith("-uncensored-leaked")
    assert d["final_url"] == calls[1]
    assert d["title"].startswith("ABC-123")
    assert "error" not in d


def test_fetch_all_404(monkeypatch):
    get, _ = _fake_get([(404, ""), (404, "")])
    monkeypatch.setattr(nj, "http_get", get)
    assert nj.fetch_njavtv("ABC-123")["error"].startswith("404")


def test_fetch_challenge_reports_blocked(monkeypatch):
    get, _ = _fake_get([(403, "<html><title>Just a moment...</title></html>")])
    monkeypatch.setattr(nj, "http_get", get)
    d = nj.fetch_njavtv("ABC-123")
    assert d["error"].startswith("blocked")
    assert "title" not in d


def test_fetch_browser_mode_uses_browser_get(monkeypatch):
    seen = {}

    def _browser(url, **kw):
        seen.update(kw)
        return fetching.FetchResult(url=url, status_code=200, text=DETAIL_HTML, via="browser")

    monkeypatch.setattr(nj, "browser_get", _browser)
    monkeypatch.setattr(nj, "http_get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("http used")))
    d = nj.fetch_njavtv("ABC-123", use_browser=True)
    assert d["via"] == "browser"
    assert seen["page_action"] is nj._page_action
    assert seen["solve_cloudflare"] is True


def test_crawler_njavtv_stage_maps_to_db_dict(monkeypatch):
    from javstory.harvest import crawler
    import javstory.utils.actress_profile as ap

    monkeypatch.setattr(ap, "dedupe_crawled_actor_tokens", lambda xs: list(dict.fromkeys(xs)))
    get, _ = _fake_get([(200, DETAIL_HTML)])
    monkeypatch.setattr(nj, "http_get", get)
    d = crawler._scrape_njavtv("ABC-123", False)
    assert d["title"].startswith("ABC-123")
    assert d["actors"] == ["女優A", "女優B"]
    assert d["maker"] == "メーカーX"
    assert d["_final_url"] == "https://njavtv.com/ja/abc-123"

    get, _ = _fake_get([(404, ""), (404, "")])
    monkeypatch.setattr(nj, "http_get", get)
    assert crawler._scrape_njavtv("ABC-123", False) == {}
