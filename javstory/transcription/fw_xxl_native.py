"""Pure faster-whisper (CTranslate2) native pipeline — no stable-ts wrapper.

Matches the reference "Faster-Whisper-XXL via PotPlayer" tool's actual shape:

    video → ffmpeg 16kHz mono WAV → WhisperModel.transcribe() → SRT

stable-ts's own VAD pass, word-timestamp DTW realignment, and
regroup/split/merge post-processing are intentionally NOT used here — the
reference tool doesn't have that layer either, and stable-ts's separate
Silero VAD (a different model/runtime than faster-whisper's own bundled
one) was the leading suspect for near-empty transcripts on some content.

Runs entirely synchronously on the caller's thread (no manual
producer-thread/queue/heartbeat) so cleanup (``del model`` /
``torch.cuda.empty_cache()``) always happens after decoding is fully done,
never racing a still-active decode thread.
"""
from __future__ import annotations

import gc
import os
from pathlib import Path
from typing import Any, Callable, Optional

import ffmpeg
import torch

from javstory.transcription.stt_config import (
    faster_whisper_model_from_env,
    fw_xxl_options_from_env,
)
from javstory.transcription.stt_types import (
    STTCancelled,
    STTProgressEvent,
    SimpleSegment,
    safe_console_print,
)
from javstory.transcription.win_cuda_dlls import add_windows_cuda_dll_paths
from javstory.utils.ffmpeg_path import bootstrap_path_env, get_ffmpeg

OptionalLogger = Optional[Callable[[str], None]]
ProgressCallback = Optional[Callable[[STTProgressEvent], None]]
CancelCheck = Optional[Callable[[], bool]]

add_windows_cuda_dll_paths()
bootstrap_path_env()


def _default_download_root() -> Path:
    la = os.environ.get("LOCALAPPDATA")
    if la:
        return Path(la) / "JAVSTORY" / "whisper_models"
    return Path.home() / "AppData" / "Local" / "JAVSTORY" / "whisper_models"


def _extract_audio_16k_mono(video_path: str, wav_path: Path, *, logger: OptionalLogger = None) -> None:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    if logger:
        logger(f"오디오 추출(16kHz mono PCM): {Path(video_path).name}")
    (
        ffmpeg.input(video_path)
        .output(str(wav_path), ac=1, ar=16000, acodec="pcm_s16le")
        .run(cmd=get_ffmpeg(), overwrite_output=True, quiet=True)
    )


def _fmt_ts(sec: float) -> str:
    if sec < 0:
        sec = 0.0
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    whole = int(s)
    ms = int(round((s - whole) * 1000))
    if ms >= 1000:
        whole += 1
        ms = 0
    return f"{h:02d}:{m:02d}:{whole:02d},{ms:03d}"


def write_srt(segments: list[SimpleSegment], path: Path) -> None:
    lines: list[str] = []
    n = 0
    for seg in segments:
        text = (seg.text or "").strip()
        if not text:
            continue
        n += 1
        lines.append(str(n))
        lines.append(f"{_fmt_ts(float(seg.start))} --> {_fmt_ts(float(seg.end))}")
        lines.append(text)
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _build_temperature(fw: dict[str, Any]) -> float | list[float]:
    t0 = float(fw["temperature"])
    t_inc = float(fw["temperature_increment_on_fallback"])
    if t_inc <= 0:
        return t0
    temps: list[float] = []
    t = t0
    while t <= 1.0 + 1e-6:
        temps.append(round(t, 2))
        t += t_inc
    return temps


