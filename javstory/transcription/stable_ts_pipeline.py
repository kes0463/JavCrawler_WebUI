"""
stable-ts STT pipeline: ffmpeg WAV → model transcribe (VAD) → split/merge → SRT.

Engines (JAVSTORY_STT_ENGINE):
  stable_ts       — PyTorch stable_whisper.load_model
  stable_ts_fw    — stable_whisper.load_faster_whisper (CTranslate2)
  anime_whisper   — stable_whisper.load_hf_whisper (litagin/anime-whisper)
  whisperx        — not implemented
"""
from __future__ import annotations

import gc
import os
from pathlib import Path
from typing import Callable, Optional

import ffmpeg

from javstory.transcription.dialogue_filter import filter_whisper_result, fix_sticky_hallucination_segments
from javstory.transcription.stt_config import (
    STT_ENGINE_ANIME_WHISPER,
    STT_ENGINE_STABLE_TS,
    STT_ENGINE_STABLE_TS_FW,
    STT_ENGINE_WHISPERX,
    dialogue_only_from_env,
    faster_whisper_model_from_env,
    hf_whisper_model_from_env,
    stt_engine_from_env,
    vad_threshold_from_env,
    whisper_model_from_env,
)
from javstory.transcription.stt_types import STTCancelled, STTProgressEvent
from javstory.utils.ffmpeg_path import bootstrap_path_env, get_ffmpeg

OptionalLogger = Optional[Callable[[str], None]]
ProgressCallback = Optional[Callable[[STTProgressEvent], None]]
CancelCheck = Optional[Callable[[], bool]]

from javstory.transcription.win_cuda_dlls import add_windows_cuda_dll_paths  # noqa: E402

add_windows_cuda_dll_paths()
bootstrap_path_env()

import torch  # noqa: E402
import stable_whisper  # noqa: E402


def _default_download_root() -> Path:
    la = os.environ.get("LOCALAPPDATA")
    if la:
        return Path(la) / "JAVSTORY" / "whisper_models"
    return Path.home() / "AppData" / "Local" / "JAVSTORY" / "whisper_models"


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
        .run(cmd=get_ffmpeg(), overwrite_output=True, quiet=True)
    )


def _load_model_for_engine(
    engine: str,
    *,
    device: str,
    download_root: Path,
    logger: OptionalLogger = None,
):
    if engine == STT_ENGINE_WHISPERX:
        raise NotImplementedError(
            "WhisperX 엔진은 아직 지원되지 않습니다. 설정에서 Stable TS 또는 Anime-Whisper를 선택하세요."
        )
    if engine == STT_ENGINE_STABLE_TS_FW:
        fw_name = faster_whisper_model_from_env()
        if logger:
            logger(f"faster-whisper 모델 로드: {fw_name} ({device})")
        return stable_whisper.load_faster_whisper(
            fw_name,
            device=device,
            download_root=str(download_root),
        )
    if engine == STT_ENGINE_ANIME_WHISPER:
        hf_id = hf_whisper_model_from_env()
        if logger:
            logger(f"HF Whisper 모델 로드: {hf_id} ({device})")
        return stable_whisper.load_hf_whisper(hf_id, device=device)
    name = whisper_model_from_env()
    if logger:
        logger(f"Whisper 모델 로드: {name} ({device})")
    return stable_whisper.load_model(name, device=device, download_root=str(download_root))


def _engine_label(engine: str) -> str:
    from javstory.transcription.stt_config import STT_ENGINE_LABELS

    return STT_ENGINE_LABELS.get(engine, engine)


def _postprocess_result(result, *, logger: OptionalLogger = None):
    try:
        processed = (
            result.split_by_length(50)
            .split_by_duration(6.0)
            .merge_by_gap(0.1)
        )
    except Exception as e:
        if logger:
            logger(f"[경고] 세그먼트 후처리(분할/병합) 중 에러: {e}. 원본 결과를 사용합니다.")
        processed = result
    processed = fix_sticky_hallucination_segments(processed, logger=logger)
    if dialogue_only_from_env():
        before = len(getattr(processed, "segments", []) or [])
        filter_whisper_result(processed)
        after = len(getattr(processed, "segments", []) or [])
        if logger and before != after:
            logger(f"[대사 필터] {before - after}개 비대사 세그먼트 제거 ({before} → {after})")
    return processed


