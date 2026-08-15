"""브라우저 HTML5 재생용 HLS 프록시 (TS/AVI/MKV/HEVC MP4 등)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Literal, Optional

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

# 프로세스 크래시로 남은 고아 .tmp 판정 임계값(초). ffmpeg는 변환 중 .tmp를
# 지속적으로 갱신하므로, 이 시간 이상 갱신이 없으면 죽은 작업으로 보고 재시작한다.
_STALE_TMP_SEC = 90.0

# (percent 0~100, eta_sec | None) 진행률 콜백
ProgressCb = Optional[Callable[[float, Optional[float]], None]]

_FFMPEG_TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")

_HLS_PLAYLIST = "playlist.m3u8"
_HLS_SEGMENT_GLOB = "seg_*.ts"
_PROXY_CACHE_VERSION = "hlsv3"
_HLS_SEGMENT_SEC = 4


def _building_payload(key: str) -> dict[str, Any]:
    """변환 진행 중 응답 — _JOBS에 기록된 진행률/ETA를 함께 실어 보낸다."""
    with _LOCK:
        row = _JOBS.get(key) or {}
        progress = row.get("progress")
        eta = row.get("eta_sec")
    return {
        "ready": False,
        "needs_proxy": True,
        "status": "building",
        "progress": progress,
        "eta_sec": eta,
    }


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
                "stream=codec_type,codec_name,profile,has_b_frames,r_frame_rate,avg_frame_rate",
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
    # 컨테이너·코덱은 브라우저 호환이어도 SPS 프로필 위반(Baseline+B-frame)이나
    # VFR이면 하드웨어 디코더에서 끊겨 보인다 — 직접재생 대신 프록시(재인코딩)로.
    if _vfr_from_probe(data) or _nonconformant_baseline_bframes_from_probe(data):
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


def _source_codecs(path: Path) -> tuple[str | None, str | None]:
    data = _ffprobe_json(path)
    if not data:
        return None, None
    video_codec: str | None = None
    audio_codec: str | None = None
    for stream in data.get("streams") or []:
        if not isinstance(stream, dict):
            continue
        kind = (stream.get("codec_type") or "").lower()
        name = (stream.get("codec_name") or "").lower()
        if kind == "video" and video_codec is None:
            video_codec = name
        elif kind == "audio" and audio_codec is None:
            audio_codec = name
    return video_codec, audio_codec


def _parse_ffprobe_rate(raw: str | None) -> float:
    if not raw:
        return 0.0
    num, _, den = raw.partition("/")
    try:
        n = float(num)
        d = float(den) if den else 1.0
        return n / d if d else 0.0
    except ValueError:
        return 0.0


def _vfr_from_probe(data: dict[str, Any] | None) -> bool:
    """공칭 프레임레이트(r_frame_rate)와 실제 평균(avg_frame_rate)이 크게 다르면 VFR.

    VFR 타임스탬프가 스트림카피로 그대로 HLS에 남으면 디코드 부하와 무관하게
    재생 내내 끊겨 보인다(judder) — 이런 소스는 재인코딩(CFR 정규화)이 필요하다.
    """
    if not data:
        return False
    for stream in data.get("streams") or []:
        if not isinstance(stream, dict) or (stream.get("codec_type") or "").lower() != "video":
            continue
        r = _parse_ffprobe_rate(stream.get("r_frame_rate"))
        avg = _parse_ffprobe_rate(stream.get("avg_frame_rate"))
        if r <= 0 or avg <= 0:
            return False
        return abs(r - avg) / r > 0.05
    return False


def _is_vfr_source(path: Path) -> bool:
    return _vfr_from_probe(_ffprobe_json(path))


def _nonconformant_baseline_bframes_from_probe(data: dict[str, Any] | None) -> bool:
    """SPS는 Baseline(B-frame 금지)인데 실제로 B-frame이 있는 비표준 비트스트림 판별.

    일부 비표준 인코더(예: ShanaEncoder류 자막 인코더)가 SPS에 프로필을 잘못
    기록해 만드는 파일로, 소프트웨어 디코더는 관대하게 재생하지만 브라우저의
    하드웨어 가속 디코더(NVDEC/D3D11VA)는 profile_idc를 신뢰해 리오더 버퍼를
    할당하지 않고 세션을 구성 — B-frame을 만나면 프레임을 놓치거나 깨뜨려
    CPU/GPU 부하 없이도 재생 내내 끊겨 보인다. 스트림카피로는 고칠 수 없고
    재인코딩(프로필 재작성)해야 한다.
    """
    if not data:
        return False
    for stream in data.get("streams") or []:
        if not isinstance(stream, dict) or (stream.get("codec_type") or "").lower() != "video":
            continue
        profile = (stream.get("profile") or "").lower()
        try:
            has_b = int(stream.get("has_b_frames") or 0)
        except (TypeError, ValueError):
            has_b = 0
        return "baseline" in profile and has_b > 0
    return False


def _has_nonconformant_baseline_bframes(path: Path) -> bool:
    return _nonconformant_baseline_bframes_from_probe(_ffprobe_json(path))


def _can_hls_stream_copy(source: Path) -> bool:
    """H.264/AAC(또는 무음)이면 재인코딩 없이 HLS 세그먼트 분할만 시도."""
    video_codec, audio_codec = _source_codecs(source)
    if video_codec != "h264":
        return False
    if audio_codec and audio_codec not in _BROWSER_AUDIO_CODECS:
        return False
    if _is_vfr_source(source):
        return False
    if _has_nonconformant_baseline_bframes(source):
        return False
    return True


def _hls_quality_mode() -> str:
    raw = (os.environ.get("JAVSTORY_PLAYBACK_HLS_QUALITY", "fast") or "fast").strip().lower()
    return raw if raw in {"fast", "balanced"} else "fast"


def _hls_audio_opts(source: Path, *, for_copy: bool) -> list[str]:
    _video, audio = _source_codecs(source)
    if for_copy:
        if source.suffix.lower() == ".ts" and audio == "aac":
            return ["-c:a", "copy", "-bsf:a", "aac_adtstoasc"]
        return ["-c:a", "copy"]
    if audio == "aac":
        return ["-c:a", "copy"]
    return ["-c:a", "aac", "-b:a", "128k"]


def _h264_transcode_plans() -> list[tuple[str, list[str], list[str]]]:
    """(이름, 입력 옵션, 비디오 인코더 옵션) — 실패 시 다음 플랜 시도."""
    gop_opts = ["-g", "48", "-keyint_min", "48", "-sc_threshold", "0"]
    fast = _hls_quality_mode() == "fast"
    # VFR 소스(AVI/MKV 등에 흔함)의 불규칙한 프레임 타이밍을 그대로 재인코딩하면
    # 재생 내내 끊겨 보인다(judder) — CFR로 정규화해 출력한다.
    cfr_opts = ["-fps_mode", "cfr"]
    plans: list[tuple[str, list[str], list[str]]] = []
    if _hw_encode_enabled():
        enc = _ffmpeg_encoder_ids()
        cq = "26" if fast else "23"
        if "h264_nvenc" in enc:
            nvenc_v = [
                "-c:v", "h264_nvenc",
                "-preset", "p1" if fast else "p4",
                "-tune", "ll",
                "-rc", "vbr",
                "-cq", cq,
                "-pix_fmt", "yuv420p",
                "-g", "48",
                "-forced-idr", "1",
                *cfr_opts,
            ]
            plans.append(("h264_nvenc_cuda", ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"], nvenc_v))
            plans.append(("h264_nvenc", [], nvenc_v))
        if "h264_qsv" in enc:
            qsv_v = ["-c:v", "h264_qsv", "-global_quality", cq, "-g", "48", *cfr_opts]
            if fast:
                qsv_v.extend(["-look_ahead", "0", "-async_depth", "1"])
            plans.append(("h264_qsv", [], qsv_v))
        if "h264_amf" in enc:
            plans.append((
                "h264_amf",
                [],
                [
                    "-c:v", "h264_amf",
                    "-quality", "speed" if fast else "balanced",
                    "-rc", "cqp",
                    "-qp_i", cq,
                    "-qp_p", cq,
                    "-g", "48",
                    *cfr_opts,
                ],
            ))
    crf = "23" if fast else "20"
    plans.append((
        "libx264",
        [],
        ["-c:v", "libx264", "-preset", "ultrafast", "-crf", crf, "-threads", "0", "-pix_fmt", "yuv420p", *gop_opts, *cfr_opts],
    ))
    return plans


def proxy_cache_dir() -> Path:
    return DATA_ROOT / "cache" / "playback_proxy"


def _proxy_cache_digest(source: Path, *, version: str = _PROXY_CACHE_VERSION) -> str:
    try:
        stat = source.stat()
        key = f"{source.resolve()}|{stat.st_size}|{int(stat.st_mtime)}|{version}"
    except OSError:
        key = f"{source}|{version}"
    return hashlib.sha256(key.encode("utf-8", errors="ignore")).hexdigest()[:24]


def proxy_hls_dir(source: Path) -> Path:
    """Web 재생용 HLS VOD 캐시 디렉터리."""
    return proxy_cache_dir() / _proxy_cache_digest(source)


def proxy_hls_playlist(source: Path) -> Path:
    return proxy_hls_dir(source) / _HLS_PLAYLIST


def proxy_cache_path(source: Path) -> Path:
    """Web HLS 캐시 디렉터리 (하위 호환 alias)."""
    return proxy_hls_dir(source)


def _processing_mp4_path(source: Path) -> Path:
    """ffmpeg 스냅샷/프리뷰용 TS remux MP4 (Web HLS와 별도)."""
    digest = _proxy_cache_digest(source, version="proc")
    return proxy_cache_dir() / f"{digest}.mp4"


def _dir_size(path: Path) -> int:
    total = 0
    try:
        if path.is_file():
            return path.stat().st_size
        if path.is_dir():
            for item in path.rglob("*"):
                if item.is_file():
                    total += item.stat().st_size
    except OSError:
        return 0
    return total


def _iter_hls_cache_dirs(base: Path):
    if not base.is_dir():
        return
    for playlist in base.glob(f"*/{_HLS_PLAYLIST}"):
        if playlist.is_file():
            yield playlist.parent


def _remove_path(path: Path) -> int:
    """파일/디렉터리 삭제 후 확보된 바이트 수."""
    try:
        size = _dir_size(path)
    except OSError:
        size = 0
    try:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.is_file():
            path.unlink()
        else:
            return 0
    except OSError:
        return 0
    return size


def _proxy_hls_ready(hls_dir: Path) -> bool:
    playlist = hls_dir / _HLS_PLAYLIST
    try:
        if not playlist.is_file() or playlist.stat().st_size <= 0:
            return False
    except OSError:
        return False
    try:
        return any(hls_dir.glob(_HLS_SEGMENT_GLOB))
    except OSError:
        return False


def cache_max_bytes() -> int:
    """프록시 캐시 용량 상한(바이트). 기본 30GB, 0 이하이면 무제한(매우 큼)."""
    raw = (os.environ.get("JAVSTORY_PLAYBACK_CACHE_MAX_GB", "30") or "30").strip()
    try:
        gb = float(raw)
    except ValueError:
        gb = 30.0
    if gb <= 0:
        return 1 << 62
    return int(gb * (1024 ** 3))


def proxy_cache_stats() -> dict[str, int]:
    d = proxy_cache_dir()
    total = 0
    count = 0
    if d.is_dir():
        seen: set[Path] = set()
        for hls_dir in _iter_hls_cache_dirs(d):
            if hls_dir in seen:
                continue
            seen.add(hls_dir)
            total += _dir_size(hls_dir)
            count += 1
        for f in d.glob("*.mp4"):
            try:
                total += f.stat().st_size
                count += 1
            except OSError:
                continue
    return {"total_bytes": total, "file_count": count, "max_bytes": cache_max_bytes()}


def clear_proxy_cache() -> dict[str, int]:
    """프록시 캐시(HLS 디렉터리·레거시 MP4·tmp)를 모두 삭제한다."""
    d = proxy_cache_dir()
    freed = 0
    removed = 0
    if d.is_dir():
        for hls_dir in list(_iter_hls_cache_dirs(d)):
            freed += _remove_path(hls_dir)
            removed += 1
        for item in list(d.iterdir()):
            name = item.name
            if name.endswith(".tmp") or item.suffix == ".mp4":
                freed += _remove_path(item)
                removed += 1
    with _LOCK:
        _JOBS.clear()
    invalidate_stream_resolve_cache()
    logger.info("Playback proxy cache cleared: %d entries, %d bytes", removed, freed)
    return {"removed": removed, "freed_bytes": freed}


def evict_proxy_cache(
    protected_digests: set[str] | None = None,
    *,
    max_bytes: int | None = None,
) -> dict[str, int]:
    """용량 상한 초과 시 보호 대상을 제외하고 오래된(mtime) 순으로 삭제(LRU)."""
    d = proxy_cache_dir()
    if not d.is_dir():
        return {"evicted": 0, "freed_bytes": 0, "total_bytes": 0}
    limit = max_bytes if max_bytes is not None else cache_max_bytes()
    protected = protected_digests or set()

    entries: list[tuple[Path, int, float]] = []
    total = 0
    for hls_dir in _iter_hls_cache_dirs(d):
        try:
            st = hls_dir.stat()
        except OSError:
            continue
        size = _dir_size(hls_dir)
        entries.append((hls_dir, size, st.st_mtime))
        total += size
    for f in d.glob("*.mp4"):
        try:
            st = f.stat()
        except OSError:
            continue
        entries.append((f, st.st_size, st.st_mtime))
        total += st.st_size

    if total <= limit:
        return {"evicted": 0, "freed_bytes": 0, "total_bytes": total}

    entries.sort(key=lambda t: t[2])
    freed = 0
    evicted = 0
    for path, size, _mtime in entries:
        if total - freed <= limit:
            break
        if path.name in protected or path.stem in protected:
            continue
        freed += _remove_path(path)
        evicted += 1
    if evicted:
        logger.info(
            "Playback proxy cache evicted %d entries (%d bytes), now %d bytes",
            evicted,
            freed,
            total - freed,
        )
    return {"evicted": evicted, "freed_bytes": freed, "total_bytes": total - freed}


# 서비스 레이어가 "보호 대상(나중에 볼·미시청) 프록시 digest" 계산기를 주입한다.
# (library 레이어가 services/DB를 직접 import하지 않도록 역주입 방식 사용)
_protected_digests_provider: Callable[[], set[str]] | None = None


def set_protected_digests_provider(fn: Callable[[], set[str]] | None) -> None:
    global _protected_digests_provider
    _protected_digests_provider = fn


def _maybe_evict_after_build() -> None:
    try:
        protected = _protected_digests_provider() if _protected_digests_provider else set()
    except Exception:
        protected = set()
    try:
        evict_proxy_cache(protected)
    except Exception:
        pass


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


def _remux_mp4_faststart(
    source: Path,
    tmp: Path,
    *,
    duration_sec: float = 0.0,
    on_progress: ProgressCb = None,
) -> tuple[bool, str]:
    from javstory.utils.ffmpeg_path import get_ffmpeg

    ffmpeg = get_ffmpeg()
    tmp.parent.mkdir(parents=True, exist_ok=True)
    return _run_ffmpeg_progress(
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
        duration_sec=duration_sec,
        on_progress=on_progress,
    )


def _remux_ts_stream_copy(
    source: Path,
    tmp: Path,
    *,
    duration_sec: float = 0.0,
    on_progress: ProgressCb = None,
) -> tuple[bool, str]:
    from javstory.utils.ffmpeg_path import get_ffmpeg

    ffmpeg = get_ffmpeg()
    tmp.parent.mkdir(parents=True, exist_ok=True)
    return _run_ffmpeg_progress(
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
        ],
        duration_sec=duration_sec,
        on_progress=on_progress,
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

    proxy = _processing_mp4_path(source)
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
    return _proxy_hls_ready(proxy_hls_dir(source))


def resolve_hls_dir_for_stream(source: Path) -> Path | None:
    """HLS 스트리밍 핫패스 — ffprobe 없이 stat·캐시만 사용."""
    if not source.is_file():
        return None

    ident = _source_cache_key(source)
    if ident is None:
        return None
    key, mtime, size = ident

    cached = _HLS_RESOLVE_CACHE.get(key)
    if cached and cached[0] == mtime and cached[1] == size:
        result = cached[2]
        if result is None:
            return None
        if not _proxy_hls_ready(result):
            _HLS_RESOLVE_CACHE.pop(key, None)
        else:
            try:
                os.utime(result, None)
            except OSError:
                pass
            return result

    if not needs_browser_proxy_cached(source):
        result: Path | None = None
    else:
        hls_dir = proxy_hls_dir(source)
        if _proxy_hls_ready(hls_dir):
            try:
                os.utime(hls_dir, None)
            except OSError:
                pass
            result = hls_dir
        else:
            result = None

    _HLS_RESOLVE_CACHE[key] = (mtime, size, result)
    return result


def get_proxy_job_state(source: Path) -> ProxyStatus | None:
    key = _job_key(source)
    with _LOCK:
        row = _JOBS.get(key)
    if not row:
        return None
    return row.get("status")


# Range/HLS 스트리밍 핫패스 캐시 — 시크 시 연속 GET마다 ffprobe/atom 스캔을 반복하지 않도록.
_NEEDS_PROXY_CACHE: dict[str, tuple[float, int, bool]] = {}
_STREAM_RESOLVE_CACHE: dict[str, tuple[float, int, Path | None]] = {}
_HLS_RESOLVE_CACHE: dict[str, tuple[float, int, Path | None]] = {}


def _source_cache_key(source: Path) -> tuple[str, float, int] | None:
    try:
        return str(source.resolve()), source.stat().st_mtime, source.stat().st_size
    except OSError:
        return None


def invalidate_stream_resolve_cache() -> None:
    _NEEDS_PROXY_CACHE.clear()
    _STREAM_RESOLVE_CACHE.clear()
    _HLS_RESOLVE_CACHE.clear()


def needs_browser_proxy_cached(source: Path) -> bool:
    """needs_browser_proxy() 결과를 source mtime/size 기준으로 캐시."""
    ident = _source_cache_key(source)
    if ident is None:
        return needs_browser_proxy(source)
    key, mtime, size = ident
    cached = _NEEDS_PROXY_CACHE.get(key)
    if cached and cached[0] == mtime and cached[1] == size:
        return cached[2]
    result = needs_browser_proxy(source)
    _NEEDS_PROXY_CACHE[key] = (mtime, size, result)
    return result


def resolve_playback_file_for_stream(source: Path) -> Path | None:
    """직접 재생 MP4 Range 스트리밍 핫패스 — 프록시 필요 시 None (HLS 별도)."""
    if not source.is_file():
        return None

    ident = _source_cache_key(source)
    if ident is None:
        return None
    key, mtime, size = ident

    cached = _STREAM_RESOLVE_CACHE.get(key)
    if cached and cached[0] == mtime and cached[1] == size:
        return cached[2]

    if not needs_browser_proxy_cached(source):
        result: Path | None = source
    else:
        result = None

    _STREAM_RESOLVE_CACHE[key] = (mtime, size, result)
    return result


def resolve_playback_file(source: Path) -> Path | None:
    """재생에 쓸 경로. 프록시 필요 시 준비된 HLS 디렉터리만 반환."""
    if not source.is_file():
        return None
    if not needs_browser_proxy(source):
        return source
    hls_dir = proxy_hls_dir(source)
    if proxy_is_ready(source):
        try:
            os.utime(hls_dir, None)
        except OSError:
            pass
        return hls_dir
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
    hls_dir = proxy_hls_dir(source)
    tmp_dir = hls_dir.with_name(f"{hls_dir.name}.tmp")

    with _LOCK:
        row = _JOBS.get(key)
        if row:
            st = row.get("status")
            if st == "failed":
                err = row.get("error") or "ffmpeg 변환 실패 (브라우저 호환 HLS 생성 불가)"
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
                return _with_reason({
                    "ready": False,
                    "needs_proxy": True,
                    "status": "building",
                    "progress": row.get("progress"),
                    "eta_sec": row.get("eta_sec"),
                })
            if st == "ready":
                if proxy_is_ready(source):
                    return _with_reason({"ready": True, "needs_proxy": True, "status": "ready"})
                _JOBS.pop(key, None)

    try:
        tstat = tmp_dir.stat()
        if tmp_dir.is_dir() or tstat.st_size > 0:
            age = time.time() - tstat.st_mtime
            if age < _STALE_TMP_SEC:
                with _LOCK:
                    _JOBS[key] = {"status": "building", "error": None}
                return _with_reason(_building_payload(key))
            logger.warning(
                "Removing stale playback proxy tmp (age=%.0fs): %s", age, tmp_dir.name
            )
            _remove_path(tmp_dir)
    except OSError:
        pass

    with _LOCK:
        _JOBS[key] = {"status": "building", "error": None}

    thread = threading.Thread(
        target=_run_proxy_job,
        args=(source, hls_dir, key),
        daemon=True,
        name=f"playback-proxy-{source.name}",
    )
    thread.start()
    logger.info("Playback proxy HLS transcode started: %s", source.name)
    return _with_reason(_building_payload(key))


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


def _run_ffmpeg_progress(
    cmd: list[str],
    *,
    timeout: int | None = None,
    duration_sec: float = 0.0,
    on_progress: ProgressCb = None,
) -> tuple[bool, str]:
    """ffmpeg를 실행하며 stderr의 `time=`을 파싱해 진행률/ETA를 콜백한다."""
    if not on_progress or duration_sec <= 0:
        return _run_ffmpeg(cmd, timeout=timeout)
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except Exception as exc:
        return False, str(exc)

    chunks: list[str] = []
    started = time.time()

    def _emit(line: str) -> None:
        m = _FFMPEG_TIME_RE.search(line)
        if not m:
            return
        try:
            h, mi, s = m.groups()
            t = int(h) * 3600 + int(mi) * 60 + float(s)
        except (TypeError, ValueError):
            return
        pct = max(0.0, min(99.0, t / duration_sec * 100.0))
        elapsed = time.time() - started
        eta: float | None = None
        if pct > 1.0:
            eta = max(0.0, elapsed / (pct / 100.0) - elapsed)
        try:
            on_progress(pct, eta)
        except Exception:
            pass

    def _read() -> None:
        if proc.stdout is None:
            return
        # ffmpeg는 진행 상황을 \n이 아닌 \r로 같은 줄을 갱신하므로 readline()으로는
        # 인코딩이 끝날 때까지 한 줄도 못 읽는다. 블록 단위로 읽고 \r·\n 모두로 분리한다.
        buf = ""
        while True:
            try:
                block = proc.stdout.read1(4096)
            except (ValueError, OSError):
                break
            if not block:
                break
            txt = block.decode("utf-8", errors="replace")
            chunks.append(txt)
            if len(chunks) > 500:
                del chunks[:250]
            buf += txt
            parts = re.split(r"[\r\n]", buf)
            buf = parts.pop()  # 마지막 미완성 조각은 다음 블록과 이어 붙인다.
            for line in parts:
                _emit(line)
        if buf:
            _emit(buf)

    reader = threading.Thread(target=_read, daemon=True)
    reader.start()
    try:
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=10)
        except Exception:
            pass
        reader.join(timeout=5)
        tail = "".join(chunks)[-2000:]
        return False, tail or f"ffmpeg 시간 초과 ({timeout}s)"
    finally:
        reader.join(timeout=5)
    return int(rc) == 0, "".join(chunks)[-2000:]


def _ffmpeg_input_opts(source: Path) -> list[str]:
    """손상/비표준 컨테이너(특히 AVI) 프로브 안정화."""
    ext = source.suffix.lower()
    if ext in {".avi", ".mkv", ".wmv", ".mov", ".ts"}:
        return ["-probesize", "50M", "-analyzeduration", "100M", "-fflags", "+genpts"]
    return []


def _transcode_to_h264_mp4(
    source: Path,
    tmp: Path,
    *,
    duration_sec: float = 0.0,
    on_progress: ProgressCb = None,
) -> tuple[bool, str]:
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
        ok, log = _run_ffmpeg_progress(
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
            duration_sec=duration_sec,
            on_progress=on_progress,
        )
        if ok and tmp.is_file() and tmp.stat().st_size > 0:
            return True, log
        last_log = log or last_log
    return False, last_log


def _clear_hls_tmp_dir(tmp_dir: Path) -> None:
    try:
        if tmp_dir.is_dir():
            for item in tmp_dir.iterdir():
                if item.is_file():
                    item.unlink(missing_ok=True)
    except OSError:
        pass


def _run_hls_ffmpeg(
    source: Path,
    tmp_dir: Path,
    *,
    video_opts: list[str],
    audio_opts: list[str],
    input_opts: list[str] | None = None,
    duration_sec: float = 0.0,
    on_progress: ProgressCb = None,
) -> tuple[bool, str]:
    from javstory.utils.ffmpeg_path import get_ffmpeg

    ffmpeg = get_ffmpeg()
    tmp_dir.mkdir(parents=True, exist_ok=True)
    segment_pattern = str(tmp_dir / "seg_%05d.ts")
    playlist = tmp_dir / _HLS_PLAYLIST
    return _run_ffmpeg_progress(
        [
            ffmpeg,
            "-hide_banner",
            "-y",
            *(input_opts or []),
            *_ffmpeg_input_opts(source),
            "-i",
            path_for_ffmpeg(source),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            *video_opts,
            *audio_opts,
            "-f",
            "hls",
            "-hls_time",
            str(_HLS_SEGMENT_SEC),
            "-hls_playlist_type",
            "vod",
            "-hls_flags",
            "independent_segments",
            "-hls_segment_filename",
            path_for_ffmpeg(Path(segment_pattern), output=True),
            path_for_ffmpeg(playlist, output=True),
        ],
        timeout=_playback_proxy_timeout_sec(),
        duration_sec=duration_sec,
        on_progress=on_progress,
    )


def _remux_to_hls_copy(
    source: Path,
    tmp_dir: Path,
    *,
    duration_sec: float = 0.0,
    on_progress: ProgressCb = None,
) -> tuple[bool, str]:
    """H.264 소스는 재인코딩 없이 HLS로 분할 — 디스크 I/O 수준 속도."""
    _clear_hls_tmp_dir(tmp_dir)
    return _run_hls_ffmpeg(
        source,
        tmp_dir,
        video_opts=["-c:v", "copy"],
        audio_opts=_hls_audio_opts(source, for_copy=True),
        duration_sec=duration_sec,
        on_progress=on_progress,
    )


def _transcode_to_hls(
    source: Path,
    tmp_dir: Path,
    *,
    duration_sec: float = 0.0,
    on_progress: ProgressCb = None,
) -> tuple[bool, str]:
    last_log = ""
    audio_opts = _hls_audio_opts(source, for_copy=False)

    for _encoder_name, input_opts, video_opts in _h264_transcode_plans():
        _clear_hls_tmp_dir(tmp_dir)
        ok, log = _run_hls_ffmpeg(
            source,
            tmp_dir,
            video_opts=video_opts,
            audio_opts=audio_opts,
            input_opts=input_opts,
            duration_sec=duration_sec,
            on_progress=on_progress,
        )
        if ok and _proxy_hls_ready(tmp_dir):
            return True, log
        last_log = log or last_log
    return False, last_log


def _build_proxy(
    source: Path,
    tmp_dir: Path,
    *,
    duration_sec: float = 0.0,
    on_progress: ProgressCb = None,
) -> tuple[bool, str]:
    if _can_hls_stream_copy(source):
        ok, log = _remux_to_hls_copy(
            source, tmp_dir, duration_sec=duration_sec, on_progress=on_progress
        )
        if ok and _proxy_hls_ready(tmp_dir):
            logger.info("Playback proxy HLS remux (stream copy): %s", source.name)
            return True, log
        _clear_hls_tmp_dir(tmp_dir)
    return _transcode_to_hls(
        source, tmp_dir, duration_sec=duration_sec, on_progress=on_progress
    )


def _run_proxy_job(source: Path, hls_dir: Path, key: str) -> None:
    tmp_dir = hls_dir.with_name(f"{hls_dir.name}.tmp")
    duration_sec = _probe_duration_sec(source)

    def _on_progress(pct: float, eta: float | None) -> None:
        with _LOCK:
            row = _JOBS.get(key)
            if row is not None and row.get("status") == "building":
                row["progress"] = round(pct, 1)
                row["eta_sec"] = round(eta) if eta is not None else None

    try:
        _remove_path(tmp_dir)
        ok, log = _build_proxy(
            source, tmp_dir, duration_sec=duration_sec, on_progress=_on_progress
        )
        if ok and _proxy_hls_ready(tmp_dir):
            if hls_dir.exists():
                shutil.rmtree(hls_dir, ignore_errors=True)
            tmp_dir.rename(hls_dir)
            with _LOCK:
                _JOBS[key] = {"status": "ready", "error": None}
            logger.info("Playback proxy HLS ready: %s -> %s", source.name, hls_dir.name)
            _maybe_evict_after_build()
            return
        _remove_path(tmp_dir)
        err = log or "ffmpeg 변환 실패 (브라우저 호환 HLS 생성 불가)"
        logger.warning("Playback proxy HLS failed: %s (%s)", source, err[-400:])
        with _LOCK:
            _JOBS[key] = {"status": "failed", "error": err}
    except Exception as exc:
        _remove_path(tmp_dir)
        with _LOCK:
            _JOBS[key] = {"status": "failed", "error": str(exc)}
