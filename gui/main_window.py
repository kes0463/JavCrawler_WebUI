"""메인 윈도우 클래스 정의: UI 위젯을 포함하므로 QApplication 생성 후 로드되어야 함."""
import sys
from PyQt6.QtCore import Qt
from qfluentwidgets import (
    NavigationItemPosition, FluentWindow,
    FluentIcon as FIF
)

from gui.theme_manager import theme_manager, AppTheme
from gui.views.dashboard import DashboardView
from gui.views.harvest import HarvestView
from gui.views.processing import ProcessingView
from gui.views.library import LibraryView
from gui.views.settings import SettingsView
from gui.components.log_drawer import LogDrawer

class JAVStoryMainWindow(FluentWindow):
    _instance = None

    @staticmethod
    def instance() -> JAVStoryMainWindow | None:
        return JAVStoryMainWindow._instance

    def __init__(self):
        super().__init__()
        JAVStoryMainWindow._instance = self
        self.setWindowTitle("JAVSTORY Pro - AI Story Analyzer")
        self.resize(1100, 750)
        self._mica_applied = False
        
        # Mica 효과 적용
        self._apply_mica()
        
        # 로그 드로어 UI (하단 고정)
        self.log_drawer = LogDrawer(self)
        self.log_drawer.hide()
        
        # 실제 뷰 초기화
        self._init_navigation()
        
        # UI 폴리싱: 여백 및 레이아웃 조정 (초기화 후 수행)
        self.navigationInterface.setMenuButtonVisible(True)
        self.navigationInterface.setExpandWidth(250)
        
        # 테마 변경 신호 연결
        theme_manager.themeChanged.connect(self._on_theme_changed)
        
        # 초기 테마 로드
        theme_manager.set_theme(AppTheme.WIN11_NATIVE)
        
        # 전역 QSS 적용 (사이드바 및 버튼 스타일 보정)
        self._apply_global_styles()

    def _apply_global_styles(self):
        # 사이드바 아이템의 배경색과 테두리를 투명하게 강제 설정 (잔상 및 블랙박스 현상 제거)
        style = """
            #NavigationInterface, #NavigationBar, #NavigationPanel {
                background-color: transparent !important;
                border: none;
            }
            NavigationItem {
                background-color: transparent !important;
            }
            NavigationItem:hover {
                background-color: rgba(255, 255, 255, 0.1) !important;
            }
            #NavigationPanel {
                background-color: rgba(255, 255, 255, 0.02) !important;
            }
        """
        self.setStyleSheet(style)
        # 윈도우 배경색 미세 조정 (잔상 방지용 베이스 레이어)
        self.setProperty("mica-enabled", True)

    def _apply_mica(self):
        if self._mica_applied:
            return
            
        if sys.platform == "win32":
            try:
                import win32mica
                import darkdetect
                hwnd = int(self.winId())
                mode = win32mica.MicaTheme.DARK if darkdetect.isDark() else win32mica.MicaTheme.LIGHT
                win32mica.ApplyMica(hwnd, mode)
                self._mica_applied = True
            except Exception as e:
                print(f"[UI] Mica 효과 적용 실패 (무시됨): {e}")

    def _init_navigation(self):
        # 1. Dashboard
        self.dashboard_view = DashboardView(self)
        self.addSubInterface(self.dashboard_view, FIF.HOME, "대시보드")
        
        # 2. Harvest (Stage 1, 2)
        self.harvest_view = HarvestView(self)
        self.addSubInterface(self.harvest_view, FIF.SEARCH, "수집")
        
        # 3. Transcription (STT + 멀티파트)
        self.processing_view = ProcessingView(self)
        self.addSubInterface(self.processing_view, FIF.MICROPHONE, "전사")
        
        # 4. Library — Harvest + canonical
        self.library_view = LibraryView(self)
        self.addSubInterface(self.library_view, FIF.LIBRARY, "라이브러리")
        
        # 5. Settings
        self.settings_view = SettingsView(self)
        self.addSubInterface(
            self.settings_view, FIF.SETTING, "설정",
            position=NavigationItemPosition.BOTTOM
        )

    def _on_theme_changed(self, theme: AppTheme):
        if theme == AppTheme.WIN11_NATIVE:
            self._apply_mica()
        self.log_drawer.append_log(f"테마가 {theme.value} 모드로 변경되었습니다.")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_QuoteLeft and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if self.log_drawer.isHidden():
                self.log_drawer.show()
                self.log_drawer.setGeometry(0, self.height() - 300, self.width(), 300)
            else:
                self.log_drawer.hide()
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'log_drawer') and not self.log_drawer.isHidden():
            self.log_drawer.setGeometry(0, self.height() - 300, self.width(), 300)
