from javstory.harvest.scrapers.av123_scraper import parse_video_html

WATCH_LAYOUT_HTML = """
<html><body>
<h1 class="watch__title">DLDSS-520 — sample title</h1>
<section class="watch__block">
  <h2 class="watch__bhead">詳細</h2>
  <div class="watch__desc">
    <p class="watch__desc-text">「もう許してくれ…。」不在票の話。</p>
    <button class="watch__more" type="button"><span>もっと見る</span></button>
  </div>
</section>
</body></html>
"""

LEGACY_LAYOUT_HTML = """
<html><body>
<div id="details">
  <div class="description short"><p>레거시 시놉시스 본문</p></div>
</div>
</body></html>
"""


def test_parse_video_html_watch_layout_description():
    info = parse_video_html(WATCH_LAYOUT_HTML, locale="ja")
    assert info.description == "「もう許してくれ…。」不在票の話。"
    assert "もっと見る" not in info.description


def test_parse_video_html_legacy_description():
    info = parse_video_html(LEGACY_LAYOUT_HTML, locale="ja")
    assert info.description == "레거시 시놉시스 본문"
