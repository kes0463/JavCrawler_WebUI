"""라이브러리 그리드 카드 — Harvest 메타 + canonical 배지."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout
from qfluentwidgets import CardWidget, StrongBodyLabel, CaptionLabel, setFont


class LibraryCard(CardWidget):
    """표지·제목·품번·배우 한 줄·씬/스틸 배지."""

    clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sku = ""
        self._title_text = ""
        self.setFixedSize(260, 280)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 12)
        root.setSpacing(6)

        self.cover = QLabel(self)
        self.cover.setFixedHeight(150)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setStyleSheet(
            "QLabel { background-color: rgba(0,0,0,0.35); border-radius: 8px; color: rgba(255,255,255,0.5); }"
        )
        self.cover.setText("NO COVER")
        root.addWidget(self.cover)

        self.sku_label = StrongBodyLabel("", self)
        setFont(self.sku_label, 13, weight=700)
        root.addWidget(self.sku_label)

        self.title_label = CaptionLabel("", self)
        self.title_label.setWordWrap(True)
        root.addWidget(self.title_label)

        self.sub_label = CaptionLabel("", self)
        self.sub_label.setWordWrap(True)
        self.sub_label.setStyleSheet("color: rgba(255,255,255,0.55);")
        root.addWidget(self.sub_label)

        badge_row = QHBoxLayout()
        self.badge_scenes = CaptionLabel("", self)
        self.badge_canon = CaptionLabel("", self)
        badge_row.addWidget(self.badge_scenes)
        badge_row.addStretch()
        badge_row.addWidget(self.badge_canon)
        root.addLayout(badge_row)

    def set_summary(self, *, product_code: str, title_ko: str, actors_ko: str, scene_count: int, has_canonical: bool, cover_path: str | None) -> None:
        self.sku = product_code
        self._title_text = title_ko or ""
        self.sku_label.setText(product_code)
        self.title_label.setText(title_ko or "(제목 없음)")
        act = (actors_ko or "").strip()
        self.sub_label.setText(act[:80] + ("…" if len(act) > 80 else ""))

        self.badge_scenes.setText(f"씬 {scene_count}")
        if has_canonical:
            self.badge_canon.setText("canonical ✓")
            self.badge_canon.setStyleSheet("color: #4ECDC4;")
        else:
            self.badge_canon.setText("canonical —")
            self.badge_canon.setStyleSheet("color: rgba(255,255,255,0.35);")

        self._load_cover(cover_path)

    def _load_cover(self, path: str | None) -> None:
        if path and path.strip():
            p = path.strip()
            pm = QPixmap(p)
            if not pm.isNull():
                self.cover.setPixmap(pm.scaled(self.cover.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
                self.cover.setText("")
                return
        self.cover.clear()
        self.cover.setText("NO COVER")

    def filter_text(self) -> str:
        return f"{self.sku} {self._title_text}".lower()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.sku)
        super().mouseReleaseEvent(event)
