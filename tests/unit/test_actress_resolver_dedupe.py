"""Actress / genre dedupe during harvest resolve."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from javstory.utils.actress_profile import normalize_actor_name_key
from javstory.utils.actress_resolver import ActressResolver, collapse_actor_name_lists
from javstory.utils.common import dedupe_preserve_order, tagify


def test_normalize_actor_key_nfkc_without_kana_unify():
    """가·히라 통일 없음 — DB 별명·합치기로 동일인 처리."""
    assert normalize_actor_name_key("蜜コノハ") != normalize_actor_name_key("蜜このは")
    assert normalize_actor_name_key("佐野ﾅﾂ") == normalize_actor_name_key("佐野ナツ")


def test_dedupe_preserve_order_casefold():
    assert dedupe_preserve_order(["거유", "거유", "슬렌더"]) == ["거유", "슬렌더"]


def test_tagify_dedupes_list():
    assert tagify(["미츠 코노하", "미츠 코노하"]) == "미츠 코노하"


def test_resolve_names_merges_hangul_and_ja_crawl():
    resolver = ActressResolver()
    row = MagicMock()
    row.id = 42
    row.name_ja = "蜜コノハ"
    row.japanese = "蜜コノハ"
    row.name_ko = "미츠 코노하"
    row.korean = "미츠 코노하"
    row.name_en = ""
    row.romaji = "Mitsu Konoha"

    session = MagicMock()
    session.query.return_value.filter_by.return_value.first.return_value = row

    def _resolve(session, name, *, name_index):
        if name in ("蜜このは", "蜜コノハ", "미츠 코노하"):
            return row, 42
        return None, None

    with patch("javstory.utils.actress_resolver.get_db_session", return_value=session):
        with patch(
            "javstory.utils.actress_resolver._build_actress_name_index",
            return_value={normalize_actor_name_key("蜜このは"): [42]},
        ):
            with patch(
                "javstory.utils.actress_resolver._resolve_actress_row_in_session",
                side_effect=_resolve,
            ):
                with patch("javstory.utils.actress_resolver.commit_with_retry"):
                    result = resolver.resolve_names(["미츠 코노하", "蜜このは"])

    assert result["ko"] == ["미츠 코노하"]
    assert result["ja"] == ["蜜コノハ"]


def test_resolve_names_links_deferred_ja_when_only_hangul_resolved():
    resolver = ActressResolver()
    row = MagicMock()
    row.id = 42
    row.name_ja = ""
    row.japanese = ""
    row.name_ko = "미츠 코노하"
    row.korean = "미츠 코노하"
    row.name_en = ""
    row.romaji = ""

    session = MagicMock()
    session.query.return_value.filter_by.return_value.first.return_value = row

    def _resolve(session, name, *, name_index):
        if name == "미츠 코노하":
            return row, 42
        return None, None

    with patch("javstory.utils.actress_resolver.get_db_session", return_value=session):
        with patch(
            "javstory.utils.actress_resolver._build_actress_name_index",
            return_value={},
        ):
            with patch(
                "javstory.utils.actress_resolver._resolve_actress_row_in_session",
                side_effect=_resolve,
            ):
                with patch("javstory.utils.actress_resolver.commit_with_retry"):
                    with patch(
                        "javstory.utils.actress_resolver._link_ja_crawl_to_seen_actress",
                        return_value=row,
                    ) as link_mock:
                        result = resolver.resolve_names(["미츠 코노하", "蜜このは"])

    link_mock.assert_called_once()
    assert result["ko"] == ["미츠 코노하"]


def test_collapse_actor_ko_drops_ja_fallback_when_hangul_exists():
    ja, ko, ro = collapse_actor_name_lists(
        ["蜜このは", "蜜このは"],
        ["미츠 코노하", "蜜このは"],
        ["Mitsu Konoha", "蜜このは"],
    )
    assert ko == ["미츠 코노하"]
    assert ja == ["蜜このは"]


def test_dedupe_crawled_actor_names_merges_hangul_and_ja(monkeypatch):
    from javstory.utils.actress_resolver import dedupe_crawled_actor_names

    fake_row = MagicMock(
        id=7,
        name_ja="蜜コノハ",
        japanese="蜜コノハ",
        name_ko="미츠 코노하",
        korean="미츠 코노하",
    )
    session = MagicMock()
    session.query.return_value.filter_by.return_value.first.return_value = fake_row

    def _resolve(_session, name):
        if name in ("미츠 코노하", "蜜このは"):
            return 7
        return None

    monkeypatch.setattr(
        "javstory.utils.actress_profile._build_actress_name_index",
        lambda _s: {},
    )
    monkeypatch.setattr(
        "javstory.utils.actress_profile._resolve_actress_id_in_session",
        _resolve,
    )

    out = dedupe_crawled_actor_names(session, ["미츠 코노하", "蜜このは"])
    assert out == ["미츠 코노하"]


def test_collapse_actor_keeps_ja_when_no_hangul_profile():
    ja, ko, ro = collapse_actor_name_lists(
        ["蜜コノハ", "三上悠亜"],
        ["蜜コノハ", "三上悠亜"],
        ["蜜コノハ", "三上悠亜"],
    )
    assert ko == ["蜜コノハ", "三上悠亜"]
    assert len(ja) == 2


def test_dedupe_crawled_keeps_two_different_actresses(monkeypatch):
    from javstory.utils.actress_resolver import dedupe_crawled_actor_names

    rows = {
        1: MagicMock(
            id=1, name_ja="三上悠亜", japanese="三上悠亜", name_ko="", korean=""
        ),
        2: MagicMock(
            id=2, name_ja="白石茉莉奈", japanese="白石茉莉奈", name_ko="", korean=""
        ),
    }
    session = MagicMock()

    def _resolve(_session, name):
        if name == "三上悠亜":
            return 1
        if name == "白石茉莉奈":
            return 2
        return None

    def _query(_model):
        q = MagicMock()

        def _filter_by(**kw):
            f = MagicMock()
            f.first = lambda: rows.get(int(kw.get("id") or 0))
            return f

        q.filter_by = _filter_by
        return q

    session.query = _query

    monkeypatch.setattr(
        "javstory.utils.actress_profile._build_actress_name_index",
        lambda _s: {},
    )
    monkeypatch.setattr(
        "javstory.utils.actress_profile._resolve_actress_id_in_session",
        _resolve,
    )

    out = dedupe_crawled_actor_names(session, ["三上悠亜", "白石茉莉奈"])
    assert out == ["三上悠亜", "白石茉莉奈"]


def test_resolve_names_keeps_two_different_actresses():
    resolver = ActressResolver()

    def _make_row(aid, ja, ko):
        row = MagicMock()
        row.id = aid
        row.name_ja = ja
        row.japanese = ja
        row.name_ko = ko
        row.korean = ko
        row.name_en = ""
        row.romaji = ""
        return row

    row1 = _make_row(1, "三上悠亜", "미카미 유아")
    row2 = _make_row(2, "白石茉莉奈", "시라이시 마리나")
    session = MagicMock()
    session.query.return_value.filter_by.return_value.first.side_effect = lambda: row1

    def _resolve(session, name, *, name_index):
        if name in ("三上悠亜", "미카미 유아"):
            return row1, 1
        if name in ("白石茉莉奈", "시라이시 마리나"):
            return row2, 2
        return None, None

    with patch("javstory.utils.actress_resolver.get_db_session", return_value=session):
        with patch(
            "javstory.utils.actress_resolver._build_actress_name_index",
            return_value={},
        ):
            with patch(
                "javstory.utils.actress_resolver._resolve_actress_row_in_session",
                side_effect=_resolve,
            ):
                with patch("javstory.utils.actress_resolver.commit_with_retry"):
                    result = resolver.resolve_names(["三上悠亜", "白石茉莉奈"])

    assert len(result["ko"]) == 2
    assert result["ko"] == ["미카미 유아", "시라이시 마리나"]


def test_merge_locale_actresses_unions_by_href():
    from javstory.harvest.scrapers.av123_scraper import VideoInfo, _merge_locale_pages

    info_ja = VideoInfo(
        code="STARS-001",
        actresses=[
            {"name": "蜜このは", "href": "/ja/actresses/mitsu-konoha"},
            {"name": "三上悠亜", "href": "/ja/actresses/yua-mikami"},
        ],
    )
    info_ko = VideoInfo(
        title="테스트",
        actresses=[
            {"name": "미츠 코노하", "href": "/ko/actresses/mitsu-konoha"},
        ],
    )
    merged = _merge_locale_pages(info_ja, info_ko)
    names = [a["name"] for a in merged.actresses]
    assert len(names) == 2
    assert "미츠 코노하" in names
    assert "三上悠亜" in names
    assert "蜜このは" not in names


def test_dedupe_crawled_actor_tokens_uses_db_profile(monkeypatch):
    from javstory.utils.actress_profile import dedupe_crawled_actor_tokens

    class FakeRow:
        id = 42
        name_ja = "蜜コノハ"
        japanese = "蜜コノハ"
        name_ko = "미츠 코노하"
        korean = "미츠 코노하"

    session = MagicMock()
    session.query.return_value.filter_by.return_value.first.return_value = FakeRow()

    def _resolve(_session, name):
        if name in ("蜜コノハ", "蜜このは", "미츠 코노하"):
            return 42
        return None

    monkeypatch.setattr(
        "javstory.utils.actress_profile._resolve_actress_id_in_session",
        _resolve,
    )
    monkeypatch.setattr(
        "javstory.utils.actress_profile._build_actress_name_index",
        lambda _s: {},
    )

    assert dedupe_crawled_actor_tokens(["蜜コノハ", "蜜このは"], session=session) == ["蜜コノハ"]
    assert dedupe_crawled_actor_tokens(["미츠 코노하", "蜜このは"], session=session) == ["미츠 코노하"]
    out = dedupe_crawled_actor_tokens(
        ["佐野ﾅﾂ", "佐野ナツ", "水谷心音(藤崎ﾘｵ)", "水谷心音", "Aika", "AIKA"],
        session=session,
    )
    assert out == ["佐野ﾅﾂ", "水谷心音", "Aika"]


def test_resolve_genres_dedupes_ko(monkeypatch):
    from javstory.harvest.coordinator import _resolve_genres

    class FakeGenre:
        def __init__(self, japanese, korean, english=None):
            self.japanese = japanese
            self.korean = korean
            self.english = english

    rows = {
        "巨乳": FakeGenre("巨乳", "거유"),
        "スレンダー": FakeGenre("スレンダー", "슬렌더"),
    }

    class FakeSession:
        def query(self, _model):
            return self

        def filter_by(self, **kwargs):
            self._key = kwargs.get("japanese")
            return self

        def first(self):
            return rows.get(self._key)

        def add(self, _obj):
            return None

        def commit(self):
            return None

        def rollback(self):
            return None

    class FakeCtx:
        def __enter__(self):
            return FakeSession()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("javstory.harvest.coordinator.get_db_session_ctx", lambda: FakeCtx())
    monkeypatch.setattr("javstory.harvest.coordinator.commit_with_retry", lambda _s: None)

    resolved = _resolve_genres(["巨乳", "巨乳", "スレンダー", "スレンダー"])
    assert resolved["ko"] == ["거유", "슬렌더"]
