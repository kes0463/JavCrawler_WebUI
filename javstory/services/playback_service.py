"""WebUI / playback: video path resolution and safe media access."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from javstory.harvest.database import WatchHistory, get_db_session_ctx
from javstory.harvest.product_repository import resolve_video_paths_for_playback
from javstory.library.multipart.detect import sort_video_parts
from javstory.library.playback_proxy import (
    ensure_hls_segment,
    needs_browser_proxy,
    prepare_playback_file,
    proxy_is_ready,
    proxy_reason,
    resolve_hls_dir_for_stream,
    resolve_playback_file,
    resolve_playback_file_for_stream,
)
from javstory.library.subtitle_parser import find_subtitle_files, load_subtitle_cues
from javstory.library.video_ext import is_video_file
from javstory.services.library_service import LibraryService

_VIDEO_MIME = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
    ".wmv": "video/x-ms-wmv",
    ".ts": "video/mp2t",
}


def _normalize_watch_key(video_path: str) -> str:
    if not (video_path or "").strip():
        return ""
    try:
        return str(Path(video_path).resolve()).replace("\\", "/").lower()
    except OSError:
        return str(video_path).strip().replace("\\", "/").lower()


def _resume_ms(product_code: str, video_path: str) -> int:
    pc = (product_code or "").strip().upper()
    if not pc:
        return 0
    try:
        with get_db_session_ctx() as session:
            row = session.query(WatchHistory).filter_by(product_code=pc).first()
            if not row:
                return 0
            key = _normalize_watch_key(video_path)
            raw = getattr(row, "last_positions_json", None)
            if key and raw:
                try:
                    data = json.loads(raw)
                    if isinstance(data, dict) and key in data:
                        return int(data[key])
                except (TypeError, ValueError, json.JSONDecodeError):
                    pass
            return int(row.last_position or 0)
    except Exception:
        return 0


def guess_video_mime(path: Path) -> str:
    return _VIDEO_MIME.get(path.suffix.lower(), "application/octet-stream")


class PlaybackService:
    _part_path_cache: dict[tuple[str, int], tuple[str, float, int, Path]] = {}

    def __init__(self) -> None:
        self._library = LibraryService()

    def _sorted_paths(self, product_code: str, folder_path: str | None) -> list[Path]:
        paths = resolve_video_paths_for_playback(product_code, folder_path)
        return sort_video_parts([p.resolve() for p in paths if p.is_file()])

    def playback_info(self, product_code: str) -> Optional[dict[str, Any]]:
        pc = (product_code or "").strip().upper()
        if not pc:
            return None
        row = self._library.get_by_code(pc)
        folder = (row.folder_path or "").strip() if row else ""
        paths = self._sorted_paths(pc, folder or None)
        if not paths:
            return None
        title = ""
        if row:
            title = (row.title_ko or row.title_ja or "").strip()
        parts = []
        for idx, path in enumerate(paths):
            tracks = find_subtitle_files(str(path))
            needs_proxy = needs_browser_proxy(path)
            parts.append(
                {
                    "index": idx,
                    "filename": path.name,
                    "resume_ms": _resume_ms(pc, str(path)),
                    "needs_proxy": needs_proxy,
                    "proxy_ready": (not needs_proxy) or proxy_is_ready(path),
                    "proxy_reason": proxy_reason(path) if needs_proxy else None,
                    "stream_mode": "hls" if needs_proxy else "direct",
                    "subtitle_tracks": [
                        {
                            "index": ti,
                            "label": t["label"],
                            "filename": t["filename"],
                            "ext": Path(t["filename"]).suffix.lower().lstrip("."),
                        }
                        for ti, t in enumerate(tracks)
                    ],
                }
            )
        return {
            "product_code": pc,
            "title": title,
            "parts": parts,
        }

    def resolve_part_path(self, product_code: str, part_index: int) -> Optional[Path]:
        pc = (product_code or "").strip().upper()
        cache_key = (pc, part_index)
        cached = self._part_path_cache.get(cache_key)
        if cached:
            resolved, mtime, size, path = cached
            try:
                if path.is_file() and str(path.resolve()) == resolved:
                    st = path.stat()
                    if st.st_mtime == mtime and st.st_size == size:
                        return path
            except OSError:
                pass
            self._part_path_cache.pop(cache_key, None)

        row = self._library.get_by_code(pc)
        folder = (row.folder_path or "").strip() if row else ""
        paths = self._sorted_paths(pc, folder or None)
        if part_index < 0 or part_index >= len(paths):
            self._part_path_cache.pop(cache_key, None)
            return None
        path = paths[part_index]
        if not is_video_file(path):
            return None
        try:
            st = path.stat()
            self._part_path_cache[cache_key] = (str(path.resolve()), st.st_mtime, st.st_size, path)
        except OSError:
            pass
        return path

    def resolve_stream_path(self, product_code: str, part_index: int) -> Optional[Path]:
        source = self.resolve_part_path(product_code, part_index)
        if not source:
            return None
        return resolve_playback_file_for_stream(source)

    def resolve_hls_dir(self, product_code: str, part_index: int) -> Optional[Path]:
        source = self.resolve_part_path(product_code, part_index)
        if not source:
            return None
        return resolve_hls_dir_for_stream(source)

    def resolve_hls_playlist(self, product_code: str, part_index: int) -> Optional[Path]:
        hls_dir = self.resolve_hls_dir(product_code, part_index)
        if not hls_dir:
            return None
        playlist = hls_dir / "playlist.m3u8"
        return playlist if playlist.is_file() else None

    def resolve_hls_segment(
        self,
        product_code: str,
        part_index: int,
        segment_name: str,
    ) -> Optional[Path]:
        if not segment_name or "/" in segment_name or "\\" in segment_name or ".." in segment_name:
            return None
        if not segment_name.endswith(".ts"):
            return None
        source = self.resolve_part_path(product_code, part_index)
        if not source:
            return None
        # 온디맨드 빌드 중이고 세그먼트가 아직 없으면, 그 지점을 우선 인코딩한 뒤
        # (시크 대응) 경로를 돌려준다. 이미 있으면 즉시 반환.
        return ensure_hls_segment(source, segment_name)

    def prepare_stream(self, product_code: str, part_index: int) -> Optional[dict[str, Any]]:
        source = self.resolve_part_path(product_code, part_index)
        if not source:
            return None
        return prepare_playback_file(source)

    def resolve_subtitle_path(
        self,
        product_code: str,
        part_index: int,
        track_index: int,
    ) -> Optional[Path]:
        video = self.resolve_part_path(product_code, part_index)
        if not video:
            return None
        tracks = find_subtitle_files(str(video))
        if track_index < 0 or track_index >= len(tracks):
            return None
        path = Path(tracks[track_index]["path"])
        if not path.is_file():
            return None
        if not self._is_subtitle_allowed(path, video):
            return None
        return path

    @staticmethod
    def _is_subtitle_allowed(sub_path: Path, video_path: Path) -> bool:
        try:
            sub = sub_path.resolve()
            video = video_path.resolve()
            if sub.parent != video.parent:
                return False
            stem = video.stem
            name = sub.name
            return name.startswith(stem + ".") or name.startswith(stem + "_")
        except OSError:
            return False

    def read_subtitle_cues(self, path: Path) -> list[dict[str, Any]]:
        """이미 해석된 자막 경로에서 큐를 읽는다(경로 재탐색 없음)."""
        return load_subtitle_cues(str(path))
