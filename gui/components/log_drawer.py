"""로그 드로어: UI 하단에 숨겨진 반투명 로그 콘솔 컴포넌트."""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextEdit
from PyQt6.QtCore import QDateTime
from qfluentwidgets import SubtitleLabel, setFont

class LogDrawer(QWidget):
    """
    사용자가 필요할 때만 슬라이드 형식으로 올라오는 로그 드로어.
    Mica/Acrylic 디자인 언어를 유지하며 반투명하게 구현합니다.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(300)
        
        # 레이아웃 구성
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 타이틀바
        header = QWidget()
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 0)
        
        title = SubtitleLabel("시스템 로그", self)
        setFont(title, 14)
        h_layout.addWidget(title)
        
        layout.addWidget(header)
        
        # 로그 텍스트 영역
        self.log_text = QTextEdit(self)
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: rgba(30, 30, 30, 180);
                color: #d4d4d4;
                border: none;
                border-radius: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 13px;
            }
        """)
        layout.addWidget(self.log_text)
        
        # 반투명 배경 및 라운드 코너
        self.setStyleSheet("""
            LogDrawer {
                background-color: rgba(20, 20, 20, 200);
                border-top: 1px solid rgba(255, 255, 255, 30);
                border-top-left-radius: 16px;
                border-top-right-radius: 16px;
            }
        """)

    def append_log(self, text: str):
        """로그를 추가하고 가장 아래로 스크롤합니다."""
        now = QDateTime.currentDateTime().toString("HH:mm:ss")
        self.log_text.append(f"[{now}] {text}")
        self.log_text.ensureCursorVisible()

    def clear(self):
        self.log_text.clear()
