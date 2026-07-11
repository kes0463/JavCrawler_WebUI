"""STT / subtitle pipeline execution for WebAPI processing queue."""

from __future__ import annotations

import asyncio
import os
import re
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

ProgressFn = Callable[[str, int], None]
CancelFn = Callable[[], bool]
LogFn = Callable[[str, str], None]
ContentLineFn = Callable[[dict[str, object]], None]


@dataclass
class SttJobResult:
    ok: bool
    message: str
    srt_path: str = ""
    skipped: bool = False


@dataclass
class SubtitleJobResult:
    ok: bool
    message: str
    ko_srt_path: str = ""
    skipped: bool = False


def _has_builtin_subtitle_marker(video_path: Path) -> bool:
    return any("자체자막" in part for part in video_path.parts)


def _stt_skip_existing(base_name: str) -> SttJobResult | None:
    ko_srt = base_name + ".ko.srt"
    plain_srt = base_name + ".srt"
    if os.path.exists(ko_srt):
        return SttJobResult(True, "기존 .ko.srt 존재: STT 스킵", ko_srt, skipped=True)
    if os.path.exists(plain_srt):
        return SttJobResult(True, "기존 .srt 존재: STT 스킵", plain_srt, skipped=True)
    return None


def _subtitle_skip_existing(base_name: str) -> SubtitleJobResult | None:
    ko_srt = base_name + ".ko.srt"
    plain_srt = base_name + ".srt"
    if os.path.exists(ko_srt):
        return SubtitleJobResult(True, "기존 .ko.srt 존재: 번역 스킵", ko_srt, skipped=True)
    if os.path.exists(plain_srt):
        return SubtitleJobResult(True, "기존 .srt 존재: 번역 스킵", plain_srt, skipped=True)
    return None


def run_stt_job(
    video_path: str,
    *,
    on_progress: ProgressFn | None = None,
    on_log: LogFn | None = None,
    on_content_line: ContentLineFn | None = None,
    should_cancel: CancelFn | None = None,
) -> SttJobResult:
    from javstory.transcription.engine import (
        STT_PRESET_DEFAULT,
        clear_vram,
        process_video_to_segments,
    )
    from javstory.transcription.stt_types import STTCancelled

    path = Path(video_path).resolve()
    if not path.is_file():
        return SttJobResult(False, f"파일을 찾을 수 없습니다: {path}")

    base_name = str(path.with_suffix(""))

    if _has_builtin_subtitle_marker(path):
        for candidate in (base_name + ".ko.srt", base_name + ".ja.srt", base_name + ".srt"):
            if os.path.exists(candidate):
                on_progress and on_progress("[완료] 자체자막 표기 → STT 스킵", 100)
                return SttJobResult(True, "자체자막 표기: STT 스킵", candidate, skipped=True)
        on_progress and on_progress("[완료] 자체자막 표기 → STT 스킵", 100)
        return SttJobResult(True, "자체자막 표기: STT 스킵", skipped=True)

    skip = _stt_skip_existing(base_name)
    if skip:
        on_progress and on_progress(f"[완료] {skip.message}", 100)
        return skip

    output_dir = str(path.parent / "stt_work")
    last_percent = 0

    def log_bridge(msg: str) -> None:
        nonlocal last_percent
        try:
            m = re.search(r"\[P:(\d+)\]", msg)
            if m:
                p = int(m.group(1))
                last_percent = max(last_percent, max(0, min(100, p)))
                msg = re.sub(r"\[P:\d+\]\s*", "", msg)
        except Exception:
            pass
        if on_log:
            on_log("info", msg)
        if on_progress:
            on_progress(msg, last_percent)

    def progress_event_bridge(ev) -> None:
        nonlocal last_percent
        try:
            p = int(getattr(ev, "percent", last_percent))
        except Exception:
            p = last_percent
        p = max(0, min(100, p))
        last_percent = max(last_percent, p)
        stage = (getattr(ev, "stage", "") or "").strip()
        msg = getattr(ev, "message", "") or ""
        stage_label_map = {
            "init": "초기화",
            "extract": "오디오 추출",
            "uvr": "보컬 분리",
            "snr": "SNR",
            "preprocess": "전처리",
            "whisper": "전사(stable-ts)",
            "post": "후처리",
            "llm": "LLM 교정",
            "write": "저장",
            "done": "완료",
        }
        if stage:
            label = stage_label_map.get(stage, stage)
            msg = f"[{label}] {msg}" if msg else f"[{label}]"
        if on_progress:
            on_progress(msg or "처리 중...", last_percent)

    try:
        on_progress and on_progress("자막 생성 공정 시동 중...", 5)
        process_video_to_segments(
            video_path=str(path),
            output_dir=output_dir,
            skip_vocal_sep=False,
            with_llm=False,
            logger_func=log_bridge,
            progress_callback=progress_event_bridge,
            on_content_line=on_content_line,
            stt_preset=STT_PRESET_DEFAULT,
            should_cancel=should_cancel,
        )
        ja_srt = base_name + ".ja.srt"
        plain_srt = base_name + ".srt"
        if os.path.exists(ja_srt):
            on_progress and on_progress("자막 생성 완료 (stable-ts)", 100)
            return SttJobResult(True, "자막 생성 완료 (stable-ts)", ja_srt)
        if os.path.exists(plain_srt):
            on_progress and on_progress("기존 .srt 사용", 100)
            return SttJobResult(True, "기존 .srt 사용 (STT 스킵)", plain_srt, skipped=True)
        return SttJobResult(False, "자막 파일이 생성되지 않았습니다.")
    except STTCancelled:
        return SttJobResult(False, "사용자에 의해 STT가 중단되었습니다.")
    except Exception as e:
        traceback.print_exc()
        return SttJobResult(False, f"STT 공정 에러: {e}")
    finally:
        clear_vram()
        try:
            out_dir = Path(output_dir).resolve()
            if out_dir.name == "stt_work" and out_dir.parent == path.parent and out_dir.exists():
                import shutil

                shutil.rmtree(out_dir, ignore_errors=True)
        except Exception:
            pass


