"""프리뷰(WebP) 생성 전역 큐 모델 (동시 실행 제한)."""

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

PERSIST_NAME = "preview"


@dataclass
class _Job:
    job_id: str
    product_code: str
    video_path: str
    output_path: str
    status: str  # queued|running|done|error
    progress: int
    message: str
    created_at_ms: int
    seed: int = 0


class PreviewQueueListModel(QAbstractListModel):
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


class PreviewQueueController(QObject):
    _instance = None

    @staticmethod
    def instance() -> "PreviewQueueController | None":
        return PreviewQueueController._instance

    queueCountChanged = Signal()
    runningCountChanged = Signal()
    pendingCountChanged = Signal()
    toastMessage = Signal(str, str)  # msg, level
    logMessage = Signal(str)
    queueChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        PreviewQueueController._instance = self
        self._model = PreviewQueueListModel(self)
        self._running: Dict[str, object] = {}  # job_id -> worker
        raw = (os.environ.get("JAVSTORY_PREVIEW_QUEUE_CONCURRENCY", "") or "").strip()
        try:
            n = int(raw) if raw else 2
        except ValueError:
            n = 2
        self._max_parallel = max(1, min(6, n))
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
            self.logMessage.emit(f"[PreviewQueue] persist failed: {e}")

    def flushQueueState(self) -> None:
        self._flush_persist()

    def _load_persisted(self) -> None:
        try:
            from javstory.config.app_config import E_MEDIA_ROOT

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
                pc = (it.get("product_code") or "").strip().upper()
                vp = (it.get("video_path") or "").strip()
                if not pc or not vp:
                    continue
                outp = (it.get("output_path") or "").strip() or str(
                    Path(E_MEDIA_ROOT) / pc / "Preview" / "preview.webp"
                )
                jid = str(it.get("job_id") or "").strip() or f"{pc}_{it.get('created_at_ms', 0)}"
                jobs.append(
                    _Job(
                        job_id=str(jid)[:200],
                        product_code=pc,
                        video_path=vp,
                        output_path=str(outp),
                        status="queued",
                        progress=0,
                        message="이어서 하기 대기",
                        created_at_ms=int(it.get("created_at_ms") or 0) or int(time.time() * 1000),
                        seed=int(it.get("seed") or 0),
                    )
                )
            if not jobs:
                return
            self._model._replace_all(jobs)
            self._emit_counts()
            self.logMessage.emit(
                f"[PreviewQueue] restored {len(jobs)} job(s) from disk (이어서 하기로 진행)"
            )
        except Exception as e:
            self.logMessage.emit(f"[PreviewQueue] load persisted failed: {e}")

    def _upstream_blocks_preview(self) -> bool:
        """번역 또는 하이라이트가 진행/대기 중이면 프리뷰는 대기."""
        try:
            from gui.playback_guard import is_playback_active

            if is_playback_active():
                return True
        except Exception:
            pass
        try:
            from gui.models.translation_queue_model import TranslationQueueController

            tq = TranslationQueueController.instance()
            if tq is not None and tq.is_translation_active():
                return True
        except Exception:
            pass
        try:
            from gui.models.highlight_queue_model import HighlightQueueController

            hq = HighlightQueueController.instance()
            if hq is not None and hq.has_highlight_pending_or_running():
                return True
        except Exception:
            pass
        try:
            from javstory.services.harvest_queue_service import harvest_queue

            if harvest_queue.running:
                return True
        except Exception:
            pass
        return False

    @Slot(str, result="QVariantMap")
    def productState(self, product_code: str):
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

        prev = self._model._find_latest_for_product(pc)
        if prev and prev.status in {"queued", "running"}:
            self.toastMessage.emit(f"[프리뷰] 이미 대기/진행 중입니다: {pc}", "info")
            self.logMessage.emit(f"[PreviewQueue] skip duplicate: {pc}")
            return

        from javstory.config.app_config import E_MEDIA_ROOT
        from javstory.library.highlight.video_preview import is_montage_preview_fresh

        output_path = str(Path(E_MEDIA_ROOT) / pc / "Preview" / "preview.webp")
        outp = Path(output_path)
        if is_montage_preview_fresh(webp_path=outp, video_path=Path(vp)):
            self.toastMessage.emit(f"[프리뷰] 이미 최신입니다: {pc}", "info")
            return

        job_id = f"{pc}_{int(time.time() * 1000)}"
        job = _Job(
            job_id=job_id,
            product_code=pc,
            video_path=vp,
            output_path=output_path,
            status="queued",
            progress=0,
            message="대기 중",
            created_at_ms=int(time.time() * 1000),
            seed=0,
        )
        self._model._append(job)
        self._emit_counts()
        self.toastMessage.emit(f"[프리뷰] 큐에 추가됨: {pc}", "success")
        self.logMessage.emit(f"[PreviewQueue] enqueued: {pc} | {os.path.basename(vp)}")
        
        # [핵심] 백그라운드 스레드(HarvestWorker 등)에서 호출될 수 있으므로, 
        # 메인 스레드에서 펌핑되도록 지연 실행 보장.
        QTimer.singleShot(0, self, self._pump)

    @Slot(str, str)
    def regenerate(self, product_code: str, video_path: str) -> None:
        """preview.webp가 있어도 강제로 삭제 후 재생성 큐 등록."""
        pc = (product_code or "").strip().upper()
        vp = (video_path or "").strip()
        if not pc or not vp:
            return

        prev = self._model._find_latest_for_product(pc)
        if prev and prev.status in {"queued", "running"}:
            self.toastMessage.emit(f"[프리뷰] 이미 대기/진행 중입니다: {pc}", "info")
            self.logMessage.emit(f"[PreviewQueue] skip duplicate(force): {pc}")
            return

        from javstory.config.app_config import E_MEDIA_ROOT

        output_path = Path(E_MEDIA_ROOT) / pc / "Preview" / "preview.webp"
        try:
            if output_path.is_file():
                output_path.unlink(missing_ok=True)  # type: ignore[arg-type]
        except TypeError:
            # py<3.8 compatibility guard (실제로는 3.12이지만 안전)
            try:
                if output_path.is_file():
                    output_path.unlink()
            except Exception:
                pass
        except Exception:
            pass

        # 기존 메타데이터가 있으면 seed를 읽어서 증가시킴 (다른 구간 추출 유도)
        seed = 0
        try:
            import json
            meta_path = output_path.with_suffix(output_path.suffix + ".meta.json")
            if meta_path.is_file():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                seed = meta.get("params", {}).get("seed", 0) + 1
        except Exception:
            pass

        # 강제 재생성은 enqueue 로직의 "exists" 체크를 우회해야 하므로 직접 job 생성
        job_id = f"{pc}_{int(time.time() * 1000)}"
        job = _Job(
            job_id=job_id,
            product_code=pc,
            video_path=vp,
            output_path=str(output_path),
            status="queued",
            progress=0,
            message=f"대기 중(재생성 #{seed})",
            created_at_ms=int(time.time() * 1000),
            seed=seed,
        )
        self._model._append(job)
        self._emit_counts()
        self.toastMessage.emit(f"[프리뷰] 재생성 큐에 추가됨: {pc}", "success")
        self.logMessage.emit(f"[PreviewQueue] enqueued(force): {pc} | {os.path.basename(vp)}")
        QTimer.singleShot(0, self._pump)

    @Slot()
    def enqueueMissingPreviews(self) -> None:
        """DB를 스캔해 preview 누락·구버전 작품을 큐 등록."""
        try:
            from javstory.harvest.database import get_db_session, JAVMetadata
            from gui.library_data import guess_video_path_for_product
            from javstory.library.highlight.video_preview import is_montage_preview_fresh

            from javstory.config.app_config import E_MEDIA_ROOT

            session = get_db_session()
            try:
                rows = session.query(JAVMetadata.product_code, JAVMetadata.folder_path).all()
            finally:
                try:
                    session.close()
                except Exception:
                    pass

            added = 0
            skipped_no_video = 0
            no_video_pcs: list[str] = []
            skipped_fresh = 0
            for pc_raw, folder_path in (rows or []):
                pc = (pc_raw or "").strip().upper()
                if not pc:
                    continue
                outp = Path(E_MEDIA_ROOT) / pc / "Preview" / "preview.webp"

                vp = guess_video_path_for_product(pc, folder_path or None)
                if not vp or not vp.is_file():
                    skipped_no_video += 1
                    no_video_pcs.append(pc)
                    continue
                if is_montage_preview_fresh(webp_path=outp, video_path=vp):
                    skipped_fresh += 1
                    continue

                self.enqueue(pc, str(vp))
                added += 1

            if no_video_pcs:
                sample = ", ".join(no_video_pcs[:5])
                self.logMessage.emit(
                    f"[프리뷰 백필] 영상 없음 {len(no_video_pcs)}건"
                    + (f" — 예: {sample}" if sample else "")
                )

            self.toastMessage.emit(
                f"[프리뷰 백필] 추가 {added}건 (최신 {skipped_fresh} / 영상없음 {skipped_no_video})"
                + (f" — 예: {', '.join(no_video_pcs[:5])}" if no_video_pcs else ""),
                "success" if added > 0 else "info",
            )
        except Exception as e:
            self.toastMessage.emit(f"[프리뷰 백필] 실패: {e}", "error")

    @Slot()
    def enqueueAllPreviewsForce(self) -> None:
        """DB를 스캔해 가능한 모든 작품을 프리뷰 '강제 재생성'으로 큐 등록."""
        try:
            from javstory.harvest.database import get_db_session, JAVMetadata
            from gui.library_data import guess_video_path_for_product

            session = get_db_session()
            try:
                rows = session.query(JAVMetadata.product_code, JAVMetadata.folder_path).all()
            finally:
                try:
                    session.close()
                except Exception:
                    pass

            added = 0
            skipped_no_video = 0
            no_video_pcs: list[str] = []
            for pc_raw, folder_path in (rows or []):
                pc = (pc_raw or "").strip().upper()
                if not pc:
                    continue
                vp = guess_video_path_for_product(pc, folder_path or None)
                if not vp or not vp.is_file():
                    skipped_no_video += 1
                    no_video_pcs.append(pc)
                    continue
                self.regenerate(pc, str(vp))
                added += 1

            if no_video_pcs:
                sample = ", ".join(no_video_pcs[:5])
                self.logMessage.emit(
                    f"[프리뷰 일괄 재생성] 영상 없음 {len(no_video_pcs)}건"
                    + (f" — 예: {sample}" if sample else "")
                )

            self.toastMessage.emit(
                f"[프리뷰 일괄 재생성] 추가 {added}건 (영상없음 {skipped_no_video})"
                + (f" — 예: {', '.join(no_video_pcs[:5])}" if no_video_pcs else ""),
                "success" if added > 0 else "info",
            )
        except Exception as e:
            self.toastMessage.emit(f"[프리뷰 일괄 재생성] 실패: {e}", "error")

    def _pump(self) -> None:
        if len(self._running) >= self._max_parallel:
            return
        if self._upstream_blocks_preview():
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
            # 하나씩 순차적으로 비동기 시작을 유도 (경쟁 방지)
            break

    def _start_job(self, job: _Job) -> None:
        try:
            from gui.workers.preview_worker import PreviewWorker
        except Exception as e:
            self._model._update_by_id(job.job_id, status="error", message=f"워커 로드 실패: {e}")
            self._emit_counts()
            return

        self._model._update_by_id(job.job_id, status="running", progress=0, message="시작 중...")
        self._emit_counts()

        worker = PreviewWorker(job.product_code, job.video_path, job.output_path, seed=job.seed)
        self._running[job.job_id] = worker
        self._last_progress_log[job.job_id] = -1

        worker.progressUpdated.connect(lambda p, msg, jid=job.job_id: self._on_progress(jid, p, msg))
        worker.resultReady.connect(lambda ok, msg, jid=job.job_id: self._on_result(jid, ok, msg))
        # worker는 스레드 종료(QThread.finished)까지 유지해야 안전함
        worker.finished.connect(lambda jid=job.job_id: self._on_thread_finished(jid, worker))
        worker.start()
        self.logMessage.emit(f"[PreviewQueue] started: {job.product_code}")
        self._emit_counts()
        
        # [추가] 다음 슬롯이 바로 비어있을 경우 연쇄 펌핑
        QTimer.singleShot(100, self._pump)

    def _on_progress(self, job_id: str, percent: int, message: str = "") -> None:
        p = int(max(0, min(100, percent)))
        msg = message if message else f"{p}%"
        self._model._update_by_id(job_id, progress=p, message=msg)
        last = self._last_progress_log.get(job_id, -1)
        step = int(p // 10)
        if step != last and p < 100:
            self._last_progress_log[job_id] = step
            self.logMessage.emit(f"[PreviewQueue] progress: {p}% (job={job_id})")

    def _on_result(self, job_id: str, success: bool, message: str) -> None:
        if success:
            self._model._update_by_id(job_id, status="done", progress=100, message=message or "완료")
            self.logMessage.emit(f"[PreviewQueue] done: job={job_id} | {message}")
        else:
            self._model._update_by_id(job_id, status="error", message=message or "실패")
            self.logMessage.emit(f"[PreviewQueue] error: job={job_id} | {message}")
        self._emit_counts()

    @Slot(str)
    def removeJob(self, job_id: str) -> None:
        """프리뷰 생성 작업 삭제."""
        worker = self._running.pop(job_id, None)
        if worker:
            from gui.utils.qt_worker import stop_qthread

            result = stop_qthread(worker, context=f"PreviewQueue job={job_id}")
            self.logMessage.emit(
                f"[PreviewQueue] stop worker ({result.log_label()}): job={job_id}",
            )

        if self._model._remove_by_id(job_id):
            self.logMessage.emit(f"[PreviewQueue] removed job: {job_id}")
            self._emit_counts()
            QTimer.singleShot(0, self._pump)

    @Slot()
    def clearFinished(self) -> None:
        """완료/에러 항목 일괄 제거."""
        count = self._model._clear_finished()
        if count > 0:
            self.logMessage.emit(f"[PreviewQueue] cleared {count} finished jobs")
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

    def _on_thread_finished(self, job_id: str, worker) -> None:
        # 워커 참조 지연 제거 (worker 객체를 직접 캡처하여 2초간 생존 보장)
        def _cleanup(w_ref=worker):
            self._running.pop(job_id, None)
            self._last_progress_log.pop(job_id, None)
            self._emit_counts()
            
            # 슬롯이 비워진 후 다음 작업 시작
            self._pump()
        
        QTimer.singleShot(2000, _cleanup)

