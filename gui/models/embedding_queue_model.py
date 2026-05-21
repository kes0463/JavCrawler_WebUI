"""Ollama embedding generation queue for the dashboard."""

from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import (
    QAbstractListModel,
    QCoreApplication,
    QModelIndex,
    QObject,
    Property,
    QThread,
    QTimer,
    Qt,
    Signal,
    Slot,
)

from gui.utils.queue_persistence import clear_queue_state, load_queue_state, save_queue_state

PERSIST_NAME = "embedding"


def _env_or_dotenv_value(key: str) -> str:
    raw = (os.environ.get(key, "") or "").strip()
    if raw:
        return raw
    try:
        from dotenv import dotenv_values
        from javstory.config.app_config import ENV_FILE_PATH

        value = dotenv_values(ENV_FILE_PATH).get(key)
        return str(value or "").strip()
    except Exception:
        return ""


@dataclass
class _Job:
    job_id: str
    product_code: str
    title: str
    model: str
    force: bool
    status: str  # queued|running|done|error
    progress: int
    message: str
    created_at_ms: int


class EmbeddingQueueListModel(QAbstractListModel):
    JobIdRole = Qt.ItemDataRole.UserRole + 1
    ProductCodeRole = Qt.ItemDataRole.UserRole + 2
    VideoNameRole = Qt.ItemDataRole.UserRole + 3
    StatusRole = Qt.ItemDataRole.UserRole + 4
    ProgressRole = Qt.ItemDataRole.UserRole + 5
    MessageRole = Qt.ItemDataRole.UserRole + 6
    ModelRole = Qt.ItemDataRole.UserRole + 7
    ForceRole = Qt.ItemDataRole.UserRole + 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[_Job] = []

    def roleNames(self):
        return {
            self.JobIdRole: b"jobId",
            self.ProductCodeRole: b"productCode",
            self.VideoNameRole: b"videoName",
            self.StatusRole: b"status",
            self.ProgressRole: b"progress",
            self.MessageRole: b"message",
            self.ModelRole: b"modelName",
            self.ForceRole: b"force",
        }

    def rowCount(self, parent=QModelIndex()):
        return len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        it = self._items[index.row()]
        if role == self.JobIdRole:
            return it.job_id
        if role == self.ProductCodeRole:
            return it.product_code
        if role == self.VideoNameRole:
            prefix = "강제 재생성 · " if it.force else ""
            return f"{prefix}{it.title or it.model}"
        if role == self.StatusRole:
            return it.status
        if role == self.ProgressRole:
            return int(it.progress)
        if role == self.MessageRole:
            return it.message
        if role == self.ModelRole:
            return it.model
        if role == self.ForceRole:
            return bool(it.force)
        return None

    def _append(self, job: _Job) -> None:
        start = len(self._items)
        self.beginInsertRows(QModelIndex(), start, start)
        self._items.append(job)
        self.endInsertRows()

    def _update_by_id(self, job_id: str, **kwargs) -> None:
        for i, it in enumerate(self._items):
            if it.job_id == job_id:
                for k, v in kwargs.items():
                    if hasattr(it, k):
                        setattr(it, k, v)
                idx = self.index(i, 0)
                self.dataChanged.emit(
                    idx,
                    idx,
                    [
                        self.StatusRole,
                        self.ProgressRole,
                        self.MessageRole,
                        self.VideoNameRole,
                    ],
                )
                return

    def _find_latest_for_product(self, product_code: str, model: str = "") -> Optional[_Job]:
        pc = (product_code or "").strip().upper()
        m = (model or "").strip()
        for it in reversed(self._items):
            if (it.product_code or "").strip().upper() != pc:
                continue
            if m and (it.model or "").strip() != m:
                continue
            return it
        return None

    def _all(self) -> list[_Job]:
        return list(self._items)

    def _remove_by_id(self, job_id: str) -> bool:
        for i, it in enumerate(self._items):
            if it.job_id == job_id:
                self.beginRemoveRows(QModelIndex(), i, i)
                self._items.pop(i)
                self.endRemoveRows()
                return True
        return False

    def _clear_finished(self) -> int:
        rows = [i for i, it in enumerate(self._items) if it.status in {"done", "error"}]
        for i in sorted(rows, reverse=True):
            self.beginRemoveRows(QModelIndex(), i, i)
            self._items.pop(i)
            self.endRemoveRows()
        return len(rows)

    def _replace_all(self, jobs: List[_Job]) -> None:
        self.beginResetModel()
        self._items = list(jobs)
        self.endResetModel()


