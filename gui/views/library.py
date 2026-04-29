"""라이브러리 뷰 — Harvest 메타 카드 + canonical 연동 상세."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel
from qfluentwidgets import (
    TitleLabel,
    SubtitleLabel,
    SearchLineEdit,
    PushButton,
    PrimaryPushButton,
    FluentIcon as FIF,
    setFont,
    FlowLayout,
    InfoBar,
    InfoBarPosition,
    ComboBox,
    ToolButton,
)

from javstory.harvest.database import get_db_session
from gui.library_data import LibraryWorkSummary, load_library_summaries_from_session
from gui.components.library_card import LibraryCard
from gui.components.library_detail_dialog import LibraryDetailDialog


class LibraryView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LibraryView")
        self._cards: dict[str, LibraryCard] = {}
        self._summaries: list[LibraryWorkSummary] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(18)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title = TitleLabel("스토리 라이브러리", self)
        desc = SubtitleLabel("Harvest DB 메타 + 로컬 canonical(library_state.json)", self)
        setFont(title, 28, weight=700)
        title_col.addWidget(title)
        title_col.addWidget(desc)
        header.addLayout(title_col)
        header.addStretch()
        self.btn_refresh = PrimaryPushButton(FIF.SYNC, "새로고침", self)
        self.btn_refresh.clicked.connect(self.reload)
        header.addWidget(self.btn_refresh)
        layout.addLayout(header)

        search_row = QHBoxLayout()
        self.search = SearchLineEdit(self)
        self.search.setPlaceholderText("품번·제목으로 필터…")
        self.search.setFixedWidth(420)
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(180)
        self._filter_timer.timeout.connect(self._rebuild_cards)
        self.search.textChanged.connect(lambda: self._filter_timer.start())
        search_row.addWidget(self.search)
        self.btn_clear = PushButton("필터 지우기", self)
        self.btn_clear.clicked.connect(self._clear_filter)
        search_row.addWidget(self.btn_clear)

        search_row.addStretch()

        self.sort_combo = ComboBox(self)
        self.sort_combo.addItems(["품번순", "날짜순 (최신)", "날짜순 (오래된)", "씬 수 (많은)"])
        self.sort_combo.setFixedWidth(160)
        self.sort_combo.currentIndexChanged.connect(lambda: self._rebuild_cards())
        search_row.addWidget(self.sort_combo)

        layout.addLayout(search_row)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.container = QWidget()
        self.container.setObjectName("LibraryContainer")
        self.container.setStyleSheet("#LibraryContainer { background: transparent; }")
        self.flow = FlowLayout(self.container)
        self.flow.setContentsMargins(0, 0, 0, 0)
        self.flow.setSpacing(16)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        self.empty_label = QLabel("수집된 작품이 없습니다. 「수집」에서 크롤링하세요.", self)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: rgba(255,255,255,0.45); padding: 40px;")
        layout.addWidget(self.empty_label)
        self.empty_label.hide()

        QTimer.singleShot(100, self.reload)

    def reload(self) -> None:
        session = get_db_session()
        try:
            self._summaries = load_library_summaries_from_session(session)
        except Exception as e:
            self._summaries = []
            InfoBar.warning(
                "라이브러리",
                f"DB 로드 실패: {e}",
                duration=5000,
                position=InfoBarPosition.BOTTOM_RIGHT,
                parent=self.window(),
            )
        finally:
            session.close()

        self._rebuild_cards()
        if self._summaries:
            win = self.window()
            InfoBar.success(
                "라이브러리",
                f"{len(self._summaries)}건 로드",
                duration=1800,
                position=InfoBarPosition.BOTTOM_RIGHT,
                parent=win,
            )

    def _sorted_summaries(self) -> list[LibraryWorkSummary]:
        items = list(self._summaries)
        idx = self.sort_combo.currentIndex() if hasattr(self, 'sort_combo') else 0
        if idx == 0:
            items.sort(key=lambda s: s.product_code)
        elif idx == 1:
            items.sort(key=lambda s: s.release_date or "", reverse=True)
        elif idx == 2:
            items.sort(key=lambda s: s.release_date or "")
        elif idx == 3:
            items.sort(key=lambda s: s.scene_count, reverse=True)
        return items

    def _rebuild_cards(self) -> None:
        for c in list(self._cards.values()):
            self.flow.removeWidget(c)
            c.deleteLater()
        self._cards.clear()

        q = (self.search.text() or "").strip().lower()
        visible_any = False
        for s in self._sorted_summaries():
            if q:
                blob = f"{s.product_code} {s.title_ko} {s.actors_ko}".lower()
                if q not in blob:
                    continue
            card = LibraryCard(self.container)
            card.set_summary(
                product_code=s.product_code,
                title_ko=s.title_ko,
                actors_ko=s.actors_ko,
                scene_count=s.scene_count,
                has_canonical=s.has_canonical,
                cover_path=s.cover_effective_path or s.cover_local_path,
            )
            card.clicked.connect(self._on_card_clicked)
            self._cards[s.product_code] = card
            self.flow.addWidget(card)
            visible_any = True

        self.empty_label.setVisible(not visible_any)
        self.scroll.setVisible(visible_any)

    def _clear_filter(self) -> None:
        self.search.clear()
        self._rebuild_cards()

    def _on_card_clicked(self, sku: str) -> None:
        s = next((x for x in self._summaries if x.product_code == sku), None)
        if not s:
            return
        dlg = LibraryDetailDialog(s, self.window())
        dlg.exec()
