"""Transcription(stable-ts) 다중 파일 큐 — 체크박스·DnD·중복 제거·행별 제거(X)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QFileDialog,
    QSizePolicy,
    QCheckBox,
)

from qfluentwidgets import (
    CaptionLabel,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    TransparentPushButton,
    FluentIcon as FIF,
)

from gui.transcription_queue_utils import (
    collect_videos_flat_folder,
    is_video_file,
    normalize_unique_paths,
)

_PATH_ROLE = Qt.ItemDataRole.UserRole + 10


class _QueueDropList(QListWidget):
    """리스트 영역에 떨어진 파일/폴더도 부모 큐와 동일 규칙으로 처리."""

    def __init__(self, owner: "TranscriptionQueueWidget", parent=None):
        super().__init__(parent)
        self._owner = owner
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._owner._handle_mime_urls(event.mimeData())
        event.acceptProposedAction()


class TranscriptionQueueWidget(QWidget):
    """드롭 영역 + 리스트. 체크된 경로만 순차 실행에 넘긴다."""

    pathsChanged = pyqtSignal()
    runRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.addWidget(StrongBodyLabel("Transcription 작업 큐 (stable-ts)", self))
        title_row.addStretch()
        title_row.addWidget(CaptionLabel("동영상만 · 폴더 드롭 시 직하위만", self))
        root.addLayout(title_row)

        btn_row = QHBoxLayout()
        self.btn_add_files = PushButton(FIF.DOCUMENT, "파일 추가", self)
        self.btn_add_files.clicked.connect(self._pick_files)
        self.btn_add_folder = PushButton(FIF.FOLDER, "폴더 추가(직하위)", self)
        self.btn_add_folder.setToolTip("선택한 폴더 **한 단계 아래** 동영상만 큐에 넣습니다 (하위 폴더는 스킵).")
        self.btn_add_folder.clicked.connect(self._pick_folder)
        self.btn_check_all = PushButton(FIF.ACCEPT, "전체 선택", self)
        self.btn_check_all.clicked.connect(lambda: self._set_all_checks(True))
        self.btn_uncheck_all = PushButton(FIF.CLOSE, "전체 해제", self)
        self.btn_uncheck_all.clicked.connect(lambda: self._set_all_checks(False))
        self.btn_clear = PushButton(FIF.DELETE, "목록 비우기", self)
        self.btn_clear.clicked.connect(self._clear_all)
        self.btn_run = PrimaryPushButton(FIF.PLAY, "선택 항목 순차 실행", self)
        self.btn_run.clicked.connect(self.runRequested.emit)

        btn_row.addWidget(self.btn_add_files)
        btn_row.addWidget(self.btn_add_folder)
        btn_row.addWidget(self.btn_check_all)
        btn_row.addWidget(self.btn_uncheck_all)
        btn_row.addWidget(self.btn_clear)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_run)
        root.addLayout(btn_row)

        self.list_w = _QueueDropList(self, self)
        self.list_w.setMinimumHeight(200)
        self.list_w.setAlternatingRowColors(True)
        self.list_w.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list_w.setStyleSheet("QListWidget { border-radius: 8px; }")
        root.addWidget(self.list_w, stretch=1)

        hint = CaptionLabel(
            "파일·폴더를 리스트로 끌어다 놓거나, 버튼으로 추가하세요. 같은 경로는 한 번만 표시됩니다.",
            self,
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._handle_mime_urls(event.mimeData())
        event.acceptProposedAction()

    def _handle_mime_urls(self, mime) -> None:
        collected: list[Path] = []
        for url in mime.urls():
            local = url.toLocalFile()
            if not local:
                continue
            p = Path(local)
            if p.is_dir():
                collected.extend(collect_videos_flat_folder(p))
            elif p.is_file() and is_video_file(p):
                collected.append(p)
        self._merge_paths(collected)

    def _pick_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "동영상 선택 (여러 개)",
            "",
            "Video (*.mp4 *.mkv *.avi *.mov *.webm *.m4v);;All (*.*)",
        )
        if not files:
            return
        self._merge_paths([Path(f) for f in files])

    def _pick_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "폴더 선택 (직하위 동영상만)")
        if not d:
            return
        self._merge_paths(collect_videos_flat_folder(Path(d)))

    def _merge_paths(self, new_paths: list[Path]) -> None:
        cur = self.all_paths()
        combined = normalize_unique_paths([str(p) for p in cur] + [str(p) for p in new_paths])
        self._set_paths_ordered(combined)

    def _set_paths_ordered(self, paths: list[Path]) -> None:
        self.list_w.clear()
        for p in paths:
            self._append_row(p)
        self.pathsChanged.emit()

    def _append_row(self, path: Path) -> None:
        p = path.resolve()
        item = QListWidgetItem()
        item.setData(_PATH_ROLE, str(p))

        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(8, 4, 8, 4)

        cb = QCheckBox(row)
        cb.setChecked(True)
        cb.stateChanged.connect(lambda _s: self.pathsChanged.emit())

        name = QLabel(p.name, row)
        name.setMinimumWidth(140)
        sub = QLabel(str(p), row)
        sub.setStyleSheet("color: rgba(255,255,255,0.45);")
        sub.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        rm = TransparentPushButton(FIF.CLOSE, "", row)
        rm.setFixedSize(28, 28)
        rm.setToolTip("큐에서 제거")
        rm.clicked.connect(lambda _=False, pp=p: self._remove_path(pp))

        lay.addWidget(cb)
        lay.addWidget(name)
        lay.addWidget(sub, stretch=1)
        lay.addWidget(rm)

        self.list_w.addItem(item)
        self.list_w.setItemWidget(item, row)
        item.setSizeHint(row.sizeHint())

    def _remove_path(self, path: Path) -> None:
        key = str(path.resolve()).lower()
        keep = [p for p in self.all_paths() if str(p.resolve()).lower() != key]
        self._set_paths_ordered(keep)

    def _clear_all(self) -> None:
        self.list_w.clear()
        self.pathsChanged.emit()

    def _set_all_checks(self, checked: bool) -> None:
        for i in range(self.list_w.count()):
            item = self.list_w.item(i)
            w = self.list_w.itemWidget(item)
            if not w:
                continue
            for cb in w.findChildren(QCheckBox):
                cb.setChecked(checked)
                break
        self.pathsChanged.emit()

    def all_paths(self) -> list[Path]:
        out: list[Path] = []
        for i in range(self.list_w.count()):
            item = self.list_w.item(i)
            s = item.data(_PATH_ROLE)
            if s:
                out.append(Path(str(s)))
        return out

    def checked_paths(self) -> list[Path]:
        out: list[Path] = []
        for i in range(self.list_w.count()):
            item = self.list_w.item(i)
            w = self.list_w.itemWidget(item)
            if not w:
                continue
            cbs = w.findChildren(QCheckBox)
            if not cbs or not cbs[0].isChecked():
                continue
            s = item.data(_PATH_ROLE)
            if s:
                out.append(Path(str(s)))
        return out

    def set_controls_enabled(self, enabled: bool) -> None:
        self.btn_add_files.setEnabled(enabled)
        self.btn_add_folder.setEnabled(enabled)
        self.btn_check_all.setEnabled(enabled)
        self.btn_uncheck_all.setEnabled(enabled)
        self.btn_clear.setEnabled(enabled)
        self.btn_run.setEnabled(enabled)
