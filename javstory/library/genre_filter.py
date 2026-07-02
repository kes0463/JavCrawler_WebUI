"""라이브러리 장르 목록·SQL 필터."""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import or_
from sqlalchemy.orm import Query
from sqlalchemy.sql.elements import ColumnElement

from javstory.harvest.database import JAVMetadata


def genre_token_sql_match(column, genre: str) -> ColumnElement:
    """쉼표 구분 genres_ko 필드에서 장르 토큰 정확 일치."""
    g = (genre or "").strip()
    if not g:
        return column.isnot(None)
    return or_(
        column == g,
        column.like(f"{g},%"),
        column.like(f"%,{g},%"),
        column.like(f"%,{g}"),
        column.like(f"{g}, %"),
        column.like(f"%, {g},%"),
        column.like(f"%, {g}"),
    )


def apply_genre_filters(
    query: Query,
    genres: list[str] | None,
    *,
    mode: str = "and",
    exclude_genres: list[str] | None = None,
) -> Query:
    selected = [g.strip() for g in (genres or []) if g and str(g).strip()]
    excluded = [g.strip() for g in (exclude_genres or []) if g and str(g).strip()]
    active_mode = (mode or "and").strip().lower()

    if selected:
        col_ko = JAVMetadata.genres_ko
        col_legacy = JAVMetadata.genres

        def _match(genre: str):
            return or_(
                genre_token_sql_match(col_ko, genre),
                genre_token_sql_match(col_legacy, genre),
            )

        if active_mode == "or":
            query = query.filter(or_(*[_match(g) for g in selected]))
        else:
            for g in selected:
                query = query.filter(_match(g))

    if excluded:
        col_ko = JAVMetadata.genres_ko
        col_legacy = JAVMetadata.genres
        for g in excluded:
            query = query.filter(
                ~or_(
                    genre_token_sql_match(col_ko, g),
                    genre_token_sql_match(col_legacy, g),
                )
            )

    return query


def aggregate_genre_counts(
    genre_rows: Iterable[str | None],
    *,
    limit: int = 200,
) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for raw in genre_rows:
        for g in str(raw or "").split(","):
            name = g.strip()
            if not name:
                continue
            counts[name] = counts.get(name, 0) + 1
    cap = max(1, min(500, int(limit or 200)))
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:cap]
    return [{"name": name, "count": count} for name, count in items]
