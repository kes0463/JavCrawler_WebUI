"""전사(Transcription) 뷰: STT(stable-ts) + 멀티파트 SRT 합성."""
import os
import sys
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy, QFileDialog
from qfluentwidgets import (
    SubtitleLabel, ProgressBar, BodyLabel,
    FluentIcon as FIF, PushButton, TextBrowser, setFont,
    StrongBodyLabel, PrimaryPushButton,
)

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from gui.workers.stt_worker import STTWorker
from gui.components.transcription_queue_widget import TranscriptionQueueWidget
from gui.components.multipart_merge_dialog import MultiPartMergeDialog


class ProcessingView(QWidget):
    """STT 전사 및 멀티파트 SRT 합성 뷰."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ProcessingView")
        self.stt_worker = None
        self._stt_queue_mode = False
        self._queue_paths: list[str] = []
        self._queue_idx = 0

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(30, 20, 30, 20)
        self.main_layout.setSpacing(16)

        self._init_header()
        self._init_transcription_queue()
        self._init_logs()
        self._init_controls()

    def _init_header(self):
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)

        self.title_label = SubtitleLabel("전사 (Transcription)")
        setFont(self.title_label, 26)

        self.file_info_label = BodyLabel("영상을 선택하거나 큐를 사용하여 자막을 생성하세요.")
        self.file_info_label.setTextColor(Qt.GlobalColor.gray)

        self.overall_progress = ProgressBar()
        self.overall_progress.setValue(0)
        self.overall_progress.setFixedHeight(4)

        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.file_info_label)
        header_layout.addWidget(self.overall_progress)

        self.main_layout.addWidget(header_widget)

    def _init_transcription_queue(self) -> None:
        self.transcription_queue = TranscriptionQueueWidget(self)
        self.transcription_queue.runRequested.connect(self._on_queue_run_stt)
        self.main_layout.addWidget(self.transcription_queue)

        mp_row = QHBoxLayout()
        self.btn_multipart = PushButton(FIF.MOVE, "멀티파트 · 논리 타임라인 SRT 합성…", self)
        self.btn_multipart.setToolTip(
            "파트별 동명 SRT가 있을 때만. 합본은 번역·참고용 — 플레이어는 파트마다 개별 SRT 사용."
        )
        self.btn_multipart.clicked.connect(self._on_multipart_merge_dialog)
        mp_row.addWidget(self.btn_multipart)
        mp_row.addStretch()
        self.main_layout.addLayout(mp_row)

    def _on_multipart_merge_dialog(self) -> None:
        dlg = MultiPartMergeDialog(self.window())
        dlg.exec()

    def _init_logs(self):
        log_section = QWidget()
        log_section.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        log_layout = QVBoxLayout(log_section)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(4)

        log_header = QHBoxLayout()
        log_header.setContentsMargins(0, 0, 0, 0)
        log_header.setSpacing(0)
        log_header.addWidget(StrongBodyLabel("실시간 로그"), 0, Qt.AlignmentFlag.AlignTop)
        log_header.addStretch()

        self.log_browser = TextBrowser()
        self.log_browser.setMinimumHeight(200)
        self.log_browser.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.log_browser.setPlaceholderText("STT 엔진 대기 중...")

        log_layout.addLayout(log_header)
        log_layout.addWidget(self.log_browser, stretch=1)

        self.main_layout.addWidget(log_section, stretch=1)

    def _init_controls(self):
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(10)

        self.select_btn = PushButton(FIF.FOLDER, "파일 선택")
        self.select_btn.clicked.connect(self._on_select_file)

        self.start_btn = PrimaryPushButton(FIF.MICROPHONE, "자막 생성")
        self.start_btn.clicked.connect(self._on_generate_stt)

        self.stop_btn = PushButton(FIF.CANCEL, "중지")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)

        controls_layout.addWidget(self.select_btn)
        controls_layout.addStretch()
        controls_layout.addWidget(self.start_btn)
        controls_layout.addWidget(self.stop_btn)

        self.main_layout.addLayout(controls_layout)

    # --- Event Handlers ---

    def _on_select_file(self):
        video_file, _ = QFileDialog.getOpenFileName(
            self, "비디오 파일 선택", "", "Videos (*.mp4 *.mkv *.avi)"
        )
        if video_file:
            self.video_path = video_file
            self.file_info_label.setText(f"대상: {os.path.basename(video_file)}")
            self.file_info_label.setTextColor(Qt.GlobalColor.gray)
            self.overall_progress.setValue(0)
            self.log_browser.clear()
            self.log_browser.append(f"[시스템] STT 대기: {video_file}")

    def _on_generate_stt(self):
        if not hasattr(self, "video_path") or not self.video_path:
            self.log_browser.append("[에러] 먼저 파일을 선택하세요.")
            return
        if self.stt_worker is not None and self.stt_worker.isRunning():
            self.log_browser.append("[경고] 자막 생성이 이미 진행 중입니다.")
            return
        if self._stt_queue_mode:
            self.log_browser.append("[경고] 큐 실행 중에는 단일 자막 생성을 시작할 수 없습니다.")
            return

        self._set_ui_busy(True)
        self.log_browser.append("\n[stable-ts] STT 자막 생성 시작…")

        self.stt_worker = STTWorker(self.video_path)
        self.stt_worker.progress.connect(self._on_stt_progress)
        self.stt_worker.finished.connect(self._on_stt_finished)
        self.stt_worker.start()

    def _on_queue_run_stt(self) -> None:
        paths = self.transcription_queue.checked_paths()
        if not paths:
            self.log_browser.append("[Transcription 큐] 체크된 동영상이 없습니다.")
            return
        if self.stt_worker is not None and self.stt_worker.isRunning():
            self.log_browser.append("[경고] 자막 생성이 이미 진행 중입니다.")
            return

        self._stt_queue_mode = True
        self._queue_paths = [str(p) for p in paths]
        self._queue_idx = 0
        self._set_ui_busy(True)
        self.log_browser.append(f"[Transcription 큐] {len(self._queue_paths)}건 순차 실행 시작")
        self.overall_progress.setValue(0)
        self._start_next_queue_stt()

    def _start_next_queue_stt(self) -> None:
        if not self._stt_queue_mode:
            return
        if self._queue_idx >= len(self._queue_paths):
            self._finish_queue_stt()
            return
        path = self._queue_paths[self._queue_idx]
        n = len(self._queue_paths)
        i = self._queue_idx + 1
        self.file_info_label.setText(f"[큐 {i}/{n}] {os.path.basename(path)}")
        self.file_info_label.setTextColor(Qt.GlobalColor.gray)
        self.log_browser.append(f"\n[큐 {i}/{n}] STT 시작: {path}")

        self.stt_worker = STTWorker(path)
        self.stt_worker.progress.connect(self._on_stt_progress)
        self.stt_worker.finished.connect(self._on_stt_finished)
        self.stt_worker.start()

    def _finish_queue_stt(self, aborted: bool = False) -> None:
        self._stt_queue_mode = False
        self._queue_paths = []
        self._queue_idx = 0
        self._set_ui_busy(False)
        if aborted:
            self.log_browser.append("[Transcription 큐] 중단됨.")
        else:
            self.log_browser.append("[Transcription 큐] 전체 순차 실행 완료.")
        self.file_info_label.setText("영상을 선택하거나 큐를 사용하세요.")
        self.overall_progress.setValue(0)

    def _on_stt_progress(self, msg: str, percent: int):
        self.log_browser.append(f"  > {msg}")
        self.overall_progress.setValue(percent)

    def _on_stt_finished(self, srt_path: str, success: bool, message: str):
        if self._stt_queue_mode:
            self._on_stt_finished_queue(srt_path, success, message)
            return

        self._set_ui_busy(False)
        if success:
            self.log_browser.append(f"\n[성공] stable-ts 자막 생성 완료: {os.path.basename(srt_path)}")
            self.file_info_label.setText(f"완료: {os.path.basename(srt_path)}")
            self.file_info_label.setTextColor(Qt.GlobalColor.green)
            self.overall_progress.setValue(100)
        else:
            if "중단" in message:
                self.log_browser.append(f"\n[중단] {message}")
            else:
                self.log_browser.append(f"\n[실패] 자막 생성 중 오류: {message}")
            self.overall_progress.setValue(0)

    def _on_stt_finished_queue(self, srt_path: str, success: bool, message: str) -> None:
        if not self._queue_paths or self._queue_idx >= len(self._queue_paths):
            self._finish_queue_stt(aborted=True)
            return

        cur = self._queue_paths[self._queue_idx]
        base = os.path.basename(cur)
        if "중단" in message:
            self.log_browser.append(f"[큐 중단] {base}: {message}")
            self._finish_queue_stt(aborted=True)
            return

        if success:
            self.log_browser.append(f"[큐 완료] {base} → {message}")
        else:
            self.log_browser.append(f"[큐 실패] {base}: {message}")

        self._queue_idx += 1
        total = max(1, len(self._queue_paths))
        done = min(self._queue_idx, total)
        self.overall_progress.setValue(int(100 * done / total))
        self._start_next_queue_stt()

    def _on_stop(self):
        if self.stt_worker:
            self.stt_worker.stop()
        self.log_browser.append("[시스템] 중단 요청됨.")
        self._set_ui_busy(False)

    def _set_ui_busy(self, is_busy: bool):
        self.start_btn.setEnabled(not is_busy)
        self.select_btn.setEnabled(not is_busy)
        self.stop_btn.setEnabled(is_busy)
        if hasattr(self, "transcription_queue"):
            self.transcription_queue.set_controls_enabled(not is_busy)
        if hasattr(self, "btn_multipart"):
            self.btn_multipart.setEnabled(not is_busy)
