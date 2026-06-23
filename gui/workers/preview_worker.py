from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal as pyqtSignal

from gui.workers.cancellable_thread import CancellableQThread


class PreviewWorker(CancellableQThread):
    """Golden Preview(WebP) 생성 워커 (Harvest 후 자동/백필용)."""

    resultReady = pyqtSignal(bool, str)  # success, message
    progressUpdated = pyqtSignal(int, str)  # 0~100 퍼센트 진행률, 상세 메시지

    def __init__(self, product_code: str, video_path: str, output_path: str, seed: int = 0):
        super().__init__()
        self.product_code = (product_code or "").strip().upper()
        self.video_path = Path(video_path)
        self.output_path = Path(output_path)
        self.seed = seed

    def run(self):
        if self.is_cancelled():
            self.resultReady.emit(False, "cancelled")
            return
        try:
            self.progressUpdated.emit(0, "준비 중...")
            if not self.video_path.exists():
                self.resultReady.emit(False, f"원본 영상을 찾을 수 없습니다: {self.video_path}")
                return

            self.output_path.parent.mkdir(parents=True, exist_ok=True)

            from javstory.library.highlight.video_preview import create_golden_preview
            from javstory.utils.derived_cache import is_up_to_date, mark_up_to_date
            from javstory.utils.process_limit import ffmpeg_semaphore

            self.progressUpdated.emit(1, "기존 프리뷰 확인 중...")
            meta_path = self.output_path.with_suffix(self.output_path.suffix + ".meta.json")
            params = {"duration_sec": 8.0, "seed": self.seed}
            if self.output_path.is_file() and is_up_to_date(
                meta_path=meta_path,
                inputs={"video": self.video_path},
                params=params,
            ):
                self.progressUpdated.emit(100, "이미 최신 상태입니다.")
                self.resultReady.emit(True, "프리뷰(WebP)는 이미 최신입니다.")
                return

            self.progressUpdated.emit(5, "리소스 확보 대기 중...")
            with ffmpeg_semaphore:
                if self.is_cancelled():
                    self.resultReady.emit(False, "cancelled")
                    return
                self.progressUpdated.emit(10, "프리뷰(WebP) 생성 시작...")
                res = create_golden_preview(
                    product_code=self.product_code,
                    video_path=self.video_path,
                    output_path=self.output_path,
                    progress_callback=lambda p: self.progressUpdated.emit(int(p), "인코딩 중..."),
                    duration_sec=8.0,
                    seed=self.seed,
                )
            if self.is_cancelled():
                self.resultReady.emit(False, "cancelled")
                return
            if res and res.is_file():
                mark_up_to_date(meta_path=meta_path, inputs={"video": self.video_path}, params=params)
                self.resultReady.emit(True, "프리뷰(WebP)가 생성되었습니다!")
            else:
                self.resultReady.emit(False, "프리뷰 생성에 실패했습니다.")
        except Exception as e:
            if self.is_cancelled():
                self.resultReady.emit(False, "cancelled")
                return
            self.resultReady.emit(False, f"에러 발생: {e}")
