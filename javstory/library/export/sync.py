"""내보낸 파일 직접 수정 감지 및 canonical과의 동기화 선택."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from javstory.library.canonical.schema import LibraryCanonical
from javstory.library.export.bundle import ExportBundleConfig, export_canonical_bundle, fingerprint_paths_from_manifest
from javstory.library.export.fingerprints import file_fingerprint
from javstory.library.export.story_export import (
    merge_story_file_into_canonical,
    read_story_context_json,
    story_file_wins_canonical,
)


@dataclass
class ExportDrift:
    """한 산출물에 대한 기대 지문 vs 현재 디스크."""

    key: str
    path: Path
    stored_sha256: str | None
    current_sha256: str | None
    file_exists: bool


def list_export_drift(
    state: LibraryCanonical,
    project_root: Path | str,
    *,
    extra_paths: dict[str, Path] | None = None,
) -> list[ExportDrift]:
    """
    마지막 export 이후 디스크 파일이 바뀌었는지 검사.
    manifest가 없거나 지문이 비어 있으면 빈 목록(검사 불가).
    """
    em = state.export_manifest
    if not em or not em.file_fingerprints:
        return []

    pr = Path(project_root)
    resolved = fingerprint_paths_from_manifest(state, pr)
    if extra_paths:
        for k, p in extra_paths.items():
            resolved[str(k)] = Path(p).resolve()

    out: list[ExportDrift] = []
    for key, prev_fp in em.file_fingerprints.items():
        path = resolved.get(key)
        if path is None:
            continue
        cur = file_fingerprint(path)
        prev_hash = prev_fp.get("sha256") if isinstance(prev_fp, dict) else None
        cur_hash = cur.get("sha256") if cur else None
        if prev_hash == cur_hash:
            continue
        out.append(
            ExportDrift(
                key=key,
                path=path,
                stored_sha256=prev_hash,
                current_sha256=cur_hash,
                file_exists=cur is not None,
            )
        )
    return out


class ExportSyncChoice(str, Enum):
    """GUI에서 사용자 선택에 매핑."""

    REEXPORT_FROM_CANONICAL = "reexport_from_canonical"
    MERGE_STORY_FILE_INTO_CANONICAL = "merge_story_file_into_canonical"
    REPLACE_CANONICAL_FROM_STORY_FILE = "replace_canonical_from_story_file"


def apply_export_sync_choice(
    state: LibraryCanonical,
    config: ExportBundleConfig,
    choice: ExportSyncChoice,
    *,
    story_json_path: Path | None = None,
) -> LibraryCanonical:
    """
    drift 확인 후 사용자가 고른 동기화 방향 적용.

    - REEXPORT_FROM_CANONICAL: canonical 기준으로 story·master_db 다시 씀.
    - MERGE_STORY_FILE_INTO_CANONICAL: 디스크 story JSON을 merge_grok_draft 규칙으로 반영(+스틸 경로).
    - REPLACE_CANONICAL_FROM_STORY_FILE: story JSON만 신뢰(잠금 포함 전부 파일 기준).
    """
    sp = story_json_path or config.resolved_story_path(state.product_code)
    if choice == ExportSyncChoice.REEXPORT_FROM_CANONICAL:
        return export_canonical_bundle(state, config)

    data = read_story_context_json(sp)
    if choice == ExportSyncChoice.MERGE_STORY_FILE_INTO_CANONICAL:
        merged = merge_story_file_into_canonical(state, data)
        return export_canonical_bundle(merged, config)

    if choice == ExportSyncChoice.REPLACE_CANONICAL_FROM_STORY_FILE:
        fresh = story_file_wins_canonical(data)
        fresh = _preserve_timestamps_and_created(state, fresh)
        return export_canonical_bundle(fresh, config)

    raise ValueError(f"지원하지 않는 선택: {choice}")


def _preserve_timestamps_and_created(previous: LibraryCanonical, new: LibraryCanonical) -> LibraryCanonical:
    from dataclasses import replace

    return replace(
        new,
        created_at=previous.created_at or new.created_at,
    )


def has_export_drift(state: LibraryCanonical, project_root: Path | str) -> bool:
    return bool(list_export_drift(state, project_root))
