"""
Build embedding documents from:
- meta (DB-applied canonical fields)
- canonical (scenes etc.)
- subtitles (.srt)
"""

from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import pysrt

from javstory.library.canonical.schema import LibraryCanonical, SceneEntry
from javstory.library.paths import work_library_dir
from javstory.translation.story_grok_module import load_cached_grok_json_flexible


def _norm_ws(s: str) -> str:
    return re.sub(r"[ \t]+", " ", (s or "").replace("\u00A0", " ")).strip()


def _safe_join(lines: Iterable[str]) -> str:
    out: List[str] = []
    for x in lines:
        t = _norm_ws(str(x))
        if t:
            out.append(t)
    return "\n".join(out).strip()


from javstory.harvest.database import get_db_session, JAVMetadata

def _format_meta_block(state: LibraryCanonical) -> str:
    genres = ""
    try:
        session = get_db_session()
        row = session.query(JAVMetadata).filter_by(product_code=state.product_code).first()
        if row:
            genres = row.genres_ko or row.genres or ""
        session.close()
    except Exception:
        pass

    return _safe_join(
        [
            f"[product_code] {state.product_code}",
            f"[title_ko] {state.title_ko}",
            f"[title_ja] {state.title_ja}",
            f"[actress] {state.actress}",
            f"[maker] {state.maker}",
            f"[genres] {genres}",
            f"[release_date] {state.release_date}",
            f"[synopsis_short] {state.synopsis_short}",
            f"[overall_summary] {state.overall_summary}",
        ]
    )


def _format_scenes_block(scenes: List[SceneEntry]) -> str:
    if not scenes:
        return ""
    parts: List[str] = ["[scenes]"]
    for s in scenes:
        parts.append(
            _safe_join(
                [
                    f"- scene_id: {s.scene_id}",
                    f"  time_range: {s.time_range}",
                    f"  label: {s.scene_label}",
                    f"  tone: {s.tone}",
                    f"  key_tags: {', '.join(s.key_tags or [])}",
                    f"  summary: {s.scene_summary}",
                ]
            )
        )
    return _safe_join(parts)


def _find_subtitle_candidate_paths(state: LibraryCanonical, *, library_root: Path | None = None) -> List[Path]:
    """
    Best-effort subtitle discovery.
    Priority:
    - canonical.media.merged_timeline_srt_relpath (if present, relative to work dir)
    - work dir sibling *.ko.srt, *.ja.srt, *.srt (first match per priority)
    """
    work_dir = work_library_dir(state.product_code, root=library_root)
    out: List[Path] = []

    if state.media and state.media.merged_timeline_srt_relpath:
        p = work_dir / str(state.media.merged_timeline_srt_relpath)
        out.append(p)

    # fallbacks: any SRT in work dir (common output location for pipeline assets)
    # prefer ko > ja > plain
    for pat in ("*.ko.srt", "*.ja.srt", "*.srt"):
        try:
            for p in sorted(work_dir.glob(pat)):
                if p not in out:
                    out.append(p)
        except Exception:
            continue

    return out


def load_srt_text_for_state(
    state: LibraryCanonical,
    *,
    library_root: Path | None = None,
    encoding: str = "utf-8",
    max_chars: int = 200_000,
) -> Tuple[str, Optional[str]]:
    """
    Returns (subtitle_text, picked_path_str|None).
    Note: We may merge multiple SRT sources (ko/ja/plain) for richer retrieval.
    """
    picked: List[str] = []
    merged_lines: List[str] = []
    total = 0

    # Merge multiple SRT files in priority order (ko > ja > any), de-duping by path.
    for p in _find_subtitle_candidate_paths(state, library_root=library_root):
        try:
            if not p.is_file():
                continue
            if str(p) in picked:
                continue
            subs = pysrt.open(str(p), encoding=encoding)
            for sub in subs:
                t = _norm_ws(sub.text)
                if not t:
                    continue
                merged_lines.append(t)
                total += len(t) + 1
                if total >= max_chars:
                    break
            picked.append(str(p))
            if total >= max_chars:
                break
        except Exception:
            continue

    txt = _safe_join(merged_lines)
    if not txt:
        return "", None
    # If multiple were used, return a joined hint; the caller can store it as meta.
    picked_hint = ", ".join(picked[:6]) if picked else None
    return txt[:max_chars], picked_hint


