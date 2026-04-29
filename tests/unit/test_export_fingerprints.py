"""파일 지문."""

from __future__ import annotations

from javstory.library.export.fingerprints import (
    build_manifest_fingerprints,
    file_fingerprint,
    manifest_has_drift,
)


def test_file_fingerprint_round_trip(tmp_path) -> None:
    p = tmp_path / "a.bin"
    p.write_bytes(b"hello")
    fp = file_fingerprint(p)
    assert fp is not None
    assert fp["sha256"] == file_fingerprint(p)["sha256"]


def test_manifest_has_drift_detects_change(tmp_path) -> None:
    p = tmp_path / "x.txt"
    p.write_text("a")
    fp = file_fingerprint(p)
    assert fp is not None
    stored = {"k": fp}
    assert manifest_has_drift(stored, {"k": p}) == []
    p.write_text("b")
    assert "k" in manifest_has_drift(stored, {"k": p})


def test_build_manifest_fingerprints_skips_missing(tmp_path) -> None:
    p = tmp_path / "exists.txt"
    p.write_text("ok")
    out = build_manifest_fingerprints({"a": p, "b": tmp_path / "nope.bin"})
    assert "a" in out
    assert "b" not in out
