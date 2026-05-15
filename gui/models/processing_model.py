"""전사/자막 처리 모델: STT 큐 + SubtitleWorker 통합."""

from __future__ import annotations

import os
from pathlib import Path

from javstory.utils.product_code import extract_product_code_from_path
from PySide6.QtCore import (
    QObject, Property, Signal, Slot,
    QAbstractListModel, QModelIndex, Qt,
)


class STTQueueModel(QAbstractListModel):
    FileNameRole = Qt.ItemDataRole.UserRole + 1
    PathRole = Qt.ItemDataRole.UserRole + 2
    CheckedRole = Qt.ItemDataRole.UserRole + 3
    StatusRole = Qt.ItemDataRole.UserRole + 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[dict] = []

    def roleNames(self):
        return {
            self.FileNameRole: b"fileName",
            self.PathRole: b"filePath",
            self.CheckedRole: b"checked",
            self.StatusRole: b"status",
        }

    def rowCount(self, parent=QModelIndex()):
        return len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self._items[index.row()]
        mapping = {
            self.FileNameRole: "fileName",
            self.PathRole: "filePath",
            self.CheckedRole: "checked",
            self.StatusRole: "status",
        }
        return item.get(mapping.get(role))

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid():
            return False
        if role == self.CheckedRole:
            self._items[index.row()]["checked"] = value
            self.dataChanged.emit(index, index)
            return True
        return False

    def flags(self, index):
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable

    def add_files(self, paths: list[str]):
        existing = {it["filePath"] for it in self._items}
        new_items = []
        for p in paths:
            if p not in existing:
                new_items.append({
                    "fileName": os.path.basename(p),
                    "filePath": p,
                    "checked": True,
                    "status": "pending",
                })
        if new_items:
            start = len(self._items)
            self.beginInsertRows(QModelIndex(), start, start + len(new_items) - 1)
            self._items.extend(new_items)
            self.endInsertRows()

    def remove(self, row: int):
        if 0 <= row < len(self._items):
            self.beginRemoveRows(QModelIndex(), row, row)
            self._items.pop(row)
            self.endRemoveRows()

    def checked_paths(self) -> list[str]:
        return [it["filePath"] for it in self._items if it.get("checked")]

    def set_status(self, path: str, status: str):
        for i, it in enumerate(self._items):
            if it["filePath"] == path:
                it["status"] = status
                idx = self.index(i, 0)
                self.dataChanged.emit(idx, idx)
                break


