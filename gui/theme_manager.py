"""테마 매니저: JAVSTORY의 3가지 테마(Win11 Native, White, Dark)를 관리."""
from enum import Enum
from pathlib import Path
import darkdetect
from PyQt6.QtCore import QObject, pyqtSignal
from qfluentwidgets import Theme, setTheme, setThemeColor

class AppTheme(Enum):
    WIN11_NATIVE = "win11"
    PRETTY_WHITE = "white"
    ELEGANT_DARK = "dark"

class ThemeManager(QObject):
    themeChanged = pyqtSignal(AppTheme)

    def __init__(self):
        super().__init__()
        self._current_theme = AppTheme.WIN11_NATIVE
        self.styles_dir = Path(__file__).parent / "styles"

    def get_theme(self) -> AppTheme:
        return self._current_theme

    def set_theme(self, theme: AppTheme):
        """테마를 설정하고 신호를 발생시킵니다."""
        self._current_theme = theme
        
        # Fluent Widgets 기본 테마 설정
        if theme == AppTheme.PRETTY_WHITE:
            setTheme(Theme.LIGHT)
            setThemeColor("#00ADB5")  # Cyan Accent
        elif theme == AppTheme.ELEGANT_DARK:
            setTheme(Theme.DARK)
            setThemeColor("#00ADB5")
        elif theme == AppTheme.WIN11_NATIVE:
            # 시스템 설정에 따라 다크/라이트 결정 (Mica는 메인 윈도우에서 처리)
            is_dark = darkdetect.isDark()
            setTheme(Theme.DARK if is_dark else Theme.LIGHT)
            setThemeColor("#00ADB5")

        self.themeChanged.emit(theme)

    def get_qss_path(self, theme: AppTheme) -> str:
        """테마별 추가 QSS 경로를 반환합니다."""
        p = self.styles_dir / f"{theme.value}.qss"
        return str(p) if p.exists() else ""

# 싱글톤 인스턴스
theme_manager = ThemeManager()
