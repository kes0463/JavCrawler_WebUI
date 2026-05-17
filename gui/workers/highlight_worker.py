from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Signal as pyqtSignal

from gui.workers.cancellable_thread import CancellableQThread


class HighlightWorker(CancellableQThread):
    """영상에서 하이라이트 클립을 추출하는 백그라운드 워커(사용자 수동 트리거)."""

    resultReady = pyqtSignal(bool, str)  # success, message
    progressUpdated = pyqtSignal(int, str)  # 0~100 퍼센트 진행률, 상세 메시지

    def __init__(self, product_code: str, video_path: str, output_dir: str):
        super().__init__()
        self.product_code = (product_code or "").strip().upper()
        self.video_path = Path(video_path)
        self.output_dir = Path(output_dir)

    def run(self):
        if self.is_cancelled():
            self.resultReady.emit(False, "cancelled")
            return
        success = False
        msg = ""
        try:
            self.progressUpdated.emit(0, "준비 중...")
            if self.is_cancelled():
                self.resultReady.emit(False, "cancelled")
                return
            if not self.video_path.exists():
                self.resultReady.emit(False, f"원본 영상을 찾을 수 없습니다: {self.video_path}")
                return

            self.output_dir.mkdir(parents=True, exist_ok=True)

            self.progressUpdated.emit(1, "리소스 확보 대기 중...")
            from javstory.library.highlight.highlight import create_highlight_video
            from javstory.utils.process_limit import ffmpeg_semaphore

            with ffmpeg_semaphore:
                if self.is_cancelled():
                    self.resultReady.emit(False, "cancelled")
                    return
                self.progressUpdated.emit(5, "하이라이트 분석 및 생성 시작...")
                res_path = create_highlight_video(
                    product_code=self.product_code,
                    video_path=self.video_path,
                    output_dir=self.output_dir,
                    progress_callback=lambda p: self.progressUpdated.emit(int(p), "처리 중..."),
                )

            if self.is_cancelled():
                self.resultReady.emit(False, "cancelled")
                return
            if res_path and res_path.exists():
                success = True
                msg = "하이라이트 영상이 생성되었습니다!"
            else:
                msg = "하이라이트 생성 중 하이라이트 구간을 찾지 못했거나 오류가 발생했습니다."
        except Exception as e:
            if self.is_cancelled():
                self.resultReady.emit(False, "cancelled")
                return
            success = False
            msg = f"에러 발생: {str(e)}"

        self.resultReady.emit(success, msg)
