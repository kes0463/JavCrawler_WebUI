"""DB에 저장된 작품 폴더 연결의 존재 여부 감시 — 이동·삭제 시 알림 및 후보 경로 안내."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Property, QRunnable, QThreadPool, QTimer, Signal, Slot

from javstory.folder_watch.candidates import search_folder_candidates
from javstory.folder_watch.paused import (
    is_monitoring_paused,
    load_paused_product_codes,
    pause_monitoring,
    resume_monitoring,
)

try:
    from PySide6.QtCore import QFileSystemWatcher
except ImportError:
    QFileSystemWatcher = None  # type: ignore[misc, assignment]


def _disabled() -> bool:
    v = (os.environ.get("JAVSTORY_DISABLE_FOLDER_WATCH") or "").strip().lower()
    return v in {"1", "true", "yes", "on"}


class _FolderCandidateSearchRunnable(QRunnable):
    """Heavy filesystem scan must not run on the Qt GUI thread."""

    def __init__(self, svc: "FolderMoveWatchService", pc: str, fp: str) -> None:
        super().__init__()
        self._svc = svc
        self._pc = pc
        self._fp = fp

    def run(self) -> None:
        cands = search_folder_candidates(self._pc, old_path=self._fp)
        self._svc._folder_search_done.emit(self._pc, self._fp, cands)


class FolderMoveWatchService(QObject):
    """
    - 주기적으로 DB의 folder_path 존재 여부 확인
    - QFileSystemWatcher로 상위 디렉터리 변경 시 즉시 재검사 (Windows 한계 내에서만 경로 등록)
    - 경로가 사라지면 LibraryModel.folderBindingNeedsReview만 발생 — 자동 토스트·refresh 없음 (QML 확인)
    - 품번별 감시 일시중지: 전체 디스크 후보 검색·알림 재발송 생략 (DB folder_path 유지)
    """

    _folder_search_done = Signal(str, str, list)
    pausedRevisionChanged = Signal()

    def __init__(self, library_model: QObject, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._library = library_model
        self._paths: dict[str, str] = {}
        self._broken_notified: set[str] = set()
        self._paused_revision: int = 0
        self._folder_search_done.connect(self._deliver_folder_binding_review)
        self._search_pool = QThreadPool(self)
        self._search_pool.setMaxThreadCount(2)
        self._watcher = QFileSystemWatcher(self) if QFileSystemWatcher else None
        if self._watcher:
            self._watcher.directoryChanged.connect(self._schedule_verify)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(450)
        self._debounce.timeout.connect(self.verify_bindings)

        self._poll = QTimer(self)
        self._poll.setInterval(60_000)
        self._poll.timeout.connect(self.verify_bindings)

        self._refresh_db_debounce = QTimer(self)
        self._refresh_db_debounce.setSingleShot(True)
        self._refresh_db_debounce.setInterval(2500)
        self._refresh_db_debounce.timeout.connect(self._refresh_paths_from_db_worker)
        self._refresh_db_in_flight = False

    def _bump_paused_revision(self) -> None:
        self._paused_revision += 1
        self.pausedRevisionChanged.emit()

    @Property(int, notify=pausedRevisionChanged)
    def pausedRevision(self) -> int:
        return self._paused_revision

    @Slot(str, result=bool)
    def isMonitoringPaused(self, product_code: str) -> bool:
        return is_monitoring_paused(product_code)

    @Slot(str)
    def pauseMonitoringForProduct(self, product_code: str) -> None:
        pc = (product_code or "").strip().upper()
        if not pc:
            return
        pause_monitoring(pc)
        self._broken_notified.discard(pc)
        self._bump_paused_revision()

    @Slot(str)
    def resumeMonitoringForProduct(self, product_code: str) -> None:
        pc = (product_code or "").strip().upper()
        if not pc:
            return
        resume_monitoring(pc)
        self._broken_notified.discard(pc)
        self._bump_paused_revision()
        QTimer.singleShot(0, self.verify_bindings)

    @Slot(str, str, list)
    def _deliver_folder_binding_review(self, pc: str, fp: str, cands: list) -> None:
        try:
            if is_monitoring_paused(pc):
                return
            rel = getattr(self._library, "folderBindingNeedsReview", None)
            if rel is not None:
                rel.emit(pc, fp, cands)
        except Exception as e:
            _ = e

    @Slot()
    def refresh_paths_from_db(self) -> None:
        """DB folder_path 목록 갱신 — debounce 후 백그라운드에서 조회(메인 스레드 블록 방지)."""
        if _disabled():
            return
        self._refresh_db_debounce.start()

    def _refresh_paths_from_db_worker(self) -> None:
        if _disabled():
            return
        if self._refresh_db_in_flight:
            self._refresh_db_debounce.start(800)
            return
        self._refresh_db_in_flight = True

        def _job():
            paths: dict[str, str] = {}
            try:
                from javstory.harvest.database import JAVMetadata, get_db_session

                session = get_db_session()
                try:
                    rows = session.query(JAVMetadata.product_code, JAVMetadata.folder_path).all()
                    for pc, fp in rows:
                        if not fp or not str(fp).strip():
                            continue
                        paths[(pc or "").strip().upper()] = str(Path(fp).expanduser())
                finally:
                    session.close()
            except Exception:
                paths = {}

            def _apply():
                self._refresh_db_in_flight = False
                self._paths = paths
                self._rebuild_watcher_paths()
                if not self._poll.isActive():
                    self._poll.start()

            QTimer.singleShot(0, self, _apply)

        threading.Thread(target=_job, daemon=True, name="folder-watch-refresh").start()

    def _rebuild_watcher_paths(self) -> None:
        if not self._watcher:
            return
        try:
            old = self._watcher.directories()
            if old:
                self._watcher.removePaths(old)
        except Exception:
            pass

        parents: set[str] = set()
        for fp in self._paths.values():
            try:
                p = Path(fp)
                if p.is_dir():
                    parents.add(str(p.resolve()))
                par = p.parent
                if par.is_dir():
                    parents.add(str(par.resolve()))
            except OSError:
                continue

        max_watch = 96
        for i, d in enumerate(sorted(parents)):
            if i >= max_watch:
                break
            try:
                self._watcher.addPath(d)
            except Exception:
                pass

    def _schedule_verify(self) -> None:
        self._debounce.start()

    @Slot()
    def verify_bindings(self) -> None:
        if _disabled():
            return
        paused = load_paused_product_codes()
        for pc, fp in list(self._paths.items()):
            if pc in paused:
                continue
            try:
                ok = Path(fp).is_dir()
            except OSError:
                ok = False
            if ok:
                if pc in self._broken_notified:
                    self._broken_notified.discard(pc)
                continue

            if pc in self._broken_notified:
                continue
            self._broken_notified.add(pc)

            self._search_pool.start(_FolderCandidateSearchRunnable(self, pc, fp))
