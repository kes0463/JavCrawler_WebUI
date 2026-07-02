from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from javstory.utils.ffmpeg_path import get_ffmpeg, get_ffprobe, path_for_ffmpeg


@dataclass(frozen=True)
class PreviewProgressInfo:
    segment_index: int = 0
    segment_total: int = 0
    source_position_sec: float = 0.0
    source_duration_sec: float = 0.0


ProgressCb = Optional[Callable[[int, PreviewProgressInfo | None], None]]

logger = logging.getLogger(__name__)

SEGMENT_COUNT = 10
SEGMENT_SEC = 2.0
MARGIN_RATIO = 0.02  # 앞뒤 2% 여유 — 처음~끝 구간을 균등 샘플링
MAX_PREVIEW_BYTES = 5 * 1024 * 1024
ENCODE_QUALITIES = (75, 45)
MP4_CRF_FROM_QUALITY = {90: 23, 75: 26, 60: 28, 45: 30}
PREVIEW_FPS = 20
PREVIEW_WIDTH = 720
MONTAGE_META_KEY = f"{SEGMENT_COUNT}x{SEGMENT_SEC}@segment-ss-mp4"
# 구버전 몽타주 — 이미 생성된 프리뷰는 재큐잉하지 않음
LEGACY_MONTAGE_META_KEYS = frozenset(
    {
        "5x3.0@segment-ss-mp4",
        "10x3.0@segment-ss-mp4",
    }
)
ACCEPTED_MONTAGE_META_KEYS = frozenset({MONTAGE_META_KEY, *LEGACY_MONTAGE_META_KEYS})


def _preview_ffmpeg_threads() -> int:
    raw = (os.environ.get("JAVSTORY_PREVIEW_FFMPEG_THREADS", "") or "").strip()
    try:
        n = int(raw) if raw else 6
    except ValueError:
        n = 6
    return max(1, min(16, n))


def _preview_x264_preset() -> str:
    preset = (os.environ.get("JAVSTORY_PREVIEW_X264_PRESET", "") or "veryfast").strip()
    return preset or "veryfast"


def _preview_vf() -> str:
    return f"fps={PREVIEW_FPS},scale={PREVIEW_WIDTH}:-2:flags=lanczos"


def _preview_use_nvenc() -> bool:
    raw = (os.environ.get("JAVSTORY_PREVIEW_USE_NVENC", "") or "").strip().lower()
    if not raw:
        return True
    return raw not in {"0", "false", "no", "off"}


def _nvenc_cq_from_crf(crf: int) -> int:
    return max(18, min(40, int(crf)))


def _append_h264_encode_args(
    cmd: list[str],
    *,
    crf: int,
    threads: int,
    use_nvenc: bool,
) -> None:
    if use_nvenc:
        cmd += [
            "-c:v",
            "h264_nvenc",
            "-preset",
            "p4",
            "-rc",
            "vbr",
            "-cq",
            str(_nvenc_cq_from_crf(crf)),
            "-profile:v",
            "main",
            "-level:v",
            "4.1",
            "-tag:v",
            "avc1",
            "-pix_fmt",
            "yuv420p",
        ]
    else:
        cmd += [
            "-c:v",
            "libx264",
            "-preset",
            _preview_x264_preset(),
            "-crf",
            str(crf),
            "-threads",
            str(threads),
            "-profile:v",
            "main",
            "-level:v",
            "4.1",
            "-pix_fmt",
            "yuv420p",
        ]


def _append_mp4_mux_flags(cmd: list[str]) -> None:
    cmd += ["-movflags", "+faststart"]


def _segment_output_ok(out: Path, seg_len: float) -> bool:
    if not out.is_file():
        return False
    try:
        if out.stat().st_size <= 0:
            return False
    except OSError:
        return False
    return _ffprobe_duration_sec(out) >= seg_len * 0.65


def _concat_output_ok(out: Path, segment_count: int, *, seg_len: float = SEGMENT_SEC) -> bool:
    if not out.is_file():
        return False
    try:
        if out.stat().st_size <= 0:
            return False
    except OSError:
        return False
    min_expected = max(8.0, segment_count * seg_len * 0.55)
    return _ffprobe_duration_sec(out) >= min_expected


def _preview_skip_webp_default() -> bool:
    raw = (os.environ.get("JAVSTORY_PREVIEW_SKIP_WEBP", "") or "").strip().lower()
    if not raw:
        return False
    return raw in {"1", "true", "yes", "on"}


