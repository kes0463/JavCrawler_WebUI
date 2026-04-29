"""Grok 초안을 기존 canonical에 병합 — work_locked_fields / scene.locked_fields 존중."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from javstory.library.canonical.schema import (
    LibraryCanonical,
    SceneEntry,
    library_canonical_from_grok_dict,
    utc_now_iso,
)

_WORK_LEVEL_KEYS = (
    "schema_version",
    "verification_ok",
    "code_mismatch",
    "mismatch_reason",
    "title_ja",
    "title_ko",
    "actress",
    "maker",
    "release_date",
    "synopsis_short",
    "overall_summary",
)


def merge_grok_draft(current: LibraryCanonical, grok: dict[str, Any]) -> LibraryCanonical:
    """
    Grok가 다시 준 dict를 반영한다. 잠긴 필드는 유지한다.
    품번이 둘 다 있으면 대소문자 무시 동일해야 한다.
    """
    incoming = library_canonical_from_grok_dict(grok)

    c_code = (current.product_code or "").strip().upper()
    i_code = (incoming.product_code or "").strip().upper()
    if c_code and i_code and c_code != i_code:
        raise ValueError(f"품번 불일치: canonical={current.product_code!r} grok={incoming.product_code!r}")

    product = current.product_code or incoming.product_code

    work_updates: dict[str, Any] = {}
    for wk in _WORK_LEVEL_KEYS:
        if wk not in current.work_locked_fields:
            work_updates[wk] = getattr(incoming, wk)

    merged_scenes = _merge_scenes(current.scenes, incoming.scenes)

    out = replace(
        current,
        product_code=product,
        **work_updates,
        scenes=merged_scenes,
        updated_at=utc_now_iso(),
    )
    return out


def _merge_scenes(
    current: list[SceneEntry],
    incoming: list[SceneEntry],
) -> list[SceneEntry]:
    by_id_cur = {s.scene_id: s for s in current}
    by_id_inc = {s.scene_id: s for s in incoming}
    order: list[str] = []
    seen: set[str] = set()
    for s in current:
        if s.scene_id not in seen:
            order.append(s.scene_id)
            seen.add(s.scene_id)
    for s in incoming:
        if s.scene_id not in seen:
            order.append(s.scene_id)
            seen.add(s.scene_id)

    out: list[SceneEntry] = []
    for sid in order:
        base = by_id_cur.get(sid)
        inc = by_id_inc.get(sid)
        if base is None and inc is not None:
            out.append(replace(inc, needs_still_refresh=True))
            continue
        if inc is None and base is not None:
            out.append(base)
            continue
        if base is not None and inc is not None:
            out.append(_merge_one_scene(base, inc))
    return out


def _merge_one_scene(base: SceneEntry, inc: SceneEntry) -> SceneEntry:
    locked = base.locked_fields
    tr = base.time_range if "time_range" in locked else inc.time_range
    sl = base.scene_label if "scene_label" in locked else inc.scene_label
    ss = base.scene_summary if "scene_summary" in locked else inc.scene_summary
    tn = base.tone if "tone" in locked else inc.tone
    kt = base.key_tags if "key_tags" in locked else inc.key_tags
    tl = base.time_label if "time_label" in locked else inc.time_label

    time_changed = "time_range" not in locked and tr != base.time_range
    start_sec = base.start_sec if "time_range" in locked else inc.start_sec
    end_sec = base.end_sec if "time_range" in locked else inc.end_sec

    still_paths = list(base.still_paths)
    needs_refresh = base.needs_still_refresh
    if time_changed:
        still_paths = []
        start_sec = inc.start_sec
        end_sec = inc.end_sec
        needs_refresh = True

    return replace(
        base,
        time_range=tr,
        scene_label=sl,
        scene_summary=ss,
        tone=tn,
        key_tags=list(kt),
        time_label=tl or tr,
        start_sec=start_sec,
        end_sec=end_sec,
        still_paths=still_paths,
        locked_fields=set(base.locked_fields),
        needs_still_refresh=needs_refresh,
    )
