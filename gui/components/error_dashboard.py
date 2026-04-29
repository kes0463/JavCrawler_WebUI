"""
Error Dashboard Widget - GUI 에러 상태 표시

대시보드에 에러 복구 상태를 표시하는 위젯입니다.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTableWidget, QTableWidgetItem, 
    QHeaderView, QFrame, QProgressBar
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont
import logging

logger = logging.getLogger(__name__)


class ErrorDashboardWidget(QWidget):
    """
    에러 대시보드 위젯
    
    표시 항목:
    - 현재 대기 중인 에러 작업 수
    - 재시도 예정 작업
    - 실패 횟수 초과 작업
    - "지금 재시도" 버튼
    """
    
    # 시그널
    retry_requested = pyqtSignal()  # 재시도 요청
    error_selected = pyqtSignal(str)  # 에러 선택 (품번)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_stats)
        self._refresh_timer.start(30000)  # 30초마다 갱신
    
    def _setup_ui(self):
        """UI 구성"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # 헤더
        header = QLabel("⚠️ 에러 복구 상태")
        header.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        layout.addWidget(header)
        
        # 통계 요약
        stats_frame = QFrame()
        stats_frame.setFrameShape(QFrame.Shape.StyledPanel)
        stats_layout = QHBoxLayout(stats_frame)
        
        self._pending_label = QLabel("대기: 0")
        self._pending_label.setFont(QFont("Segoe UI", 12))
        stats_layout.addWidget(self._pending_label)
        
        self._retry_label = QLabel("재시도 예정: 0")
        self._retry_label.setFont(QFont("Segoe UI", 12))
        stats_layout.addWidget(self._retry_label)
        
        self._failed_label = QLabel("최대 초과: 0")
        self._failed_label.setFont(QFont("Segoe UI", 12))
        self._failed_label.setStyleSheet("color: #e74c3c;")
        stats_layout.addWidget(self._failed_label)
        
        layout.addWidget(stats_frame)
        
        # 에러 목록 테이블
        self._error_table = QTableWidget()
        self._error_table.setColumnCount(5)
        self._error_table.setHorizontalHeaderLabels([
            "품번", "단계", "에러 유형", "재시도 횟수", "실패 시간"
        ])
        self._error_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._error_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._error_table.horizontalHeader().setStretchLastSection(True)
        self._error_table.setAlternatingRowColors(True)
        layout.addWidget(self._error_table)
        
        # 버튼 영역
        button_layout = QHBoxLayout()
        
        self._retry_button = QPushButton("🔄 지금 재시도")
        self._retry_button.clicked.connect(self._on_retry_clicked)
        button_layout.addWidget(self._retry_button)
        
        self._refresh_button = QPushButton("🔃 새로고침")
        self._refresh_button.clicked.connect(self._refresh_stats)
        button_layout.addWidget(self._refresh_button)
        
        layout.addLayout(button_layout)
        
        # 초기 통계 로드
        self._refresh_stats()
    
    def _refresh_stats(self):
        """통계 새로고침"""
        try:
            from javstory.utils.error_watcher import get_error_watcher
            from javstory.utils.error_recovery import ErrorType
            
            watcher = get_error_watcher()
            
            # 비동기 통계 가져오기
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                stats = loop.run_until_complete(watcher.get_stats())
            finally:
                loop.close()
            
            # UI 업데이트
            self._pending_label.setText(f"대기: {stats.pending_retries}")
            self._retry_label.setText(f"재시도 예정: {stats.pending_retries}")
            self._failed_label.setText(f"최대 초과: {stats.max_retries_exceeded}")
            
            # 테이블 업데이트
            self._update_error_table(stats)
            
        except Exception as e:
            logger.error(f"[ErrorDashboard] 통계 로드 오류: {e}")
    
    def _update_error_table(self, stats):
        """에러 테이블 업데이트"""
        # TODO: 실제 에러 목록 가져오기
        # 현재는 통계만 표시
        self._error_table.setRowCount(0)
        
        # 샘플 데이터 (실제 구현 시 제거)
        # self._error_table.setRowCount(1)
        # self._error_table.setItem(0, 0, QTableWidgetItem("ABC-123"))
        # self._error_table.setItem(0, 1, QTableWidgetItem("HARVEST"))
        # self._error_table.setItem(0, 2, QTableWidgetItem("NETWORK_ERROR"))
        # self._error_table.setItem(0, 3, QTableWidgetItem("1/3"))
        # self._error_table.setItem(0, 4, QTableWidgetItem("2026-04-25 10:30"))
    
    def _on_retry_clicked(self):
        """재시도 버튼 클릭"""
        self.retry_requested.emit()
        
        try:
            from javstory.utils.error_watcher import get_error_watcher
            
            watcher = get_error_watcher()
            
            # 비동기 재시도 실행
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results = loop.run_until_complete(watcher.force_retry_all())
                
                # 결과 표시
                msg = f"재시도 완료: 성공 {results['succeeded']}건, 실패 {results['failed']}건"
                logger.info(f"[ErrorDashboard] {msg}")
                
            finally:
                loop.close()
            
            # 통계 새로고침
            self._refresh_stats()
            
        except Exception as e:
            logger.error(f"[ErrorDashboard] 재시도 오류: {e}")
    
    def showEvent(self, event):
        """위젯 표시 시 통계 새로고침"""
        super().showEvent(event)
        self._refresh_stats()


class ErrorStatusBadge(QWidget):
    """
    에러 상태 배지 (단일 항목용)
    
    상태:
    - pending: 대기 중 (노랑)
    - retrying: 재시도 중 (파랑)
    - failed: 최대 초과 (빨강)
    - resolved: 해결됨 (초록)
    """
    
    def __init__(self, status: str = "pending", parent=None):
        super().__init__(parent)
        self._status = status
        self._setup_ui()
    
    def _setup_ui(self):
        """UI 구성"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        
        self._label = QLabel()
        self._update_style()
        
        layout.addWidget(self._label)
    
    def _update_style(self):
        """상태별 스타일 업데이트"""
        colors = {
            "pending": ("#f39c12", "대기"),
            "retrying": ("#3498db", "재시도 중"),
            "failed": ("#e74c3c", "최대 초과"),
            "resolved": ("#27ae60", "해결됨"),
        }
        
        color, text = colors.get(self._status, ("#95a5a6", "알 수 없음"))
        
        self._label.setText(f"● {text}")
        self._label.setStyleSheet(f"""
            QLabel {{
                color: {color};
                font-weight: bold;
                font-size: 12px;
            }}
        """)
    
    def set_status(self, status: str):
        """상태 설정"""
        self._status = status
        self._update_style()


# 테스트
if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    window = ErrorDashboardWidget()
    window.show()
    
    sys.exit(app.exec())