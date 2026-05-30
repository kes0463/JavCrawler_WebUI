"""LibraryModel 분리 서비스 단위 테스트."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gui.models.library.detail_service import LibraryDetailService
from gui.models.library.folder_bind import FolderBindHooks, LibraryFolderBind
from gui.models.library.search import match_summary, parse_search_expr
from gui.models.library.sort_filter import LibrarySortFilter, ListRebuildOptions
from javstory.llm.engine import AllTiersExhaustedError


class _Summary:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_parse_search_expr_genre_and_text():
    groups, excl, terms = parse_search_expr('#드라마|#로맨스 -#공포 일본')
    assert groups == [["드라마", "로맨스"]]
    assert "공포" in excl
    assert "일본" in terms


def test_match_summary_genre_filter():
    s = _Summary(product_code="A", genres_ko="드라마, 로맨스", title_ko="x")
    assert match_summary(s, [["드라마"]], set(), []) is True
    assert match_summary(s, [["공포"]], set(), []) is False


def test_library_sort_filter_rebuild_groups_by_base():
    rows = [
        _Summary(
            product_code="ABW-358",
            title_ko="t1",
            release_date="2026-01-01",
            scene_count=1,
            pipeline_stage="none",
        ),
        _Summary(
            product_code="ABW-358",
            title_ko="t2",
            release_date="2026-02-01",
            scene_count=2,
            pipeline_stage="harvest",
        ),
    ]
    items = LibrarySortFilter.rebuild(
        ListRebuildOptions(all_summaries=rows, sort_mode=0)
    )
    assert len(items) == 1
    assert items[0]["product_code"] == "ABW-358"
    assert items[0]["part_count"] == 2


def test_library_sort_filter_rebuild_sorts_by_preference(monkeypatch):
    monkeypatch.setattr(
        "gui.models.library.sort_filter.build_watch_feedback_by_base",
        lambda: {
            "USER-001": {"liked": True, "rating": 2},
            "RATE-001": {"liked": False, "rating": 5},
        },
    )
    monkeypatch.setattr(
        "gui.models.library.sort_filter.preview_path_for",
        lambda *_args, **_kwargs: "",
    )
    rows = [
        _Summary(
            product_code="SITE-001",
            title_ko="site",
            release_date="2026-01-01",
            scene_count=0,
            pipeline_stage="none",
            favorite_score=10_000,
        ),
        _Summary(
            product_code="USER-001",
            title_ko="liked",
            release_date="2026-01-01",
            scene_count=0,
            pipeline_stage="none",
            favorite_score=0,
        ),
        _Summary(
            product_code="RATE-001",
            title_ko="rated",
            release_date="2026-01-01",
            scene_count=0,
            pipeline_stage="none",
            favorite_score=0,
        ),
    ]

    items = LibrarySortFilter.rebuild(
        ListRebuildOptions(all_summaries=rows, sort_mode=15)
    )

    assert [it["product_code"] for it in items] == ["USER-001", "RATE-001", "SITE-001"]
    assert items[0]["preference_score"] > items[1]["preference_score"]


def test_work_list_model_refresh_appends_when_prefix_matches():
    from gui.models.library_model import WorkListModel

    model = WorkListModel()
    model.refresh([{"product_code": "AAA-001", "title_ko": "A"}])
    model.refresh([
        {"product_code": "AAA-001", "title_ko": "A"},
        {"product_code": "BBB-002", "title_ko": "B"},
    ])

    assert model.rowCount() == 2
    assert model.productCodeAt(1) == "BBB-002"


def test_library_detail_service_build_minimal():
    s = _Summary(
        product_code="TST-1",
        title_ko="ko",
        title_ja="ja",
        actors_ko="",
        maker_ko="",
        release_date="",
        synopsis_ko="",
        genres_ko="",
        cover_effective_path="",
        cover_local_path="",
        scene_count=0,
        pipeline_stage="none",
        has_canonical=False,
        overall_summary_preview="",
        is_hardcoded=False,
        has_ja_srt=False,
        has_ko_srt=False,
        lamp_hardcoded=False,
        folder_path="",
        favorite_score=0,
    )
    data = LibraryDetailService.build_detail_data(s)
    assert data["product_code"] == "TST-1"
    assert data["title_ko"] == "ko"


def test_folder_bind_hooks_mock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    toasts: list[tuple[str, str]] = []

    class _Row:
        product_code = "ABC-100"
        id = 1
        folder_path = None
        is_hardcoded = False
        is_mopa = False

    class _Session:
        def query(self, _):
            return self

        def filter_by(self, **_):
            return self

        def first(self):
            return _Row()

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(
        "javstory.harvest.database.get_db_session",
        lambda: _Session(),
    )
    monkeypatch.setattr(
        "javstory.utils.product_code.extract_product_code_from_path",
        lambda _p: "ABC-100",
    )
    monkeypatch.setattr(
        "gui.library_data._first_video_in_dir",
        lambda _p: None,
    )
    monkeypatch.setattr(
        "javstory.harvest.product_repository.set_folder_path",
        lambda _s, _pc, _fp: None,
    )
    monkeypatch.setattr(
        "javstory.harvest.product_repository.sync_product_from_metadata_row",
        lambda _s, _r: None,
    )

    hooks = FolderBindHooks(
        toast=lambda m, l: toasts.append((m, l)),
        refresh_product=lambda _pc: None,
        summaries_reloaded=lambda: None,
        schedule_auto_snapshots=lambda _p, _f: None,
    )
    ok = LibraryFolderBind.bind_folder(
        "ABC-100",
        str(tmp_path),
        force=False,
        hooks=hooks,
    )
    assert ok is True
    assert any("저장" in t[0] for t in toasts)


def test_all_tiers_exhausted_in_engine():
    err = AllTiersExhaustedError("x", last_model="m")
    assert err.last_model == "m"
