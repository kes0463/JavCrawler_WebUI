from PySide6.QtCore import (
    Property,
    Signal,
    Slot,
    QTimer,
    QAbstractListModel,
    Qt,
    QModelIndex,
)
from gui.workers.translation_worker import TranslationWorker
from gui.utils.queue_persistence import clear_queue_state, load_queue_state, save_queue_state
from gui.utils.qt_thread_util import is_on_app_main_thread
from javstory.utils.common import log_ts

PERSIST_NAME = "translation"

class TranslationQueueController(QAbstractListModel):
    SkuRole = Qt.ItemDataRole.UserRole + 1
    PathRole = Qt.ItemDataRole.UserRole + 2
    StatusRole = Qt.ItemDataRole.UserRole + 3
    ProgressRole = Qt.ItemDataRole.UserRole + 4

    _instance = None
    countChanged = Signal()
    # 개수뿐 아니라 status(queued↔running) 갱신 시 QML 뱃지/요약이 바뀌도록
    stateChanged = Signal()
    toastMessage = Signal(str, str)

    @staticmethod
    def instance() -> "TranslationQueueController | None":
        return TranslationQueueController._instance

    def __init__(self, parent=None):
        super().__init__(parent)
        TranslationQueueController._instance = self
        self._items = []  # list of {sku, video_path, status, progress}
        self._active_workers = {}  # sku -> worker
        self._is_running = False
        self._persist_timer = QTimer(self)
        self._persist_timer.setSingleShot(True)
        self._persist_timer.setInterval(350)
        self._persist_timer.timeout.connect(self._flush_persist)
        QTimer.singleShot(0, self, self._load_persisted)
        log_ts("[TranslationQueue] Controller initialized.")

    def roleNames(self):
        return {
            self.SkuRole: b"sku",
            self.PathRole: b"video_path",
            self.StatusRole: b"status",
            self.ProgressRole: b"progress"
        }

    def rowCount(self, parent=QModelIndex()):
        return len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        item = self._items[index.row()]
        if role == self.SkuRole:
            return item["sku"]
        if role == self.PathRole:
            return item["video_path"]
        if role == self.StatusRole:
            return item["status"]
        if role == self.ProgressRole:
            return item.get("progress", 0)
        return None

    @Property(int, notify=countChanged)
    def count(self):
        return len(self._items)

    def _running_count(self) -> int:
        return sum(1 for i in self._items if i.get("status") == "running")

    def _queued_count(self) -> int:
        return sum(1 for i in self._items if i.get("status") == "queued")

    @Property(int, notify=stateChanged)
    def runningCount(self):
        return self._running_count()

    @Property(int, notify=stateChanged)
    def queuedCount(self):
        return self._queued_count()

    @Property(str, notify=stateChanged)
    def summaryLabel(self) -> str:
        n = len(self._items)
        if n == 0:
            return ""
        nr, nq = self._running_count(), self._queued_count()
        if nr and nq:
            return f"번역 {nr} · 대기 {nq} · 총 {n}건"
        if nr:
            return f"번역 중 {nr} · 총 {n}건"
        return f"대기 {nq}건"

    def is_translation_active(self) -> bool:
        """번역 큐에 대기/진행 작업이 있으면 True (하이라이트·프리뷰보다 우선)."""
        if self._is_running:
            return True
        for item in self._items:
            if item.get("status") in ("queued", "running"):
                return True
        return False

    def _pump_downstream_queues(self) -> None:
        """번역 1건 종료 직후 하이라이트·프리뷰가 대기를 풀고 진행하도록 펌핑."""
        try:
            from gui.models.highlight_queue_model import HighlightQueueController

            hq = HighlightQueueController.instance()
            if hq is not None:
                hq._pump()
        except Exception:
            pass
        try:
            from gui.models.preview_queue_model import PreviewQueueController

            pq = PreviewQueueController.instance()
            if pq is not None:
                pq._pump()
        except Exception:
            pass

    def _emit_count_and_state(self) -> None:
        self.countChanged.emit()
        self.stateChanged.emit()
        self._schedule_persist()

    def _schedule_persist(self) -> None:
        if not is_on_app_main_thread():
            QTimer.singleShot(0, self, self._schedule_persist)
            return
        self._persist_timer.start()

    def _flush_persist(self) -> None:
        try:
            if not self._items:
                clear_queue_state(PERSIST_NAME)
                return
            items = []
            for it in self._items:
                st = (it.get("status") or "").strip()
                if st in ("done",):
                    continue
                items.append(
                    {
                        "sku": (it.get("sku") or "").strip().upper(),
                        "video_path": str(it.get("video_path") or ""),
                        "status": st if st in ("queued", "running") else "queued",
                        "progress": int(it.get("progress") or 0),
                    }
                )
            if not items:
                clear_queue_state(PERSIST_NAME)
                return
            save_queue_state(PERSIST_NAME, {"items": items})
        except Exception as e:
            log_ts(f"[TranslationQueue] persist failed: {e}")

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
            norm: list[dict] = []
            for it in raw:
                if not isinstance(it, dict):
                    continue
                sku = (it.get("sku") or "").strip().upper()
                vp = str(it.get("video_path") or "")
                if not sku or not vp:
                    continue
                norm.append(
                    {
                        "sku": sku,
                        "video_path": vp,
                        "status": "queued",
                        "progress": 0,
                    }
                )
            if not norm:
                return
            self.beginResetModel()
            self._items = norm
            self._is_running = False
            self._active_workers.clear()
            self.endResetModel()
            self._emit_count_and_state()
            log_ts(f"[TranslationQueue] restored {len(norm)} item(s) from disk (이어서 하기로 진행)")
            # 재시작 직후 사용자가 이어하기를 누르지 않아도 큐가 자동으로 진행되도록
            QTimer.singleShot(500, self, self._process_next)
        except Exception as e:
            log_ts(f"[TranslationQueue] load persisted failed: {e}")

    @Slot()
    def resume(self) -> None:
        """앱 재시작 후 큐에 남은 항목을 이어서 처리."""
        # 실제 QThread가 돌고 있는데 큐만 초기화하면 동일 SKU로 워커가 중복 실행될 수 있음(크롤+번역 이중 실행·멈춘 것처럼 보임).
        if any(getattr(w, "isRunning", lambda: False)() for w in self._active_workers.values()):
            try:
                self.toastMessage.emit("번역이 진행 중입니다. 완료된 뒤 이어하기를 눌러주세요.", "warning")
            except Exception:
                pass
            return
        if self._is_running and self._active_workers:
            try:
                self.toastMessage.emit("번역 결과를 정리하는 중입니다. 잠시 후 다시 시도해주세요.", "info")
            except Exception:
                pass
            return
        if self._is_running and not self._active_workers:
            self._is_running = False
        for i, it in enumerate(self._items):
            if it.get("status") == "running":
                it["status"] = "queued"
                it["progress"] = 0
                self.dataChanged.emit(
                    self.index(i), self.index(i), [self.StatusRole, self.ProgressRole]
                )
        self.stateChanged.emit()
        self._active_workers.clear()
        self._is_running = False
        self._process_next()

    @Slot()
    def clearFinished(self) -> None:
        """
        UI의 '완료 제거' 버튼용.
        번역 큐는 완료 시 자동으로 리스트에서 제거되지만,
        남아있는 레거시/비정상 상태(또는 디스크 persist)를 정리할 수 있게 제공한다.
        """
        try:
            # in-memory: done 상태만 제거
            i = 0
            removed = 0
            while i < len(self._items):
                if (self._items[i].get("status") or "") == "done":
                    self.beginRemoveRows(QModelIndex(), i, i)
                    self._items.pop(i)
                    self.endRemoveRows()
                    removed += 1
                    continue
                i += 1
            # persisted queue는 done을 저장하지 않지만, 남아있는 파일 정리
            try:
                clear_queue_state(PERSIST_NAME)
            except Exception:
                pass
            self._emit_count_and_state()
            self.toastMessage.emit(f"번역 큐 정리 완료 ({removed}건)", "success")
        except Exception as e:
            self.toastMessage.emit(f"번역 큐 정리 실패: {e}", "error")
        QTimer.singleShot(0, self, lambda: QTimer.singleShot(500, self, self._process_next))
        self._schedule_persist()

    @Slot(str, str, bool)
    def enqueue(self, sku, video_path: str, force_rebuild: bool = False) -> None:
        """UI 스레드(컨트롤러의 스레드)가 아닌 곳(예: 수집 워커)에서 호출되면 메인에 위임한다."""
        s = (sku or "").strip().upper()
        vp = str(video_path or "")
        fr = bool(force_rebuild)
        if not is_on_app_main_thread():
            QTimer.singleShot(0, self, lambda s2=s, v2=vp, f2=fr: self._enqueue_on_main(s2, v2, f2))
            return
        self._enqueue_on_main(s, vp, fr)

    def _enqueue_on_main(self, sku: str, video_path: str, force_rebuild: bool = False) -> None:
        sku = (sku or "").strip().upper()
        # 중복 체크
        for item in self._items:
            if item["sku"] == sku:
                if force_rebuild and not item.get("force_rebuild"):
                    item["force_rebuild"] = True
                return

        start = len(self._items)
        self.beginInsertRows(QModelIndex(), start, start)
        self._items.append(
            {
                "sku": sku,
                "video_path": video_path,
                "status": "queued",
                "progress": 0,
                "force_rebuild": bool(force_rebuild),
            }
        )
        self.endInsertRows()
        self._emit_count_and_state()
        # 모델·타이머는 컨트롤러(메인) 스레드에만 둔다
        QTimer.singleShot(0, self, lambda: QTimer.singleShot(500, self, self._process_next))

    @Slot()
    def _process_next(self):
        # 데드락 방지: 플래그만 켜져 있고 추적 중인 워커가 없을 때만 리셋.
        # UI에 status=running 행이 남아 있으면 실제 스레드가 도는 중일 수 있어 여기서 리셋하면 중복 워커가 뜰 수 있음.
        _has_running_row = any((it.get("status") == "running") for it in self._items)
        if self._is_running and not self._active_workers and not _has_running_row:
            log_ts("[TranslationQueue] Deadlock detected. Resetting is_running flag.")
            self._is_running = False

        if self._is_running:
            return
            
        # 대기 중인 첫 번째 항목 찾기
        idx = -1
        for i, item in enumerate(self._items):
            if item["status"] == "queued":
                idx = i
                break
        
        if idx == -1:
            return
        
        self._is_running = True
        self._items[idx]["status"] = "running"
        self._items[idx]["progress"] = 50  # 시작하면 50%로 표시
        self.dataChanged.emit(
            self.index(idx), self.index(idx), [self.StatusRole, self.ProgressRole]
        )
        self.stateChanged.emit()

        item = self._items[idx]
        sku = item["sku"]
        vp = item["video_path"]
        
        log_ts(f"[TranslationQueue] Starting translation for: {sku}")
        
        worker = TranslationWorker(sku, vp, force_rebuild=bool(item.get("force_rebuild")))
        # 지연 cleanup으로 dict에만 남아 있는 종료된 워커 참조 제거
        for _k, _w in list(self._active_workers.items()):
            try:
                if not getattr(_w, "isRunning", lambda: False)():
                    del self._active_workers[_k]
            except Exception:
                pass
        self._active_workers[sku] = worker
        
        # 워커 종료 시 안전하게 정리
        worker.translationFinished.connect(
            lambda ok, msg, s=sku, w=worker: self._on_finished(s, ok, msg, w)
        )
        # 스레드가 완전히 끝난 뒤: dict 정리·좀비(running만 남은 경우) 재큐·다음 작업 예약
        worker.finished.connect(lambda s=sku, w=worker: self._on_worker_thread_exited(s, w))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_worker_thread_exited(self, sku: str, worker: TranslationWorker) -> None:
        """QThread 종료 시점. dict 정리만 하고, 결과 시그널이 없을 때만 running 행을 재큐한다.
        Qt 이벤트 순서상 finished 가 translationFinished 슬롯보다 먼저 올 수 있어 _translation_notified 로 구분한다."""
        try:
            if self._active_workers.get(sku) is worker:
                del self._active_workers[sku]
        except Exception:
            pass
        if getattr(worker, "_translation_notified", False):
            # 정상 경로: _on_finished 가 진행·다음 작업 예약을 담당
            return
        for i, it in enumerate(self._items):
            if it.get("sku") == sku and it.get("status") == "running":
                log_ts(f"[TranslationQueue] 스레드 종료 후에도 '{sku}'가 running — 재시도 큐로 복구합니다.")
                it["status"] = "queued"
                it["progress"] = 0
                self.dataChanged.emit(
                    self.index(i), self.index(i), [self.StatusRole, self.ProgressRole]
                )
                break
        self._is_running = False
        self.stateChanged.emit()
        QTimer.singleShot(0, self, lambda: QTimer.singleShot(500, self, self._process_next))

    def _on_finished(self, sku, success, msg, worker):
        self._is_running = False

        # 번역이 성공했다면 라이브러리 요약/상세 캐시를 즉시 갱신한다.
        # (라이브러리 화면은 self._all_summaries 기반이므로 DB 변경만으로 자동 반영되지 않을 수 있음)
        if bool(success):
            pc = (sku or "").strip().upper()
            def _refresh_library():
                try:
                    from gui.models.library_model import LibraryModel
                    lib = LibraryModel.instance()
                    if lib and pc:
                        lib.refreshProduct(pc)
                except Exception:
                    pass
            QTimer.singleShot(0, _refresh_library)

        # 리스트에서 해당 SKU 제거 (완료 시)
        for i, item in enumerate(self._items):
            if item["sku"] == sku:
                # 잠깐 100%로 표시 (시각적 완료감)
                self._items[i]["progress"] = 100
                self._items[i]["status"] = "done"
                self.dataChanged.emit(
                    self.index(i), self.index(i), [self.StatusRole, self.ProgressRole]
                )
                self.stateChanged.emit()
                
                # 지연 삭제 (리스트에서 제거)
                def _remove(idx=i):
                    if idx < len(self._items) and self._items[idx]["sku"] == sku:
                        self.beginRemoveRows(QModelIndex(), idx, idx)
                        self._items.pop(idx)
                        self.endRemoveRows()
                        self._emit_count_and_state()
                
                QTimer.singleShot(1000, _remove)
                break
        
        if not success:
            log_ts(f"❌ [TranslationQueue] Error ({sku}): {msg}")
            self.toastMessage.emit(f"번역 실패 ({sku}): {msg}", "error")
        else:
            log_ts(f"✅ [TranslationQueue] Finished: {sku}")
            # 스킵도 사용자에게 명확히 알린다.
            if (msg or "").startswith("번역 스킵"):
                try:
                    self.toastMessage.emit(f"{sku}: {msg}", "info")
                except Exception:
                    pass
        
        # 다음 작업 진행
        QTimer.singleShot(0, self, lambda: QTimer.singleShot(500, self, self._process_next))
        # 하이라이트/프리뷰는 번역이 비어갈 때까지 대기 — 번역 1건 완료 시마다 다운스트림 펌핑
        QTimer.singleShot(0, self, self._pump_downstream_queues)
