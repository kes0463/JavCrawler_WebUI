"""몽타주 생성 전역 큐 모델 (동시 실행 1개 권장)."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import (
    QObject,
    Property,
    Signal,
    Slot,
    QAbstractListModel,
    QCoreApplication,
    QModelIndex,
    Qt,
    QThread,
    QTimer,
)
from gui.utils.queue_persistence import clear_queue_state, load_queue_state, save_queue_state

PERSIST_NAME = "montage"


@dataclass
class _Job:
    job_id: str
    product_codes: list[str]
    output_path: str
    status: str  # queued|running|done|error
    progress: int
    message: str
    created_at_ms: int


class MontageQueueListModel(QAbstractListModel):
    JobIdRole = Qt.ItemDataRole.UserRole + 1
    TitleRole = Qt.ItemDataRole.UserRole + 2
    StatusRole = Qt.ItemDataRole.UserRole + 3
    ProgressRole = Qt.ItemDataRole.UserRole + 4
    MessageRole = Qt.ItemDataRole.UserRole + 5
    OutputPathRole = Qt.ItemDataRole.UserRole + 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[_Job] = []

    def roleNames(self):
        return {
            self.JobIdRole: b"jobId",
            self.TitleRole: b"title",
            self.StatusRole: b"status",
            self.ProgressRole: b"progress",
            self.MessageRole: b"message",
            self.OutputPathRole: b"outputPath",
        }

    def rowCount(self, parent=QModelIndex()):
        return len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        it = self._items[index.row()]
        if role == self.JobIdRole:
            return it.job_id
        if role == self.TitleRole:
            return f"{len(it.product_codes)}개 작품 몽타주"
        if role == self.StatusRole:
            return it.status
        if role == self.ProgressRole:
            return int(it.progress)
        if role == self.MessageRole:
            return it.message
        if role == self.OutputPathRole:
            return it.output_path
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
                # 모든 관련 role 갱신 통보 (특히 ProgressRole)
                roles = [
                    self.StatusRole, self.ProgressRole, self.MessageRole
                ]
                self.dataChanged.emit(idx, idx, roles)
                return

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
        to_del = []
        for i, it in enumerate(self._items):
            if it.status in {"done", "error"}:
                to_del.append(i)

        if not to_del:
            return 0

        count = 0
        for i in sorted(to_del, reverse=True):
            self.beginRemoveRows(QModelIndex(), i, i)
            self._items.pop(i)
            self.endRemoveRows()
            count += 1
        return count

    def _find_latest(self) -> Optional[_Job]:
        return self._items[-1] if self._items else None

    def _replace_all(self, jobs: List[_Job]) -> None:
        self.beginResetModel()
        self._items = list(jobs)
        self.endResetModel()


class MontageQueueController(QObject):
    _instance = None

    @staticmethod
    def instance() -> "MontageQueueController | None":
        return MontageQueueController._instance

    queueCountChanged = Signal()
    runningCountChanged = Signal()
    pendingCountChanged = Signal()
    toastMessage = Signal(str, str)  # msg, level
    logMessage = Signal(str)
    queueChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        MontageQueueController._instance = self
        self._model = MontageQueueListModel(self)
        self._running: Dict[str, object] = {}
        # 몽타주는 GPU/IO 부하가 커서 기본 1 (환경변수로만 확장 허용)
        import os

        raw = (os.environ.get("JAVSTORY_MONTAGE_QUEUE_CONCURRENCY", "") or "").strip()
        try:
            n = int(raw) if raw else 1
        except ValueError:
            n = 1
        self._max_parallel = max(1, min(2, n))
        self._last_progress_log: Dict[str, int] = {}
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
        n = 0
        for it in self._model._all():
            if it.status in {"queued", "running"}:
                n += 1
        return n

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
                if (it.status or "") not in {"queued", "running"}:
                    continue
                d = asdict(it)
                d["status"] = "queued" if d.get("status") == "running" else d.get("status", "queued")
                d["product_codes"] = list(d.get("product_codes") or [])
                rows.append(d)
            if not rows:
                clear_queue_state(PERSIST_NAME)
                return
            save_queue_state(PERSIST_NAME, {"items": rows})
        except Exception as e:
            self.logMessage.emit(f"[MontageQueue] persist failed: {e}")

    def flushQueueState(self) -> None:
        self._flush_persist()

    def _load_persisted(self) -> None:
        try:
            data = load_queue_state(PERSIST_NAME)
            if not data:
                return
            raw = data.get("items")
            if not isinstance(raw, list) or not raw:
                return
            jobs: list[_Job] = []
            for it in raw:
                if not isinstance(it, dict) or (it.get("status") or "") == "error":
                    continue
                pcs = it.get("product_codes")
                if not isinstance(pcs, list) or len(pcs) < 2:
                    continue
                out = (it.get("output_path") or "").strip()
                if not out:
                    continue
                jid = str(it.get("job_id") or "").strip() or f"MONTAGE_{it.get('created_at_ms', 0)}"
                norm_pcs: list[str] = []
                for p in pcs:
                    s = str(p or "").strip().upper()
                    if s:
                        norm_pcs.append(s)
                if len(norm_pcs) < 2:
                    continue
                jobs.append(
                    _Job(
                        job_id=str(jid)[:200],
                        product_codes=norm_pcs,
                        output_path=str(out),
                        status="queued",
                        progress=0,
                        message="이어서 하기 대기",
                        created_at_ms=int(it.get("created_at_ms") or 0) or int(time.time() * 1000),
                    )
                )
            if not jobs:
                return
            self._model._replace_all(jobs)
            self._emit_counts()
            self.logMessage.emit(
                f"[MontageQueue] restored {len(jobs)} job(s) from disk (이어서 하기로 진행)"
            )
        except Exception as e:
            self.logMessage.emit(f"[MontageQueue] load persisted failed: {e}")

    @Slot(result="QVariantMap")
    def latestState(self):
        it = self._model._find_latest()
        if not it:
            return {"status": "none", "progress": 0, "message": "", "outputPath": ""}
        return {
            "status": it.status,
            "progress": int(it.progress or 0),
            "message": it.message or "",
            "outputPath": it.output_path or "",
        }

    @Slot("QVariantList")
    def enqueue(self, product_codes):
        pcs = []
        try:
            for pc in (product_codes or []):
                s = str(pc or "").strip().upper()
                if s:
                    pcs.append(s)
        except Exception:
            pcs = []
        if len(pcs) < 2:
            self.toastMessage.emit("[몽타주] 2개 이상 선택해야 합니다.", "warning")
            return

        from javstory.config.app_config import E_DATA_ROOT

        # 몽타주는 공용 폴더에 저장 (작품 폴더와 분리)
        out_dir = Path(E_DATA_ROOT) / "Montage"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"montage_{int(time.time())}.mp4"

        job_id = f"MONTAGE_{int(time.time() * 1000)}"
        job = _Job(
            job_id=job_id,
            product_codes=pcs,
            output_path=str(out_path),
            status="queued",
            progress=0,
            message="대기 중",
            created_at_ms=int(time.time() * 1000),
        )
        self._model._append(job)
        self._emit_counts()
        self.toastMessage.emit(f"[몽타주] 큐에 추가됨: {len(pcs)}개", "success")
        self._pump()

    def _pump(self) -> None:
        if len(self._running) >= self._max_parallel:
            return
        # 자기 치유: status가 running인데 실제 워커가 없으면 queued로 리셋
        for it in self._model._all():
            if it.status == "running" and it.job_id not in self._running:
                self._model._update_by_id(it.job_id, status="queued", message="재시작 대기 중(복구)")

        for it in self._model._all():
            if len(self._running) >= self._max_parallel:
                break
            if it.status != "queued":
                continue
            self._start_job(it)
            break

    def _start_job(self, job: _Job) -> None:
        try:
            from gui.workers.montage_worker import MontageWorker
        except Exception as e:
            self._model._update_by_id(job.job_id, status="error", message=f"워커 로드 실패: {e}")
            self._emit_counts()
            return

        self._model._update_by_id(job.job_id, status="running", progress=0, message="시작 중...")
        self._emit_counts()

        worker = MontageWorker(job.product_codes, job.output_path)
        self._running[job.job_id] = worker
        self._last_progress_log[job.job_id] = -1

        worker.progressUpdated.connect(lambda p, msg, jid=job.job_id: self._on_progress(jid, p, msg))
        worker.resultReady.connect(lambda ok, msg, outp, jid=job.job_id: self._on_result(jid, ok, msg, outp))
        worker.finished.connect(lambda jid=job.job_id: self._on_thread_finished(jid, worker))
        worker.start()
        self.logMessage.emit(f"[MontageQueue] started: job={job.job_id}")
        self._emit_counts()
        
        # [추가] 연쇄 펌핑
        QTimer.singleShot(100, self._pump)

    def _on_progress(self, job_id: str, percent: int, message: str = "") -> None:
        p = int(max(0, min(100, percent)))
        msg = message if message else f"{p}%"
        self._model._update_by_id(job_id, progress=p, message=msg)
        last = self._last_progress_log.get(job_id, -1)
        step = int(p // 10)
        if step != last and p < 100:
            self._last_progress_log[job_id] = step
            self.logMessage.emit(f"[MontageQueue] progress: {p}% (job={job_id})")

    def _on_result(self, job_id: str, success: bool, message: str, output_path: str) -> None:
        if success:
            self._model._update_by_id(job_id, status="done", progress=100, message=message or "완료", output_path=output_path)
            self.logMessage.emit(f"[MontageQueue] done: job={job_id} | {message}")
        else:
            self._model._update_by_id(job_id, status="error", message=message or "실패")
            self.logMessage.emit(f"[MontageQueue] error: job={job_id} | {message}")
        self._emit_counts()

    def _on_thread_finished(self, job_id: str, worker) -> None:
        # 워커 참조 지연 제거 (worker 객체를 직접 캡처하여 2초간 생존 보장)
        def _cleanup(w_ref=worker):
            self._running.pop(job_id, None)
            self._last_progress_log.pop(job_id, None)
            self._emit_counts()
            # 슬롯이 비워진 후 다음 작업 시작
            self._pump()
        
        QTimer.singleShot(2000, _cleanup)

    @Slot(str)
    def removeJob(self, job_id: str) -> None:
        """몽타주 생성 작업 삭제."""
        worker = self._running.pop(job_id, None)
        if worker:
            try:
                worker.terminate()
                worker.wait()
            except Exception:
                pass
            self.logMessage.emit(f"[MontageQueue] terminated worker: job={job_id}")

        if self._model._remove_by_id(job_id):
            self.logMessage.emit(f"[MontageQueue] removed job: {job_id}")
            self._emit_counts()
            self._pump()

    @Slot()
    def clearFinished(self) -> None:
        """완료/에러 항목 일괄 제거."""
        count = self._model._clear_finished()
        if count > 0:
            self.logMessage.emit(f"[MontageQueue] cleared {count} finished jobs")
            self._emit_counts()

    @Slot()
    def resume(self) -> None:
        """앱 재시작 후 대기 항목을 이어서 처리."""
        for it in self._model._all():
            if it.status == "running" and it.job_id not in self._running:
                self._model._update_by_id(
                    it.job_id, status="queued", message="이어서 하기", progress=0
                )
        QTimer.singleShot(0, self, self._pump)

