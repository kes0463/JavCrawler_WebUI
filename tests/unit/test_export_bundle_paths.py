"""ExportBundleConfig 경로 해석."""

from __future__ import annotations

from javstory.library.export.bundle import ExportBundleConfig


def test_resolved_paths_default(tmp_path) -> None:
    c = ExportBundleConfig(project_root=tmp_path)
    assert c.resolved_master_path() == tmp_path / "data" / "derived" / "master_db.js"
    assert c.resolved_story_path("FOO-001") == tmp_path / "data" / "derived" / "stories" / "FOO-001_story_context.json"


def test_resolved_story_unknown_code(tmp_path) -> None:
    c = ExportBundleConfig(project_root=tmp_path)
    p = c.resolved_story_path("   ")
    assert p.name.endswith("_story_context.json")
