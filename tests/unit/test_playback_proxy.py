"""playback_proxy 단위 테스트."""

from __future__ import annotations

from pathlib import Path

from javstory.library.playback_proxy import (
    _proxy_hls_ready,
    clear_proxy_cache,
    ensure_ffmpeg_processing_source,
    evict_proxy_cache,
    invalidate_stream_resolve_cache,
    is_browser_playable,
    is_fragmented_mp4,
    needs_browser_proxy,
    needs_browser_proxy_cached,
    needs_ffmpeg_processing_remux,
    prepare_playback_file,
    proxy_cache_path,
    proxy_hls_dir,
    resolve_hls_dir_for_stream,
    resolve_playback_file,
    resolve_playback_file_for_stream,
)


def _write_hls_dir(hls_dir: Path) -> None:
    hls_dir.mkdir(parents=True, exist_ok=True)
    (hls_dir / "playlist.m3u8").write_text(
        "#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:4.0,\nseg_00000.ts\n#EXT-X-ENDLIST\n",
        encoding="utf-8",
    )
    (hls_dir / "seg_00000.ts").write_bytes(b"fake ts")


def test_proxy_reason_hevc(monkeypatch) -> None:
    monkeypatch.setattr(
        "javstory.library.playback_proxy.is_fragmented_mp4",
        lambda _path: False,
    )
    monkeypatch.setattr(
        "javstory.library.playback_proxy._ffprobe_json",
        lambda _path: {
            "streams": [
                {"codec_type": "video", "codec_name": "hevc"},
                {"codec_type": "audio", "codec_name": "aac"},
            ]
        },
    )
    from javstory.library.playback_proxy import proxy_reason

    assert proxy_reason(Path("clip.mp4")) == "hevc"


def test_h264_transcode_plans_includes_software_fallback(monkeypatch) -> None:
    from javstory.library.playback_proxy import _h264_transcode_plans

    monkeypatch.setattr(
        "javstory.library.playback_proxy._hw_encode_enabled",
        lambda: False,
    )
    monkeypatch.setattr(
        "javstory.library.playback_proxy._hls_quality_mode",
        lambda: "fast",
    )
    plans = _h264_transcode_plans()
    assert len(plans) == 1
    assert plans[0][0] == "libx264"
    assert "-crf" in plans[0][2]
    assert "23" in plans[0][2]


def test_can_hls_stream_copy_h264_ts(monkeypatch) -> None:
    from javstory.library.playback_proxy import _can_hls_stream_copy

    monkeypatch.setattr(
        "javstory.library.playback_proxy._source_codecs",
        lambda _path: ("h264", "aac"),
    )
    assert _can_hls_stream_copy(Path("clip.ts")) is True


def test_can_hls_stream_copy_rejects_hevc(monkeypatch) -> None:
    from javstory.library.playback_proxy import _can_hls_stream_copy

    monkeypatch.setattr(
        "javstory.library.playback_proxy._source_codecs",
        lambda _path: ("hevc", "aac"),
    )
    assert _can_hls_stream_copy(Path("clip.mp4")) is False


def test_build_proxy_prefers_hls_remux(monkeypatch, tmp_path: Path) -> None:
    from javstory.library.playback_proxy import _build_proxy

    source = tmp_path / "clip.ts"
    source.write_bytes(b"\x00" * 8)
    tmp_dir = tmp_path / "out"
    calls: list[str] = []

    def fake_remux(_src, _tmp, **kwargs):
        calls.append("remux")
        _write_hls_dir(_tmp)
        return True, "ok"

    def fake_transcode(_src, _tmp, **kwargs):
        calls.append("transcode")
        return False, "should not run"

    monkeypatch.setattr(
        "javstory.library.playback_proxy._can_hls_stream_copy",
        lambda _path: True,
    )
    monkeypatch.setattr(
        "javstory.library.playback_proxy._remux_to_hls_copy",
        fake_remux,
    )
    monkeypatch.setattr(
        "javstory.library.playback_proxy._transcode_to_hls",
        fake_transcode,
    )
    ok, _log = _build_proxy(source, tmp_dir)
    assert ok is True
    assert calls == ["remux"]


