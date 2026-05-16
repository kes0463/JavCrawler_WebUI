"""
Deprecated — PyQt6 Fluent 대시보드.

운영 UI: gui/qml/views/DashboardView.qml
→ gui/views/README.md
"""
import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel,
)
from PyQt6.QtCore import QTimer
from qfluentwidgets import (
    TitleLabel, SubtitleLabel, ProgressBar,
    setFont, CardWidget,
    ListWidget,
)
import subprocess
from javstory.harvest.database import get_db_session, JAVMetadata


class DashboardView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DashboardView")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(30, 30, 30, 30)
        self.layout.setSpacing(20)

        self._init_header()
        self._init_resource_monitor()
        self._init_task_list()

        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_all)
        self.update_timer.start(3000)

        QTimer.singleShot(500, self._update_all)

    def _init_header(self):
        header_layout = QHBoxLayout()

        title_layout = QVBoxLayout()
        title = TitleLabel("대시보드", self)
        desc = SubtitleLabel("시스템 리소스 및 작업 현황", self)
        setFont(title, 28, weight=700)
        title_layout.addWidget(title)
        title_layout.addWidget(desc)

        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        self.layout.addLayout(header_layout)

    def _init_resource_monitor(self):
        monitor_layout = QHBoxLayout()

        self.vram_card = CardWidget(self)
        v_layout = QVBoxLayout(self.vram_card)
        v_layout.addWidget(SubtitleLabel("GPU VRAM 점유율", self.vram_card))

        self.vram_bar = ProgressBar(self.vram_card)
        self.vram_bar.setValue(0)
        v_layout.addWidget(self.vram_bar)

        self.vram_label = QLabel("0.0 GB / 0.0 GB", self.vram_card)
        v_layout.addWidget(self.vram_label)

        monitor_layout.addWidget(self.vram_card)

        self.cpu_card = CardWidget(self)
        c_layout = QVBoxLayout(self.cpu_card)
        c_layout.addWidget(SubtitleLabel("시스템 상태", self.cpu_card))
        self.cpu_bar = ProgressBar(self.cpu_card)
        self.cpu_bar.setValue(0)
        c_layout.addWidget(self.cpu_bar)
        self.cpu_label = QLabel("CPU: - %", self.cpu_card)
        c_layout.addWidget(self.cpu_label)
        self.mem_bar = ProgressBar(self.cpu_card)
        self.mem_bar.setValue(0)
        c_layout.addWidget(self.mem_bar)
        self.mem_label = QLabel("메모리: - / - GB", self.cpu_card)
        c_layout.addWidget(self.mem_label)

        monitor_layout.addWidget(self.cpu_card)

        # 에러 상태 카드
        self.error_card = CardWidget(self)
        e_layout = QVBoxLayout(self.error_card)
        e_layout.addWidget(SubtitleLabel("⚠️ 에러 복구 상태", self.error_card))

        self.error_label = QLabel("로딩 중...", self.error_card)
        e_layout.addWidget(self.error_label)

        self.error_retry_btn = None  # 버튼은 나중에 추가

        monitor_layout.addWidget(self.error_card)

        self.layout.addLayout(monitor_layout)

    def _init_task_list(self):
        v_layout = QVBoxLayout()
        v_layout.addWidget(SubtitleLabel("작업 현황 (Pending Queue)", self))

        self.task_list = ListWidget(self)
        self.task_list.setMinimumHeight(400)

        v_layout.addWidget(self.task_list)
        self.layout.addLayout(v_layout)

    def _update_all(self):
        self._update_vram()
        self._update_cpu_mem()
        self._update_queue()
        self._update_error_status()

    def _update_vram(self):
        try:
            cmd = "nvidia-smi --query-gpu=memory.total,memory.used --format=csv,nounits,noheader"
            output = subprocess.check_output(cmd, shell=True).decode().strip()
            total, used = map(float, output.split(","))

            percent = int((used / total) * 100)
            self.vram_bar.setValue(percent)
            self.vram_label.setText(f"{used / 1024:.1f} GB / {total / 1024:.1f} GB")
        except Exception:
            self.vram_bar.setValue(0)
            self.vram_label.setText("GPU를 감지할 수 없습니다.")

    def _update_queue(self):
        session = get_db_session()
        try:
            pending_tasks = session.query(JAVMetadata).filter_by(analysis_status="pending").all()

            self.task_list.clear()
            if not pending_tasks:
                self.task_list.addItem("분석 대기 중인 항목이 없습니다.")
            else:
                for task in pending_tasks:
                    title = task.title or task.product_code
                    if len(title) > 60:
                        title = title[:57] + "..."
                    self.task_list.addItem(f"[{task.product_code}] {title}")
        except Exception as e:
            print(f"[Dashboard] 큐 갱신 오류: {e}")
        finally:
            session.close()

    def _update_cpu_mem(self):
        try:
            import psutil

            cpu = psutil.cpu_percent(interval=0)
            mem = psutil.virtual_memory()
            self.cpu_bar.setValue(int(cpu))
            self.cpu_label.setText(f"CPU: {cpu:.0f}%")
            used_gb = mem.used / (1024**3)
            total_gb = mem.total / (1024**3)
            self.mem_bar.setValue(int(mem.percent))
            self.mem_label.setText(f"메모리: {used_gb:.1f} / {total_gb:.1f} GB ({mem.percent:.0f}%)")
        except ImportError:
            self.cpu_label.setText("CPU: psutil 미설치")
            self.mem_label.setText("메모리: psutil 미설치")
        except Exception:
            self.cpu_label.setText("CPU: 측정 불가")
            self.mem_label.setText("메모리: 측정 불가")

    def _update_error_status(self):
        """에러 복구 상태 업데이트"""
        try:
            from javstory.utils.error_watcher import get_error_watcher
            import asyncio

            watcher = get_error_watcher()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                stats = loop.run_until_complete(watcher.get_stats())
            finally:
                loop.close()

            # 상태 텍스트 구성
            pending = stats.pending_retries
            max_exceeded = stats.max_retries_exceeded
            resolved = stats.resolved

            if pending == 0 and max_exceeded == 0:
                status_text = "✅ 에러 없음"
                color = "#27ae60"
            elif max_exceeded > 0:
                status_text = f"⚠️ 재시도 초과: {max_exceeded}건"
                color = "#e74c3c"
            else:
                status_text = f"⏳ 재시도 대기: {pending}건"
                color = "#f39c12"

            self.error_label.setText(status_text)
            self.error_label.setStyleSheet(f"color: {color}; font-weight: bold;")

        except Exception as e:
            self.error_label.setText("⚠️ 에러 상태 로드 실패")
            print(f"[Dashboard] 에러 상태 업데이트 오류: {e}")
