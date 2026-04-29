"""javstory.library.service 단위 테스트."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from javstory.library.canonical.schema import LibraryCanonical, SceneEntry
from javstory.library.service import (
    load_work,
    merge_grok_into_work,
    save_work,
    toggle_scene_lock,
    toggle_work_lock,
    update_scene,
)


def _minimal_state() -> LibraryCanonical:
    return LibraryCanonical(
        product_code="TST-001",
        scenes=[
            SceneEntry(
                scene_id="s1",
                time_range="00:01:00 ~ 00:02:00",
                scene_label="A",
                start_sec=60.0,
                end_sec=120.0,
            ),
        ],
    )


def _replace_scene(state: LibraryCanonical, **kwargs: object) -> LibraryCanonical:
    sc = state.scenes[0]
    return replace(state, scenes=[replace(sc, **kwargs)])


def test_update_scene_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAVSTORY_LIBRARY_ROOT", str(tmp_path))
    st = _minimal_state()
    st = update_scene(st, "s1", {"scene_summary": "hello"})
    assert st.scenes[0].scene_summary == "hello"


def test_update_scene_time_range_clears_stills(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAVSTORY_LIBRARY_ROOT", str(tmp_path))
    st = _minimal_state()
    st = _replace_scene(st, still_paths=["stills/x/a.jpg"], needs_still_refresh=False)
    st = update_scene(st, "s1", {"time_range": "00:05:00 ~ 00:06:00"})
    assert st.scenes[0].still_paths == []
    assert st.scenes[0].needs_still_refresh is True


def test_toggle_locks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAVSTORY_LIBRARY_ROOT", str(tmp_path))
    st = _minimal_state()
    st = toggle_scene_lock(st, "s1", "scene_summary")
    assert "scene_summary" in st.scenes[0].locked_fields
    st = toggle_scene_lock(st, "s1", "scene_summary")
    assert "scene_summary" not in st.scenes[0].locked_fields

    st = toggle_work_lock(st, "title_ko")
    assert "title_ko" in st.work_locked_fields


def test_merge_grok_respects_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAVSTORY_LIBRARY_ROOT", str(tmp_path))
    st = _minimal_state()
    st = replace(
        st,
        title_ko="고정",
        work_locked_fields={"title_ko"},
    )
    grok = {
        "schema_version": 1,
        "product_code": "TST-001",
        "title_ko": "바뀜",
        "title_ja": "",
        "actress": "",
        "maker": "",
        "release_date": "",
        "synopsis_short": "",
        "overall_summary": "",
        "scenes": [],
    }
    out = merge_grok_into_work(st, grok)
    assert out.title_ko == "고정"


def test_save_work_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAVSTORY_LIBRARY_ROOT", str(tmp_path))
    st = _minimal_state()
    st = replace(st, overall_summary="요약")
    p = save_work(st)
    assert p.is_file()
    loaded = load_work("TST-001")
    assert loaded is not None
    assert loaded.overall_summary == "요약"