def run_subtitle_job(
    product_code: str,
    video_path: str,
    *,
    on_progress: ProgressFn | None = None,
    on_log: LogFn | None = None,
    on_content_line: ContentLineFn | None = None,
    should_cancel: CancelFn | None = None,
) -> SubtitleJobResult:
    from javstory.llm.engine import AllTiersExhaustedError
    from javstory.transcription.stt_types import STTCancelled

    video = Path(video_path).resolve()
    if not video.is_file():
        return SubtitleJobResult(False, f"파일을 찾을 수 없습니다: {video}")

    base_name = str(video.with_suffix(""))
    pc = (product_code or "").strip().upper()
    if not pc:
        from javstory.utils.product_code import resolve_product_code_for_video

        pc = resolve_product_code_for_video(video)
    if not pc:
        return SubtitleJobResult(False, "품번을 확인할 수 없습니다.")

    if _has_builtin_subtitle_marker(video):
        ko_srt = base_name + ".ko.srt"
        plain_srt = base_name + ".srt"
        res = ko_srt if os.path.exists(ko_srt) else (plain_srt if os.path.exists(plain_srt) else "")
        on_progress and on_progress("[완료] 자체자막 표기 → 번역 스킵", 100)
        return SubtitleJobResult(True, "자체자막 표기: 번역 스킵", res, skipped=True)

    skip = _subtitle_skip_existing(base_name)
    if skip:
        on_progress and on_progress(f"[완료] {skip.message}", 100)
        return skip

    ja_srt = base_name + ".ja.srt"
    if not os.path.exists(ja_srt):
        return SubtitleJobResult(False, "JA 자막 파일(.ja.srt)을 찾을 수 없습니다. STT를 먼저 실행하세요.")

    def _logger(msg: str) -> None:
        if on_log:
            on_log("info", msg)
        if on_progress:
            on_progress(msg, -1)

    try:
        from javstory.pipeline.orchestrator import build_default_router
        from javstory.translation.subtitle_pipeline_orchestrator import SubtitlePipelineOrchestrator

        on_progress and on_progress("자막 파이프라인 초기화...", 5)
        router = build_default_router(logger_func=_logger)
        orch = SubtitlePipelineOrchestrator(router)

        kwargs = {
            "ja_srt_path": ja_srt,
            "should_cancel": should_cancel or (lambda: False),
            "logger_func": _logger,
            "on_content_line": on_content_line,
        }

        async def _run_subtitle() -> None:
            try:
                await orch.run_for_product(pc, **kwargs)
            finally:
                from javstory.llm.llamacpp_backend import cleanup_llamacpp_after_job

                cleanup_llamacpp_after_job(
                    cancelled=should_cancel() if should_cancel else False,
                    logger_func=_logger,
                )
                await router.close()

        on_progress and on_progress("KO 번역 진행 중...", 20)
        asyncio.run(_run_subtitle())

        ko_srt = str(video.with_suffix("")).rsplit(".ja", 1)[0] + ".ko.srt"
        if not Path(ko_srt).exists():
            ko_srt = str(video.with_suffix(".ko.srt"))
        if Path(ko_srt).exists():
            on_progress and on_progress("자막 파이프라인 완료", 100)
            return SubtitleJobResult(True, f"자막 파이프라인 완료: {ko_srt}", ko_srt)
        return SubtitleJobResult(True, "자막 파이프라인 완료 (KO SRT 경로 확인 필요)")
    except STTCancelled:
        return SubtitleJobResult(False, "사용자에 의해 자막 파이프라인이 중단되었습니다.")
    except AllTiersExhaustedError as e:
        hint = (
            "[OpenRouter] 모든 LLM 티어가 실패했거나 검열되었습니다. "
            "API 키·모델 설정을 확인하세요. (docs/llm_troubleshooting.md)"
        )
        last = getattr(e, "last_model", None)
        if last:
            hint += f" 마지막 티어: {last}."
        return SubtitleJobResult(False, hint)
    except Exception as e:
        if type(e).__name__ == "AllTiersExhaustedError":
            return SubtitleJobResult(
                False,
                "[OpenRouter] 모든 LLM 티어가 실패했거나 검열되었습니다. "
                "docs/llm_troubleshooting.md 참고.",
            )
        traceback.print_exc()
        return SubtitleJobResult(False, f"자막 파이프라인 오류: {e}")