class EmbeddingWorker(QThread):
    progressUpdated = Signal(int, str)
    resultReady = Signal(bool, str)

    def __init__(self, product_code: str, model: str, force: bool, parent=None):
        super().__init__(parent)
        self.product_code = (product_code or "").strip().upper()
        self.model = (model or "").strip() or "nomic-embed-text"
        self.force = bool(force)

    def run(self) -> None:
        try:
            import asyncio

            from javstory.library.embeddings.pipeline import build_and_store_embeddings_for_product

            def _log(message: str) -> None:
                msg = str(message or "").strip()
                if msg:
                    self.progressUpdated.emit(45, msg)

            self.progressUpdated.emit(5, "문서 구성 중")
            path = asyncio.run(
                build_and_store_embeddings_for_product(
                    self.product_code,
                    model=self.model,
                    include_subtitles=True,
                    force=self.force,
                    logger_func=_log,
                )
            )
            if path:
                name = Path(path).name
                self.progressUpdated.emit(100, "저장 완료")
                self.resultReady.emit(True, f"완료: {name}")
            else:
                self.resultReady.emit(False, "문서 없음 또는 생성 스킵")
        except Exception as e:
            self.resultReady.emit(False, str(e))


class EmbeddingQueueController(QObject):
    _instance = None

    @staticmethod
    def instance() -> "EmbeddingQueueController | None":
        return EmbeddingQueueController._instance

    queueCountChanged = Signal()
    runningCountChanged = Signal()
    pendingCountChanged = Signal()
    toastMessage = Signal(str, str)
    logMessage = Signal(str)
    queueChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        EmbeddingQueueController._instance = self
        self._model = EmbeddingQueueListModel(self)
        self._running: Dict[str, EmbeddingWorker] = {}
        raw = _env_or_dotenv_value("JAVSTORY_EMBEDDING_QUEUE_CONCURRENCY")
        try:
            n = int(raw) if raw else 1
        except ValueError:
            n = 1
        self._max_parallel = max(1, n)
        self._persist_timer = QTimer(self)
        self._persist_timer.setSingleShot(True)
        self._persist_timer.setInterval(350)
        self._persist_timer.timeout.connect(self._flush_persist)
        QTimer.singleShot(0, self, self._load_persisted)

    @Property(QObject, constant=True)
    def queue(self):
        return self._model

    @Property(int, notify=queueCountChanged)
    def queueCount(self) -> int:
        return self._model.rowCount()

    @Property(int, notify=runningCountChanged)
    def runningCount(self) -> int:
        return len(self._running)

    @Property(int, notify=pendingCountChanged)
    def pendingCount(self) -> int:
        return sum(1 for it in self._model._all() if it.status in {"queued", "running"})

    def _emit_counts(self) -> None:
        self.queueCountChanged.emit()
        self.runningCountChanged.emit()
        self.pendingCountChanged.emit()
        self.queueChanged.emit()
        self._schedule_persist()

    def _schedule_persist(self) -> None:
        app = QCoreApplication.instance()
        if app and QThread.currentThread() is not app.thread():
            QTimer.singleShot(0, self, self._schedule_persist)
            return
        self._persist_timer.start()

    def _flush_persist(self) -> None:
        try:
            rows: List[Dict[str, Any]] = []
            for it in self._model._all():
                if it.status not in {"queued", "running"}:
                    continue
                d = asdict(it)
                d["status"] = "queued"
                rows.append(d)
            if rows:
                save_queue_state(PERSIST_NAME, {"items": rows})
            else:
                clear_queue_state(PERSIST_NAME)
        except Exception as e:
            self.logMessage.emit(f"[EmbeddingQueue] persist failed: {e}")

    def flushQueueState(self) -> None:
        self._flush_persist()

    def _load_persisted(self) -> None:
        try:
            data = load_queue_state(PERSIST_NAME)
            raw = data.get("items") if isinstance(data, dict) else None
            if not isinstance(raw, list) or not raw:
                return
            jobs: list[_Job] = []
            for it in raw:
                if not isinstance(it, dict):
                    continue
                pc = (it.get("product_code") or "").strip().upper()
                if not pc:
                    continue
                jobs.append(
                    _Job(
                        job_id=str(it.get("job_id") or f"{pc}_{int(time.time() * 1000)}")[:200],
                        product_code=pc,
                        title=str(it.get("title") or pc)[:120],
                        model=str(it.get("model") or "nomic-embed-text")[:160],
                        force=bool(it.get("force")),
                        status="queued",
                        progress=0,
                        message="이어서 하기 대기",
                        created_at_ms=int(it.get("created_at_ms") or 0) or int(time.time() * 1000),
                    )
                )
            if jobs:
                self._model._replace_all(jobs)
                self._emit_counts()
                self.logMessage.emit(f"[EmbeddingQueue] restored {len(jobs)} job(s)")
        except Exception as e:
            self.logMessage.emit(f"[EmbeddingQueue] load persisted failed: {e}")

    def _title_for_product(self, product_code: str) -> str:
        try:
            from javstory.harvest.database import JAVMetadata, get_db_session

            session = get_db_session()
            try:
                row = session.query(JAVMetadata.title, JAVMetadata.title_ko).filter_by(product_code=product_code).first()
                if row:
                    return str((row.title_ko or row.title or product_code) or product_code)[:120]
            finally:
                session.close()
        except Exception:
            pass
        return product_code

    @Slot(str, str, bool)
    def enqueue(self, product_code: str, model: str = "", force: bool = False) -> None:
        pc = (product_code or "").strip().upper()
        m = (model or "").strip() or "nomic-embed-text"
        if not pc:
            return

        prev = self._model._find_latest_for_product(pc, m)
        if prev and prev.status in {"queued", "running"}:
            self.toastMessage.emit(f"[임베딩] 이미 대기/진행 중입니다: {pc}", "info")
            return

        job = _Job(
            job_id=f"{pc}_{int(time.time() * 1000)}",
            product_code=pc,
            title=self._title_for_product(pc),
            model=m,
            force=bool(force),
            status="queued",
            progress=0,
            message="대기 중",
            created_at_ms=int(time.time() * 1000),
        )
        self._model._append(job)
        self._emit_counts()
        self.toastMessage.emit(f"[임베딩] 큐에 추가됨: {pc}", "success")
        self.logMessage.emit(f"[EmbeddingQueue] enqueued: {pc} (model={m}, force={bool(force)})")
        QTimer.singleShot(0, self, self._pump)

    @Slot("QVariantList", str, bool)
    def enqueueMany(self, product_codes, model: str = "", force: bool = False) -> None:
        added = 0
        for raw in product_codes or []:
            before = self.queueCount
            self.enqueue(str(raw or ""), model, force)
            if self.queueCount > before:
                added += 1
        if added > 1:
            self.toastMessage.emit(f"[임베딩] {added}건 큐에 추가됨", "success")

    def _pump(self) -> None:
        if len(self._running) >= self._max_parallel:
            return
        for it in self._model._all():
            if it.status == "running" and it.job_id not in self._running:
                self._model._update_by_id(it.job_id, status="queued", message="재시작 대기 중(복구)")
        for it in self._model._all():
            if len(self._running) >= self._max_parallel:
                break
            if it.status != "queued":
                continue
            self._start_job(it)

    def _start_job(self, job: _Job) -> None:
        self._model._update_by_id(job.job_id, status="running", progress=0, message="시작 중")
        self._emit_counts()

        worker = EmbeddingWorker(job.product_code, job.model, job.force)
        self._running[job.job_id] = worker
        worker.progressUpdated.connect(lambda p, msg, jid=job.job_id: self._on_progress(jid, p, msg))
        worker.resultReady.connect(lambda ok, msg, jid=job.job_id: self._on_result(jid, ok, msg))
        worker.finished.connect(lambda jid=job.job_id, w=worker: self._on_thread_finished(jid, w))
        worker.start()
        self.logMessage.emit(f"[EmbeddingQueue] started: {job.product_code}")

    def _on_progress(self, job_id: str, percent: int, message: str = "") -> None:
        p = int(max(0, min(100, percent)))
        self._model._update_by_id(job_id, progress=p, message=message or f"{p}%")

    def _on_result(self, job_id: str, success: bool, message: str) -> None:
        if success:
            self._model._update_by_id(job_id, status="done", progress=100, message=message or "완료")
            self.logMessage.emit(f"[EmbeddingQueue] done: job={job_id} | {message}")
        else:
            self._model._update_by_id(job_id, status="error", message=message or "실패")
            self.logMessage.emit(f"[EmbeddingQueue] error: job={job_id} | {message}")
        self._emit_counts()

    def _on_thread_finished(self, job_id: str, worker: EmbeddingWorker) -> None:
        def _cleanup(w_ref=worker):
            self._running.pop(job_id, None)
            self._emit_counts()
            self._pump()

        QTimer.singleShot(500, _cleanup)

    @Slot(str)
    def removeJob(self, job_id: str) -> None:
        worker = self._running.pop(job_id, None)
        if worker:
            from gui.utils.qt_worker import stop_qthread

            result = stop_qthread(worker, context=f"EmbeddingQueue job={job_id}")
            self.logMessage.emit(f"[EmbeddingQueue] stop worker ({result.log_label()}): job={job_id}")
        if self._model._remove_by_id(job_id):
            self._emit_counts()
            QTimer.singleShot(0, self, self._pump)

    @Slot()
    def clearFinished(self) -> None:
        count = self._model._clear_finished()
        if count:
            self.logMessage.emit(f"[EmbeddingQueue] cleared {count} finished jobs")
            self._emit_counts()

    @Slot()
    def resume(self) -> None:
        for it in self._model._all():
            if it.status == "running" and it.job_id not in self._running:
                self._model._update_by_id(it.job_id, status="queued", message="이어서 하기", progress=0)
        QTimer.singleShot(0, self, self._pump)

