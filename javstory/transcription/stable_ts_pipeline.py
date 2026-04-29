"""
stable-ts 단일 전사 파이프라인: ffmpeg WAV → WhisperModel.transcribe(VAD) → 분할/병합 → SRT.
Obsolete·core/Whisper 미사용.
"""
from __future__ import annotations

import gc
import os
from pathlib import Path
from typing import Callable, Optional

import ffmpeg

from javstory.transcription.stt_types import STTCancelled, STTProgressEvent

OptionalLogger = Optional[Callable[[str], None]]
ProgressCallback = Optional[Callable[[STTProgressEvent], None]]
CancelCheck = Optional[Callable[[], bool]]

from javstory.transcription.win_cuda_dlls import add_windows_cuda_dll_paths  # noqa: E402

add_windows_cuda_dll_paths()

import torch  # noqa: E402
import stable_whisper  # noqa: E402


def _default_download_root() -> Path:
    la = os.environ.get("LOCALAPPDATA")
    if la:
        return Path(la) / "JAVSTORY" / "whisper_models"
    return Path.home() / "AppData" / "Local" / "JAVSTORY" / "whisper_models"


def _default_model_name() -> str:
    return os.environ.get("JAVSTORY_WHISPER_MODEL", "large-v2").strip() or "large-v2"


def extract_audio_16k_mono(
    video_path: str,
    wav_path: Path,
    *,
    logger: OptionalLogger = None,
) -> None:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    if logger:
        logger(f"오디오 추출(16kHz mono PCM): {Path(video_path).name}")
    (
        ffmpeg.input(video_path)
        .output(str(wav_path), ac=1, ar=16000, acodec="pcm_s16le")
        .run(overwrite_output=True, quiet=True)
    )


def run_stable_ts(
    *,
    video_path: str,
    work_dir: Path,
    logger: OptionalLogger = None,
    progress: ProgressCallback = None,
    should_cancel: CancelCheck = None,
    model_name: Optional[str] = None,
) -> tuple[Path, "stable_whisper.result.WhisperResult"]:
    """
    Returns (path to written .ja.srt whisper-side candidate — caller may move),
            WhisperResult after postprocess (for debugging).
    실제 .ja.srt 최종 경로는 engine에서 비디오 옆으로 정한다.
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    wav_path = work_dir / "stable_ts_16k_mono.wav"
    interim_srt = work_dir / "stable_ts_out.ja.srt"

    def emit(stage: str, pct: int, msg: str) -> None:
        if progress:
            progress(STTProgressEvent(stage, pct, msg))
        if logger:
            logger(f"[P:{pct}] {msg}")

    def check_cancel() -> None:
        if should_cancel and should_cancel():
            raise STTCancelled()

    emit("extract", 8, "오디오 추출 중...")
    check_cancel()
    extract_audio_16k_mono(video_path, wav_path, logger=logger)

    name = model_name or _default_model_name()
    download_root = os.environ.get("JAVSTORY_WHISPER_DOWNLOAD_ROOT")
    droot = Path(download_root).expanduser() if download_root else _default_download_root()
    droot.mkdir(parents=True, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    emit("init", 12, f"Whisper 모델 로드: {name} ({device})")
    check_cancel()

    model = stable_whisper.load_model(name, device=device, download_root=str(droot))

    last_seek = [0.0]
    last_total = [1.0]

    def transcribe_progress(seek_dur: float, total_dur: float) -> None:
        last_seek[0] = float(seek_dur)
        last_total[0] = max(float(total_dur), 1.0)
        check_cancel()
        # 전사 구간 전체를 대략 12~85%로 매핑
        frac = min(1.0, last_seek[0] / last_total[0])
        pct = int(12 + frac * 73)
        emit("whisper", pct, f"전사(VAD on) {seek_dur:.1f}s / {total_dur:.1f}s")

    emit("whisper", 14, "전사 시작 (VAD=True, language=ja)")
    check_cancel()

    use_fp16 = device == "cuda"
    ignore_compat = os.environ.get("JAVSTORY_WHISPER_IGNORE_COMPAT", "").lower() in (
        "1",
        "true",
        "yes",
    )
    result = model.transcribe(
        str(wav_path),
        language="ja",
        word_timestamps=True,
        vad=True,
        vad_threshold=float(os.environ.get("JAVSTORY_VAD_THRESHOLD", "0.35")),
        verbose=False,
        regroup=True,
        fp16=use_fp16,
        beam_size=int(os.environ.get("JAVSTORY_WHISPER_BEAM_SIZE", "5")),
        progress_callback=transcribe_progress,
        ignore_compatibility=ignore_compat,
    )

    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        try:
            torch.cuda.ipc_collect()
        except Exception:
            pass

    emit("post", 88, "세그먼트 후처리: split_by_length(50) -> split_by_duration(10) -> merge_by_gap(0.1)")
    check_cancel()
    
    # [수정] 특정 조건(무음 등)에서 split_by_duration 등이 ValueError(argmin of empty)를 던질 수 있음.
    # 이 경우 후처리를 포기하고 원본 전사 결과(result)를 사용해 크래시를 방지함.
    try:
        processed = (
            result.split_by_length(50)
            .split_by_duration(10.0)
            .merge_by_gap(0.1)
        )
    except Exception as e:
        if logger:
            logger(f"[경고] 세그먼트 후처리(분할/병합) 중 에러 발생: {e}. 원본 결과를 사용합니다.")
        processed = result

    processed.to_srt_vtt(str(interim_srt), segment_level=True, word_level=False)
    emit("write", 95, f"SRT 저장(임시): {interim_srt.name}")
    return interim_srt, processed