def _preview_work_dir() -> Path:
    from javstory.config.app_config import DATA_ROOT

    base = DATA_ROOT / "cache" / "preview_work"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _preview_segment_temp_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="preview_seg_", dir=str(_preview_work_dir())))


def _preview_montage_temp_file() -> Path:
    fd, tmp_name = tempfile.mkstemp(
        suffix=".mp4",
        prefix="preview_montage_",
        dir=str(_preview_work_dir()),
    )
    os.close(fd)
    return Path(tmp_name)


def _segment_extract_timeout_sec() -> int:
    return 300


def _preview_montage_timeout_sec() -> int | None:
    """몽타주 ffmpeg 타임아웃(초). 0 이하이면 제한 없음. 기본 30분."""
    raw = (os.environ.get("JAVSTORY_PREVIEW_ENCODE_TIMEOUT_SEC", "") or "").strip()
    if not raw:
        return 1800
    try:
        n = int(raw)
    except ValueError:
        return 1800
    if n <= 0:
        return None
    return max(120, min(7200, n))


def montage_preview_params(*, seed: int = 0, skip_webp: bool = False) -> dict[str, object]:
    return {"montage": MONTAGE_META_KEY, "seed": int(seed), "skip_webp": bool(skip_webp)}


def preview_asset_paths(webp_path: Path | str) -> tuple[Path, Path, Path]:
    webp = Path(webp_path)
    return webp, webp.with_suffix(".mp4"), webp.with_suffix(webp.suffix + ".meta.json")


def _meta_params(meta_path: Path) -> dict[str, object]:
    try:
        if not meta_path.is_file():
            return {}
        import json

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        params = meta.get("params")
        return params if isinstance(params, dict) else {}
    except Exception:
        return {}


def _meta_montage_key(meta_path: Path) -> str | None:
    v = _meta_params(meta_path).get("montage")
    return str(v) if v else None


def _meta_skip_webp(meta_path: Path) -> bool:
    return bool(_meta_params(meta_path).get("skip_webp"))


def _expected_duration_for_montage_key(key: str | None) -> float:
    if not key:
        return 0.0
    m = re.match(r"^(\d+)x([\d.]+)@", key.strip())
    if not m:
        return 0.0
    try:
        return float(m.group(1)) * float(m.group(2))
    except ValueError:
        return 0.0


def resolve_preview_media_type(webp_path: Path | str) -> str | None:
    """UI/API용 프리뷰 미디어 종류 (mp4|webp). 몽타주 메타가 있으면 구 webp보다 mp4 우선."""
    webp, mp4, meta_path = preview_asset_paths(webp_path)
    try:
        mp4_ok = mp4.is_file() and mp4.stat().st_size > 0
        if mp4_ok and meta_path.is_file():
            if _meta_montage_key(meta_path) in ACCEPTED_MONTAGE_META_KEYS:
                return "mp4"
        if is_montage_preview_fresh(webp_path=webp_path):
            return "mp4"
        if webp.is_file() and webp.stat().st_size > 0:
            return "webp"
        if mp4_ok:
            return "mp4"
    except OSError:
        pass
    return None


def is_montage_preview_fresh(
    *,
    webp_path: Path | str,
    video_path: Path | str | None = None,
) -> bool:
    """10×2초(또는 구버전 5×3·10×3) MP4 몽타주가 최신인지 확인."""
    webp, mp4, meta_path = preview_asset_paths(webp_path)
    try:
        if not mp4.is_file() or mp4.stat().st_size <= 0:
            return False
        skip_webp = _meta_skip_webp(meta_path)
        if not skip_webp:
            if not webp.is_file() or webp.stat().st_size <= 0:
                return False
    except OSError:
        return False

    meta_key = _meta_montage_key(meta_path)
    if meta_key not in ACCEPTED_MONTAGE_META_KEYS:
        return False

    expected = _expected_duration_for_montage_key(meta_key)
    if expected > 0 and _ffprobe_duration_sec(mp4) < expected * 0.85:
        return False

    if video_path is None:
        return True

    from javstory.utils.derived_cache import is_up_to_date

    vp = Path(video_path)
    if not vp.is_file():
        return False
    params = _meta_params(meta_path)
    check_params = {
        "montage": meta_key,
        "seed": int(params.get("seed") or 0),
        "skip_webp": bool(params.get("skip_webp")),
    }
    return is_up_to_date(
        meta_path=meta_path,
        inputs={"video": vp},
        params=check_params,
    )


