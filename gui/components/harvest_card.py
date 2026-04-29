"""하베스트 카드: 개별 수집 작업의 상태를 시각화하는 프리미엄 카드 위젯."""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from qfluentwidgets import (
    CardWidget, StrongBodyLabel, CaptionLabel, ProgressBar,
    TransparentPushButton, FluentIcon as FIF, setFont
)

class HarvestCard(CardWidget):
    """
    Stage 1-2의 수집 상태를 보여주는 카드.
    품번, 현재 상태 메시지, 프로그레스 바 등으로 구성됩니다.
    """
    def __init__(self, sku: str, parent=None):
        super().__init__(parent)
        self.sku = sku
        self.setFixedSize(320, 120)
        
        # 메인 레이아웃
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.layout.setSpacing(8)
        
        # 상단: 품번 및 삭제 버튼
        header = QHBoxLayout()
        self.title_label = StrongBodyLabel(sku, self)
        setFont(self.title_label, 16, weight=700)
        
        self.close_btn = TransparentPushButton(FIF.CLOSE, "", self)
        self.close_btn.setFixedSize(24, 24)
        
        header.addWidget(self.title_label)
        header.addStretch()
        header.addWidget(self.close_btn)
        self.layout.addLayout(header)
        
        # 중간: 상태 메시지
        self.status_label = CaptionLabel("수집 대기 중...", self)
        self.layout.addWidget(self.status_label)
        
        # 하단: 프로그레스 바
        self.progress_bar = ProgressBar(self)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(4)
        self.layout.addWidget(self.progress_bar)

    def update_status(self, message: str, percentage: int):
        """작업 진행 상황을 업데이트합니다."""
        self.status_label.setText(message)
        self.progress_bar.setValue(percentage)
        
        # 완료 시 디자인 변경 (옵션)
        if percentage >= 100:
            self.status_label.setStyleSheet("color: #00ADB5;") # 완성 색상
            
    def set_error(self, message: str):
        """에러 발생 시 상태를 표시합니다."""
        self.status_label.setText(f"에러: {message}")
        self.status_label.setStyleSheet("color: #FF4D4F;")
        self.progress_bar.pause()
