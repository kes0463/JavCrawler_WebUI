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

from javstory.transcription.stt_types import (
    STTCancelled,
    STTProgressEvent,
    SimpleSegment,
    STT_PRESET_DEFAULT,
)
from javstory.transcription.stt_config import (
    stt_engine_from_env,
    STT_ENGINE_LABELS,
    STT_ENGINE_STABLE_TS_FW,
)
from javstory.transcription.stable_ts_pipeline import run_stt
from javstory.transcription.fw_xxl_native import run_fw_native_subprocess

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
ContentLineCallback = Optional[Callable[[dict[str, object]], None]]


def _emit_stt_segments(
    segments: List[SimpleSegment],
    on_content_line: ContentLineCallback,
) -> None:
    if not on_content_line:
        return
    for i, seg in enumerate(segments):
        text = (seg.text or "").strip()
        if not text:
            continue
        on_content_line(
            {
                "lang": "ja",
                "text": text,
                "start": float(seg.start),
                "end": float(seg.end),
                "index": i,
            }
        )


def clear_vram() -> None:
    gc.collect()
    # torch.cuda.empty_cache() 의도적으로 생략: STT 작업 직후(ctranslate2 모델 정리와
    # 가까운 시점) 호출 시 트레이스백 없는 네이티브 크래시(0xe06d7363/0xc0000409)가
    # 재현됨 — javstory/transcription/fw_xxl_native.py의 동일 수정 참고.
    print("[VRAM] gc.collect 완료 (CUDA 캐시 비우기는 크래시 방지를 위해 생략)")


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
    on_content_line: ContentLineCallback = None,
    stt_preset: Optional[str] = None,
    should_cancel: CancelCheck = None,
) -> List[SimpleSegment]:
    """
    비디오 옆 `{stem}.ja.srt` 및 작업 폴더에 임시 WAV 등을 둔다.
    `stt_preset`이 있으면 JAVSTORY_STT_ENGINE 대신 사용(하위 호환).
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
        segments = _load_existing_srt(ja_srt_final)
        _emit_stt_segments(segments, on_content_line)
        return segments

    if os.path.isfile(ko_srt_final):
        log(f"기존 자막 사용: {os.path.basename(ko_srt_final)}")
        prog(STTProgressEvent("done", 100, "기존 .ko.srt 로드 (STT 스킵)"))
        segments = _load_existing_srt(ko_srt_final)
        _emit_stt_segments(segments, on_content_line)
        return segments

    # 일반 .srt(대개 다운로드본 KO 자막 등)가 있으면 STT를 스킵하고 그대로 사용
    if os.path.isfile(plain_srt_final):
        log(f"기존 자막 사용: {os.path.basename(plain_srt_final)}")
        prog(STTProgressEvent("done", 100, "기존 .srt 로드 (STT 스킵)"))
        segments = _load_existing_srt(plain_srt_final)
        _emit_stt_segments(segments, on_content_line)
        return segments

    if skip_vocal_sep:
        log("[안내] stable-ts 단일 경로에서는 보컬 분리(UVR)를 사용하지 않습니다. skip_vocal_sep 무시.")
    if with_llm:
        log("[안내] STT 엔진에서 LLM 교정은 수행하지 않습니다. 별도 correction 파이프라인을 사용하세요.")

    engine = stt_engine_from_env()
    if stt_preset:
        from javstory.transcription.stt_config import normalize_stt_engine

        engine = normalize_stt_engine(stt_preset)
    label = STT_ENGINE_LABELS.get(engine, engine)
    prog(STTProgressEvent("init", 5, f"STT 파이프라인 시작 ({label})"))
    if engine == STT_ENGINE_STABLE_TS_FW:
        # 참조 Faster-Whisper-XXL 툴과 동일한 형태: ffmpeg 추출 → WhisperModel.transcribe()
        # 직접 호출 → SRT. stable-ts VAD/후처리를 안 거침(별도 Silero VAD·재분할이
        # 근접 무음 결과의 원인 후보였음). 별도 프로세스에서 실행 — ctranslate2/CUDA
        # 정리 단계 네이티브 크래시가 webapi 자체를 죽이지 않도록 격리(fw_xxl_native.py 참고).
        interim_srt, _ = run_fw_native_subprocess(
            video_path=video_path,
            work_dir=out_dir,
            logger=log,
            progress=prog,
            should_cancel=should_cancel,
        )
    else:
        interim_srt, _ = run_stt(
            video_path=video_path,
            work_dir=out_dir,
            logger=log,
            progress=prog,
            should_cancel=should_cancel,
            engine=engine,
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
    _emit_stt_segments(segments, on_content_line)
    prog(STTProgressEvent("done", 100, f"완료 - 세그먼트 {len(segments)}개"))
    return segments