def _startupinfo_hidden() -> object | None:
    if os.name != "nt":
        return None
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return si


def _clamp(p: int) -> int:
    try:
        return int(max(0, min(100, p)))
    except Exception:
        return 0


def _format_media_timestamp(sec: float) -> str:
    total = max(0, int(sec))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_preview_progress_message(info: PreviewProgressInfo | None) -> str:
    if (
        info
        and info.segment_total > 0
        and info.segment_index > 0
        and info.source_duration_sec > 0
    ):
        pos = _format_media_timestamp(info.source_position_sec)
        total = _format_media_timestamp(info.source_duration_sec)
        return f"구간 {info.segment_index}/{info.segment_total} · 원본 {pos} / {total}"
    return "인코딩 중…"


def _emit_progress(
    progress_callback: ProgressCb,
    percent: int,
    info: PreviewProgressInfo | None = None,
) -> None:
    if not progress_callback:
        return
    progress_callback(_clamp(percent), info)


_FFMPEG_TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")


def _parse_ffmpeg_time_sec(chunk: str) -> float | None:
    m = _FFMPEG_TIME_RE.search(chunk)
    if not m:
        return None
    try:
        h, mi, s = m.groups()
        return int(h) * 3600 + int(mi) * 60 + float(s)
    except (TypeError, ValueError):
        return None


def _run_ffmpeg_with_stderr_progress(
    cmd: list[str],
    *,
    timeout: int | None,
    on_stderr_line: Callable[[str], None] | None = None,
) -> tuple[int, str]:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        startupinfo=_startupinfo_hidden(),
    )
    stderr_chunks: list[str] = []

    def _read_stderr() -> None:
        if proc.stderr is None:
            return
        for raw in iter(proc.stderr.readline, b""):
            txt = raw.decode("utf-8", errors="replace")
            stderr_chunks.append(txt)
            if on_stderr_line:
                on_stderr_line(txt)

    reader = threading.Thread(target=_read_stderr, daemon=True)
    reader.start()
    try:
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired as e_to:
        proc.kill()
        proc.wait(timeout=10)
        return -999, f"TimeoutExpired: {e_to}"
    finally:
        reader.join(timeout=5)
    return int(rc), "".join(stderr_chunks)


def _ffprobe_duration_sec(path: Path) -> float:
    try:
        cp = subprocess.run(
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
            startupinfo=_startupinfo_hidden(),
            check=False,
        )
        v = (cp.stdout or "").strip()
        return float(v) if v else 0.0
    except Exception:
        return 0.0


def _resolve_preview_source(video_path: Path) -> Path | None:
    """몽타주 소스: TS는 remux MP4 캐시, 그 외는 원본."""
    src = Path(video_path)
    if not src.is_file():
        return None
    from javstory.library.playback_proxy import ensure_ffmpeg_processing_source

    return ensure_ffmpeg_processing_source(src)


def compute_montage_segments(
    dur: float,
    *,
    segment_count: int = SEGMENT_COUNT,
    segment_sec: float = SEGMENT_SEC,
    seed: int = 0,
) -> list[tuple[float, float]]:
    """영상 처음~끝(앞뒤 2% 여유)을 균등 샘플링한 (start, duration) 목록."""
    if dur <= 0:
        return []

    n = max(1, segment_count)
    seg_len = float(segment_sec)

    if dur < n * seg_len:
        n = max(1, min(n, int(dur / seg_len) or 1))
        seg_len = min(seg_len, dur / n) if n else seg_len

    usable_start = dur * MARGIN_RATIO
    usable_end = dur * (1.0 - MARGIN_RATIO)
    usable = usable_end - usable_start

    if usable <= seg_len:
        start = max(0.0, min(dur - seg_len, (dur - seg_len) / 2))
        return [(start, min(seg_len, dur))]

    seed_offset = 0.0
    if seed:
        seed_offset = ((seed % 7) - 3) * 0.01 * usable
    segments: list[tuple[float, float]] = []

    for i in range(n):
        if n == 1:
            center = usable_start + usable / 2.0
        else:
            center = usable_start + (i / (n - 1)) * usable + seed_offset
        center = max(usable_start + seg_len / 2.0, min(usable_end - seg_len / 2.0, center))
        start = max(0.0, center - seg_len / 2.0)
        if start + seg_len > dur:
            start = max(0.0, dur - seg_len)
        segments.append((start, seg_len))

    return segments


