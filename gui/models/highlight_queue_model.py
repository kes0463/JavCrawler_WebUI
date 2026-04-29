"""하이라이트 생성 전역 큐 모델 (동시 실행 2개 제한)."""

from __future__ import annotations

import os
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

PERSIST_NAME = "highlight"


@dataclass
class _Job:
    job_id: str
    product_code: str
    video_path: str
    output_dir: str
    status: str  # queued|running|done|error
    progress: int
    message: str
    created_at_ms: int


class HighlightQueueListModel(QAbstractListModel):
    JobIdRole = Qt.ItemDataRole.UserRole + 1
    ProductCodeRole = Qt.ItemDataRole.UserRole + 2
    VideoNameRole = Qt.ItemDataRole.UserRole + 3
    StatusRole = Qt.ItemDataRole.UserRole + 4
    ProgressRole = Qt.ItemDataRole.UserRole + 5
    MessageRole = Qt.ItemDataRole.UserRole + 6

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
            return os.path.basename(it.video_path)
        if role == self.StatusRole:
            return it.status
        if role == self.ProgressRole:
            return int(it.progress)
        if role == self.MessageRole:
            return it.message
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

    def _find_latest_for_product(self, product_code: str) -> Optional[_Job]:
        pc = (product_code or "").strip().upper()
        for it in reversed(self._items):
            if (it.product_code or "").strip().upper() == pc:
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
        to_del = []
        for i, it in enumerate(self._items):
            if it.status in {"done", "error"}:
                to_del.append(i)

        if not to_del:
            return 0

        # 역순으로 제거해야 인덱스가 꼬이지 않음
        count = 0
        for i in sorted(to_del, reverse=True):
            self.beginRemoveRows(QModelIndex(), i, i)
            self._items.pop(i)
            self.endRemoveRows()
            count += 1
        return count

    def _replace_all(self, jobs: List[_Job]) -> None:
        self.beginResetModel()
        self._items = list(jobs)
        self.endResetModel()


