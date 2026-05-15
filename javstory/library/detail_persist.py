"""라이브러리 상세 메타 저장 — jav_metadata + library_state.json + Grok 캐시 JSON 동기화."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from javstory.library.canonical.schema import LibraryCanonical, SceneEntry


def merge_scene_edit_with_previous(previous: list[SceneEntry], edited: list[SceneEntry]) -> list[SceneEntry]:
    """
    편집된 씬 목록을 저장할 때, 동일 scene_id의 기존 스틸 경로·잠금을 가능하면 유지.
    time_range 가 바뀌면 스틸은 비우고 재추출 플래그(needs_still_refresh) 유사 동작을 위해 still_paths 비움.
    """
    prev_map = {s.scene_id: s for s in previous}
    merged: list[SceneEntry] = []
    for n in edited:
        o = prev_map.get(n.scene_id)
        if not o:
            merged.append(n)
            continue
        time_same = (o.time_range or "").strip() == (n.time_range or "").strip()
        if time_same:
            merged.append(
                replace(
                    n,
                    still_paths=list(o.still_paths),
                    locked_fields=set(o.locked_fields),
                    needs_still_refresh=o.needs_still_refresh,
                )
            )
        else:
            merged.append(
                replace(
                    n,
                    still_paths=[],
                    locked_fields=set(o.locked_fields),
                    needs_still_refresh=True,
                )
            )
    return merged
from javstory.library.canonical.store import load_library_state, save_library_state
from javstory.library.export.story_export import (
    canonical_from_story_context_file_dict,
    read_story_context_json,
    write_story_context_json,
)
from javstory.library.paths import library_state_path


def resolve_story_json_paths(product_code: str) -> list[Path]:
    """캐노니컬 동기화 대상 story JSON 경로. 현행 `{품번}_grok.json` 최우선, 레거시는 파일이 있을 때만."""
    from javstory.translation.story_grok_module import (
        merge_story_context_tier,
        story_context_cache_path,
        story_context_cache_path_grok,
        story_context_cache_dir,
    )

    pc = (product_code or "").strip().upper()
    tier = merge_story_context_tier(None)
    model_hint = str(tier.get("model") or "").strip()
    paths: list[Path] = []
    primary = story_context_cache_path_grok(pc)
    paths.append(primary)

    p1 = story_context_cache_path(pc, model_hint)
    p2 = story_context_cache_path(pc, "")
    for p in (p1, p2):
        if p.is_file() and p not in paths:
            paths.append(p)

    stem = primary.stem
    pc_san = stem[:-5] if stem.endswith("_grok") else stem
    try:
        d = story_context_cache_dir()
        for p in sorted(d.glob(f"{pc_san}__*.json")):
            if p.is_file() and p not in paths:
                paths.append(p)
    except OSError:
        pass

    return paths


def load_canonical_for_product(product_code: str) -> LibraryCanonical:
    """library_state.json 우선, 없으면 Grok 캐시 JSON, 없으면 빈 캐노니컬."""
    pc = (product_code or "").strip().upper()
    ls = library_state_path(pc)
    if ls.is_file():
        return load_library_state(ls)

    for gp in resolve_story_json_paths(pc):
        if gp.is_file():
            try:
                data = read_story_context_json(gp)
                return canonical_from_story_context_file_dict(data)
            except (OSError, ValueError, TypeError):
                continue

    return LibraryCanonical(product_code=pc)


def apply_jav_metadata_row_to_canonical_meta(state: LibraryCanonical, row: Any) -> LibraryCanonical:
    """SQLAlchemy JAVMetadata 행 → 캐노니컬 작품 단위 필드만 갱신(씬 배열 유지)."""
    synopsis = (getattr(row, "synopsis_ko", None) or getattr(row, "synopsis", None) or "").strip()
    short = synopsis if len(synopsis) <= 16000 else synopsis[:16000]

    return replace(
        state,
        title_ko=(getattr(row, "title_ko", None) or getattr(row, "title", None) or "").strip(),
        title_ja=(getattr(row, "title_ja", None) or getattr(row, "original_title", None) or "").strip(),
        actress=(getattr(row, "actors_ko", None) or getattr(row, "actors", None) or "").strip(),
        maker=(getattr(row, "maker_ko", None) or getattr(row, "maker", None) or "").strip(),
        release_date=(getattr(row, "release_date", None) or "").strip(),
        synopsis_short=short,
    )


def persist_metadata_row_and_sync_files(
    product_code: str,
    row: Any,
    *,
    scenes_override: list[SceneEntry] | None = None,
    translation_note_override: str | None = None,
) -> None:
    """
    DB 행이 이미 커밋된 뒤 호출 — library_state.json 및 모든 후보 Grok 캐시 JSON에 동일 캐노니컬 반영.
    scenes_override가 있으면 씬 배열을 통째로 교체(편집 세션 저장).
    translation_note_override가 None이 아니면 작품 단위 번역 노트도 교체.
    """
    pc = (product_code or "").strip().upper()
    state = load_canonical_for_product(pc)
    state = apply_jav_metadata_row_to_canonical_meta(state, row)
    state.product_code = pc
    if scenes_override is not None:
        merged = merge_scene_edit_with_previous(state.scenes, list(scenes_override))
        state = replace(state, scenes=merged)
    if translation_note_override is not None:
        state = replace(state, translation_note=str(translation_note_override or ""))

    ls_path = library_state_path(pc)
    ls_path.parent.mkdir(parents=True, exist_ok=True)
    save_library_state(ls_path, state)

    for gp in resolve_story_json_paths(pc):
        gp.parent.mkdir(parents=True, exist_ok=True)
        write_story_context_json(gp, state)

    # Optional: meta+canonical(+subtitles) → Ollama embeddings cache
    # - Keep it opt-in to avoid unexpected heavy work during normal saves.
    try:
        from javstory.library.embeddings.pipeline import embeddings_enabled_from_env

        if embeddings_enabled_from_env():
            import asyncio
            import threading

            from javstory.library.embeddings.pipeline import build_and_store_embeddings_for_product

            def _run_embedding():
                try:
                    asyncio.run(
                        build_and_store_embeddings_for_product(
                            pc,
                            state=state,
                            include_subtitles=True,
                            logger_func=None,
                        )
                    )
                except Exception:
                    pass

            # Sync context: run a small async task. 
            # UI(MainThread)에서 호출된 경우 Ollama 호출이 수 초간 멈추므로 무조건 스레드로 분리한다.
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    loop.create_task(
                        build_and_store_embeddings_for_product(
                            pc,
                            state=state,
                            include_subtitles=True,
                            logger_func=None,
                        )
                    )
                else:
                    threading.Thread(target=_run_embedding, daemon=True).start()
            except RuntimeError:
                # No running loop (likely main thread or a worker thread)
                threading.Thread(target=_run_embedding, daemon=True).start()
    except Exception:
        pass


def persist_scenes_only(product_code: str, scenes: list[SceneEntry]) -> None:
    """메타 DB는 건드리지 않고 씬 배열만 반영 — library_state + Grok 캐시."""
    pc = (product_code or "").strip().upper()
    state = load_canonical_for_product(pc)
    merged = merge_scene_edit_with_previous(state.scenes, list(scenes))
    state = replace(state, scenes=merged)
    state.product_code = pc

    ls_path = library_state_path(pc)
    ls_path.parent.mkdir(parents=True, exist_ok=True)
    save_library_state(ls_path, state)

    for gp in resolve_story_json_paths(pc):
        gp.parent.mkdir(parents=True, exist_ok=True)
        write_story_context_json(gp, state)