def _build_montage_filter(segments: list[tuple[float, float]]) -> str:
    """filter_complex 몽타주 (split 없이 trim만 쓰면 전 구간이 t=0 근처로 붙는 ffmpeg 버그가 있음)."""
    n = len(segments)
    if n == 1:
        start, seg_len = segments[0]
        end = start + seg_len
        return (
            f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS,"
            f"fps={PREVIEW_FPS},scale={PREVIEW_WIDTH}:-2:flags=lanczos[outv]"
        )
    split_labels = "".join(f"[s{i}]" for i in range(n))
    parts = [f"[0:v]split={n}{split_labels}"]
    vlabels: list[str] = []
    for i, (start, seg_len) in enumerate(segments):
        end = start + seg_len
        parts.append(
            f"[s{i}]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS,"
            f"fps={PREVIEW_FPS},scale={PREVIEW_WIDTH}:-2:flags=lanczos[v{i}]"
        )
        vlabels.append(f"[v{i}]")
    parts.append(f"{''.join(vlabels)}concat=n={n}:v=1:a=0[outv]")
    return ";".join(parts)


def _encode_segment_webp(
    *,
    src: Path,
    out: Path,
    start: float,
    seg_len: float,
    quality: int,
) -> tuple[int, str]:
    frame_count = max(1, int(seg_len * PREVIEW_FPS))
    cmd = [
        get_ffmpeg(),
        "-y",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(src),
        "-t",
        f"{seg_len:.3f}",
        "-an",
        "-vf",
        _preview_vf(),
        "-frames:v",
        str(frame_count),
        "-preset",
        "picture",
        "-quality",
        str(quality),
        "-compression_level",
        "6",
        str(out),
    ]
    try:
        cp = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=_startupinfo_hidden(),
            check=False,
            timeout=120,
        )
        return cp.returncode, (cp.stderr or b"").decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired as e_to:
        return -999, f"TimeoutExpired: {e_to}"
    except Exception as e_run:
        return -1, f"subprocess exception: {e_run!r}"


def _concat_webp_segments(segment_paths: list[Path], out: Path, quality: int) -> tuple[int, str]:
    if not segment_paths:
        return -1, "no segments"
    if len(segment_paths) == 1:
        shutil.copy2(segment_paths[0], out)
        return 0, ""

    list_path = out.with_suffix(out.suffix + ".concat.txt")
    try:
        lines = []
        for p in segment_paths:
            # concat demuxer: 경로 이스케이프
            escaped = str(p.resolve()).replace("'", "'\\''")
            lines.append(f"file '{escaped}'")
        list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        cmd = [
            get_ffmpeg(),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-an",
            "-c:v",
            "libwebp",
            "-loop",
            "0",
            "-preset",
            "picture",
            "-quality",
            str(quality),
            "-compression_level",
            "6",
            str(out),
        ]
        cp = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=_startupinfo_hidden(),
            check=False,
            timeout=180,
        )
        return cp.returncode, (cp.stderr or b"").decode("utf-8", errors="replace")
    finally:
        try:
            list_path.unlink(missing_ok=True)
        except OSError:
            pass


def _extract_segment_mp4(
    *,
    src: Path,
    out: Path,
    start: float,
    seg_len: float,
    crf: int,
    threads: int,
    fast_seek: bool = True,
    prefer_nvenc: bool | None = None,
) -> tuple[int, str]:
    if prefer_nvenc is None:
        prefer_nvenc = _preview_use_nvenc()

    def _attempt(*, nvenc: bool, seek_fast: bool) -> tuple[int, str]:
        cmd = [
            get_ffmpeg(),
            "-y",
            "-err_detect",
            "ignore_err",
        ]
        if nvenc:
            cmd += ["-hwaccel", "auto"]
        src_path = path_for_ffmpeg(src)
        out_path = path_for_ffmpeg(out, output=True)
        if seek_fast:
            cmd += ["-ss", f"{start:.3f}", "-i", src_path, "-t", f"{seg_len:.3f}"]
        else:
            cmd += ["-i", src_path, "-ss", f"{start:.3f}", "-t", f"{seg_len:.3f}"]
        cmd += ["-an", "-vf", _preview_vf()]
        _append_h264_encode_args(cmd, crf=crf, threads=threads, use_nvenc=nvenc)
        _append_mp4_mux_flags(cmd)
        cmd.append(out_path)
        try:
            cp = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=_startupinfo_hidden(),
                check=False,
                timeout=_segment_extract_timeout_sec(),
            )
            return cp.returncode, (cp.stderr or b"").decode("utf-8", errors="replace")
        except subprocess.TimeoutExpired as e_to:
            return -999, f"TimeoutExpired: {e_to}"
        except Exception as e_run:
            return -1, f"subprocess exception: {e_run!r}"

    encoders = (True, False) if prefer_nvenc else (False,)
    last_rc = -1
    last_stderr = ""
    for nvenc in encoders:
        last_rc, last_stderr = _attempt(nvenc=nvenc, seek_fast=fast_seek)
        if last_rc == 0 and _segment_output_ok(out, seg_len):
            return last_rc, last_stderr
        if nvenc and prefer_nvenc:
            logger.warning(
                "preview segment NVENC failed, CPU fallback: %s (seek_fast=%s)",
                src.name,
                fast_seek,
            )
    return last_rc, last_stderr


