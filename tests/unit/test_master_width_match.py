"""genres/makers 마스터 대조 — 크롤러의 NFKC 정규화 후에도 반각으로 저장된 기존 행(번역 포함)을 찾는지."""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from javstory.harvest import coordinator
from javstory.harvest.database import Genre, Maker


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Genre.__table__.create(engine)
    Maker.__table__.create(engine)
    Session = sessionmaker(bind=engine)

    @contextmanager
    def _ctx():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    monkeypatch.setattr(coordinator, "get_db_session_ctx", _ctx)
    monkeypatch.setattr(coordinator, "commit_with_retry", lambda s: s.commit())
    with _ctx() as s:
        s.add_all(
            [
                Genre(japanese="中出ｼ", korean="질내사정", english="Creampie", needs_review=False),
                Genre(japanese="ｱｸﾒ･ｵｰｶﾞｽﾞﾑ", korean=None, english=None, needs_review=True),
                Genre(japanese="アクメ・オーガズム", korean="절정", english="Orgasm", needs_review=False),
                Maker(japanese="ﾀﾞｽｯ!", korean="다스!", english="Dasu", slug="dasu", needs_review=False),
            ]
        )
        s.commit()
    return _ctx


def _count(ctx, model):
    with ctx() as s:
        return s.query(model).count()


def test_fullwidth_genre_maps_to_existing_halfwidth_row(db):
    out = coordinator._resolve_genres(["中出シ"])
    assert out["ko"] == ["질내사정"]
    assert out["en"] == ["Creampie"]
    assert _count(db, Genre) == 3  # 새 pending 행 안 생김


def test_prefers_translated_row_among_width_variants(db):
    out = coordinator._resolve_genres(["アクメ・オーガズム", "ｱｸﾒ･ｵｰｶﾞｽﾞﾑ"])
    assert out["ko"] == ["절정"]  # 같은 장르 두 표기 → 번역 있는 행 하나로


def test_unknown_genre_still_creates_pending_row(db):
    out = coordinator._resolve_genres(["新ジャンル"])
    assert out["ko"] == ["新ジャンル"]
    assert _count(db, Genre) == 4


def test_fullwidth_maker_maps_to_existing_halfwidth_row(db):
    out = coordinator._resolve_maker("ダスッ!")
    assert out["ko"] == "다스!"
    assert _count(db, Maker) == 1


def test_width_key():
    assert coordinator._width_key(" ﾍﾞｽﾄ･総集編 ") == coordinator._width_key("ベスト・総集編")
    assert coordinator._width_key("OL") == coordinator._width_key("Ol")


def test_terms_stay_paired_when_korean_duplicates_are_dropped(db):
    # 같은 한국어로 가는 표기 2개(アクメ・オーガズム / ｱｸﾒ･ｵｰｶﾞｽﾞﾑ → 절정)가 있어도
    # 뒤에 오는 장르의 용어 짝이 밀리면 안 된다 (예전 zip(ja, ko) 버그)
    out = coordinator._resolve_genres(["アクメ・オーガズム", "ｱｸﾒ･ｵｰｶﾞｽﾞﾑ", "中出シ"])
    assert out["ko"] == ["절정", "질내사정"]
    assert out["terms"] == {"アクメ・オーガズム": "절정", "ｱｸﾒ･ｵｰｶﾞｽﾞﾑ": "절정", "中出シ": "질내사정"}


def test_require_safe_code():
    from javstory.library.paths import require_safe_code, work_library_dir

    assert require_safe_code("SNOS-334") == "SNOS-334"
    assert require_safe_code("FC2_PPV-123") == "FC2_PPV-123"
    for bad in (r"..\..\x", "../x", "a/b", "", ".hidden", "C:x"):
        with pytest.raises(ValueError):
            require_safe_code(bad)
    with pytest.raises(ValueError):
        work_library_dir(r"..\evil")
