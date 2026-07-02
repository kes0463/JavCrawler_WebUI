"""장르 필터 SQL 단위 테스트."""

from __future__ import annotations

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from javstory.harvest.database import Base, JAVMetadata
from javstory.library.genre_filter import apply_genre_filters, aggregate_genre_counts


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _add(session, code: str, genres: str) -> None:
    session.add(JAVMetadata(product_code=code, genres_ko=genres, title_ko="t"))
    session.commit()


def test_genre_filter_and_mode() -> None:
    session = _session()
    _add(session, "A-001", "미인, 단독작품")
    _add(session, "B-002", "미인, 학원")
    _add(session, "C-003", "학원")

    q = session.query(JAVMetadata)
    q = apply_genre_filters(q, ["미인", "단독작품"], mode="and")
    codes = {r.product_code for r in q.all()}
    assert codes == {"A-001"}

    q2 = session.query(JAVMetadata)
    q2 = apply_genre_filters(q2, ["미인", "학원"], mode="or")
    codes_or = {r.product_code for r in q2.all()}
    assert codes_or == {"A-001", "B-002", "C-003"}


def test_genre_filter_exact_token_not_partial() -> None:
    session = _session()
    _add(session, "A-001", "미인")
    _add(session, "B-002", "미인여우")

    q = session.query(JAVMetadata)
    q = apply_genre_filters(q, ["미인"], mode="and")
    codes = {r.product_code for r in q.all()}
    assert codes == {"A-001"}


def test_aggregate_genre_counts() -> None:
    rows = ["미인, 학원", "미인", "학원, 코스프레"]
    items = aggregate_genre_counts(rows, limit=10)
    by_name = {i["name"]: i["count"] for i in items}
    assert by_name["미인"] == 2
    assert by_name["학원"] == 2
    assert by_name["코스프레"] == 1