def _concat_mp4_segments(segment_paths: list[Path], out: Path) -> tuple[int, str]:
    if not segment_paths:
        return -1, "no segments"
    if len(segment_paths) == 1:
        shutil.copy2(segment_paths[0], out)
        return 0, ""

    list_path = out.with_suffix(out.suffix + ".concat.txt")
    try:
        lines = []
        for p in segment_paths:
            escaped = str(p.resolve()).replace("'", "'\\''")
            lines.append(f"file '{escaped}'")
        list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        out_path = path_for_ffmpeg(out, output=True)
        list_arg = str(list_path.resolve())
        # concat -c copy는 구간별 SPS/PPS가 달라 브라우저 <video> 재생이 실패하는 경우가 많음 → 항상 재인코딩
        threads = _preview_ffmpeg_threads()
        last_stderr = ""
        encoders = (True, False) if _preview_use_nvenc() else (False,)
        last_rc = -1
        for nvenc in encoders:
            cmd_reencode = [
                get_ffmpeg(),
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                list_arg,
                "-an",
            ]
            _append_h264_encode_args(
                cmd_reencode,
                crf=28,
                threads=threads,
                use_nvenc=nvenc,
            )
            cmd_reencode += [
                "-reset_timestamps",
                "1",
            ]
            _append_mp4_mux_flags(cmd_reencode)
            cmd_reencode.append(out_path)
            cp2 = subprocess.run(
                cmd_reencode,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=_startupinfo_hidden(),
                check=False,
                timeout=300,
            )
            last_stderr = (cp2.stderr or b"").decode("utf-8", errors="replace")
            if cp2.returncode == 0 and _concat_output_ok(out, len(segment_paths)):
                return cp2.returncode, last_stderr
            if nvenc:
                logger.warning("preview concat NVENC failed, CPU fallback")
        return cp2.returncode, last_stderr
    finally:
        try:
            list_path.unlink(missing_ok=True)
        except OSError:
            pass


