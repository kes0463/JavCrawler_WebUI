"""자막 파이프라인 워커: JA 교정 + KO 번역을 백그라운드에서 실행."""
import asyncio
import os
import sys
import traceback
from pathlib import Path
from PySide6.QtCore import QThread, Signal

from javstory.transcription.stt_types import STTCancelled
from javstory.llm.engine import AllTiersExhaustedError

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


class SubtitleWorker(QThread):
    """
    SubtitlePipelineOrchestrator.run_for_product 를 QThread에서 실행.
    결과: .ja.corrected.srt + .ko.srt 생성.
    """
    progress = Signal(str, int)   # message, percent
    finished = Signal(bool, str)  # success, message

    def __init__(
        self,
        product_code: str,
        video_path: str,
        *,
        ja_srt_path: str | None = None,
        work_dir: str | None = None,
        subtitle_kwargs: dict | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.product_code = product_code
        self.video_path = video_path
        self.ja_srt_path = ja_srt_path
        self.work_dir = work_dir
        self.subtitle_kwargs = subtitle_kwargs or {}
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        try:
            base_name = os.path.splitext(self.video_path)[0]
            ko_srt = base_name + ".ko.srt"
            plain_srt = base_name + ".srt"

            # 1. 자체자막 표기 감지 시 스킵
            p = Path(self.video_path)
            if any("자체자막" in part for part in p.parts):
                self.progress.emit("[완료] 자체자막 표기 감지 → 번역 스킵", 100)
                res_path = ko_srt if os.path.exists(ko_srt) else (plain_srt if os.path.exists(plain_srt) else "")
                self.finished.emit(True, f"자체자막 표기: 번역 공정 스킵 완료 (기존:{os.path.basename(res_path)})")
                return

            # 2. 결과물(KO SRT)이 이미 존재하면 스킵
            if os.path.exists(ko_srt):
                self.progress.emit("[완료] 기존 .ko.srt 감지 → 번역 스킵", 100)
                self.finished.emit(True, "기존 .ko.srt 존재: 번역 공정 스킵")
                return
            if os.path.exists(plain_srt):
                self.progress.emit("[완료] 기존 .srt(외부) 감지 → 번역 스킵", 100)
                self.finished.emit(True, "기존 .srt 존재: 번역 공정 스킵")
                return

            self.progress.emit("자막 파이프라인 초기화...", 5)
            
            from javstory.pipeline.orchestrator import build_default_router
            from javstory.translation.subtitle_pipeline_orchestrator import SubtitlePipelineOrchestrator
            
            def _logger(msg: str):
                self.progress.emit(msg, -1)
            
            router = build_default_router(logger_func=_logger)
            orch = SubtitlePipelineOrchestrator(router)
            
            video = Path(self.video_path)
            ja_srt = self.ja_srt_path
            if not ja_srt:
                candidate = video.with_suffix("").with_suffix(".ja.srt")
                if candidate.exists():
                    ja_srt = str(candidate)
            
            if not ja_srt or not Path(ja_srt).exists():
                self.finished.emit(False, "JA 자막 파일(.ja.srt)을 찾을 수 없습니다.")
                return

            kwargs = {
                **self.subtitle_kwargs,
                "ja_srt_path": ja_srt,
                "should_cancel": lambda: not self._is_running,
                "logger_func": _logger,
            }
            if self.work_dir:
                kwargs["work_dir"] = self.work_dir

            self.progress.emit("JA 교정 + KO 번역 진행 중...", 20)

            async def _run_subtitle() -> None:
                try:
                    await orch.run_for_product(self.product_code, **kwargs)
                finally:
                    from javstory.llm.llamacpp_backend import cleanup_llamacpp_after_job

                    cleanup_llamacpp_after_job(
                        cancelled=not self._is_running,
                        logger_func=_logger,
                    )
                    await router.close()

            asyncio.run(_run_subtitle())

            ko_srt = str(video.with_suffix("")).rsplit(".ja", 1)[0] + ".ko.srt"
            if not Path(ko_srt).exists():
                ko_srt = str(video.with_suffix(".ko.srt"))

            if Path(ko_srt).exists():
                self.finished.emit(True, f"자막 파이프라인 완료: {ko_srt}")
            else:
                self.finished.emit(True, "자막 파이프라인 완료 (KO SRT 경로 확인 필요)")

        except STTCancelled:
            self.progress.emit("[중단] 자막 파이프라인이 취소되었습니다.", 0)
            self.finished.emit(False, "[중단] 사용자가 작업을 취소했거나 처리 탭에서 중지했습니다.")
        except AllTiersExhaustedError as e:
            hint = (
                "[OpenRouter] 모든 LLM 티어가 실패했거나 검열되었습니다. "
                "API 키·모델 설정을 확인하세요. (docs/llm_troubleshooting.md)"
            )
            last = getattr(e, "last_model", None)
            if last:
                hint += f" 마지막 티어: {last}."
            self.progress.emit(hint, 0)
            self.finished.emit(False, hint)
        except Exception as e:
            if type(e).__name__ == "AllTiersExhaustedError":
                self.progress.emit(
                    "[OpenRouter] 모든 LLM 티어가 실패했거나 검열되었습니다.", 0
                )
                self.finished.emit(
                    False,
                    "[OpenRouter] 모든 LLM 티어가 실패했거나 검열되었습니다. "
                    "docs/llm_troubleshooting.md 참고.",
                )
                return
            traceback.print_exc()
            self.finished.emit(False, f"자막 파이프라인 오류: {e}")
