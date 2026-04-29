"""
stable-ts 단일 STT 진입점. GUI `stt_worker` 계약 유지. Obsolete·레거시 Whisper 미사용.
"""
from __future__ import annotations

import gc
import os
import shutil
import tempfile
from pathlib import Path
from typing import Callable, List, Optional

from javstory.transcription.win_cuda_dlls import add_windows_cuda_dll_paths

add_windows_cuda_dll_paths()

import pysrt
import torch

from javstory.transcription.stt_types import (
    STTCancelled,
    STTProgressEvent,
    SimpleSegment,
    STT_PRESET_DEFAULT,
)
from javstory.transcription.stable_ts_pipeline import run_stable_ts

# stt_worker 호환 re-export
__all__ = [
    "STTCancelled",
    "STTProgressEvent",
    "SimpleSegment",
    "STT_PRESET_DEFAULT",
    "clear_vram",
    "process_video_to_segments",
]

ProgressCallback = Optional[Callable[[STTProgressEvent], None]]
OptionalLogger = Optional[Callable[[str], None]]
CancelCheck = Optional[Callable[[], bool]]


def clear_vram() -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    print("[VRAM] gc.collect + CUDA 캐시 비우기 완료")


def _load_existing_srt(srt_path: str) -> List[SimpleSegment]:
    subs = pysrt.open(srt_path, encoding="utf-8")
    out: List[SimpleSegment] = []
    for s in subs:
        out.append(
            SimpleSegment(s.start.ordinal / 1000.0, s.end.ordinal / 1000.0, s.text)
        )
    return out


def process_video_to_segments(
    video_path: str,
    output_dir: str,
    skip_vocal_sep: bool = False,
    with_llm: bool = False,
    logger_func: OptionalLogger = None,
    progress_callback: ProgressCallback = None,
    stt_preset: Optional[str] = None,
    should_cancel: CancelCheck = None,
) -> List[SimpleSegment]:
    """
    비디오 옆 `{stem}.ja.srt` 및 작업 폴더에 임시 WAV 등을 둔다.
    `stt_preset`은 하위 호환용으로만 받고 무시한다.
    """
    video_path = str(Path(video_path).resolve())
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        if logger_func:
            logger_func(msg)

    def prog(ev: STTProgressEvent) -> None:
        if progress_callback:
            progress_callback(ev)

    base = os.path.splitext(video_path)[0]
    ja_srt_final = base + ".ja.srt"
    plain_srt_final = base + ".srt"
    ko_srt_final = base + ".ko.srt"

    if os.path.isfile(ja_srt_final):
        log(f"기존 자막 사용: {os.path.basename(ja_srt_final)}")
        prog(STTProgressEvent("done", 100, "기존 .ja.srt 로드"))
        return _load_existing_srt(ja_srt_final)

    if os.path.isfile(ko_srt_final):
        log(f"기존 자막 사용: {os.path.basename(ko_srt_final)}")
        prog(STTProgressEvent("done", 100, "기존 .ko.srt 로드 (STT 스킵)"))
        return _load_existing_srt(ko_srt_final)

    # 일반 .srt(대개 다운로드본 KO 자막 등)가 있으면 STT를 스킵하고 그대로 사용
    if os.path.isfile(plain_srt_final):
        log(f"기존 자막 사용: {os.path.basename(plain_srt_final)}")
        prog(STTProgressEvent("done", 100, "기존 .srt 로드 (STT 스킵)"))
        return _load_existing_srt(plain_srt_final)

    if skip_vocal_sep:
        log("[안내] stable-ts 단일 경로에서는 보컬 분리(UVR)를 사용하지 않습니다. skip_vocal_sep 무시.")
    if with_llm:
        log("[안내] STT 엔진에서 LLM 교정은 수행하지 않습니다. 별도 correction 파이프라인을 사용하세요.")
    if stt_preset and stt_preset != STT_PRESET_DEFAULT:
        log(f"[안내] stt_preset={stt_preset!r} 는 무시됩니다. (고정: stable-ts)")

    prog(STTProgressEvent("init", 5, "stable-ts 파이프라인 시작"))
    interim_srt, _ = run_stable_ts(
        video_path=video_path,
        work_dir=out_dir,
        logger=log,
        progress=prog,
        should_cancel=should_cancel,
    )

    # 부분 쓰기 방지: 동일 디렉터리에 임시 파일로 쓴 뒤 원자적 교체
    tmp_dir = os.path.dirname(ja_srt_final) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".ja_srt_tmp_", suffix=".srt", dir=tmp_dir)
    try:
        os.close(fd)
        shutil.copy2(str(interim_srt), tmp_path)
        os.replace(tmp_path, ja_srt_final)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
    log(f"저장: {os.path.basename(ja_srt_final)}")

    segments = _load_existing_srt(ja_srt_final)
    prog(STTProgressEvent("done", 100, f"완료 - 세그먼트 {len(segments)}개"))
    return segments