def _run_ffmpeg_montage_segmented(
    *,
    src: Path,
    out: Path,
    segments: list[tuple[float, float]],
    quality: int,
    progress_callback: ProgressCb = None,
    progress_from: int = 20,
    progress_to: int = 82,
    source_duration_sec: float = 0.0,
) -> tuple[int, str]:
    """구간별 추출 후 concat (긴 원본에서 filter_complex split보다 빠름)."""
    threads = _preview_ffmpeg_threads()
    crf = MP4_CRF_FROM_QUALITY.get(quality, 28)
    temp_dir = _preview_segment_temp_dir()
    last_stderr = ""
    try:
        seg_paths: list[Path] = []
        n = max(1, len(segments))
        span = max(1, progress_to - progress_from)
        src_dur = source_duration_sec if source_duration_sec > 0 else _ffprobe_duration_sec(src)
        for i, (start, seg_len) in enumerate(segments):
            if progress_callback:
                _emit_progress(
                    progress_callback,
                    _clamp(progress_from + int(span * i / n)),
                    PreviewProgressInfo(
                        segment_index=i + 1,
                        segment_total=n,
                        source_position_sec=start,
                        source_duration_sec=src_dur,
                    ),
                )
            seg_out = temp_dir / f"seg_{i:02d}.mp4"
            rc = -1
            stderr = ""
            for seek_fast in (True, False):
                rc, stderr = _extract_segment_mp4(
                    src=src,
                    out=seg_out,
                    start=start,
                    seg_len=seg_len,
                    crf=crf,
                    threads=threads,
                    fast_seek=seek_fast,
                )
                last_stderr = stderr
                if rc == 0 and _segment_output_ok(seg_out, seg_len):
                    break
            if rc != 0 or not _segment_output_ok(seg_out, seg_len):
                return rc, stderr
            seg_paths.append(seg_out)
            if progress_callback:
                _emit_progress(
                    progress_callback,
                    _clamp(progress_from + int(span * (i + 1) / n)),
                    PreviewProgressInfo(
                        segment_index=i + 1,
                        segment_total=n,
                        source_position_sec=start,
                        source_duration_sec=src_dur,
                    ),
                )

        rc, stderr = _concat_mp4_segments(seg_paths, out)
        last_stderr = stderr or last_stderr
        return rc, last_stderr
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _run_ffmpeg_montage(
    *,
    src: Path,
    out: Path,
    segments: list[tuple[float, float]],
    quality: int,
    progress_callback: ProgressCb = None,
    progress_from: int = 20,
    progress_to: int = 82,
    source_duration_sec: float = 0.0,
) -> tuple[int, str]:
    rc, stderr = _run_ffmpeg_montage_segmented(
        src=src,
        out=out,
        segments=segments,
        quality=quality,
        progress_callback=progress_callback,
        progress_from=progress_from,
        progress_to=progress_to,
        source_duration_sec=source_duration_sec,
    )
    if (
        rc == 0
        and out.is_file()
        and out.stat().st_size > 0
        and _validate_montage_duration(out, segments)
    ):
        return rc, stderr

    logger.warning(
        "segmented montage unsuitable (rc=%s), retrying filter_complex for %s",
        rc,
        src.name,
    )
    return _run_ffmpeg_montage_filter_complex(
        src=src,
        out=out,
        segments=segments,
        quality=quality,
        progress_callback=progress_callback,
        progress_from=progress_from,
        progress_to=progress_to,
        source_duration_sec=source_duration_sec,
    )


def _run_ffmpeg_montage_filter_complex(
    *,
    src: Path,
    out: Path,
    segments: list[tuple[float, float]],
    quality: int,
    progress_callback: ProgressCb = None,
    progress_from: int = 20,
    progress_to: int = 82,
    source_duration_sec: float = 0.0,
) -> tuple[int, str]:
    filter_complex = _build_montage_filter(segments)
    is_mp4 = out.suffix.lower() == ".mp4"
    expected_out = max(1.0, sum(s[1] for s in segments))
    span = max(1, progress_to - progress_from)
    last_reported = -1
    n = max(1, len(segments))
    src_dur = source_duration_sec if source_duration_sec > 0 else _ffprobe_duration_sec(src)

    def _on_stderr_line(txt: str) -> None:
        nonlocal last_reported
        if not progress_callback:
            return
        t = _parse_ffmpeg_time_sec(txt)
        if t is None:
            return
        frac = min(1.0, max(0.0, t / expected_out))
        p = progress_from + int(span * frac)
        if p > last_reported:
            last_reported = p
            seg_idx = min(n, max(1, int(frac * n) + (1 if frac > 0 else 0)))
            start = segments[seg_idx - 1][0] if seg_idx <= len(segments) else 0.0
            _emit_progress(
                progress_callback,
                p,
                PreviewProgressInfo(
                    segment_index=seg_idx,
                    segment_total=n,
                    source_position_sec=start,
                    source_duration_sec=src_dur,
                ),
            )

    def _base_cmd(*, nvenc: bool) -> list[str]:
        cmd = [
            get_ffmpeg(),
            "-y",
            "-fflags",
            "+genpts+igndts",
            "-probesize",
            "50M",
            "-analyzeduration",
            "50M",
            "-err_detect",
            "ignore_err",
        ]
        if nvenc:
            cmd += ["-hwaccel", "auto"]
        cmd += [
            "-i",
            path_for_ffmpeg(src),
            "-filter_complex",
            filter_complex,
            "-map",
            "[outv]",
            "-an",
        ]
        return cmd

    if is_mp4:
        crf = MP4_CRF_FROM_QUALITY.get(quality, 28)
        threads = _preview_ffmpeg_threads()
        encoders = (True, False) if _preview_use_nvenc() else (False,)
        last_rc = -1
        last_stderr = ""
        for nvenc in encoders:
            cmd = _base_cmd(nvenc=nvenc)
            _append_h264_encode_args(cmd, crf=crf, threads=threads, use_nvenc=nvenc)
            _append_mp4_mux_flags(cmd)
            cmd.append(path_for_ffmpeg(out, output=True))
            last_rc, last_stderr = _run_ffmpeg_with_stderr_progress(
                cmd,
                timeout=_preview_montage_timeout_sec(),
                on_stderr_line=_on_stderr_line,
            )
            if last_rc == 0 and out.is_file() and out.stat().st_size > 0:
                return last_rc, last_stderr
            if nvenc:
                logger.warning("preview filter_complex NVENC failed, CPU fallback: %s", src.name)
        return last_rc, last_stderr

    cmd = _base_cmd(nvenc=False)
    cmd += [
        "-loop",
        "0",
        "-preset",
        "picture",
        "-quality",
        str(quality),
        "-compression_level",
        "6",
        path_for_ffmpeg(out, output=True),
    ]
    try:
        return _run_ffmpeg_with_stderr_progress(
            cmd,
            timeout=_preview_montage_timeout_sec(),
            on_stderr_line=_on_stderr_line,
        )
    except Exception as e_run:
        return -1, f"subprocess exception: {e_run!r}"


