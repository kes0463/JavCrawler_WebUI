"""
JAVSTORY 라이브러리 패키지 — canonical 저장·Grok 병합·스틸·export 지문.

GUI·스크립트는 이 모듈의 공개 API만 사용하는 것을 권장한다.
"""

from javstory.library import paths
from javstory.library.canonical import (
    CANONICAL_SCHEMA_VERSION,
    DEFAULT_EXPORT_VERSION,
    ExportManifest,
    LibraryCanonical,
    MediaBinding,
    SceneEntry,
    VideoPartRef,
    grok_story_dict_from_canonical,
    library_canonical_from_grok_dict,
    load_library_state,
    save_library_state,
)
from javstory.library.export import (
    ExportBundleConfig,
    ExportDrift,
    ExportSyncChoice,
    apply_export_sync_choice,
    build_manifest_fingerprints,
    export_canonical_bundle,
    file_fingerprint,
    has_export_drift,
    list_export_drift,
    manifest_has_drift,
)
from javstory.library.grok_merge import merge_grok_draft
from javstory.library.stills import equal_split_seconds, parse_time_range

__all__ = [
    "paths",
    "CANONICAL_SCHEMA_VERSION",
    "DEFAULT_EXPORT_VERSION",
    "ExportManifest",
    "LibraryCanonical",
    "MediaBinding",
    "VideoPartRef",
    "SceneEntry",
    "grok_story_dict_from_canonical",
    "library_canonical_from_grok_dict",
    "load_library_state",
    "save_library_state",
    "ExportBundleConfig",
    "ExportDrift",
    "ExportSyncChoice",
    "apply_export_sync_choice",
    "build_manifest_fingerprints",
    "export_canonical_bundle",
    "file_fingerprint",
    "has_export_drift",
    "list_export_drift",
    "manifest_has_drift",
    "merge_grok_draft",
    "equal_split_seconds",
    "parse_time_range",
]
