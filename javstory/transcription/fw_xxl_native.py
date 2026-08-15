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
import logging
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


class _FallbackRetryCounter(logging.Handler):
    """faster-whisper의 temperature-fallback 재시도 발생 횟수를 센다.

    generate_with_fallback()이 compression_ratio_threshold/log_prob_threshold를
    통과 못 해 다음 temperature로 재시도할 때마다 DEBUG 로그를 남기는데(faster_whisper
    자체 소스, 옵션으로 끌 수 없음), 그 로그만 골라 세서 실제 재시도 빈도를 측정한다.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.count = 0

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if "threshold is not met" in msg:
            self.count += 1


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
        "log_prob_threshold": float(fw["log_prob_threshold"]),
        "compression_ratio_threshold": float(fw["compression_ratio_threshold"]),
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
    # (원인 미파악). 단일 패스(현재 구조)는 안정적으로 검증됨.
    #
    # 이후(2026-08-05) 단일 패스에서도 정리 단계(del model 직후)에서 같은 종류의
    # 크래시(WER: 0xe06d7363/0xc0000409)가 100% 재현되는 게 확인됨 — torch.cuda.
    # empty_cache() 제거로도 안 고쳐졌고 ctranslate2 자체 소멸자가 유력한 원인.
    # 그래서 위 메모대로 프로세스 분리를 실제로 적용함: 이 함수 자체는 그대로 두고,
    # webapi에서는 run_fw_native_subprocess()(파일 하단)를 통해 별도 프로세스에서
    # 돌린다 — 여기서 크래시가 나도 SRT는 정리 전에 이미 저장돼 있어 부모 프로세스가
    # 파일 존재로 성공 판정할 수 있고, 부모(webapi) 자체는 죽지 않는다.
    fw_logger = logging.getLogger("faster_whisper")
    prev_logger_level = fw_logger.level
    prev_propagate = fw_logger.propagate
    retry_counter = _FallbackRetryCounter()
    fw_logger.addHandler(retry_counter)
    fw_logger.setLevel(logging.DEBUG)
    fw_logger.propagate = False

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
                    f"전사 {seg.end:.1f}s / {duration:.1f}s ({len(segments_out)} cues, "
                    f"fallback 재시도 {retry_counter.count}회)",
                )

        # 정리(del model/empty_cache)보다 먼저 저장 — CUDA 정리 단계에서 네이티브
        # 크래시(트레이스백 없이 프로세스 통째로 죽음)가 관측된 적이 있어서,
        # 그 경우에도 20분 넘게 걸린 전사 결과가 통째로 날아가지 않게 함.
        check_cancel()
        emit("write", 95, f"SRT 저장: {interim_srt.name} ({len(segments_out)} cues)")
        write_srt(segments_out, interim_srt)
    finally:
        fw_logger.removeHandler(retry_counter)
        fw_logger.setLevel(prev_logger_level)
        fw_logger.propagate = prev_propagate
        del model
        gc.collect()
        # torch.cuda.empty_cache() 의도적으로 생략: ctranslate2의 cuda_malloc_async
        # 할당자와 PyTorch 캐싱 할당자가 같은 프로세스에서 뒤섞여 정리되면서
        # 트레이스백 없는 네이티브 크래시(0xe06d7363 / 0xc0000409, WER로 재현 확인)를
        # 100% 재현시켰음 — 재부팅해도 동일 crash bucket으로 재현됐으므로 드라이버
        # 오염이 아니라 이 두 줄의 상호작용이 근본 원인. empty_cache()는 GPU 메모리를
        # OS로 못 돌려주는 게 아니라 PyTorch 캐시를 비우는 것뿐이라 생략해도 다음
        # 작업이 실패하지 않음 — 프로세스 종료 시 어차피 드라이버가 회수함.

    if logger:
        logger(
            f"[STT] native FW-XXL 완료: cues={len(segments_out)} "
            f"duration≈{duration:.1f}s, fallback 재시도 총 {retry_counter.count}회"
        )
    emit("done", 100, f"전사 완료 — {len(segments_out)} cues, fallback 재시도 {retry_counter.count}회")
    return interim_srt, segments_out


def run_fw_native_subprocess(
    *,
    video_path: str,
    work_dir: Path,
    logger: OptionalLogger = None,
    progress: ProgressCallback = None,
    should_cancel: CancelCheck = None,
) -> tuple[Path, list[SimpleSegment]]:
    """``run_fw_native()``를 별도 프로세스에서 실행 — ctranslate2/CUDA 정리 단계의
    네이티브 크래시(트레이스백 없이 프로세스 종료, WER로 확인된 fault bucket
    0xe06d7363/0xc0000409)가 webapi 서버 자체를 죽이지 않도록 격리한다.

    하위 프로세스가 크래시하더라도 SRT는 정리 단계보다 먼저 디스크에 쓰이므로
    (``run_fw_native`` 참고), 종료 코드와 무관하게 interim SRT 파일이 존재하면
    성공으로 취급한다.
    """
    import json
    import subprocess
    import sys

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    interim_srt = work_dir / "fw_native_out.ja.srt"
    project_root = Path(__file__).resolve().parents[2]

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"

    cmd = [
        sys.executable,
        "-u",
        "-m",
        "javstory.transcription.fw_xxl_worker",
        str(video_path),
        str(work_dir),
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(project_root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    cancelled = False
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if should_cancel and should_cancel():
                cancelled = True
                break
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                # ctranslate2 등 하위 프로세스의 원시 로그 출력 — 그대로 통과
                if logger:
                    logger(line)
                continue
            t = obj.get("type")
            if t == "log" and logger:
                logger(str(obj.get("msg", "")))
            elif t == "progress" and progress:
                progress(
                    STTProgressEvent(
                        str(obj.get("stage", "")),
                        int(obj.get("percent", 0)),
                        str(obj.get("message", "")),
                    )
                )
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=15)
        else:
            proc.wait(timeout=15)

    if cancelled:
        raise STTCancelled()

    if interim_srt.is_file():
        if logger and proc.returncode != 0:
            logger(
                f"[STT] 하위 프로세스가 비정상 종료(code={proc.returncode})했지만 "
                f"SRT는 이미 저장되어 있어 결과를 사용합니다: {interim_srt.name}"
            )
        return interim_srt, []

    raise RuntimeError(
        f"FW-XXL 하위 프로세스가 실패했습니다 (exit={proc.returncode}), SRT가 생성되지 않았습니다."
    )