class ProcessingModel(QObject):
    _instance = None

    @staticmethod
    def instance() -> ProcessingModel | None:
        return ProcessingModel._instance

    currentFileChanged = Signal()
    progressPercentChanged = Signal()
    progressMessageChanged = Signal()
    isRunningChanged = Signal()
    logMessage = Signal(str)
    toastMessage = Signal(str, str)
    sttFinished = Signal(str, bool, str)  # srt_path, success, message

    def __init__(self, parent=None):
        super().__init__(parent)
        ProcessingModel._instance = self
        self._current_file = ""
        self._progress_percent = 0
        self._progress_message = ""
        self._is_running = False
        self._queue = STTQueueModel(self)

        self._stt_worker = None
        self._subtitle_worker = None
        self._queue_mode = False
        self._queue_type = ""  # "stt" or "subtitle"
        self._queue_paths: list[str] = []
        self._queue_idx = 0

    # ── Properties ────────────────────────────────────

    @Property(QObject, constant=True)
    def queue(self):
        return self._queue

    @Property(str, notify=currentFileChanged)
    def currentFile(self):
        return self._current_file

    @Property(int, notify=progressPercentChanged)
    def progressPercent(self):
        return self._progress_percent

    @Property(str, notify=progressMessageChanged)
    def progressMessage(self):
        return self._progress_message

    @Property(bool, notify=isRunningChanged)
    def isRunning(self):
        return self._is_running

    # ── Slots ─────────────────────────────────────────

    @Slot(str)
    def addFile(self, path: str):
        self._queue.add_files([path])

    @Slot(list)
    def addFiles(self, paths):
        self._queue.add_files([str(p) for p in paths])

    @Slot(int)
    def removeQueueItem(self, row: int):
        if self._is_running:
            self.logMessage.emit("[경고] 작업 중에는 삭제할 수 없습니다.")
            return
        self._queue.remove(row)

    @Slot(str)
    def startSingleStt(self, video_path: str):
        """단일 파일 STT."""
        if self._is_running:
            self.logMessage.emit("[경고] 이미 진행 중입니다.")
            return
        self._set_running(True)
        self._current_file = os.path.basename(video_path)
        self.currentFileChanged.emit()
        self._run_stt(video_path)

    @Slot()
    def startQueueStt(self):
        """큐의 체크된 파일 순차 STT."""
        paths = self._queue.checked_paths()
        if not paths:
            self.logMessage.emit("[큐] 체크된 파일이 없습니다.")
            return
        if self._is_running:
            self.logMessage.emit("[경고] 이미 진행 중입니다.")
            return
        self._queue_mode = True
        self._queue_type = "stt"
        self._queue_paths = paths
        self._queue_idx = 0
        self._set_running(True)
        self.logMessage.emit(f"[큐] STT {len(paths)}건 순차 실행 시작")
        self._start_next_queue()

    @Slot()
    def stop(self):
        if self._stt_worker:
            self._stt_worker.stop()
        if self._subtitle_worker:
            self._subtitle_worker.stop()
        self.logMessage.emit("[시스템] 중단 요청됨.")

    @Slot()
    def startQueueSubtitle(self):
        """큐의 체크된 파일 순차 자막 파이프라인(JA교정+KO번역)."""
        paths = self._queue.checked_paths()
        if not paths:
            self.logMessage.emit("[큐] 체크된 파일이 없습니다.")
            return
        if self._is_running:
            self.logMessage.emit("[경고] 이미 진행 중입니다.")
            return
        self._queue_mode = True
        self._queue_type = "subtitle"
        self._queue_paths = paths
        self._queue_idx = 0
        self._set_running(True)
        self.logMessage.emit(f"[큐] 자막 파이프라인 {len(paths)}건 순차 실행 시작")
        self._start_next_queue()

    @Slot(str, str)
    def startSubtitle(self, product_code: str, video_path: str):
        """단일 파일 자막 파이프라인 (JA 교정 + KO 번역)."""
        if self._is_running:
            self.logMessage.emit("[경고] 이미 진행 중입니다.")
            return
        self._queue_mode = False
        self._queue_type = "subtitle"
        self._set_running(True)
        self.logMessage.emit(f"[자막] {os.path.basename(video_path)}: JA 교정 + KO 번역 시작...")
        self._run_subtitle(product_code, video_path)

    @Slot(int, bool)
    def toggleCheck(self, row: int, checked: bool):
        idx = self._queue.index(row, 0)
        self._queue.setData(idx, checked, STTQueueModel.CheckedRole)

    # ── 내부 ─────────────────────────────────────────

    def _set_running(self, v: bool):
        if v != self._is_running:
            self._is_running = v
            self.isRunningChanged.emit()

    def _run_stt(self, path: str):
        from gui.workers.stt_worker import STTWorker
        self._stt_worker = STTWorker(path, parent=self)
        self._stt_worker.progress.connect(self._on_stt_progress)
        self._stt_worker.finished.connect(self._on_stt_finished)
        self._stt_worker.start()

    def _on_stt_progress(self, msg: str, pct: int):
        if pct >= 0:
            self._progress_percent = pct
            self.progressPercentChanged.emit()
        self._progress_message = msg
        self.progressMessageChanged.emit()
        self.logMessage.emit(f"  > {msg}")

    def _on_stt_finished(self, srt_path: str, success: bool, message: str):
        self.sttFinished.emit(srt_path, success, message)
        self.logMessage.emit(f"[STT] {'성공' if success else '실패'}: {message}")

        # [추가] 라이브러리 상태 갱신
        if success:
            try:
                from javstory.utils.product_code import extract_product_code_from_path
                pc = extract_product_code_from_path(srt_path)
                if pc:
                    from gui.models.library_model import LibraryModel
                    lib = LibraryModel.instance()
                    if lib:
                        lib.refreshProduct(pc)
            except Exception as e:
                print(f"[ProcessingModel] STT 완료 후 갱신 실패: {e}")

        if self._queue_mode:
            if not success and "중단" in message:
                self._finish_queue(aborted=True)
                return
            path = self._queue_paths[self._queue_idx] if self._queue_idx < len(self._queue_paths) else ""
            self._queue.set_status(path, "done" if success else "error")
            self._queue_idx += 1
            n = max(1, len(self._queue_paths))
            self._progress_percent = int(100 * min(self._queue_idx, n) / n)
            self.progressPercentChanged.emit()
            self._start_next_queue()
        else:
            self._set_running(False)
            self._progress_percent = 100 if success else 0
            self.progressPercentChanged.emit()

    def _start_next_queue(self):
        if self._queue_idx >= len(self._queue_paths):
            self._finish_queue()
            return
        path = self._queue_paths[self._queue_idx]
        n = len(self._queue_paths)
        i = self._queue_idx + 1
        self._current_file = f"[{i}/{n}] {os.path.basename(path)}"
        self.currentFileChanged.emit()
        self._queue.set_status(path, "running")
        
        if self._queue_type == "stt":
            self._run_stt(path)
        elif self._queue_type == "subtitle":
            self._run_subtitle("", path)
        else:
            self.logMessage.emit(f"[오류] 알 수 없는 큐 타입: {self._queue_type}")
            self._finish_queue()

    def _finish_queue(self, aborted=False):
        self._queue_mode = False
        self._queue_paths = []
        self._queue_idx = 0
        self._set_running(False)
        self.logMessage.emit("[큐] " + ("중단됨." if aborted else "전체 완료."))

    def _run_subtitle(self, product_code: str, video_path: str):
        from gui.workers.subtitle_worker import SubtitleWorker

        # Grok 캐시·DB 조회는 품번(예: ABW-358)이어야 함 — 전체 파일 stem을 쓰면
        # `-__ACTRESS_____ABW-358__HD___grok.json` 같은 비정상 캐시 파일이 생김.
        pc = extract_product_code_from_path(video_path)
        if not pc:
            pc = (product_code or "").strip()
        if not pc:
            pc = os.path.splitext(os.path.basename(video_path))[0]
        pc = pc.strip().upper()

        self._subtitle_worker = SubtitleWorker(
            product_code=pc,
            video_path=video_path,
            parent=self,
        )
        self._subtitle_worker.progress.connect(self._on_sub_progress)
        self._subtitle_worker.finished.connect(self._on_sub_finished)
        self._subtitle_worker.start()

    def _on_sub_progress(self, msg: str, pct: int):
        if pct >= 0:
            self._progress_percent = pct
            self.progressPercentChanged.emit()
        self._progress_message = msg
        self.progressMessageChanged.emit()
        self.logMessage.emit(f"  [자막] {msg}")

    def _on_sub_finished(self, success: bool, message: str):
        self.logMessage.emit(f"[자막] {'성공' if success else '실패'}: {message}")
        
        # [추가] 라이브러리 상태 갱신
        if success:
            try:
                fn = self._current_file
                # "[1/5] MIUM-123" 형태일 수 있으므로 파싱
                import re
                m = re.search(r"\]\s+(.+)$", fn)
                if m: fn = m.group(1).strip()
                
                from javstory.utils.product_code import extract_product_code_from_path
                pc = extract_product_code_from_path(fn)
                if pc:
                    from gui.models.library_model import LibraryModel
                    lib = LibraryModel.instance()
                    if lib:
                        lib.refreshProduct(pc)
            except Exception as e:
                print(f"[ProcessingModel] 자막 완료 후 갱신 실패: {e}")

        if not self._queue_mode:
            self._set_running(False)
            self._progress_percent = 100 if success else 0
            self.progressPercentChanged.emit()
            self.toastMessage.emit(message, "success" if success else "error")
        else:
            if not success and "중단" in message:
                self._finish_queue(aborted=True)
                return
            path = self._queue_paths[self._queue_idx] if self._queue_idx < len(self._queue_paths) else ""
            self._queue.set_status(path, "done" if success else "error")
            self._queue_idx += 1
            n = max(1, len(self._queue_paths))
            self._progress_percent = int(100 * min(self._queue_idx, n) / n)
            self.progressPercentChanged.emit()
            self._start_next_queue()
