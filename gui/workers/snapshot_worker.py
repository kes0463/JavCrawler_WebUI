from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import QThread, Signal

class SnapshotWorker(QThread):
    """라이브러리 상세 화면 등에서 개별 작품의 스냅샷을 추출하는 워커."""
    progress = Signal(int, int) # curr, total
    finished = Signal(bool, str) # success, message

    def __init__(self, product_code: str, video_path: str, output_dir: str):
        super().__init__()
        self.product_code = product_code
        self.video_path = Path(video_path)
        self.output_dir = Path(output_dir)

    def run(self):
        try:
            if not self.video_path.is_file():
                self.finished.emit(False, f"영상을 찾을 수 없습니다: {self.video_path}")
                return

            self.output_dir.mkdir(parents=True, exist_ok=True)

            from javstory.library.stills.extract import (
                extract_snapshots_auto_adaptive, 
                suggest_snapshot_target_count, 
                probe_video_duration_seconds
            )
            
            # 예상 개수 계산 (UI 진행바용)
            dur = probe_video_duration_seconds(self.video_path)
            total_expected = suggest_snapshot_target_count(dur)
            
            def _cb(percent):
                # 퍼센트를 기반으로 대략적인 개수 계산하여 전달
                curr = int(total_expected * (percent / 100))
                self.progress.emit(curr, total_expected)

            # 자동 적응형 추출 (CUDA 가속 우선 사용)
            res = extract_snapshots_auto_adaptive(
                self.video_path,
                self.output_dir,
                progress_callback=_cb
            )
            
            if res:
                self.finished.emit(True, f"스냅샷 {len(res)}개 추출 완료")
            else:
                self.finished.emit(False, "스냅샷 추출에 실패했습니다.")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished.emit(False, f"에러 발생: {e}")