def _webp_from_mp4(
    mp4: Path,
    webp: Path,
    quality: int = 75,
    progress_callback: ProgressCb = None,
) -> tuple[int, str]:
    """데스크톱(QML AnimatedImage)용 WebP — MP4 몽타주에서 파생."""
    if progress_callback:
        _emit_progress(progress_callback, 85, None)
    cmd = [
        get_ffmpeg(),
        "-y",
        "-i",
        str(mp4),
        "-an",
        "-c:v",
        "libwebp",
        "-loop",
        "0",
        "-preset",
        "picture",
        "-quality",
        str(quality),
        "-compression_level",
        "6",
        str(webp),
    ]
    try:
        cp = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=_startupinfo_hidden(),
            check=False,
            timeout=180,
        )
        rc = cp.returncode
        stderr = (cp.stderr or b"").decode("utf-8", errors="replace")
        if rc == 0 and progress_callback:
            _emit_progress(progress_callback, 98, None)
        return rc, stderr
    except subprocess.TimeoutExpired as e_to:
        return -999, f"TimeoutExpired: {e_to}"
    except Exception as e_run:
        return -1, f"subprocess exception: {e_run!r}"


def _validate_montage_duration(out: Path, segments: list[tuple[float, float]]) -> bool:
    """MP4는 ffprobe 길이, WebP는 파일 크기로 검증."""
    if not out.is_file():
        return False
    expected = sum(s[1] for s in segments)
    n = max(1, len(segments))
    if out.suffix.lower() == ".mp4":
        dur = _ffprobe_duration_sec(out)
        if dur >= expected * 0.85:
            return True
        try:
            size = out.stat().st_size
        except OSError:
            return False
        # concat copy 메타가 짧게 잡히는 경우 — 최소 길이·용량으로 완화
        min_dur = max(12.0, expected * 0.55)
        min_size = max(120_000, n * 20_000)
        return dur >= min_dur and size >= min_size
    size = out.stat().st_size
    if size < 80_000:
        return False
    min_expected = max(400_000, n * 35_000)
    ok = size >= min_expected
    return ok


