"""라이브러리 고수준 API — canonical 편집·Grok 병합·export·스틸·drift."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from javstory.library.canonical.schema import LibraryCanonical, SceneEntry, utc_now_iso
from javstory.library.canonical.store import load_library_state, save_library_state
from javstory.library.export.bundle import ExportBundleConfig, export_canonical_bundle
from javstory.library.export.sync import ExportDrift, list_export_drift
from javstory.library.grok_merge.merge import merge_grok_draft
from javstory.library.paths import library_state_path
from javstory.library.stills.extract import refresh_all_stills
from javstory.library.stills.time_range import parse_time_range


def load_work(product_code: str, *, library_root: Path | None = None) -> LibraryCanonical | None:
    """library_state.json 로드. 없으면 None."""
    p = library_state_path(product_code, root=library_root)
    if not p.is_file():
        return None
    return load_library_state(p)


def save_work(state: LibraryCanonical, *, library_root: Path | None = None) -> Path:
    """canonical 원자 저장."""
    pc = (state.product_code or "").strip().upper()
    if not pc:
        raise ValueError("product_code가 비어 있습니다.")
    p = library_state_path(pc, root=library_root)
    save_library_state(p, state)
    return p


def _find_scene(state: LibraryCanonical, scene_id: str) -> int:
    sid = (scene_id or "").strip()
    for i, s in enumerate(state.scenes):
        if s.scene_id == sid:
            return i
    raise KeyError(f"씬 없음: {scene_id!r}")


def update_scene(
    state: LibraryCanonical,
    scene_id: str,
    updates: dict[str, Any],
    *,
    lock_updated_fields: bool = False,
) -> LibraryCanonical:
    """
    씬 필드 수정. time_range 변경 시 start_sec/end_sec 재파싱·needs_still_refresh·still_paths 초기화.
    lock_updated_fields=True이면 수정한 키를 locked_fields에 추가.
    """
    idx = _find_scene(state, scene_id)
    sc = state.scenes[idx]

    scene_summary = sc.scene_summary
    scene_label = sc.scene_label
    tone = sc.tone
    key_tags = list(sc.key_tags)
    time_range = sc.time_range
    time_label = sc.time_label or sc.time_range
    start_sec = sc.start_sec
    end_sec = sc.end_sec

    if "scene_summary" in updates:
        scene_summary = str(updates["scene_summary"])
    if "scene_label" in updates:
        scene_label = str(updates["scene_label"])
    if "tone" in updates:
        tone = str(updates["tone"])
    if "key_tags" in updates and isinstance(updates["key_tags"], list):
        key_tags = [str(x) for x in updates["key_tags"]]
    if "time_label" in updates:
        time_label = str(updates["time_label"])

    tr_old = sc.time_range
    if "time_range" in updates:
        time_range = str(updates["time_range"])
    time_changed = "time_range" in updates and time_range != tr_old

    if "start_sec" in updates:
        v = updates["start_sec"]
        start_sec = float(v) if v is not None else None
    if "end_sec" in updates:
        v = updates["end_sec"]
        end_sec = float(v) if v is not None else None

    if "time_range" in updates:
        a, b = parse_time_range(time_range)
        start_sec, end_sec = a, b

    still_paths = list(sc.still_paths)
    needs_refresh = sc.needs_still_refresh
    if time_changed:
        still_paths = []
        needs_refresh = True

    new_locked = set(sc.locked_fields)
    if lock_updated_fields:
        scene_field_keys = {
            "scene_summary",
            "scene_label",
            "tone",
            "key_tags",
            "time_range",
            "time_label",
        }
        for k in updates:
            if k in scene_field_keys:
                new_locked.add(k)

    new_scene = replace(
        sc,
        scene_summary=scene_summary,
        scene_label=scene_label,
        tone=tone,
        key_tags=key_tags,
        time_range=time_range,
        time_label=time_label or time_range,
        start_sec=start_sec,
        end_sec=end_sec,
        still_paths=still_paths,
        locked_fields=new_locked,
        needs_still_refresh=needs_refresh,
    )

    new_scenes = list(state.scenes)
    new_scenes[idx] = new_scene
    return replace(state, scenes=new_scenes, updated_at=utc_now_iso())


def toggle_scene_lock(state: LibraryCanonical, scene_id: str, field: str) -> LibraryCanonical:
    idx = _find_scene(state, scene_id)
    sc = state.scenes[idx]
    lf = set(sc.locked_fields)
    fk = (field or "").strip()
    if not fk:
        return state
    if fk in lf:
        lf.discard(fk)
    else:
        lf.add(fk)
    new_scenes = list(state.scenes)
    new_scenes[idx] = replace(sc, locked_fields=lf)
    return replace(state, scenes=new_scenes, updated_at=utc_now_iso())


def toggle_work_lock(state: LibraryCanonical, field: str) -> LibraryCanonical:
    fk = (field or "").strip()
    if not fk:
        return state
    wf = set(state.work_locked_fields)
    if fk in wf:
        wf.discard(fk)
    else:
        wf.add(fk)
    return replace(state, work_locked_fields=wf, updated_at=utc_now_iso())


def merge_grok_into_work(state: LibraryCanonical, grok_dict: dict[str, Any]) -> LibraryCanonical:
    return merge_grok_draft(state, grok_dict)


def run_export(
    state: LibraryCanonical,
    project_root: Path | str,
    *,
    video_src: str = "",
    video_duration: float = 0.0,
    video_fps: float | None = None,
    merge_into_master_db: bool = True,
) -> LibraryCanonical:
    pr = Path(project_root)
    cfg = ExportBundleConfig(
        project_root=pr,
        video_src=video_src,
        video_duration=video_duration,
        video_fps=video_fps,
        merge_into_master_db=merge_into_master_db,
    )
    return export_canonical_bundle(state, cfg)


def check_export_drift(
    state: LibraryCanonical,
    project_root: Path | str,
) -> list[ExportDrift]:
    return list_export_drift(state, project_root)


def refresh_stills(
    state: LibraryCanonical,
    video_path: Path | str,
    *,
    n_per_scene: int = 3,
    only_dirty: bool = True,
    library_root: Path | None = None,
) -> LibraryCanonical:
    return refresh_all_stills(
        video_path,
        state,
        n_per_scene=n_per_scene,
        only_needs_refresh=only_dirty,
        library_root=library_root,
    )


def save_and_export(
    state: LibraryCanonical,
    project_root: Path | str,
    video_path: Path | str | None = None,
    *,
    refresh_dirty_stills: bool = True,
    n_per_scene: int = 3,
    library_root: Path | None = None,
    merge_into_master_db: bool = True,
) -> LibraryCanonical:
    """스틸(선택) → export → 디스크 저장."""
    s = state
    vp = Path(video_path) if video_path else None
    if refresh_dirty_stills and vp and vp.is_file():
        s = refresh_stills(
            s,
            vp,
            n_per_scene=n_per_scene,
            only_dirty=True,
            library_root=library_root,
        )
    s = run_export(s, project_root, merge_into_master_db=merge_into_master_db)
    save_work(s, library_root=library_root)
    return s
