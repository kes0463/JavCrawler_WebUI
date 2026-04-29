"""canonical → master_db.js · story JSON 일괄 내보내기 및 manifest 갱신."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from javstory.library.canonical.schema import (
    DEFAULT_EXPORT_VERSION,
    ExportManifest,
    LibraryCanonical,
    SceneEntry,
    utc_now_iso,
)
from javstory.library.export.fingerprints import build_manifest_fingerprints
from javstory.library.export.master_js import (
    canonical_to_master_entries,
    load_master_db_js,
    merge_master_entries_for_source,
    write_master_db_js,
)
from javstory.library.export.story_export import write_story_context_json


def _try_relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


@dataclass
class ExportBundleConfig:
    """기본값은 JAVSTORY 웹 SPA(`index.html`)가 읽는 `data/derived/` 레이아웃."""

    project_root: Path
    master_db_path: Path | None = None
    story_json_path: Path | None = None
    merge_into_master_db: bool = True
    video_src: str = ""
    video_duration: float = 0.0
    video_fps: float | None = None
    thumb_resolver: Callable[[SceneEntry], str | None] | None = None

    def resolved_master_path(self) -> Path:
        return self.master_db_path or (self.project_root / "data" / "derived" / "master_db.js")

    def resolved_story_path(self, product_code: str) -> Path:
        if self.story_json_path is not None:
            return self.story_json_path
        code = (product_code or "").strip() or "UNKNOWN"
        return self.project_root / "data" / "derived" / "stories" / f"{code}_story_context.json"


def export_canonical_bundle(state: LibraryCanonical, config: ExportBundleConfig) -> LibraryCanonical:
    """
    story JSON·master_db.js를 쓰고, export_manifest(지문)를 state에 채워 반환한다.
    호출 측에서 save_library_state로 canonical을 저장하는 것을 권장한다.
    """
    pr = Path(config.project_root)
    code = (state.product_code or "").strip() or "UNKNOWN"
    story_path = config.resolved_story_path(code)
    master_path = config.resolved_master_path()

    write_story_context_json(story_path, state)

    new_entries = canonical_to_master_entries(
        state,
        video_src=config.video_src,
        video_duration=config.video_duration,
        video_fps=config.video_fps,
        thumb_resolver=config.thumb_resolver,
    )

    if config.merge_into_master_db and master_path.is_file():
        try:
            existing, _meta = load_master_db_js(master_path)
        except (OSError, ValueError):
            existing = []
        entries = merge_master_entries_for_source(existing, new_entries, source=code)
    else:
        entries = new_entries

    write_master_db_js(master_path, entries)

    fp_map: dict[str, Path] = {
        "story_json": story_path,
        "master_db": master_path,
    }
    fingerprints = build_manifest_fingerprints(fp_map)

    em = ExportManifest(
        export_version=DEFAULT_EXPORT_VERSION,
        generated_at=utc_now_iso(),
        story_json_relpath=_try_relative(story_path, pr),
        master_db_relpath=_try_relative(master_path, pr),
        file_fingerprints=fingerprints,
    )
    out = replace(state, export_manifest=em)
    out.touch()
    return out


def fingerprint_paths_from_manifest(state: LibraryCanonical, project_root: Path) -> dict[str, Path]:
    """manifest의 relpath를 절대 경로로 복원(검사용)."""
    em = state.export_manifest
    if not em:
        return {}
    pr = Path(project_root).resolve()
    out: dict[str, Path] = {}
    if em.story_json_relpath:
        p = Path(em.story_json_relpath)
        if p.is_absolute():
            out["story_json"] = p
        else:
            out["story_json"] = (pr / p).resolve()
    if em.master_db_relpath:
        p = Path(em.master_db_relpath)
        if p.is_absolute():
            out["master_db"] = p
        else:
            out["master_db"] = (pr / p).resolve()
    return out