def run_stt(
    *,
    video_path: str,
    work_dir: Path,
    logger: OptionalLogger = None,
    progress: ProgressCallback = None,
    should_cancel: CancelCheck = None,
    engine: str | None = None,
    model_name: str | None = None,
) -> tuple[Path, "stable_whisper.result.WhisperResult"]:
    """
    Engine-aware STT. Returns (interim .ja.srt path, WhisperResult).
    `model_name` overrides JAVSTORY_WHISPER_MODEL for stable_ts engine only (legacy).
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    wav_path = work_dir / "stable_ts_16k_mono.wav"
    interim_srt = work_dir / "stable_ts_out.ja.srt"

    eng = engine or stt_engine_from_env()
    if model_name:
        os.environ["JAVSTORY_WHISPER_MODEL"] = model_name

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

    download_root = os.environ.get("JAVSTORY_WHISPER_DOWNLOAD_ROOT")
    droot = Path(download_root).expanduser() if download_root else _default_download_root()
    droot.mkdir(parents=True, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    emit("init", 12, f"STT 엔진: {_engine_label(eng)} ({device})")
    check_cancel()

    model = _load_model_for_engine(eng, device=device, download_root=droot, logger=logger)

    last_seek = [0.0]
    last_total = [1.0]

    def transcribe_progress(seek_dur: float, total_dur: float) -> None:
        last_seek[0] = float(seek_dur)
        last_total[0] = max(float(total_dur), 1.0)
        check_cancel()
        frac = min(1.0, last_seek[0] / last_total[0])
        pct = int(12 + frac * 73)
        emit("whisper", pct, f"전사(VAD on) {seek_dur:.1f}s / {total_dur:.1f}s")

    vad = vad_threshold_from_env()
    emit("whisper", 14, f"전사 시작 (VAD={vad:.2f}, language=ja)")
    check_cancel()

    use_fp16 = device == "cuda"
    ignore_compat = os.environ.get("JAVSTORY_WHISPER_IGNORE_COMPAT", "").lower() in (
        "1",
        "true",
        "yes",
    )
    transcribe_kw: dict = {
        "language": "ja",
        "word_timestamps": True,
        "vad": True,
        "vad_threshold": vad,
        "verbose": False,
        "regroup": True,
        "progress_callback": transcribe_progress,
        "ignore_compatibility": ignore_compat,
    }
    if eng == STT_ENGINE_STABLE_TS:
        transcribe_kw["fp16"] = use_fp16
        transcribe_kw["beam_size"] = int(os.environ.get("JAVSTORY_WHISPER_BEAM_SIZE", "5"))

    try:
        transcribe_kw["suppress_silence"] = True
        result = model.transcribe(str(wav_path), **transcribe_kw)
    except TypeError:
        transcribe_kw.pop("suppress_silence", None)
        result = model.transcribe(str(wav_path), **transcribe_kw)

    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        try:
            torch.cuda.ipc_collect()
        except Exception:
            pass

    emit("post", 88, "세그먼트 후처리: split → merge → (대사 필터)")
    check_cancel()
    processed = _postprocess_result(result, logger=logger)

    processed.to_srt_vtt(str(interim_srt), segment_level=True, word_level=False)
    emit("write", 95, f"SRT 저장(임시): {interim_srt.name}")
    return interim_srt, processed


def run_stable_ts(
    *,
    video_path: str,
    work_dir: Path,
    logger: OptionalLogger = None,
    progress: ProgressCallback = None,
    should_cancel: CancelCheck = None,
    model_name: str | None = None,
) -> tuple[Path, "stable_whisper.result.WhisperResult"]:
    """Backward-compatible alias — respects JAVSTORY_STT_ENGINE."""
    return run_stt(
        video_path=video_path,
        work_dir=work_dir,
        logger=logger,
        progress=progress,
        should_cancel=should_cancel,
        model_name=model_name,
    )