class HighlightQueueController(QObject):
    _instance = None

    @staticmethod
    def instance() -> "HighlightQueueController | None":
        return HighlightQueueController._instance

    queueCountChanged = Signal()
    runningCountChanged = Signal()
    pendingCountChanged = Signal()
    toastMessage = Signal(str, str)  # msg, level
    logMessage = Signal(str)
    queueChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        HighlightQueueController._instance = self
        self._model = HighlightQueueListModel(self)
        self._running: Dict[str, object] = {}  # job_id -> worker
        raw = (os.environ.get("JAVSTORY_HIGHLIGHT_QUEUE_CONCURRENCY", "") or "").strip()
        try:
            n = int(raw) if raw else 2
        except ValueError:
            n = 2
        self._max_parallel = max(1, min(4, n))
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
                rows.append(d)
            if not rows:
                clear_queue_state(PERSIST_NAME)
                return
            save_queue_state(PERSIST_NAME, {"items": rows})
        except Exception as e:
            self.logMessage.emit(f"[HighlightQueue] persist failed: {e}")

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
            from javstory.config.app_config import E_MEDIA_ROOT

            jobs: list[_Job] = []
            for it in raw:
                if not isinstance(it, dict):
                    continue
                st = (it.get("status") or "").strip()
                if st == "error":
                    continue
                pc = (it.get("product_code") or "").strip().upper()
                vp = (it.get("video_path") or "").strip()
                if not pc or not vp:
                    continue
                jid = str(it.get("job_id") or "").strip() or f"{pc}_{it.get('created_at_ms', 0)}"
                out_dir = (it.get("output_dir") or "").strip()
                if not out_dir:
                    out_dir = str(Path(E_MEDIA_ROOT) / pc / "Highlight")
                jobs.append(
                    _Job(
                        job_id=str(jid)[:200],
                        product_code=pc,
                        video_path=vp,
                        output_dir=str(out_dir),
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
                f"[HighlightQueue] restored {len(jobs)} job(s) from disk (이어서 하기로 진행)"
            )
        except Exception as e:
            self.logMessage.emit(f"[HighlightQueue] load persisted failed: {e}")

    def has_highlight_pending_or_running(self) -> bool:
        """하이라이트 큐에 queued/running 작업이 있으면 True (프리뷰보다 우선)."""
        for it in self._model._all():
            if it.status in {"queued", "running"}:
                return True
        return False

    def _translation_blocks(self) -> bool:
        try:
            from gui.models.translation_queue_model import TranslationQueueController

            tq = TranslationQueueController.instance()
            if tq is not None and tq.is_translation_active():
                return True
        except Exception:
            pass
        return False

    def _notify_preview_queue(self) -> None:
        """하이라이트 슬롯/작업 변화 후 프리뷰가 다음 우선순위로 진행하도록 펌핑."""
        try:
            from gui.models.preview_queue_model import PreviewQueueController

            pq = PreviewQueueController.instance()
            if pq is not None:
                QTimer.singleShot(0, pq, pq._pump)
        except Exception:
            pass

    @Slot(str, result="QVariantMap")
    def productState(self, product_code: str):
        """특정 품번의 최신 하이라이트 작업 상태를 반환 (QML용)."""
        pc = (product_code or "").strip().upper()
        if not pc:
            return {"status": "none", "progress": 0, "message": ""}
        it = self._model._find_latest_for_product(pc)
        if not it:
            return {"status": "none", "progress": 0, "message": ""}
        return {
            "status": it.status,
            "progress": int(it.progress or 0),
            "message": it.message or "",
        }

    @Slot(str, str)
    def enqueue(self, product_code: str, video_path: str) -> None:
        pc = (product_code or "").strip().upper()
        vp = (video_path or "").strip()
        if not pc or not vp:
            return

        # 이미 queued/running인 동일 품번은 중복 등록 방지
        prev = self._model._find_latest_for_product(pc)
        if prev and prev.status in {"queued", "running"}:
            self.toastMessage.emit(f"[하이라이트] 이미 대기/진행 중입니다: {pc}", "info")
            self.logMessage.emit(f"[HighlightQueue] skip duplicate: {pc}")
            return

        from javstory.config.app_config import E_MEDIA_ROOT
        output_dir = str(Path(E_MEDIA_ROOT) / pc / "Highlight")
        job_id = f"{pc}_{int(time.time() * 1000)}"
        job = _Job(
            job_id=job_id,
            product_code=pc,
            video_path=vp,
            output_dir=output_dir,
            status="queued",
            progress=0,
            message="대기 중",
            created_at_ms=int(time.time() * 1000),
        )
        self._model._append(job)
        self._emit_counts()
        self.toastMessage.emit(f"[하이라이트] 큐에 추가됨: {pc}", "success")
        self.logMessage.emit(f"[HighlightQueue] enqueued: {pc} | {os.path.basename(vp)}")
        # 백그라운드 스레드에서 호출될 수 있으므로 펌프는 메인 스레드에서 수행
        QTimer.singleShot(0, self, self._pump)

    def _pump(self) -> None:
        # running 슬롯이 남아 있으면 queued job을 시작
        if len(self._running) >= self._max_parallel:
            return
        # 번역 중이면 하이라이트는 대기 (번역 완료 시 translation 쪽에서 _pump 호출)
        if self._translation_blocks():
            return

        # 자기 치유(Self-healing): status가 running인데 실제 워커가 없으면 queued로 리셋
        for it in self._model._all():
            if it.status == "running" and it.job_id not in self._running:
                self._model._update_by_id(it.job_id, status="queued", message="재시작 대기 중(복구)")

        for it in self._model._all():
            if len(self._running) >= self._max_parallel:
                break
            if it.status != "queued":
                continue
            self._start_job(it)
            # 경쟁 방지를 위해 하나 시작 후 브레이크 (QTimer가 다음 펌핑 유도)
            break

    def _start_job(self, job: _Job) -> None:
        try:
            from gui.workers.highlight_worker import HighlightWorker
        except Exception as e:
            self._model._update_by_id(job.job_id, status="error", message=f"워커 로드 실패: {e}")
            self._emit_counts()
            return

        self._model._update_by_id(job.job_id, status="running", progress=0, message="시작 중...")
        self._emit_counts()

        worker = HighlightWorker(job.product_code, job.video_path, job.output_dir)
        self._running[job.job_id] = worker
        self._last_progress_log[job.job_id] = -1

        worker.progressUpdated.connect(lambda p, msg, jid=job.job_id: self._on_progress(jid, p, msg))
        # resultReady는 작업 성공/실패 최종 상태를 반영한다.
        worker.resultReady.connect(lambda ok, msg, jid=job.job_id: self._on_finished(jid, ok, msg))
        worker.finished.connect(lambda jid=job.job_id: self._on_thread_finished(jid, worker))
        worker.start()
        self.logMessage.emit(f"[HighlightQueue] started: {job.product_code}")
        self._emit_counts()
        
        # [추가] 다음 슬롯이 바로 비어있을 경우 연쇄 펌핑
        QTimer.singleShot(100, self._pump)

    def _on_thread_finished(self, job_id: str, worker) -> None:
        # 워커 참조 지연 제거 (worker 객체를 직접 캡처하여 2초간 생존 보장)
        def _cleanup(w_ref=worker):
            self._running.pop(job_id, None)
            self._emit_counts()
            
            # 슬롯이 비워진 후 다음 작업 시작
            self._pump()
            self._notify_preview_queue()
        
        QTimer.singleShot(2000, _cleanup)

    def _on_progress(self, job_id: str, percent: int, message: str = "") -> None:
        p = int(max(0, min(100, percent)))
        msg = message if message else f"{p}%"
        self._model._update_by_id(job_id, progress=p, message=msg)
        # 터미널 로그는 과도하므로 10% 단위로만 출력
        last = self._last_progress_log.get(job_id, -1)
        step = int(p // 10)
        if step != last and p < 100:
            self._last_progress_log[job_id] = step
            self.logMessage.emit(f"[HighlightQueue] progress: {p}% (job={job_id})")

    def _on_finished(self, job_id: str, success: bool, message: str) -> None:
        # job snapshot (UI 갱신용)
        job = None
        try:
            for it in self._model._all():
                if it.job_id == job_id:
                    job = it
                    break
        except Exception:
            job = None

        self._running.pop(job_id, None)
        self._last_progress_log.pop(job_id, None)
        if success:
            self._model._update_by_id(job_id, status="done", progress=100, message=message or "완료")
            self.logMessage.emit(f"[HighlightQueue] done: job={job_id} | {message}")
        else:
            # removeJob에 의해 중단된 경우 이미 목록에서 사라졌을 수 있음
            self._model._update_by_id(job_id, status="error", message=message or "실패")
            self.logMessage.emit(f"[HighlightQueue] error: job={job_id} | {message}")
        self._emit_counts()

        # 현재 상세 화면이 해당 품번이면 즉시 재로드하여 highlightPath 반영
        try:
            if success and job and (job.product_code or "").strip():
                from gui.models.library_model import LibraryModel
                lib = LibraryModel.instance()
                pc = (job.product_code or "").strip().upper()
                if lib and lib.detail and getattr(lib.detail, "productCode", "") == pc:
                    lib.loadDetail(pc)
        except Exception:
            pass

        self._pump()
        self._notify_preview_queue()

    @Slot(str)
    def removeJob(self, job_id: str) -> None:
        """대기/진행/완료 작업을 즉시 삭제."""
        # 실행 중이면 워커 중단
        worker = self._running.pop(job_id, None)
        if worker:
            try:
                worker.terminate()
                worker.wait()
            except Exception:
                pass
            self.logMessage.emit(f"[HighlightQueue] terminated worker: job={job_id}")

        if self._model._remove_by_id(job_id):
            self.logMessage.emit(f"[HighlightQueue] removed job: {job_id}")
            self._emit_counts()
            # 실행 중인게 빠졌으니 다음 작업 펌핑
            self._pump()
            self._notify_preview_queue()

    @Slot()
    def clearFinished(self) -> None:
        """완료 또는 에러 상태인 항목을 모두 제거."""
        count = self._model._clear_finished()
        if count > 0:
            self.logMessage.emit(f"[HighlightQueue] cleared {count} finished jobs")
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

