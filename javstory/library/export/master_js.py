"""master_db.js — build_master_db.py와 동일한 전역 형식."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from javstory.library.canonical.schema import LibraryCanonical, SceneEntry
from javstory.library.export.io_utils import atomic_write_text


def parse_master_db_js(text: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """window.MASTER_DB / MASTER_DB_META 파싱."""
    decoder = json.JSONDecoder()

    def _parse_global(name: str) -> Any:
        needle = f"window.{name} = "
        i = text.find(needle)
        if i < 0:
            raise ValueError(f"문서에 {needle!r} 할당이 없습니다.")
        j = i + len(needle)
        while j < len(text) and text[j] in " \t\r\n":
            j += 1
        obj, _ = decoder.raw_decode(text, j)
        return obj

    entries = _parse_global("MASTER_DB")
    if not isinstance(entries, list):
        raise ValueError("MASTER_DB는 배열이어야 합니다.")
    try:
        meta = _parse_global("MASTER_DB_META")
    except ValueError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return entries, meta


def load_master_db_js(path: Path | str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    p = Path(path)
    return parse_master_db_js(p.read_text(encoding="utf-8"))


def write_master_db_js(
    path: Path | str,
    entries: list[dict[str, Any]],
    *,
    meta_version: str = "master_v1",
    generated_at: str | None = None,
) -> Path:
    """build_master_db.write_master_js 와 동일 레이아웃."""
    p = Path(path)
    ts = generated_at or datetime.now().isoformat(timespec="seconds")
    lines = [
        "window.MASTER_DB = ",
        json.dumps(entries, ensure_ascii=False),
        ";\n",
        "window.MASTER_DB_META = ",
        json.dumps(
            {
                "version": meta_version,
                "generated_at": ts,
                "count": len(entries),
            },
            ensure_ascii=False,
        ),
        ";\n",
    ]
    atomic_write_text(p, "".join(lines))
    return p


def merge_master_entries_for_source(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    *,
    source: str,
    source_key: str = "source",
) -> list[dict[str, Any]]:
    """동일 source(품번) 행은 제거한 뒤 incoming을 붙인 뒤 정렬."""
    src = (source or "").strip()
    kept = [e for e in existing if isinstance(e, dict) and str(e.get(source_key, "")).strip() != src]
    merged = kept + list(incoming)

    def _sort_key(e: dict[str, Any]) -> tuple[str, float]:
        v = e.get("video") if isinstance(e.get("video"), dict) else {}
        src_v = str(v.get("src") or "") if isinstance(v, dict) else ""
        sc = e.get("scene") if isinstance(e.get("scene"), dict) else {}
        t = 0.0
        if isinstance(sc, dict):
            try:
                t = float(sc.get("t", 0.0))
            except (TypeError, ValueError):
                t = 0.0
        return (src_v, t)

    merged.sort(key=_sort_key)
    return merged


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def scene_to_master_entry(
    scene: SceneEntry,
    state: LibraryCanonical,
    *,
    video_src: str = "",
    video_duration: float = 0.0,
    video_fps: float | None = None,
    thumb_web_path: str | None = None,
) -> dict[str, Any]:
    """
    js/app.js MASTER MODE가 기대하는 한 행 구조.
    thumb: 웹에서 접근 가능한 경로(프로젝트 루트 상대 등).
    """
    pc = (state.product_code or "UNKNOWN").strip()
    z_start = scene.start_sec if scene.start_sec is not None else 0.0
    z_end = scene.end_sec if scene.end_sec is not None else z_start
    t = z_start
    if z_end > z_start:
        t = z_start + (z_end - z_start) / 2.0

    zone = scene.scene_label.strip() or "UNKNOWN"
    position = (scene.key_tags[0] if scene.key_tags else "canonical") or "canonical"
    action = scene.scene_id or "scene"
    intensity = scene.tone[:80] + ("…" if len(scene.tone) > 80 else "") if scene.tone else "?"
    description = scene.scene_summary or ""

    thumb = thumb_web_path
    if thumb is None and scene.still_paths:
        thumb = scene.still_paths[0].replace("\\", "/")

    text_blob = " ".join([zone, position, action, intensity, description]).strip()

    vid: dict[str, Any] = {"src": video_src, "duration": video_duration}
    if video_fps is not None:
        vid["fps"] = video_fps

    return {
        "id": f"{pc}::{scene.scene_id}::{t:.3f}",
        "source": pc,
        "video": vid,
        "scene": {
            "t": _safe_float(t, 0.0),
            "zone": zone,
            "position": str(position),
            "action": str(action),
            "intensity": str(intensity),
            "description": description,
            "zoneStart": _safe_float(z_start, 0.0),
            "zoneEnd": _safe_float(z_end, 0.0),
        },
        "thumb": thumb,
        "text": text_blob,
    }


def canonical_to_master_entries(
    state: LibraryCanonical,
    *,
    video_src: str = "",
    video_duration: float = 0.0,
    video_fps: float | None = None,
    thumb_resolver: Callable[[SceneEntry], str | None] | None = None,
) -> list[dict[str, Any]]:
    """
    thumb_resolver: 웹에서 접근 가능한 썸네일 URL/상대 경로 생성.
    없으면 still_paths[0] 문자열을 그대로 thumb에 넣는다.
    """
    out: list[dict[str, Any]] = []
    for sc in state.scenes:
        tw = None
        if thumb_resolver is not None:
            tw = thumb_resolver(sc)
        out.append(
            scene_to_master_entry(
                sc,
                state,
                video_src=video_src,
                video_duration=video_duration,
                video_fps=video_fps,
                thumb_web_path=tw,
            )
        )
    return out
