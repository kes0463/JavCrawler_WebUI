from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Callable, Optional

from javstory.utils.ffmpeg_path import get_ffmpeg, get_ffprobe

ProgressCb = Optional[Callable[[int], None]]

logger = logging.getLogger(__name__)


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
                str(path),
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


def create_golden_preview(
    *,
    product_code: str,
    video_path: str | Path,
    output_path: str | Path,
    progress_callback: ProgressCb = None,
    duration_sec: float = 8.0,
    seed: int = 0,
) -> Path | None:
    """
    Golden Preview: 5~10초 애니메이션 WebP 생성.

    - 우선순위: {E_MEDIA_ROOT}/{pc}/Highlight/highlight.mp4 존재 시 그 파일 앞부분 사용
    - 없으면 원본 영상의 중간 구간을 사용
    - seed: 재생성 시 다른 구간을 선택하기 위한 값 (0=기본)
    """
    pc = (product_code or "").strip().upper()
    src = Path(video_path)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        progress_callback(_clamp(5))

    # highlight 산출물이 있으면 그걸 우선 사용 (이미 "골든 타임"에 가까운 요약물)
    try:
        from javstory.config.app_config import DATA_ROOT, E_DATA_ROOT, E_MEDIA_ROOT

        cand = [
            Path(E_MEDIA_ROOT) / pc / "Highlight" / "highlight.mp4",
            Path(E_DATA_ROOT) / pc / "Highlight" / "highlight.mp4",
            Path(E_DATA_ROOT) / "media" / pc / "Highlight" / "highlight.mp4",
            Path(DATA_ROOT) / "media" / pc / "Highlight" / "highlight.mp4",
        ]
        for p in cand:
            if p.is_file():
                src = p
                break
    except Exception:
        pass

    if not src.is_file():
        return None

    dur = _ffprobe_duration_sec(src)
    clip_len = float(max(5.0, min(10.0, duration_sec)))
    
    # 재생성 시 다른 구간을 선택하기 위한 오프셋 비율 목록
    # 0.5(중간)를 기본으로 하고, 이후에는 골고루 분산
    if src.name.lower() == "highlight.mp4":
        # 하이라이트 영상인 경우 앞부분이 중요하므로 0부터 시작
        ratios = [0.0, 0.4, 0.7, 0.2, 0.5, 0.8]
    else:
        # 일반 영상인 경우 중간부터 시작
        ratios = [0.5, 0.25, 0.75, 0.1, 0.4, 0.6, 0.9, 0.3, 0.8]
    
    ratio = ratios[seed % len(ratios)]
    start = 0.0
    if dur and dur > clip_len:
        start = max(0.0, (dur * ratio) - (clip_len * 0.5))
        # 영상 끝을 넘지 않도록 조정
        if start + clip_len > dur:
            start = max(0.0, dur - clip_len)

    if progress_callback:
        progress_callback(_clamp(15))

    # WebP 생성
    cmd = [
        get_ffmpeg(),
        "-y",
        "-ss",
        f"{start:.2f}",
        "-t",
        f"{clip_len:.2f}",
        "-i",
        str(src),
        "-an",
        "-vf",
        "fps=20,scale=640:-2:flags=lanczos",
        "-loop",
        "0",
        "-preset",
        "picture",
        "-quality",
        "90",
        "-compression_level",
        "6",
        str(out),
    ]
    if progress_callback:
        progress_callback(_clamp(40))

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
        stderr_text = (cp.stderr or b"").decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired as e_to:
        rc = -999
        stderr_text = f"TimeoutExpired: {e_to}"
    except Exception as e_run:
        rc = -1
        stderr_text = f"subprocess exception: {e_run!r}"

    if rc != 0 or not out.is_file() or out.stat().st_size <= 0:
        # ffmpeg 실패 시 stderr에서 의미 있는 진단 메시지를 추출해 호출자에게 전달.
        # PreviewWorker 등이 이 RuntimeError 메시지를 그대로 사용자에게 노출한다.
        reason = _extract_ffmpeg_failure_reason(stderr_text)
        logger.warning(
            "create_golden_preview failed: pc=%s rc=%s reason=%s src=%s",
            pc, rc, reason, src,
        )
        raise RuntimeError(f"ffmpeg 실패(rc={rc}): {reason} | 입력: {src.name}")

    if progress_callback:
        progress_callback(_clamp(100))
    return out


def _extract_ffmpeg_failure_reason(stderr_text: str) -> str:
    """ffmpeg stderr에서 사용자에게 보여줄 핵심 한 줄을 추출한다."""
    if not stderr_text:
        return "출력 없음"
    txt = stderr_text.strip()
    # 잘 알려진 손상 시그니처를 우선 매칭
    signatures = [
        ("moov atom not found", "손상된 MP4(컨테이너 헤더 누락: moov atom not found)"),
        ("Invalid data found when processing input", "손상되었거나 미완성 영상 파일(Invalid data)"),
        ("No such file or directory", "원본 영상 파일을 열 수 없음"),
        ("Permission denied", "원본 영상 파일 접근 권한 없음"),
        ("Operation not permitted", "원본 영상 파일 접근 거부"),
        ("Protocol not found", "지원하지 않는 입력 경로/프로토콜"),
        ("Cannot allocate memory", "메모리 부족"),
        ("low score", "컨테이너 형식 식별 실패(파일 손상 의심)"),
    ]
    for needle, label in signatures:
        if needle.lower() in txt.lower():
            return label
    # 시그니처에 매칭되지 않으면 마지막으로 의미 있는 "Error" 라인을 찾는다
    for line in reversed(txt.splitlines()):
        s = line.strip()
        if s.lower().startswith("error") and len(s) < 240:
            return s
    return txt.splitlines()[-1].strip()[:200] if txt.splitlines() else "원인 불명"

