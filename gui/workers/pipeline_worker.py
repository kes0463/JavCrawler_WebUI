"""A축 통합 워커: Harvest → STT → Subtitle 원스톱 실행."""
import asyncio
import sys
import traceback
from pathlib import Path
from PySide6.QtCore import QThread, Signal

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from javstory.pipeline.orchestrator import (
    PipelineStage,
    run_product_pipeline_async,
    build_default_router,
)


class PipelineWorker(QThread):
    """
    품번 단위 Harvest→STT→Subtitle 통합 파이프라인.
    stages 로 부분 실행도 가능.
    """
    progress = Signal(str, str, int)  # stage_name, message, percent
    finished = Signal(bool, str)      # success, summary_message

    def __init__(
        self,
        product_code: str,
        video_path: str | None = None,
        *,
        stages: set[PipelineStage] | str = "all",
        force: bool = False,
        subtitle_kwargs: dict | None = None,
        harvest_kwargs: dict | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.product_code = product_code
        self.video_path = video_path
        self.stages = stages
        self.force = force
        self.subtitle_kwargs = subtitle_kwargs or {}
        self.harvest_kwargs = harvest_kwargs or {}
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        try:
            def _logger(msg: str):
                stage = "pipeline"
                if "[Pipeline]" in msg:
                    stage = "pipeline"
                elif "[Coordinator]" in msg or "크롤" in msg:
                    stage = "harvest"
                elif "stable-ts" in msg.lower() or "whisper" in msg.lower() or "[STT" in msg:
                    stage = "stt"
                elif "번역" in msg or "교정" in msg or "KO" in msg:
                    stage = "subtitle"
                self.progress.emit(stage, msg, -1)

            self.progress.emit("pipeline", "파이프라인 시작...", 0)

            sk = {**self.subtitle_kwargs}
            sk["should_cancel"] = lambda: not self._is_running

            result = asyncio.run(
                run_product_pipeline_async(
                    product_code=self.product_code,
                    video_path=self.video_path,
                    stages=self.stages,
                    force=self.force,
                    harvest_kwargs=self.harvest_kwargs,
                    subtitle_kwargs=sk,
                    logger_func=_logger,
                    skip_if_outputs_exist=not self.force,
                )
            )

            parts = []
            for key in ("harvest", "stt", "subtitle"):
                val = result.get(key)
                if val is None:
                    continue
                if isinstance(val, str):
                    parts.append(f"{key}: {val}")
                elif isinstance(val, dict):
                    if val.get("error"):
                        parts.append(f"{key}: 실패 - {val['error']}")
                    else:
                        parts.append(f"{key}: 완료")
                else:
                    parts.append(f"{key}: {val}")

            has_error = False
            h = result.get("harvest")
            if isinstance(h, dict) and h.get("error"):
                has_error = True

            summary = " | ".join(parts) if parts else "완료"
            self.finished.emit(not has_error, summary)

        except Exception as e:
            traceback.print_exc()
            self.finished.emit(False, f"파이프라인 오류: {e}")