def run_fw_native(
    *,
    video_path: str,
    work_dir: Path,
    logger: OptionalLogger = None,
    progress: ProgressCallback = None,
    should_cancel: CancelCheck = None,
) -> tuple[Path, list[SimpleSegment]]:
    """Run pure faster-whisper XXL-parity STT. Returns (srt_path, segments)."""
    from faster_whisper import WhisperModel

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    wav_path = work_dir / "fw_native_16k_mono.wav"
    interim_srt = work_dir / "fw_native_out.ja.srt"

    def emit(stage: str, pct: int, msg: str) -> None:
        if progress:
            progress(STTProgressEvent(stage, pct, msg))
        if logger:
            logger(f"[P:{pct}] {msg}")
        safe_console_print(f"[STT:{stage}:{pct}] {msg}")

    def check_cancel() -> None:
        if should_cancel and should_cancel():
            raise STTCancelled()

    emit("extract", 8, "오디오 추출 중...")
    check_cancel()
    _extract_audio_16k_mono(video_path, wav_path, logger=logger)

    download_root = os.environ.get("JAVSTORY_WHISPER_DOWNLOAD_ROOT")
    droot = Path(download_root).expanduser() if download_root else _default_download_root()
    droot.mkdir(parents=True, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    fw = fw_xxl_options_from_env()
    model_name = faster_whisper_model_from_env()
    compute = str(fw.get("compute_type") or "float16")
    if device == "cpu" and compute in ("float16", "int8_float16"):
        compute = "int8"

    emit(
        "init",
        12,
        f"STT 엔진: Faster-Whisper native XXL ({device}, {compute}, model={model_name})",
    )
    check_cancel()
    if logger:
        logger(f"faster-whisper 모델 로드: {model_name} ({device}, {compute})")

    model = WhisperModel(model_name, device=device, compute_type=compute, download_root=str(droot))

    vad_parameters = {
        "threshold": float(fw["vad_threshold"]),
        "min_speech_duration_ms": int(fw["vad_min_speech_duration_ms"]),
        "max_speech_duration_s": float(fw["vad_max_speech_duration_s"]),
    }
    hall = float(fw["hallucination_silence_threshold"])

    common_kw: dict[str, Any] = {
        "language": str(fw["language"] or "ja"),
        "task": "transcribe",
        "beam_size": int(fw["beam_size"]),
        "best_of": int(fw["best_of"]),
        "temperature": _build_temperature(fw),
        "repetition_penalty": float(fw["repetition_penalty"]),
        "condition_on_previous_text": bool(fw["condition_on_previous_text"]),
        "no_speech_threshold": float(fw["no_speech_threshold"]),
        "word_timestamps": bool(fw["word_timestamps"]),
        "vad_filter": bool(fw["vad_filter"]),
        "vad_parameters": vad_parameters,
    }
    if hall > 0:
        common_kw["hallucination_silence_threshold"] = hall

    emit(
        "whisper",
        14,
        f"전사 시작 (VAD={vad_parameters['threshold']:.2f}, language={common_kw['language']}, "
        f"beam={common_kw['beam_size']}, vad_filter={common_kw['vad_filter']})",
    )
    check_cancel()

    # 순차 처리(batch_size 미지정) — BatchedInferencePipeline은
    # no_speech_threshold/condition_on_previous_text/hallucination_silence_threshold를
    # 문서상 "Unused Arguments"로 조용히 무시함. 참조 XXL 툴도 실측상 순차 처리.
    #
    # 참고: 이 파일 안에서 model.transcribe()를 두 번(예: VAD 켜서 실패 시 꺼서
    # 재시도) 연속 호출하는 자동 폴백을 시도했으나, 모델을 완전히 새로 로드해도
    # 두 번째 패스 막바지에 트레이스백 없는 네이티브 크래시가 재현되어 되돌림
    # (원인 미파악). 단일 패스(현재 구조)는 안정적으로 검증됨 — 다시 시도할 때는
    # 프로세스를 완전히 분리(subprocess)하는 방향을 우선 고려할 것.
    segments_out: list[SimpleSegment] = []
    duration = 1.0
    try:
        seg_iter, info = model.transcribe(str(wav_path), **common_kw)
        duration = float(getattr(info, "duration", 0.0) or 0.0) or 1.0

        last_pct = 14
        for seg in seg_iter:
            check_cancel()
            text = (getattr(seg, "text", None) or "").strip()
            if text:
                segments_out.append(
                    SimpleSegment(
                        float(seg.start),
                        float(seg.end),
                        text,
                        avg_logprob=float(getattr(seg, "avg_logprob", 0.0) or 0.0),
                        no_speech_prob=float(getattr(seg, "no_speech_prob", 0.0) or 0.0),
                        compression_ratio=float(getattr(seg, "compression_ratio", 0.0) or 0.0),
                    )
                )
            frac = min(1.0, float(seg.end) / duration)
            pct = int(14 + frac * 76)
            if pct >= last_pct + 1 or len(segments_out) % 10 == 0:
                last_pct = max(last_pct, pct)
                emit(
                    "whisper",
                    last_pct,
                    f"전사 {seg.end:.1f}s / {duration:.1f}s ({len(segments_out)} cues)",
                )
    finally:
        del model
        gc.collect()
        if torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass

    check_cancel()
    emit("write", 95, f"SRT 저장: {interim_srt.name} ({len(segments_out)} cues)")
    write_srt(segments_out, interim_srt)
    if logger:
        logger(
            f"[STT] native FW-XXL 완료: cues={len(segments_out)} "
            f"duration≈{duration:.1f}s"
        )
    emit("done", 100, f"전사 완료 — {len(segments_out)} cues")
    return interim_srt, segments_out
