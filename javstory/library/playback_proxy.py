"""브라우저 HTML5 재생용 MP4 프록시 (TS/AVI/MKV/HEVC MP4 등)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Literal

from javstory.config.app_config import DATA_ROOT
from javstory.utils.ffmpeg_path import path_for_ffmpeg

logger = logging.getLogger(__name__)

ProxyStatus = Literal["direct", "ready", "building", "failed"]

_PROXY_EXT = frozenset({".ts", ".avi", ".mkv", ".wmv", ".mov"})
_FFMPEG_PROCESSING_REMUX_EXT = frozenset({".ts"})
_BROWSER_DIRECT_EXT = frozenset({".mp4", ".m4v", ".webm"})
_BROWSER_VIDEO_CODECS = frozenset({"h264"})
_BROWSER_AUDIO_CODECS = frozenset({"aac", "mp3"})

_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}
_CACHED_FFMPEG_ENCODERS: set[str] | None = None


def _playback_proxy_timeout_sec() -> int | None:
    raw = (os.environ.get("JAVSTORY_PLAYBACK_PROXY_TIMEOUT_SEC", "7200") or "").strip()
    try:
        v = int(raw)
        return v if v > 0 else None
    except ValueError:
        return 7200


def _ffprobe_json(path: Path) -> dict[str, Any] | None:
    try:
        from javstory.utils.ffmpeg_path import get_ffprobe

        proc = subprocess.run(
            [
                get_ffprobe(),
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type,codec_name",
                "-of",
                "json",
                path_for_ffmpeg(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            check=False,
            timeout=120,
        )
        if proc.returncode != 0:
            return None
        data = json.loads(proc.stdout or "{}")
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _read_mp4_atom(f, pos: int, file_size: int) -> tuple[str, int] | None:
    f.seek(pos)
    hdr = f.read(8)
    if len(hdr) < 8:
        return None
    size = int.from_bytes(hdr[:4], "big")
    typ = hdr[4:8].decode("latin1", errors="replace")
    if size == 0:
        size = file_size - pos
    elif size == 1:
        ext = f.read(8)
        if len(ext) < 8:
            return None
        size = int.from_bytes(ext, "big")
    if size < 8:
        return None
    return typ, size


def is_fragmented_mp4(path: Path) -> bool:
    """
    다수의 mdat/moof 조각으로 나뉜 MP4는 브라우저가 메타데이터를 읽지 못한다.
    (H.264/AAC여도 스트리밍 재생 불가 → faststart remux 필요)
    """
    if path.suffix.lower() not in {".mp4", ".m4v"}:
        return False
    try:
        file_size = path.stat().st_size
        if file_size < 64:
            return False
    except OSError:
        return False
    try:
        with open(path, "rb") as f:
            pos = 0
            mdat_count = 0
            scan_until = min(file_size, 32 * 1024 * 1024)
            while pos < scan_until:
                atom = _read_mp4_atom(f, pos, file_size)
                if not atom:
                    break
                typ, size = atom
                if typ == "moof":
                    return True
                if typ == "mdat":
                    mdat_count += 1
                    if mdat_count >= 3:
                        return True
                pos += size
        return False
    except OSError:
        return False


def is_browser_playable(path: Path) -> bool:
    """HTML5 `<video>`(Chrome/Edge)에서 재생 가능한 H.264/AAC MP4 등인지 판별."""
    ext = path.suffix.lower()
    if ext == ".webm":
        return True
    if ext not in _BROWSER_DIRECT_EXT and ext not in _PROXY_EXT:
        return False

    data = _ffprobe_json(path)
    if not data:
        return ext in _BROWSER_DIRECT_EXT

    streams = data.get("streams") or []
    video_codec: str | None = None
    audio_codec: str | None = None
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        kind = (stream.get("codec_type") or "").lower()
        name = (stream.get("codec_name") or "").lower()
        if kind == "video" and video_codec is None:
            video_codec = name
        elif kind == "audio" and audio_codec is None:
            audio_codec = name

    if not video_codec:
        return False
    if video_codec not in _BROWSER_VIDEO_CODECS:
        return False
    if audio_codec and audio_codec not in _BROWSER_AUDIO_CODECS:
        return False
    return True


def needs_browser_proxy(path: Path) -> bool:
    ext = path.suffix.lower()
    if ext in _PROXY_EXT:
        return True
    if ext in (".mp4", ".m4v"):
        if is_fragmented_mp4(path):
            return True
        return not is_browser_playable(path)
    if ext == ".webm":
        return False
    return ext not in _BROWSER_DIRECT_EXT


def proxy_reason(path: Path) -> str:
    """UI/로그용 프록시 사유: fragmented | hevc | codec | container."""
    ext = path.suffix.lower()
    if ext in _PROXY_EXT:
        return "container"
    if ext in (".mp4", ".m4v"):
        if is_fragmented_mp4(path):
            return "fragmented"
        data = _ffprobe_json(path)
        if data:
            for stream in data.get("streams") or []:
                if not isinstance(stream, dict):
                    continue
                if (stream.get("codec_type") or "").lower() != "video":
                    continue
                name = (stream.get("codec_name") or "").lower()
                if name in ("hevc", "h265"):
                    return "hevc"
                if name and name not in _BROWSER_VIDEO_CODECS:
                    return "codec"
        if not is_browser_playable(path):
            return "codec"
    return "codec"


def _hw_encode_enabled() -> bool:
    raw = (os.environ.get("JAVSTORY_PLAYBACK_HW_ENCODE", "auto") or "auto").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return True


def _ffmpeg_encoder_ids() -> set[str]:
    global _CACHED_FFMPEG_ENCODERS
    if _CACHED_FFMPEG_ENCODERS is not None:
        return _CACHED_FFMPEG_ENCODERS
    ids: set[str] = set()
    try:
        from javstory.utils.ffmpeg_path import get_ffmpeg

        proc = subprocess.run(
            [get_ffmpeg(), "-hide_banner", "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            errors="replace",
            check=False,
            timeout=30,
        )
        for line in (proc.stdout or "").splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0].startswith("V"):
                ids.add(parts[1].strip())
    except Exception:
        pass
    _CACHED_FFMPEG_ENCODERS = ids
    return ids


def _h264_transcode_plans() -> list[tuple[str, list[str], list[str]]]:
    """(이름, 입력 옵션, 비디오 인코더 옵션) — 실패 시 다음 플랜 시도."""
    plans: list[tuple[str, list[str], list[str]]] = []
    if _hw_encode_enabled():
        enc = _ffmpeg_encoder_ids()
        if "h264_nvenc" in enc:
            plans.append((
                "h264_nvenc",
                [],
                ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "23", "-pix_fmt", "yuv420p"],
            ))
        if "h264_qsv" in enc:
            plans.append((
                "h264_qsv",
                [],
                ["-c:v", "h264_qsv", "-global_quality", "23"],
            ))
        if "h264_amf" in enc:
            plans.append((
                "h264_amf",
                [],
                ["-c:v", "h264_amf", "-quality", "balanced", "-rc", "cqp", "-qp_i", "23", "-qp_p", "23"],
            ))
    plans.append((
        "libx264",
        [],
        ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-pix_fmt", "yuv420p"],
    ))
    return plans


def proxy_cache_path(source: Path) -> Path:
    try:
        stat = source.stat()
        key = f"{source.resolve()}|{stat.st_size}|{int(stat.st_mtime)}"
    except OSError:
        key = str(source)
    digest = hashlib.sha256(key.encode("utf-8", errors="ignore")).hexdigest()[:24]
    return DATA_ROOT / "cache" / "playback_proxy" / f"{digest}.mp4"


def needs_ffmpeg_processing_remux(path: Path) -> bool:
    """스냅샷/프리뷰 등 ffmpeg 파이프라인에서 TS remux가 필요한지."""
    return path.suffix.lower() in _FFMPEG_PROCESSING_REMUX_EXT


def _probe_duration_sec(path: Path, *, timeout: int = 30) -> float:
    try:
        from javstory.utils.ffmpeg_path import get_ffprobe

        proc = subprocess.run(
            [
                get_ffprobe(),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path_for_ffmpeg(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
        )
        v = (proc.stdout or "").strip()
        return float(v) if v else 0.0
    except Exception:
        return 0.0


def _processing_cache_ready(proxy: Path) -> bool:
    try:
        if not proxy.is_file() or proxy.stat().st_size <= 0:
            return False
    except OSError:
        return False
    return _probe_duration_sec(proxy) > 0.0


def _remux_mp4_faststart(source: Path, tmp: Path) -> tuple[bool, str]:
    from javstory.utils.ffmpeg_path import get_ffmpeg

    ffmpeg = get_ffmpeg()
    tmp.parent.mkdir(parents=True, exist_ok=True)
    return _run_ffmpeg(
        [
            ffmpeg,
            "-hide_banner",
            "-y",
            "-i",
            path_for_ffmpeg(source),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            path_for_ffmpeg(tmp, output=True),
        ],
        timeout=_playback_proxy_timeout_sec(),
    )


def _remux_ts_stream_copy(source: Path, tmp: Path) -> tuple[bool, str]:
    from javstory.utils.ffmpeg_path import get_ffmpeg

    ffmpeg = get_ffmpeg()
    tmp.parent.mkdir(parents=True, exist_ok=True)
    return _run_ffmpeg(
        [
            ffmpeg,
            "-hide_banner",
            "-y",
            *_ffmpeg_input_opts(source),
            "-i",
            path_for_ffmpeg(source),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c",
            "copy",
            "-bsf:a",
            "aac_adtstoasc",
            "-movflags",
            "+faststart",
            path_for_ffmpeg(tmp, output=True),
        ]
    )


def _build_proxy_for_processing(source: Path, tmp: Path) -> tuple[bool, str]:
    """스냅샷/프리뷰용 MP4. 브라우저 재생 가능 여부와 무관하게 디코드 가능하면 성공."""
    if source.suffix.lower() == ".ts":
        ok, log = _remux_ts_stream_copy(source, tmp)
        if ok and tmp.is_file() and tmp.stat().st_size > 0 and _probe_duration_sec(tmp) > 0:
            return True, log
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass

    ok, log = _transcode_to_h264_mp4(source, tmp)
    return ok and tmp.is_file() and tmp.stat().st_size > 0 and _probe_duration_sec(tmp) > 0, log


def ensure_ffmpeg_processing_source(source: Path) -> Path | None:
    """
    ffmpeg 스냅샷/프리뷰/다이제스트 입력 경로.
    TS는 playback_proxy와 동일 캐시에 remux MP4를 만들어 시크·프로브 안정성을 확보한다.
    """
    if not source.is_file():
        return None
    if not needs_ffmpeg_processing_remux(source):
        return source

    proxy = proxy_cache_path(source)
    if _processing_cache_ready(proxy):
        return proxy

    proxy.parent.mkdir(parents=True, exist_ok=True)
    tmp = proxy.with_name(f"{proxy.stem}.tmp{proxy.suffix}")
    try:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        ok, log = _build_proxy_for_processing(source, tmp)
        if ok:
            tmp.replace(proxy)
            logger.info("TS remux cache ready for processing: %s -> %s", source.name, proxy.name)
            return proxy
        logger.warning(
            "TS remux for processing failed: %s (%s)",
            source,
            (log or "")[-400:],
        )
    except OSError as exc:
        logger.warning("TS remux cache write failed: %s (%s)", source, exc)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    return None


def _job_key(source: Path) -> str:
    try:
        return str(source.resolve())
    except OSError:
        return str(source)


def _proxy_file_ready(path: Path) -> bool:
    """프록시 MP4가 재생 가능한지 — ffprobe 경로 이슈 시 duration으로 폴백."""
    try:
        if not path.is_file() or path.stat().st_size <= 0:
            return False
    except OSError:
        return False
    if is_browser_playable(path):
        return True
    return _probe_duration_sec(path) > 1.0


def proxy_is_ready(source: Path) -> bool:
    proxy = proxy_cache_path(source)
    return _proxy_file_ready(proxy)


def get_proxy_job_state(source: Path) -> ProxyStatus | None:
    key = _job_key(source)
    with _LOCK:
        row = _JOBS.get(key)
    if not row:
        return None
    return row.get("status")


def resolve_playback_file(source: Path) -> Path | None:
    """재생에 쓸 파일 경로. 프록시 필요 시 준비된 MP4만 반환."""
    if not source.is_file():
        return None
    if not needs_browser_proxy(source):
        return source
    proxy = proxy_cache_path(source)
    if proxy_is_ready(source):
        return proxy
    return None


def prepare_playback_file(source: Path) -> dict[str, Any]:
    reason = proxy_reason(source) if source.is_file() else ""

    def _with_reason(payload: dict[str, Any]) -> dict[str, Any]:
        if reason:
            payload["proxy_reason"] = reason
        return payload

    if not source.is_file():
        return _with_reason({"ready": False, "needs_proxy": False, "status": "failed", "error": "파일 없음"})

    if not needs_browser_proxy(source):
        return _with_reason({"ready": True, "needs_proxy": False, "status": "direct"})

    if proxy_is_ready(source):
        return _with_reason({"ready": True, "needs_proxy": True, "status": "ready"})

    key = _job_key(source)
    proxy = proxy_cache_path(source)
    tmp = proxy.with_name(f"{proxy.stem}.tmp{proxy.suffix}")

    with _LOCK:
        row = _JOBS.get(key)
        if row:
            st = row.get("status")
            if st == "failed":
                err = row.get("error") or "ffmpeg 변환 실패 (브라우저 호환 H.264/AAC MP4 생성 불가)"
                _JOBS.pop(key, None)
                return _with_reason({
                    "ready": False,
                    "needs_proxy": True,
                    "status": "failed",
                    "error": err,
                })
            if st == "building":
                if proxy_is_ready(source):
                    _JOBS[key] = {"status": "ready", "error": None}
                    return _with_reason({"ready": True, "needs_proxy": True, "status": "ready"})
                return _with_reason({"ready": False, "needs_proxy": True, "status": "building"})
            if st == "ready":
                if proxy_is_ready(source):
                    return _with_reason({"ready": True, "needs_proxy": True, "status": "ready"})
                _JOBS.pop(key, None)

    try:
        if tmp.is_file() and tmp.stat().st_size > 0:
            with _LOCK:
                _JOBS[key] = {"status": "building", "error": None}
            return _with_reason({"ready": False, "needs_proxy": True, "status": "building"})
    except OSError:
        pass

    with _LOCK:
        _JOBS[key] = {"status": "building", "error": None}

    thread = threading.Thread(
        target=_run_proxy_job,
        args=(source, proxy, key),
        daemon=True,
        name=f"playback-proxy-{source.name}",
    )
    thread.start()
    logger.info("Playback proxy transcode started: %s", source.name)
    return _with_reason({"ready": False, "needs_proxy": True, "status": "building"})


def _run_ffmpeg(cmd: list[str], *, timeout: int | None = None) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            check=False,
            timeout=timeout,
        )
        tail = (proc.stdout or "")[-2000:]
        return proc.returncode == 0, tail
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"").decode("utf-8", errors="replace") if exc.stdout else ""
        tail = out[-2000:] if out else ""
        return False, tail or f"ffmpeg 시간 초과 ({timeout}s)"
    except Exception as exc:
        return False, str(exc)


def _ffmpeg_input_opts(source: Path) -> list[str]:
    """손상/비표준 컨테이너(특히 AVI) 프로브 안정화."""
    ext = source.suffix.lower()
    if ext in {".avi", ".mkv", ".wmv", ".mov", ".ts"}:
        return ["-probesize", "50M", "-analyzeduration", "100M", "-fflags", "+genpts"]
    return []


def _transcode_to_h264_mp4(source: Path, tmp: Path) -> tuple[bool, str]:
    from javstory.utils.ffmpeg_path import get_ffmpeg

    ffmpeg = get_ffmpeg()
    tmp.parent.mkdir(parents=True, exist_ok=True)
    last_log = ""
    for _encoder_name, input_opts, video_opts in _h264_transcode_plans():
        try:
            if tmp.is_file():
                tmp.unlink(missing_ok=True)
        except OSError:
            pass
        ok, log = _run_ffmpeg(
            [
                ffmpeg,
                "-hide_banner",
                "-y",
                *input_opts,
                *_ffmpeg_input_opts(source),
                "-i",
                path_for_ffmpeg(source),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                *video_opts,
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                path_for_ffmpeg(tmp, output=True),
            ],
            timeout=_playback_proxy_timeout_sec(),
        )
        if ok and tmp.is_file() and tmp.stat().st_size > 0:
            return True, log
        last_log = log or last_log
    return False, last_log


def _build_proxy(source: Path, tmp: Path) -> tuple[bool, str]:
    from javstory.utils.ffmpeg_path import get_ffmpeg

    ffmpeg = get_ffmpeg()
    tmp.parent.mkdir(parents=True, exist_ok=True)

    if source.suffix.lower() in {".mp4", ".m4v"} and is_browser_playable(source) and is_fragmented_mp4(source):
        ok, log = _remux_mp4_faststart(source, tmp)
        if ok and tmp.is_file() and tmp.stat().st_size > 0 and _proxy_file_ready(tmp):
            return True, log
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass

    if source.suffix.lower() == ".ts":
        ok, log = _remux_ts_stream_copy(source, tmp)
        if ok and tmp.is_file() and tmp.stat().st_size > 0 and _proxy_file_ready(tmp):
            return True, log
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass

    return _transcode_to_h264_mp4(source, tmp)


def _run_proxy_job(source: Path, proxy: Path, key: str) -> None:
    tmp = proxy.with_name(f"{proxy.stem}.tmp{proxy.suffix}")
    try:
        ok, log = _build_proxy(source, tmp)
        if ok and _proxy_file_ready(tmp):
            tmp.replace(proxy)
            with _LOCK:
                _JOBS[key] = {"status": "ready", "error": None}
            logger.info("Playback proxy ready: %s -> %s", source.name, proxy.name)
            return
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        err = log or "ffmpeg 변환 실패 (브라우저 호환 H.264/AAC MP4 생성 불가)"
        logger.warning("Playback proxy failed: %s (%s)", source, err[-400:])
        with _LOCK:
            _JOBS[key] = {"status": "failed", "error": err}
    except Exception as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        with _LOCK:
            _JOBS[key] = {"status": "failed", "error": str(exc)}