def test_needs_browser_proxy_by_extension(monkeypatch) -> None:
    monkeypatch.setattr(
        "javstory.library.playback_proxy.is_browser_playable",
        lambda _path: True,
    )
    monkeypatch.setattr(
        "javstory.library.playback_proxy.is_fragmented_mp4",
        lambda _path: False,
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
    monkeypatch.setattr(
        "javstory.library.playback_proxy.is_fragmented_mp4",
        lambda _path: False,
    )
    assert needs_browser_proxy(Path("clip.mp4")) is True


def test_needs_browser_proxy_fragmented_mp4(monkeypatch) -> None:
    monkeypatch.setattr(
        "javstory.library.playback_proxy.is_browser_playable",
        lambda _path: True,
    )
    monkeypatch.setattr(
        "javstory.library.playback_proxy.is_fragmented_mp4",
        lambda _path: True,
    )
    assert needs_browser_proxy(Path("clip.mp4")) is True


def test_is_fragmented_mp4_detects_multiple_mdat(tmp_path: Path) -> None:
    data = bytearray()
    data += (16).to_bytes(4, "big") + b"ftyp" + b"isom" + (0).to_bytes(4, "big")
    data += (32).to_bytes(4, "big") + b"moov" + b"\x00" * 24
    for _ in range(3):
        data += (24).to_bytes(4, "big") + b"mdat" + b"\x00" * 16
    path = tmp_path / "frag.mp4"
    path.write_bytes(data)
    assert is_fragmented_mp4(path) is True


def test_is_fragmented_mp4_normal_single_mdat(tmp_path: Path) -> None:
    data = bytearray()
    data += (16).to_bytes(4, "big") + b"ftyp" + b"isom" + (0).to_bytes(4, "big")
    data += (32).to_bytes(4, "big") + b"moov" + b"\x00" * 24
    data += (40).to_bytes(4, "big") + b"mdat" + b"\x00" * 32
    path = tmp_path / "ok.mp4"
    path.write_bytes(data)
    assert is_fragmented_mp4(path) is False


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


def test_proxy_hls_dir_is_stable(tmp_path: Path, monkeypatch) -> None:
    cache_root = tmp_path / "cache"
    monkeypatch.setattr(
        "javstory.library.playback_proxy.proxy_cache_dir",
        lambda: cache_root,
    )
    source = tmp_path / "clip.ts"
    source.write_bytes(b"x" * 16)
    p1 = proxy_hls_dir(source)
    p2 = proxy_hls_dir(source)
    assert p1 == p2
    assert p1.parent == cache_root


def test_proxy_cache_path_returns_hls_directory(tmp_path: Path, monkeypatch) -> None:
    cache_root = tmp_path / "cache"
    monkeypatch.setattr(
        "javstory.library.playback_proxy.proxy_cache_dir",
        lambda: cache_root,
    )
    source = tmp_path / "clip.ts"
    source.write_bytes(b"x" * 16)
    path = proxy_cache_path(source)
    assert path.parent == cache_root
    assert not path.suffix


def test_proxy_hls_ready_requires_playlist_and_segment(tmp_path: Path) -> None:
    hls_dir = tmp_path / "hls"
    assert _proxy_hls_ready(hls_dir) is False
    hls_dir.mkdir()
    (hls_dir / "playlist.m3u8").write_text("#EXTM3U\n", encoding="utf-8")
    assert _proxy_hls_ready(hls_dir) is False
    _write_hls_dir(hls_dir)
    assert _proxy_hls_ready(hls_dir) is True


def test_prepare_direct_mp4(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"\x00" * 8)
    monkeypatch.setattr(
        "javstory.library.playback_proxy.is_browser_playable",
        lambda _path: True,
    )
    monkeypatch.setattr(
        "javstory.library.playback_proxy.is_fragmented_mp4",
        lambda _path: False,
    )
    out = prepare_playback_file(source)
    assert out["ready"] is True
    assert out["needs_proxy"] is False
    assert out["status"] == "direct"
    assert resolve_playback_file(source) == source


def test_prepare_ts_starts_building(tmp_path: Path, monkeypatch) -> None:
    cache_root = tmp_path / "cache"
    monkeypatch.setattr(
        "javstory.library.playback_proxy.proxy_cache_dir",
        lambda: cache_root,
    )
    source = tmp_path / "clip.ts"
    source.write_bytes(b"\x00" * 8)
    monkeypatch.setattr(
        "javstory.library.playback_proxy.is_browser_playable",
        lambda path: path.suffix.lower() != ".ts",
    )

    def fake_worker(source: Path, hls_dir: Path, key: str) -> None:
        _write_hls_dir(hls_dir)

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

    resolved = resolve_playback_file(source)
    assert resolved is not None
    assert _proxy_hls_ready(resolved)


def test_stale_proxy_cache_not_ready(tmp_path: Path, monkeypatch) -> None:
    cache_root = tmp_path / "cache"
    monkeypatch.setattr(
        "javstory.library.playback_proxy.proxy_cache_dir",
        lambda: cache_root,
    )
    source = tmp_path / "clip.ts"
    source.write_bytes(b"\x00" * 8)
    hls_dir = proxy_hls_dir(source)
    hls_dir.mkdir(parents=True)
    (hls_dir / "playlist.m3u8").write_text("", encoding="utf-8")

    monkeypatch.setattr(
        "javstory.library.playback_proxy.is_browser_playable",
        lambda _path: False,
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
    cache_root = tmp_path / "cache"
    monkeypatch.setattr(
        "javstory.library.playback_proxy.proxy_cache_dir",
        lambda: cache_root,
    )
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


def test_resolve_playback_file_for_stream_skips_ffprobe_on_cache_hit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    invalidate_stream_resolve_cache()
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"\x00" * 64)
    calls = {"n": 0}

    def _needs(_path: Path) -> bool:
        calls["n"] += 1
        return False

    monkeypatch.setattr(
        "javstory.library.playback_proxy.needs_browser_proxy",
        _needs,
    )
    assert resolve_playback_file_for_stream(source) == source
    assert resolve_playback_file_for_stream(source) == source
    assert calls["n"] == 1


def test_resolve_playback_file_for_stream_proxy_returns_none(
    tmp_path: Path,
    monkeypatch,
) -> None:
    invalidate_stream_resolve_cache()
    source = tmp_path / "clip.ts"
    source.write_bytes(b"\x00" * 64)
    hls_dir = tmp_path / "hls"
    _write_hls_dir(hls_dir)

    monkeypatch.setattr(
        "javstory.library.playback_proxy.needs_browser_proxy_cached",
        lambda _p: True,
    )
    assert resolve_playback_file_for_stream(source) is None
    assert resolve_playback_file_for_stream(source) is None


def test_resolve_hls_dir_for_stream_stat_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    invalidate_stream_resolve_cache()
    cache_root = tmp_path / "cache"
    monkeypatch.setattr(
        "javstory.library.playback_proxy.proxy_cache_dir",
        lambda: cache_root,
    )
    source = tmp_path / "clip.ts"
    source.write_bytes(b"\x00" * 64)
    hls_dir = proxy_hls_dir(source)
    _write_hls_dir(hls_dir)

    ffprobe_calls = {"n": 0}

    def _ffprobe(_path: Path):
        ffprobe_calls["n"] += 1
        return None

    monkeypatch.setattr(
        "javstory.library.playback_proxy.needs_browser_proxy_cached",
        lambda _p: True,
    )
    monkeypatch.setattr(
        "javstory.library.playback_proxy._ffprobe_json",
        _ffprobe,
    )

    assert resolve_hls_dir_for_stream(source) == hls_dir
    assert resolve_hls_dir_for_stream(source) == hls_dir
    assert ffprobe_calls["n"] == 0


def test_clear_and_evict_hls_directories(tmp_path: Path, monkeypatch) -> None:
    cache_root = tmp_path / "cache"
    monkeypatch.setattr(
        "javstory.library.playback_proxy.proxy_cache_dir",
        lambda: cache_root,
    )
    monkeypatch.setattr(
        "javstory.library.playback_proxy.cache_max_bytes",
        lambda: 100,
    )
    hls_a = cache_root / "aaa"
    hls_b = cache_root / "bbb"
    _write_hls_dir(hls_a)
    _write_hls_dir(hls_b)

    evicted = evict_proxy_cache()
    assert evicted["evicted"] >= 1
    assert evicted["total_bytes"] <= 100

    _write_hls_dir(hls_a)
    cleared = clear_proxy_cache()
    assert cleared["removed"] >= 1
    assert not list(cache_root.glob("*/playlist.m3u8"))


def test_needs_browser_proxy_cached_reuses_result(tmp_path: Path, monkeypatch) -> None:
    invalidate_stream_resolve_cache()
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x" * 8)
    calls = {"n": 0}

    def _needs(_path: Path) -> bool:
        calls["n"] += 1
        return True

    monkeypatch.setattr(
        "javstory.library.playback_proxy.needs_browser_proxy",
        _needs,
    )
    assert needs_browser_proxy_cached(source) is True
    assert needs_browser_proxy_cached(source) is True
    assert calls["n"] == 1
