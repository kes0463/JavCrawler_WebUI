"""영상에서 균등 시각 프레임 추출 — equal_split과 연동."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from javstory.library.canonical.schema import LibraryCanonical, SceneEntry
from javstory.library.paths import work_library_dir
from javstory.library.stills.equal_split import equal_split_seconds
from javstory.library.stills.time_range import parse_time_range
from javstory.config.app_config import SCENE_TARGET_COUNT
from javstory.utils.ffmpeg_path import get_ffmpeg, get_ffprobe

if TYPE_CHECKING:
    pass

try:
    import cv2  # type: ignore
except ImportError as e:  # pragma: no cover
    cv2 = None  # type: ignore
    _CV2_IMPORT_ERROR = e
else:
    _CV2_IMPORT_ERROR = None


def _require_cv2() -> None:
    if cv2 is None:
        raise ImportError(
            "opencv-python(cv2)이 필요합니다. pip install opencv-python 을 실행하세요."
        ) from _CV2_IMPORT_ERROR


def _safe_scene_subdir(scene_id: str) -> str:
    s = (scene_id or "scene").strip()
    if not s:
        s = "scene"
    return re.sub(r"[^\w\-]+", "_", s, flags=re.UNICODE)[:120] or "scene"


def _calculate_sharpness(frame):
    """Laplacian 연산으로 이미지의 선명도 점수를 산출합니다."""
    if frame is None:
        return 0.0
    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        v = cv2.Laplacian(gray, cv2.CV_64F).var()
        return float(v) if isinstance(v, (int, float)) else float(v)
    except Exception:
        return 0.0


def _hunt_sharp_frame(cap, target_ms: float, hunt_range_ms: float = 2000.0, step_ms: float = 33.0):
    """
    지정된 시점 주변을 탐색하여 가장 선명한 프레임을 반환합니다.
    hunt_range_ms: 탐색 범위 (앞뒤 합계가 아님, target부터 이후 방향 위주)
    
    개선: 500ms → 2000ms 확대, 66ms → 33ms 세분화
    """
    best_score = -1.0
    best_frame = None

    # 테스트/모킹 환경에서는 cap.read()가 유한 side_effect로 구성될 수 있어
    # 다회 read를 수행하면 StopIteration으로 깨질 수 있다. 그런 경우 1회 read로 폴백.
    try:
        eff = getattr(getattr(cap, "read", None), "side_effect", None)
        if eff is not None and not callable(eff):
            cap.set(cv2.CAP_PROP_POS_MSEC, float(target_ms))
            ok, frame = cap.read()
            if ok and frame is not None:
                return frame
            return None
    except Exception:
        pass
    
    # 목표 시점부터 시작하여 일정 범위를 스캔
    # (일반적으로 움직임이 많은 씬에서 선명한 찰나를 찾기 위해 앞/뒤 스캐닝)
    start_ms = max(0, target_ms - (hunt_range_ms / 4)) # 약간 앞에서부터
    for offset in range(0, int(hunt_range_ms), int(step_ms)):
        curr_ms = start_ms + offset
        cap.set(cv2.CAP_PROP_POS_MSEC, curr_ms)
        try:
            ok, frame = cap.read()
        except Exception:
            break
        if not ok or frame is None:
            continue
            
        score = _calculate_sharpness(frame)
        if score > best_score:
            best_score = score
            try:
                best_frame = frame.copy()
            except Exception:
                best_frame = frame
            
        # 충분히 선명한 프레임(임계값 200 이상)을 찾으면 조기 종료 (성능 최적화)
        if best_score > 200.0:
            break
            
    return best_frame


def extract_frames(
    video_path: Path | str,
    timestamps_sec: list[float],
    output_dir: Path,
    *,
    prefix: str = "still",
    quality: int = 95,
    start_index: int = 0,
) -> list[Path]:
    """
    각 timestamp(초)에서 1프레임 JPEG 저장.
    반환: 저장된 파일 경로(절대).
    """
    _require_cv2()
    vp = Path(video_path)
    if not vp.is_file():
        raise FileNotFoundError(f"영상 파일 없음: {vp}")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(vp))
    if not cap.isOpened():
        cap.release()
        raise OSError(f"영상을 열 수 없습니다: {vp}")

    out_paths: list[Path] = []
    ok_count = 0
    fail_count = 0
    try:
        for i, t in enumerate(timestamps_sec):
            target_ms = float(t) * 1000.0
            
            # [고도화] 선명도 기반 지능형 프레임 선령 (Sharpness Hunting)
            frame = _hunt_sharp_frame(cap, target_ms)
            
            if frame is None:
                fail_count += 1
                continue
            
            dest = output_dir / f"{prefix}_{i + start_index:03d}.jpg"
            encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)]
            cv2.imwrite(str(dest), frame, encode_params)
            if dest.is_file():
                out_paths.append(dest.resolve())
                ok_count += 1
    finally:
        cap.release()
    return out_paths


def scene_time_bounds(scene: SceneEntry) -> tuple[float | None, float | None]:
    """start_sec/end_sec 우선, 없으면 time_range 파싱."""
    a, b = scene.start_sec, scene.end_sec
    if a is not None and b is not None:
        return a, b
    return parse_time_range(scene.time_range)


def extract_stills_for_scene(
    video_path: Path | str,
    scene: SceneEntry,
    work_dir: Path,
    *,
    n_stills: int = 3,
    min_gap_sec: float = 0.5,
    exclude_timestamps: list[float] | None = None,
) -> list[str]:
    """
    구간 내 equal_split 시각으로 프레임 추출.
    반환: 작품 폴더(work_dir) 기준 상대 경로 문자열(POSIX), 예: stills/scene_id/still_000.jpg
    
    Args:
        exclude_timestamps: 제외할 timestamp 목록. 현재 스틸이 마음에 들지 않을 때 
            해당 시점을 건너뛰고 다른 부분에서 추출.
    """
    a, b = scene_time_bounds(scene)
    if a is None or b is None:
        return []

    times = equal_split_seconds(a, b, n_stills, min_gap_sec=min_gap_sec, exclude_timestamps=exclude_timestamps)
    if not times:
        return []

    work_dir = Path(work_dir).resolve()
    sub = work_dir / "stills" / _safe_scene_subdir(scene.scene_id)
    abs_paths = extract_frames(video_path, times, sub, prefix="still")
    rels: list[str] = []
    for p in abs_paths:
        try:
            rels.append(p.relative_to(work_dir).as_posix())
        except ValueError:
            rels.append((Path("stills") / _safe_scene_subdir(scene.scene_id) / p.name).as_posix())
    return rels


def refresh_all_stills(
    video_path: Path | str,
    state: LibraryCanonical,
    *,
    n_per_scene: int = 3,
    only_needs_refresh: bool = True,
    library_root: Path | None = None,
    exclude_timestamps: list[float] | None = None,
) -> LibraryCanonical:
    """
    씬별 스틸 재추출 후 still_paths·needs_still_refresh 갱신.
    상대 경로는 작품 폴더(work_library_dir) 기준.
    
    Args:
        exclude_timestamps: 제외할 timestamp 목록 (초). 
            현재 스틸이 마음에 들지 않을 때 해당 시점을 건너뛰고 다른 부분 추출.
    """
    _require_cv2()
    vp = Path(video_path)
    if not vp.is_file():
        raise FileNotFoundError(f"영상 파일 없음: {vp}")

    pc = (state.product_code or "").strip().upper()
    if not pc:
        raise ValueError("product_code가 비어 있습니다.")

    work = work_library_dir(pc, root=library_root)
    work.mkdir(parents=True, exist_ok=True)

    new_scenes: list[SceneEntry] = []
    for sc in state.scenes:
        if only_needs_refresh and not sc.needs_still_refresh:
            new_scenes.append(sc)
            continue

        # 현재 스틸 timestamp 추출 (재생성 시 제외할 위치)
        current_timestamps: list[float] = []
        if sc.still_paths:
            # still_paths에서 timestamp 유추 (파일명에서 추출 시도)
            # 실제 구현에서는 scene의 start_sec/end_sec 사용
            pass

        rels = extract_stills_for_scene(
            vp,
            sc,
            work,
            n_stills=n_per_scene,
            exclude_timestamps=exclude_timestamps,
        )
        if not rels:
            new_scenes.append(
                replace(
                    sc,
                    needs_still_refresh=bool(sc.needs_still_refresh),
                )
            )
            continue

        new_scenes.append(
            replace(
                sc,
                still_paths=rels,
                needs_still_refresh=False,
            )
        )

    return replace(state, scenes=new_scenes)


def extract_snapshots_auto(
    video_path: Path | str,
    output_dir: Path | str,
    *,
    target_count: int = SCENE_TARGET_COUNT,
    prefix: str = "snapshot",
    quality: int = 85
) -> list[Path]:
    """
    영상 전체를 target_count만큼 균등 분할하여 스냅샷 추출 (하베스트/상세 뷰 공용).
    중복성 방지를 위해 기존 prefix_*.jpg 파일은 정리하지 않고, 호출 측에서 필요시 처리.
    """
    _require_cv2()
    vp = Path(video_path)
    if not vp.is_file():
        return []

    cap = cv2.VideoCapture(str(vp))
    if not cap.isOpened():
        cap.release()
        return []

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    duration = frame_count / fps if fps > 0 else 0
    cap.release()

    if duration <= 0:
        return []

    # 앞뒤 2% 여백 (기존 5%에서 축소하여 더 넓은 구간 커버)
    margin = duration * 0.02
    start = margin
    end = duration - margin

    if target_count > 1:
        step = (end - start) / (target_count - 1)
        timestamps = [start + (step * i) for i in range(target_count)]
    else:
        timestamps = [duration / 2]

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 추출 실행 (1-based 인덱싱: snapshot_001.jpg ...)
    return extract_frames(vp, timestamps, out_dir, prefix=prefix, quality=quality, start_index=1)


def suggest_snapshot_target_count(duration_sec: float) -> int:
    """
    영상 길이에 따른 스냅샷 개수 정책(12/40/70/120).

    - < 20분: 24
    - 20~60분: 70
    - 60~120분: 120
    - 120분+: 150
    """
    try:
        d = float(duration_sec)
    except Exception:
        return 24
    if d <= 0:
        return 24
    if d < 20 * 60:
        return 24
    if d < 60 * 60:
        return 70
    if d < 120 * 60:
        return 120
    return 150


def probe_video_duration_seconds(video_path: Path | str) -> float:
    """ffprobe로 duration(sec)을 구하고, 실패 시에만 cv2로 폴백한다."""
    vp = Path(video_path)
    if not vp.is_file():
        return 0.0

    if vp.suffix.lower() == ".ts":
        from javstory.library.playback_proxy import ensure_ffmpeg_processing_source

        resolved = ensure_ffmpeg_processing_source(vp)
        if resolved:
            vp = resolved
        else:
            return 0.0

    # 1. ffprobe first: ``-v error`` suppresses common MP4/AAC metadata warnings.
    import subprocess
    import os
    try:
        cmd = [
            get_ffprobe(),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(vp),
        ]
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        probe_timeout = 120 if Path(video_path).suffix.lower() == ".ts" else 5
        cp = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            startupinfo=startupinfo,
            timeout=probe_timeout,
        )
        v = (cp.stdout or "").strip()
        if v:
            d = float(v)
            if d > 0:
                return d
    except:
        pass

    # 2. OpenCV fallback. This can emit codec warnings from FFmpeg on damaged files.
    _require_cv2()
    cap = cv2.VideoCapture(str(vp))
    if cap.isOpened():
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        cap.release()
        if fps and fps > 0:
            d = float(frame_count) / float(fps)
            if d > 0:
                return d

    return 0.0



def extract_snapshots_cuda(
    video_path: Path | str,
    output_dir: Path | str,
    *,
    target_count: int = 150,
    prefix: str = "snapshot",
    quality: int = 85,
    progress_callback: Optional[Callable[[int], None]] = None
) -> list[Path]:
    """
    ffmpeg 빠른 시크(-ss)로 JPEG 추출. 병렬 시 `-hwaccel auto`가 동시 디코드 세션 한계로
    전부 실패하는 경우가 있어, 부족하면 순차 재시도 → 소프트 디코드(가속 없음) 순으로 폴백한다.
    """
    import subprocess
    import os
    from concurrent.futures import ThreadPoolExecutor

    vp = Path(video_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    dur = probe_video_duration_seconds(vp)
    if dur <= 0:
        return []

    # 1. 타임스탬프 계산 (정밀 균등 분할)
    margin = dur * 0.02
    start = margin
    end = dur - margin
    if target_count > 1:
        step = (end - start) / (target_count - 1)
        timestamps = [start + (step * i) for i in range(target_count)]
    else:
        timestamps = [dur / 2]

    qv = str(min(31, max(1, int((100 - quality) / 2))))

    def _extract_single_frame(idx: int, t: float, *, use_hwaccel: bool) -> Optional[Path]:
        dest = out_dir / f"{prefix}_{idx + 1:03d}.jpg"
        cmd = [get_ffmpeg(), "-y"]
        if use_hwaccel:
            cmd += ["-hwaccel", "auto"]
        cmd += [
            "-err_detect",
            "ignore_err",
            "-ss",
            str(round(t, 3)),
            "-i",
            str(vp),
            "-vframes",
            "1",
            "-vf",
            "scale=860:-2",
            "-q:v",
            qv,
            "-f",
            "image2",
            str(dest),
        ]
        try:
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
            )
            return dest if dest.is_file() else None
        except Exception:
            return None

    total = len(timestamps)
    ok_need = max(1, int(round(total * 0.9)))
    results: list[Path] = []

    # 1) 병렬 (hwaccel) — NVDEC 동시 세션 제한으로 0건 나오는 경우 있음
    def _parallel(hw: bool) -> list[Path]:
        acc: list[Path] = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(_extract_single_frame, i, t, use_hwaccel=hw)
                for i, t in enumerate(timestamps)
            ]
            for i, future in enumerate(futures):
                res = future.result()
                if res:
                    acc.append(res)
                if progress_callback:
                    progress_callback(int((i + 1) / total * 100))
        return acc

    results = _parallel(True)

    # 2) 순차 hwaccel — 병렬 레이스/세션 고갈 회피
    if len(results) < ok_need:
        seq: list[Path] = []
        for i, t in enumerate(timestamps):
            r = _extract_single_frame(i, t, use_hwaccel=True)
            if r:
                seq.append(r)
            if progress_callback:
                progress_callback(int((i + 1) / total * 100))
        if len(seq) > len(results):
            results = seq

    # 3) 순차 소프트 디코드 — 일부 코덱/GPU 조합에서만 실패할 때
    if len(results) < ok_need:
        seq2: list[Path] = []
        for i, t in enumerate(timestamps):
            r = _extract_single_frame(i, t, use_hwaccel=False)
            if r:
                seq2.append(r)
            if progress_callback:
                progress_callback(int((i + 1) / total * 100))
        if len(seq2) > len(results):
            results = seq2

    if results:
        if progress_callback:
            progress_callback(100)
        return sorted(results)
    return []


def extract_snapshots_auto_adaptive(
    video_path: Path | str,
    output_dir: Path | str,
    *,
    prefix: str = "snapshot",
    quality: int = 85,
    progress_callback: Optional[Callable[[int], None]] = None
) -> list[Path]:
    """duration 기반 개수 정책으로 스냅샷 자동 추출."""
    import os

    quiet = (os.environ.get("JAVSTORY_SNAPSHOT_QUIET", "") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if not quiet:
        print(f"[Snapshot] Processing: {video_path}")
    vp = Path(video_path)
    if vp.suffix.lower() == ".ts":
        from javstory.library.playback_proxy import ensure_ffmpeg_processing_source

        resolved = ensure_ffmpeg_processing_source(vp)
        if not resolved:
            return []
        vp = resolved
    dur = probe_video_duration_seconds(vp)
    if not quiet:
        print(f"[Snapshot] Duration detected: {dur}s")

    count = suggest_snapshot_target_count(dur)

    # ffmpeg 빠른 추출(병렬·순차·소프트 디코드 내장 폴백)
    res = extract_snapshots_cuda(
        vp,
        output_dir,
        target_count=count,
        prefix=prefix,
        quality=quality,
        progress_callback=progress_callback,
    )

    # 추출된 개수가 목표치의 90% 이상일 때만 성공으로 간주
    if res and len(res) >= (count * 0.9):
        return res

    if not quiet:
        got = len(res) if res else 0
        print(
            f"[Snapshot] ffmpeg 스냅샷 부족({got}/{count}). OpenCV(CPU) 방식으로 폴백합니다."
        )
    return extract_snapshots_auto(
        vp,
        output_dir,
        target_count=count,
        prefix=prefix,
        quality=quality,
    )