def build_embedding_documents(
    state: LibraryCanonical,
    *,
    include_subtitles: bool = True,
    library_root: Path | None = None,
    subtitles_max_chars: int = 200_000,
    include_grok_story: bool = True,
) -> List[dict]:
    """
    Returns list of documents:
    - doc_id, kind, text, meta
    """
    meta_block = _format_meta_block(state)
    scenes_block = _format_scenes_block(state.scenes)

    docs: List[dict] = []

    base_meta = {
        "product_code": state.product_code,
        "canonical_schema_version": state.canonical_schema_version,
        "schema_version": state.schema_version,
    }

    # 1. Official Metadata + Scenes
    docs.append(
        {
            "doc_id": f"{state.product_code}::meta_canonical",
            "kind": "meta_canonical",
            "text": _safe_join([meta_block, scenes_block]),
            "meta": {**base_meta, "has_scenes": bool(state.scenes)},
        }
    )

    # 2. Grok Story Context (if exists)
    if include_grok_story:
        try:
            from javstory.config.app_config import library_story_context_batch_tier

            grok = load_cached_grok_json_flexible(
                state.product_code, library_story_context_batch_tier()
            )
            if grok and not grok.get("code_mismatch"):
                grok_lines = ["[grok_story_context]"]
                grok_lines.append(f"Title: {grok.get('title_ko') or grok.get('title_ja')}")
                grok_lines.append(f"Summary: {grok.get('overall_summary')}")
                grok_lines.append(f"Synopsis: {grok.get('synopsis_short')}")
                
                g_scenes = grok.get("scenes") or []
                if isinstance(g_scenes, list):
                    for gs in g_scenes:
                        if not isinstance(gs, dict): continue
                        grok_lines.append(f"- {gs.get('scene_label')}: {gs.get('scene_summary')} (Tags: {', '.join(gs.get('key_tags') or [])})")
                
                docs.append({
                    "doc_id": f"{state.product_code}::grok_story",
                    "kind": "grok_story",
                    "text": _safe_join(grok_lines),
                    "meta": {**base_meta, "source": "grok-4.3-online"},
                })
        except Exception:
            pass

    # 3. Subtitles
    if include_subtitles:
        sub_txt, picked = load_srt_text_for_state(
            state,
            library_root=library_root,
            max_chars=subtitles_max_chars,
        )
        if sub_txt:
            docs.append(
                {
                    "doc_id": f"{state.product_code}::subtitles",
                    "kind": "subtitles",
                    "text": _safe_join(["[subtitles]", sub_txt]),
                    "meta": {**base_meta, "subtitle_path": picked or ""},
                }
            )

    # Optional: one doc per scene (helps retrieval granularity)
    for s in state.scenes:
        scene_text = _safe_join(
            [
                f"[product_code] {state.product_code}",
                f"[scene_id] {s.scene_id}",
                f"[time_range] {s.time_range}",
                f"[scene_label] {s.scene_label}",
                f"[tone] {s.tone}",
                f"[key_tags] {', '.join(s.key_tags or [])}",
                f"[scene_summary] {s.scene_summary}",
            ]
        )
        if scene_text:
            docs.append(
                {
                    "doc_id": f"{state.product_code}::scene::{s.scene_id}",
                    "kind": "scene",
                    "text": scene_text,
                    "meta": {**base_meta, "scene_id": s.scene_id, "start_sec": s.start_sec, "end_sec": s.end_sec},
                }
            )

    # Embed-friendly guard: drop empties
    docs = [d for d in docs if (d.get("text") or "").strip()]
    return docs

