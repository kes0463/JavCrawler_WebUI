"""
Deprecated — PyQt6 Fluent 설정 뷰.

운영 UI: gui/qml/views/SettingsView.qml (+ gui/models/settings_model.py)
→ gui/views/README.md
"""
import os
import sys
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QFileDialog, QScrollArea,
)
from qfluentwidgets import (
    SubtitleLabel, BodyLabel, CaptionLabel,
    PushButton, PrimaryPushButton, LineEdit, PasswordLineEdit,
    SwitchButton, ComboBox, CardWidget, FluentIcon as FIF,
    InfoBar, InfoBarPosition, StrongBodyLabel, HorizontalSeparator,
)

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from javstory.config.app_config import (
    OLLAMA_BASE_URL, OPENROUTER_BASE_URL,
    MANUAL_MODEL_PRESETS,
)
from gui.theme_manager import theme_manager, AppTheme


class _SectionCard(CardWidget):
    """설정 섹션을 감싸는 카드."""
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 16, 20, 16)
        self._layout.setSpacing(12)
        lbl = StrongBodyLabel(title, self)
        self._layout.addWidget(lbl)

    def add_row(self, label: str, widget: QWidget) -> QWidget:
        row = QHBoxLayout()
        row.setSpacing(12)
        lbl = BodyLabel(label, self)
        lbl.setFixedWidth(180)
        row.addWidget(lbl)
        row.addWidget(widget, 1)
        self._layout.addLayout(row)
        return widget

    def add_widget(self, w: QWidget):
        self._layout.addWidget(w)


class SettingsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsView")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 16, 24, 16)

        header = SubtitleLabel("설정", self)
        root_layout.addWidget(header)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        root_layout.addWidget(scroll)

        container = QWidget()
        self._form = QVBoxLayout(container)
        self._form.setSpacing(16)
        self._form.setContentsMargins(0, 8, 0, 8)
        scroll.setWidget(container)

        self._build_api_section()
        self._build_paths_section()
        self._build_theme_section()
        self._build_stt_section()
        self._build_translation_section()
        self._build_options_section()

        self._form.addStretch(1)

        self._load_current_values()

    # ── API 키 ──────────────────────────────────────────────
    def _build_api_section(self):
        card = _SectionCard("API 설정", self)
        self.api_key_input = PasswordLineEdit(self)
        self.api_key_input.setPlaceholderText("sk-or-v1-...")
        card.add_row("OpenRouter API 키", self.api_key_input)

        self.ollama_url_input = LineEdit(self)
        self.ollama_url_input.setPlaceholderText(OLLAMA_BASE_URL)
        card.add_row("Ollama URL", self.ollama_url_input)

        btn_row = QHBoxLayout()
        btn_save = PrimaryPushButton(FIF.SAVE, "API 키 저장", self)
        btn_save.clicked.connect(self._save_api_key)
        btn_row.addStretch()
        btn_row.addWidget(btn_save)
        card.add_widget(self._wrap_layout(btn_row))

        self._form.addWidget(card)

    # ── 경로 설정 ──────────────────────────────────────────
    def _build_paths_section(self):
        card = _SectionCard("데이터 경로", self)

        self.media_input = LineEdit(self)
        browse_media = PushButton(FIF.FOLDER, "", self)
        browse_media.setFixedWidth(36)
        browse_media.clicked.connect(lambda: self._browse_folder(self.media_input))
        row_w3 = self._input_with_button(self.media_input, browse_media)
        card.add_row("미디어 루트", row_w3)

        btn_row = QHBoxLayout()
        btn_paths = PrimaryPushButton(FIF.SAVE, "경로 저장", self)
        btn_paths.clicked.connect(self._save_paths)
        btn_row.addStretch()
        btn_row.addWidget(btn_paths)
        card.add_widget(self._wrap_layout(btn_row))

        self._form.addWidget(card)

    # ── 테마 ────────────────────────────────────────────────
    def _build_theme_section(self):
        card = _SectionCard("테마", self)
        self.theme_combo = ComboBox(self)
        self.theme_combo.addItems(["Windows 11 (시스템)", "라이트", "다크"])
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        card.add_row("외관 테마", self.theme_combo)
        self._form.addWidget(card)

    # ── STT 모델 ────────────────────────────────────────────
    def _build_stt_section(self):
        card = _SectionCard("STT (음성 인식)", self)
        self.whisper_combo = ComboBox(self)
        self.whisper_combo.addItems([
            "large-v2 (기본, 권장)",
            "large-v3",
            "medium",
            "small",
            "turbo",
        ])
        card.add_row("Whisper 모델", self.whisper_combo)
        note = CaptionLabel("환경변수 JAVSTORY_WHISPER_MODEL로도 설정 가능", self)
        card.add_widget(note)
        self._form.addWidget(card)

    # ── 번역 프로필 ─────────────────────────────────────────
    def _build_translation_section(self):
        card = _SectionCard("한국어 번역", self)
        self.trans_profile_combo = ComboBox(self)
        self.trans_profile_combo.addItems([
            "default (DeepSeek V3.2)",
            "keeper (GLM 5.1)",
            "deepseek_chat (DeepSeek Chat)",
            "budget (Ollama gemma4:e4b)",
            "qwen35 (Ollama qwen3.5:9b)",
            "qwen3_14 (Ollama qwen3:14b)",
            "gemma3_12 (Ollama gemma3:12b)",
        ])
        card.add_row("번역 프로필", self.trans_profile_combo)
        self._form.addWidget(card)

    # ── 기타 옵션 ───────────────────────────────────────────
    def _build_options_section(self):
        card = _SectionCard("기타 옵션", self)

        self.grok_switch = SwitchButton(self)
        card.add_row("Grok 스토리 맥락", self.grok_switch)
        grok_note = CaptionLabel("Harvest 후 Grok API로 스토리 컨텍스트 캐시 생성", self)
        card.add_widget(grok_note)

        card.add_widget(HorizontalSeparator(self))

        self.embed_switch = SwitchButton(self)
        card.add_row("Ollama 임베딩(메타+캐노니컬+자막)", self.embed_switch)
        embed_note = CaptionLabel("저장 시 data/cache/embeddings/ 에 벡터 캐시 생성 (옵트인)", self)
        card.add_widget(embed_note)

        self.embed_model_input = LineEdit(self)
        self.embed_model_input.setPlaceholderText("nomic-embed-text")
        card.add_row("임베딩 모델", self.embed_model_input)

        card.add_widget(HorizontalSeparator(self))

        self.dpi_switch = SwitchButton(self)
        card.add_row("DPI 우회 (GoodbyeDPI)", self.dpi_switch)
        dpi_note = CaptionLabel("크롤링 시 SNI 차단 우회 (tools/goodbyedpi 필요)", self)
        card.add_widget(dpi_note)

        btn_row = QHBoxLayout()
        btn_save_opts = PrimaryPushButton(FIF.SAVE, "옵션 저장", self)
        btn_save_opts.clicked.connect(self._save_options)
        btn_row.addStretch()
        btn_row.addWidget(btn_save_opts)
        card.add_widget(self._wrap_layout(btn_row))

        self._form.addWidget(card)

    # ── 값 로드 ─────────────────────────────────────────────
    def _load_current_values(self):
        from javstory.config import secrets_manager
        from javstory.config.app_config import E_MEDIA_ROOT

        key = secrets_manager.get_openrouter_api_key() or ""
        self.api_key_input.setText(key)

        ollama = os.environ.get("JAVSTORY_OLLAMA_URL", OLLAMA_BASE_URL)
        self.ollama_url_input.setText(ollama)

        self.media_input.setText(str(E_MEDIA_ROOT))

        whisper = os.environ.get("JAVSTORY_WHISPER_MODEL", "large-v2")
        model_map = {"large-v2": 0, "large-v3": 1, "medium": 2, "small": 3, "turbo": 4}
        self.whisper_combo.setCurrentIndex(model_map.get(whisper, 0))

        profile = os.environ.get("JAVSTORY_TRANSLATION_PROFILE", "default").lower()
        profile_map = {
            "default": 0, "keeper": 1, "deepseek_chat": 2,
            "budget": 3, "qwen35": 4, "qwen3_14": 5, "gemma3_12": 6,
        }
        self.trans_profile_combo.setCurrentIndex(profile_map.get(profile, 0))

        grok_enabled = os.environ.get("JAVSTORY_STORY_ANALYSIS_ENABLED", "1").strip().lower()
        self.grok_switch.setChecked(grok_enabled in ("1", "true", "yes", "on"))

        emb_enabled = os.environ.get("JAVSTORY_EMBEDDINGS_ENABLED", "0").strip().lower()
        self.embed_switch.setChecked(emb_enabled in ("1", "true", "yes", "on"))
        self.embed_model_input.setText(os.environ.get("JAVSTORY_EMBEDDINGS_OLLAMA_MODEL", "nomic-embed-text"))

        self.dpi_switch.setChecked(False)

        theme = theme_manager.get_theme()
        theme_idx = {AppTheme.WIN11_NATIVE: 0, AppTheme.PRETTY_WHITE: 1, AppTheme.ELEGANT_DARK: 2}
        self.theme_combo.setCurrentIndex(theme_idx.get(theme, 0))

    # ── 저장 핸들러 ─────────────────────────────────────────
    def _save_api_key(self):
        from javstory.config import secrets_manager
        key = self.api_key_input.text().strip()
        if not key:
            InfoBar.warning("경고", "API 키를 입력하세요.", parent=self,
                            duration=3000, position=InfoBarPosition.TOP)
            return
        try:
            secrets_manager.set_openrouter_api_key(key)
            ollama = self.ollama_url_input.text().strip()
            if ollama:
                os.environ["JAVSTORY_OLLAMA_URL"] = ollama
            InfoBar.success("저장 완료", "API 키가 저장되었습니다.", parent=self,
                            duration=3000, position=InfoBarPosition.TOP)
        except Exception as e:
            InfoBar.error("오류", str(e), parent=self,
                          duration=5000, position=InfoBarPosition.TOP)

    def _save_paths(self):
        media = self.media_input.text().strip()
        if media:
            os.environ["JAVSTORY_MEDIA_ROOT"] = media
        InfoBar.success("저장 완료", "경로 설정이 적용되었습니다.", parent=self,
                        duration=3000, position=InfoBarPosition.TOP)

    def _save_options(self):
        whisper_models = ["large-v2", "large-v3", "medium", "small", "turbo"]
        idx = self.whisper_combo.currentIndex()
        os.environ["JAVSTORY_WHISPER_MODEL"] = whisper_models[idx] if idx < len(whisper_models) else "large-v2"

        profiles = ["default", "keeper", "deepseek_chat", "budget", "qwen35", "qwen3_14", "gemma3_12"]
        tidx = self.trans_profile_combo.currentIndex()
        os.environ["JAVSTORY_TRANSLATION_PROFILE"] = profiles[tidx] if tidx < len(profiles) else "default"

        os.environ["JAVSTORY_STORY_ANALYSIS_ENABLED"] = "1" if self.grok_switch.isChecked() else "0"
        os.environ["JAVSTORY_EMBEDDINGS_ENABLED"] = "1" if self.embed_switch.isChecked() else "0"
        os.environ["JAVSTORY_EMBEDDINGS_OLLAMA_MODEL"] = (self.embed_model_input.text().strip() or "nomic-embed-text")

        InfoBar.success("저장 완료", "옵션이 적용되었습니다.", parent=self,
                        duration=3000, position=InfoBarPosition.TOP)

    def _on_theme_changed(self, index: int):
        themes = [AppTheme.WIN11_NATIVE, AppTheme.PRETTY_WHITE, AppTheme.ELEGANT_DARK]
        if 0 <= index < len(themes):
            theme_manager.set_theme(themes[index])

    # ── 유틸 ────────────────────────────────────────────────
    def _browse_folder(self, target_input: LineEdit):
        d = QFileDialog.getExistingDirectory(self, "폴더 선택", target_input.text())
        if d:
            target_input.setText(d)

    def _input_with_button(self, inp: QWidget, btn: QWidget) -> QWidget:
        w = QWidget(self)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(inp, 1)
        lay.addWidget(btn)
        return w

    def _wrap_layout(self, layout: QHBoxLayout) -> QWidget:
        w = QWidget(self)
        w.setLayout(layout)
        return w
