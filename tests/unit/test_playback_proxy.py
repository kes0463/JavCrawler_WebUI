"""playback_proxy 단위 테스트."""

from __future__ import annotations

from pathlib import Path

from javstory.library.playback_proxy import (
    ensure_ffmpeg_processing_source,
    is_browser_playable,
    needs_browser_proxy,
    needs_ffmpeg_processing_remux,
    prepare_playback_file,
    proxy_cache_path,
    resolve_playback_file,
)


def test_needs_browser_proxy_by_extension(monkeypatch) -> None:
    monkeypatch.setattr(
        "javstory.library.playback_proxy.is_browser_playable",
        lambda _path: True,
    )
    assert needs_browser_proxy(Path("a.ts")) is True
    assert needs_browser_proxy(Path("a.avi")) is True
    assert needs_browser_proxy(Path("a.mkv")) is True
    assert needs_browser_proxy(Path("a.mp4")) is False
    assert needs_browser_proxy(Path("a.webm")) is False


def test_needs_browser_proxy_hevc_mp4(monkeypatch) -> None:
    monkeypatch.setattr(
        "javstory.library.playback_proxy.is_browser_playable",
        lambda _path: False,
    )
    assert needs_browser_proxy(Path("clip.mp4")) is True


def test_is_browser_playable_from_probe(monkeypatch) -> None:
    monkeypatch.setattr(
        "javstory.library.playback_proxy._ffprobe_json",
        lambda _path: {
            "streams": [
                {"codec_type": "video", "codec_name": "hevc"},
                {"codec_type": "audio", "codec_name": "aac"},
            ]
        },
    )
    assert is_browser_playable(Path("x.mp4")) is False

    monkeypatch.setattr(
        "javstory.library.playback_proxy._ffprobe_json",
        lambda _path: {
            "streams": [
                {"codec_type": "video", "codec_name": "h264"},
                {"codec_type": "audio", "codec_name": "aac"},
            ]
        },
    )
    assert is_browser_playable(Path("x.mp4")) is True


def test_proxy_cache_path_is_stable(tmp_path: Path) -> None:
    source = tmp_path / "clip.ts"
    source.write_bytes(b"x" * 16)
    p1 = proxy_cache_path(source)
    p2 = proxy_cache_path(source)
    assert p1 == p2
    assert p1.name.endswith(".mp4")


def test_prepare_direct_mp4(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"\x00" * 8)
    monkeypatch.setattr(
        "javstory.library.playback_proxy.is_browser_playable",
        lambda _path: True,
    )
    out = prepare_playback_file(source)
    assert out["ready"] is True
    assert out["needs_proxy"] is False
    assert out["status"] == "direct"
    assert resolve_playback_file(source) == source


def test_prepare_ts_starts_building(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "clip.ts"
    source.write_bytes(b"\x00" * 8)
    monkeypatch.setattr(
        "javstory.library.playback_proxy.is_browser_playable",
        lambda path: path.suffix.lower() != ".ts",
    )

    def fake_worker(source: Path, proxy: Path, key: str) -> None:
        proxy.parent.mkdir(parents=True, exist_ok=True)
        proxy.write_bytes(b"fake mp4")

    monkeypatch.setattr(
        "javstory.library.playback_proxy._run_proxy_job",
        fake_worker,
    )

    out = prepare_playback_file(source)
    assert out["needs_proxy"] is True
    assert out["status"] == "building"

    import time

    deadline = time.time() + 3
    while time.time() < deadline:
        if resolve_playback_file(source):
            break
        time.sleep(0.05)

    assert resolve_playback_file(source) is not None


def test_stale_proxy_cache_not_ready(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "clip.ts"
    source.write_bytes(b"\x00" * 8)
    proxy = proxy_cache_path(source)
    proxy.parent.mkdir(parents=True, exist_ok=True)
    proxy.write_bytes(b"bad")

    playable = {proxy: False, source: False}

    def _playable(path: Path) -> bool:
        return playable.get(path, False)

    monkeypatch.setattr(
        "javstory.library.playback_proxy.is_browser_playable",
        _playable,
    )
    assert resolve_playback_file(source) is None


def test_needs_ffmpeg_processing_remux() -> None:
    assert needs_ffmpeg_processing_remux(Path("a.ts")) is True
    assert needs_ffmpeg_processing_remux(Path("a.mp4")) is False


def test_ensure_ffmpeg_processing_source_passthrough_mp4(tmp_path: Path) -> None:
    mp4 = tmp_path / "clip.mp4"
    mp4.write_bytes(b"\x00" * 8)
    assert ensure_ffmpeg_processing_source(mp4) == mp4


def test_ensure_ffmpeg_processing_source_builds_ts_cache(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "clip.ts"
    source.write_bytes(b"\x00" * 16)

    def fake_build(_src, tmp):
        tmp.write_bytes(b"mp4")
        return True, "ok"

    monkeypatch.setattr(
        "javstory.library.playback_proxy._build_proxy_for_processing",
        fake_build,
    )
    monkeypatch.setattr(
        "javstory.library.playback_proxy._probe_duration_sec",
        lambda path, timeout=30: 120.0 if path.suffix.lower() == ".mp4" else 0.0,
    )

    resolved = ensure_ffmpeg_processing_source(source)
    assert resolved is not None
    assert resolved.suffix.lower() == ".mp4"
    assert resolved.is_file()
    assert ensure_ffmpeg_processing_source(source) == resolved


def test_proxy_file_ready_duration_fallback(tmp_path: Path, monkeypatch) -> None:
    from javstory.library.playback_proxy import _proxy_file_ready

    proxy = tmp_path / "out.mp4"
    proxy.write_bytes(b"x" * 1024)
    monkeypatch.setattr(
        "javstory.library.playback_proxy.is_browser_playable",
        lambda _path: False,
    )
    monkeypatch.setattr(
        "javstory.library.playback_proxy._probe_duration_sec",
        lambda _path, timeout=30: 120.0,
    )
    assert _proxy_file_ready(proxy) is True


def test_prepare_returns_failed_without_restart(tmp_path: Path, monkeypatch) -> None:
    from javstory.library import playback_proxy as pp

    source = tmp_path / "clip.avi"
    source.write_bytes(b"\x00" * 8)
    key = pp._job_key(source)
    pp._JOBS[key] = {"status": "failed", "error": "test fail"}

    monkeypatch.setattr(pp, "needs_browser_proxy", lambda _p: True)
    monkeypatch.setattr(pp, "proxy_is_ready", lambda _p: False)

    out = pp.prepare_playback_file(source)
    assert out["status"] == "failed"
    assert "test fail" in (out.get("error") or "")