def create_golden_preview(
    *,
    product_code: str,
    video_path: str | Path,
    output_path: str | Path,
    progress_callback: ProgressCb = None,
    duration_sec: float = 8.0,
    seed: int = 0,
    segment_count: int = SEGMENT_COUNT,
    segment_sec: float = SEGMENT_SEC,
    skip_webp: bool | None = None,
) -> Path | None:
    """
    Golden Preview: 10구간×2초 몽타주 MP4 (+ 선택적 WebP).

    - 원본 영상 전체(앞뒤 2% 제외)를 10등분 샘플링 → 재생 시 처음~끝 순서로 훑음
    - highlight.mp4는 사용하지 않음 (video_path 원본만)
    """
    _ = duration_sec  # legacy callers pass 8.0
    if skip_webp is None:
        skip_webp = _preview_skip_webp_default()
    pc = (product_code or "").strip().upper()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        _emit_progress(progress_callback, 5, None)

    src = _resolve_preview_source(Path(video_path))
    if not src or not src.is_file():
        return None

    dur = _ffprobe_duration_sec(src)
    segments = compute_montage_segments(
        dur,
        segment_count=segment_count,
        segment_sec=segment_sec,
        seed=seed,
    )
    if not segments:
        return None

    if progress_callback:
        _emit_progress(
            progress_callback,
            15,
            PreviewProgressInfo(
                segment_index=1,
                segment_total=len(segments),
                source_position_sec=segments[0][0],
                source_duration_sec=dur,
            ),
        )

    tmp_mp4: Path | None = None
    try:
        tmp_mp4 = _preview_montage_temp_file()
        out_mp4 = out.with_suffix(".mp4")

        last_rc = -1
        last_stderr = ""
        chosen_quality = ENCODE_QUALITIES[0]
        for qi, quality in enumerate(ENCODE_QUALITIES):
            last_rc, last_stderr = _run_ffmpeg_montage(
                src=src,
                out=tmp_mp4,
                segments=segments,
                quality=quality,
                progress_callback=progress_callback,
                progress_from=20,
                progress_to=82,
                source_duration_sec=dur,
            )
            if last_rc != 0 or not tmp_mp4.is_file() or tmp_mp4.stat().st_size <= 0:
                break
            if not _validate_montage_duration(tmp_mp4, segments):
                logger.warning(
                    "montage output too short: pc=%s expected~%.1fs",
                    pc,
                    sum(s[1] for s in segments),
                )
                last_rc = -2
                break
            chosen_quality = quality
            if tmp_mp4.stat().st_size <= MAX_PREVIEW_BYTES * 2:
                break

        if last_rc != 0 or not tmp_mp4.is_file() or tmp_mp4.stat().st_size <= 0:
            reason = _extract_ffmpeg_failure_reason(last_stderr)
            logger.warning(
                "create_golden_preview failed: pc=%s rc=%s reason=%s src=%s",
                pc,
                last_rc,
                reason,
                src,
            )
            raise RuntimeError(f"ffmpeg 실패(rc={last_rc}): {reason} | 입력: {src.name}")

        shutil.move(str(tmp_mp4), str(out_mp4))
        tmp_mp4 = None

        if skip_webp:
            if out.is_file() and out.resolve() != out_mp4.resolve():
                try:
                    out.unlink()
                except OSError:
                    pass
            if progress_callback:
                _emit_progress(progress_callback, 100, None)
            return out_mp4

        wrc, wstderr = _webp_from_mp4(
            out_mp4, out, quality=chosen_quality, progress_callback=progress_callback
        )
        if wrc != 0 or not out.is_file() or out.stat().st_size <= 0:
            reason = _extract_ffmpeg_failure_reason(wstderr)
            raise RuntimeError(f"WebP 파생 실패(rc={wrc}): {reason}")

        if progress_callback:
            _emit_progress(progress_callback, 100, None)
        return out
    finally:
        if tmp_mp4 and tmp_mp4.is_file():
            try:
                tmp_mp4.unlink()
            except OSError:
                pass


def _extract_ffmpeg_failure_reason(stderr_text: str) -> str:
    """ffmpeg stderr에서 사용자에게 보여줄 핵심 한 줄을 추출한다."""
    if not stderr_text:
        return "출력 없음"
    txt = stderr_text.strip()
    signatures = [
        ("TimeoutExpired", "인코딩 시간 초과(CPU 부하·대용량 원본 — 병렬 수를 줄이거나 타임아웃 연장)"),
        ("moov atom not found", "손상된 MP4(컨테이너 헤더 누락: moov atom not found)"),
        ("Invalid data found when processing input", "손상되었거나 미완성 영상 파일(Invalid data)"),
        ("No such file or directory", "원본 영상 파일을 열 수 없음"),
        ("Permission denied", "원본 영상 파일 접근 권한 없음"),
        ("Operation not permitted", "원본 영상 파일 접근 거부"),
        ("Invalid argument", "ffmpeg 출력/입력 경로 오류(Invalid argument — 경로·코덱 확인)"),
        ("Option not found", "ffmpeg 옵션/입력 경로 오류(Option not found)"),
        ("Protocol not found", "지원하지 않는 입력 경로/프로토콜"),
        ("low score", "컨테이너 형식 식별 실패(파일 손상 의심)"),
    ]
    for needle, label in signatures:
        if needle.lower() in txt.lower():
            return label
    for line in reversed(txt.splitlines()):
        s = line.strip()
        if s.lower().startswith("error") and len(s) < 240:
            return s
    return txt.splitlines()[-1].strip()[:200] if txt.splitlines() else "원인 불명"
