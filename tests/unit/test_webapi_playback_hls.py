"""webapi playback HLS route tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from webapi.routes import playback as playback_mod


def _write_hls_dir(hls_dir: Path) -> None:
    hls_dir.mkdir(parents=True, exist_ok=True)
    (hls_dir / "playlist.m3u8").write_text(
        "#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:4.0,\nseg_00000.ts\n#EXT-X-ENDLIST\n",
        encoding="utf-8",
    )
    (hls_dir / "seg_00000.ts").write_bytes(b"fake ts segment")


@pytest.fixture
def hls_client(tmp_path: Path, monkeypatch):
    hls_dir = tmp_path / "hls"
    _write_hls_dir(hls_dir)

    class FakePlayback:
        def resolve_hls_playlist(self, code: str, part: int):
            if code.upper() == "TST-001" and part == 0:
                return hls_dir / "playlist.m3u8"
            return None

        def resolve_hls_segment(self, code: str, part: int, segment_name: str):
            if code.upper() != "TST-001" or part != 0:
                return None
            path = hls_dir / segment_name
            return path if path.is_file() else None

        def prepare_stream(self, _code: str, _part: int):
            return {"status": "building", "needs_proxy": True}

    monkeypatch.setattr(playback_mod, "_playback", FakePlayback())
    app = FastAPI()
    app.include_router(playback_mod.router, prefix="/api/playback")
    return TestClient(app)


def test_hls_playlist_route(hls_client: TestClient) -> None:
    r = hls_client.get("/api/playback/TST-001/hls/0/index.m3u8")
    assert r.status_code == 200
    assert "mpegurl" in r.headers.get("content-type", "")
    assert "#EXTM3U" in r.text


def test_hls_segment_route(hls_client: TestClient) -> None:
    r = hls_client.get("/api/playback/TST-001/hls/0/seg_00000.ts")
    assert r.status_code == 200
    assert "mp2t" in r.headers.get("content-type", "")
    assert r.content == b"fake ts segment"
