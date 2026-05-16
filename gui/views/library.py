"""
Deprecated — PyQt6 Fluent 라이브러리 뷰.

운영 UI: gui/qml/views/LibraryView.qml, LibraryDetail.qml
→ gui/views/README.md
"""

from __future__ import annotations

import re
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QLabel,
    QLineEdit,
)
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


_RE_MONTH = re.compile(r"^\s*(\d{4})[-/.](\d{2})")


def _release_month_key(release_date: str | None) -> str:
    s = (release_date or "").strip()
    if not s:
        return "unknown"
    m = _RE_MONTH.match(s)
    if not m:
        return "unknown"
    y = m.group(1)
    mm = m.group(2)
    try:
        mi = int(mm)
        if mi < 1 or mi > 12:
            return "unknown"
    except Exception:
        return "unknown"
    return f"{y}-{mm}"


class LibraryView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LibraryView")
        self._cards: dict[str, LibraryCard] = {}
        self._summaries: list[LibraryWorkSummary] = []
        self._month_filter: str = ""  # ""=전체, "YYYY-MM", "unknown"(미상)
        self._month_input: str = ""
        self._month_error: str = ""
        self._unknown_only: bool = False

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

        # ── 출시 연월 필터: 입력 + 월 선택 ─────────────────
        self.month_input = QLineEdit(self)
        self.month_input.setPlaceholderText("YYYY-MM")
        self.month_input.setFixedWidth(110)
        self.month_input.textChanged.connect(self._on_month_input_changed)
        self.month_input.returnPressed.connect(self._apply_month_input)
        search_row.addWidget(self.month_input)

        self.btn_month_apply = PushButton("적용", self)
        self.btn_month_apply.clicked.connect(self._apply_month_input)
        search_row.addWidget(self.btn_month_apply)

        self.btn_month_clear = PushButton("×", self)
        self.btn_month_clear.setFixedWidth(36)
        self.btn_month_clear.clicked.connect(self._clear_month_filter_only)
        search_row.addWidget(self.btn_month_clear)

        self.btn_unknown_only = PushButton("미상만", self)
        self.btn_unknown_only.setCheckable(True)
        self.btn_unknown_only.toggled.connect(self._on_unknown_only_toggled)
        search_row.addWidget(self.btn_unknown_only)

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

    def _available_years(self) -> list[int]:
        years: set[int] = set()
        for s in self._summaries:
            k = _release_month_key(s.release_date)
            if k and k != "unknown":
                try:
                    years.add(int(k[:4]))
                except Exception:
                    pass
        out = sorted(list(years), reverse=True)
        return out

    def _set_month_error(self, msg: str) -> None:
        self._month_error = msg or ""
        # 간단 강조: 배경색 변경(테마 충돌 피하려고 최소)
        if self._month_error:
            self.month_input.setStyleSheet("QLineEdit { border: 1px solid #ff4d4f; }")
        else:
            self.month_input.setStyleSheet("")

    def _on_month_input_changed(self, text: str) -> None:
        self._month_input = (text or "")
        # 입력 중에는 에러를 즉시 없애지 않음(엔터/적용에서만 검증)

    def _apply_month_input(self) -> None:
        raw = (self._month_input or "").strip()
        if not raw:
            self._set_month_error("")
            self._month_filter = ""
            self._rebuild_cards()
            return
        key = _release_month_key(raw)
        if key == "unknown":
            self._set_month_error("형식 오류: YYYY-MM")
            return
        self._set_month_error("")
        self._month_filter = key
        self._unknown_only = False
        try:
            self.btn_unknown_only.setChecked(False)
        except Exception:
            pass
        self._rebuild_cards()

    def _clear_month_filter_only(self) -> None:
        self._set_month_error("")
        self._month_filter = ""
        self._month_input = ""
        self.month_input.setText("")
        self._unknown_only = False
        try:
            self.btn_unknown_only.setChecked(False)
        except Exception:
            pass
        self._rebuild_cards()

    def _on_unknown_only_toggled(self, on: bool) -> None:
        self._unknown_only = bool(on)
        if self._unknown_only:
            self._set_month_error("")
            self._month_filter = "unknown"
        else:
            # 토글을 끄면 기존 month_filter는 유지(unknown이면 전체로)
            if self._month_filter == "unknown":
                self._month_filter = ""
        self._rebuild_cards()

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
        mf = (self._month_filter or "").strip()
        visible_any = False
        for s in self._sorted_summaries():
            if mf:
                if _release_month_key(s.release_date) != mf:
                    continue
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
        self._clear_month_filter_only()
        self._rebuild_cards()

    def _on_card_clicked(self, sku: str) -> None:
        s = next((x for x in self._summaries if x.product_code == sku), None)
        if not s:
            return
        dlg = LibraryDetailDialog(s, self.window())
        dlg.exec()
