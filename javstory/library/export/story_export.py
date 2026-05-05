"""Grok 호환 story JSON — 확장 필드(씬 still_paths 등) 직렬화·역직렬화."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from javstory.library.canonical.schema import LibraryCanonical, SceneEntry, library_canonical_from_grok_dict
from javstory.library.export.io_utils import atomic_write_text
from javstory.library.grok_merge.merge import merge_grok_draft


def story_context_file_dict_from_canonical(state: LibraryCanonical) -> dict[str, Any]:
    """
    디스크용 story JSON — Grok/번역 파이프라인 호환 필드 + 씬 확장(되돌리기용).
    """
    base = {
        "schema_version": state.schema_version if state.schema_version is not None else 1,
        "product_code": state.product_code,
        "verification_ok": state.verification_ok if state.verification_ok is not None else True,
        "code_mismatch": state.code_mismatch if state.code_mismatch is not None else False,
        "mismatch_reason": state.mismatch_reason,
        "title_ja": state.title_ja,
        "title_ko": state.title_ko,
        "actress": state.actress,
        "maker": state.maker,
        "release_date": state.release_date,
        "synopsis_short": state.synopsis_short,
        "overall_summary": state.overall_summary,
        "scenes": [],
        "translation_note": state.translation_note or "",
        "_javstory": {
            "canonical_schema_version": state.canonical_schema_version,
            "updated_at": state.updated_at,
        },
    }
    for s in state.scenes:
        base["scenes"].append(
            {
                "scene_id": s.scene_id,
                "time_range": s.time_range,
                "scene_label": s.scene_label,
                "scene_summary": s.scene_summary,
                "tone": s.tone,
                "key_tags": list(s.key_tags),
                "time_label": s.time_label or s.time_range,
                "start_sec": s.start_sec,
                "end_sec": s.end_sec,
                "still_paths": list(s.still_paths),
                "locked_fields": sorted(s.locked_fields),
                "needs_still_refresh": s.needs_still_refresh,
            }
        )
    return base


def canonical_from_story_context_file_dict(data: dict[str, Any]) -> LibraryCanonical:
    """확장 story JSON(dict) → LibraryCanonical (잠금·스틸 경로 포함)."""
    c = library_canonical_from_grok_dict(data)
    raw_scenes = data.get("scenes") or []
    if not isinstance(raw_scenes, list):
        return c

    by_id: dict[str, dict[str, Any]] = {}
    for item in raw_scenes:
        if isinstance(item, dict) and item.get("scene_id"):
            by_id[str(item["scene_id"])] = item

    new_scenes: list[SceneEntry] = []
    for sc in c.scenes:
        raw = by_id.get(sc.scene_id)
        if not raw:
            new_scenes.append(sc)
            continue
        lf = raw.get("locked_fields") or []
        if isinstance(lf, str):
            lf = [lf]
        locked = set(lf) if isinstance(lf, list) else set()
        sp = raw.get("still_paths")
        paths = [str(x) for x in sp] if isinstance(sp, list) else list(sc.still_paths)
        ss = raw.get("start_sec")
        es = raw.get("end_sec")
        start_sec = sc.start_sec
        end_sec = sc.end_sec
        if ss is not None:
            try:
                start_sec = float(ss)
            except (TypeError, ValueError):
                pass
        if es is not None:
            try:
                end_sec = float(es)
            except (TypeError, ValueError):
                pass
        new_scenes.append(
            replace(
                sc,
                time_label=str(raw.get("time_label") or sc.time_label),
                still_paths=paths,
                locked_fields=locked,
                needs_still_refresh=bool(raw.get("needs_still_refresh", sc.needs_still_refresh)),
                start_sec=start_sec,
                end_sec=end_sec,
            )
        )

    meta = data.get("_javstory")
    updated_at = c.updated_at
    if isinstance(meta, dict) and meta.get("updated_at"):
        updated_at = str(meta["updated_at"])

    note = str(data.get("translation_note", "") or "")
    return replace(c, scenes=new_scenes, updated_at=updated_at, translation_note=note)


def write_story_context_json(path: Path | str, state: LibraryCanonical, *, indent: int = 2) -> Path:
    p = Path(path)
    payload = story_context_file_dict_from_canonical(state)
    atomic_write_text(p, json.dumps(payload, ensure_ascii=False, indent=indent) + "\n")
    return p


def read_story_context_json(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"story JSON이 객체가 아닙니다: {p}")
    return data


def merge_story_file_into_canonical(current: LibraryCanonical, data: dict[str, Any]) -> LibraryCanonical:
    """
    디스크에서 고친 story JSON을 반영 — 텍스트는 merge_grok_draft(잠금) 규칙,
    still_paths·needs_still_refresh 등은 씬별로 파일 값을 덮어쓴다(잠금 시 유지).
    """
    merged = merge_grok_draft(current, data)
    raw_list = data.get("scenes") if isinstance(data.get("scenes"), list) else []
    raw_by_id: dict[str, dict[str, Any]] = {}
    for item in raw_list:
        if isinstance(item, dict) and item.get("scene_id"):
            raw_by_id[str(item["scene_id"])] = item

    new_scenes: list[SceneEntry] = []
    for sc in merged.scenes:
        r = raw_by_id.get(sc.scene_id)
        if not r:
            new_scenes.append(sc)
            continue
        if "still_paths" in sc.locked_fields:
            new_scenes.append(sc)
            continue
        sp_raw = r.get("still_paths")
        paths = [str(x) for x in sp_raw] if isinstance(sp_raw, list) else list(sc.still_paths)
        ns = bool(r.get("needs_still_refresh", sc.needs_still_refresh))
        new_scenes.append(replace(sc, still_paths=paths, needs_still_refresh=ns))
    return replace(merged, scenes=new_scenes)


def story_file_wins_canonical(data: dict[str, Any]) -> LibraryCanonical:
    """파일 내용을 그대로 canonical로 — 잠금 무시(전부 파일 기준)."""
    return canonical_from_story_context_file_dict(data)
