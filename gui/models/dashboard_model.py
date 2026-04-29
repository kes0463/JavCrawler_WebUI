"""대시보드 모델: GPU/CPU/메모리 모니터링 + 대기 큐."""

from __future__ import annotations

import subprocess
from PySide6.QtCore import (
    QObject, QTimer, Property, Signal, Slot,
    QAbstractListModel, QModelIndex, Qt,
)


class PendingQueueModel(QAbstractListModel):
    SkuRole = Qt.ItemDataRole.UserRole + 1
    TitleRole = Qt.ItemDataRole.UserRole + 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[dict] = []

    def roleNames(self):
        return {
            self.SkuRole: b"sku",
            self.TitleRole: b"title",
        }

    def rowCount(self, parent=QModelIndex()):
        return len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self._items[index.row()]
        if role == self.SkuRole:
            return item["sku"]
        if role == self.TitleRole:
            return item["title"]
        return None

    def refresh(self, items: list[dict]):
        self.beginResetModel()
        self._items = items
        self.endResetModel()


class DashboardModel(QObject):
    gpuNameChanged = Signal()
    gpuUsagePercentChanged = Signal()
    gpuTotalChanged = Signal()
    gpuUsedChanged = Signal()
    cpuPercentChanged = Signal()
    memPercentChanged = Signal()
    memUsedChanged = Signal()
    memTotalChanged = Signal()
    pendingCountChanged = Signal()
    logMessage = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._gpu_name = ""
        self._gpu_usage_percent = 0
        self._gpu_total = 0.0
        self._gpu_used = 0.0
        self._cpu_percent = 0
        self._mem_percent = 0
        self._mem_used = 0.0
        self._mem_total = 0.0

        self._pending_model = PendingQueueModel(self)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(3000)
        QTimer.singleShot(500, self._poll)

    # ── Properties ────────────────────────────────────

    @Property(str, notify=gpuNameChanged)
    def gpuName(self):
        return self._gpu_name

    @Property(int, notify=gpuUsagePercentChanged)
    def gpuUsagePercent(self):
        return self._gpu_usage_percent

    @Property(float, notify=gpuTotalChanged)
    def gpuTotal(self):
        return self._gpu_total

    @Property(float, notify=gpuUsedChanged)
    def gpuUsed(self):
        return self._gpu_used

    @Property(int, notify=cpuPercentChanged)
    def cpuPercent(self):
        return self._cpu_percent

    @Property(int, notify=memPercentChanged)
    def memPercent(self):
        return self._mem_percent

    @Property(float, notify=memUsedChanged)
    def memUsed(self):
        return self._mem_used

    @Property(float, notify=memTotalChanged)
    def memTotal(self):
        return self._mem_total

    @Property(int, notify=pendingCountChanged)
    def pendingCount(self):
        return self._pending_model.rowCount()

    @Property(QObject, constant=True)
    def pendingQueue(self):
        return self._pending_model

    # ── Polling ───────────────────────────────────────

    def _poll(self):
        self._poll_gpu()
        self._poll_cpu()
        self._poll_queue()

    def _poll_gpu(self):
        try:
            out = subprocess.check_output(
                "nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,nounits,noheader",
                shell=True,
            ).decode().strip()
            parts = [p.strip() for p in out.split(",")]
            name = parts[0]
            total = float(parts[1])
            used = float(parts[2])
            pct = int(used / total * 100) if total else 0

            if name != self._gpu_name:
                self._gpu_name = name
                self.gpuNameChanged.emit()
            if pct != self._gpu_usage_percent:
                self._gpu_usage_percent = pct
                self.gpuUsagePercentChanged.emit()
            gb_total = total / 1024
            gb_used = used / 1024
            if abs(gb_total - self._gpu_total) > 0.01:
                self._gpu_total = gb_total
                self.gpuTotalChanged.emit()
            if abs(gb_used - self._gpu_used) > 0.01:
                self._gpu_used = gb_used
                self.gpuUsedChanged.emit()
        except Exception:
            if self._gpu_name != "N/A":
                self._gpu_name = "N/A"
                self.gpuNameChanged.emit()

    def _poll_cpu(self):
        try:
            import psutil
            cpu = int(psutil.cpu_percent(interval=0))
            mem = psutil.virtual_memory()
            if cpu != self._cpu_percent:
                self._cpu_percent = cpu
                self.cpuPercentChanged.emit()
            mp = int(mem.percent)
            if mp != self._mem_percent:
                self._mem_percent = mp
                self.memPercentChanged.emit()
            mu = round(mem.used / (1024 ** 3), 1)
            mt = round(mem.total / (1024 ** 3), 1)
            if abs(mu - self._mem_used) > 0.05:
                self._mem_used = mu
                self.memUsedChanged.emit()
            if abs(mt - self._mem_total) > 0.05:
                self._mem_total = mt
                self.memTotalChanged.emit()
        except ImportError:
            pass

    def _poll_queue(self):
        try:
            from javstory.harvest.database import get_db_session, JAVMetadata
            session = get_db_session()
            try:
                # 3초마다 full-scan은 부담이 큼: 필요한 컬럼만 + 상한 + 최신순 정렬
                rows = (
                    session.query(JAVMetadata.product_code, JAVMetadata.title)
                    .filter_by(analysis_status="pending")
                    .order_by(JAVMetadata.updated_at.desc())
                    .limit(200)
                    .all()
                )
                items = [{"sku": (pc or ""), "title": (title or pc or "")[:60]} for pc, title in (rows or [])]
            finally:
                session.close()
            old_count = self._pending_model.rowCount()
            self._pending_model.refresh(items)
            if len(items) != old_count:
                self.pendingCountChanged.emit()
        except Exception:
            pass

    @Slot(str)
    def cancelPending(self, sku: str) -> None:
        """대기 중인 수집 작업을 취소(DB 상태 변경)."""
        try:
            from javstory.harvest.database import get_db_session, JAVMetadata
            session = get_db_session()
            try:
                row = session.query(JAVMetadata).filter_by(product_code=sku).first()
                if row:
                    row.analysis_status = "none"
                    session.commit()
                    self.logMessage.emit(f"[Dashboard] cancelled pending task: {sku}")
            finally:
                session.close()
            self._poll_queue()
        except Exception as e:
            self.logMessage.emit(f"[Dashboard] failed to cancel {sku}: {e}")

    @Slot()
    def clearAllPending(self) -> None:
        """모든 대기 중인 수집 작업을 취소."""
        try:
            from javstory.harvest.database import get_db_session, JAVMetadata
            session = get_db_session()
            try:
                rows = session.query(JAVMetadata).filter_by(analysis_status="pending").all()
                for row in rows:
                    row.analysis_status = "none"
                session.commit()
                self.logMessage.emit(f"[Dashboard] cleared all {len(rows)} pending tasks")
            finally:
                session.close()
            self._poll_queue()
        except Exception as e:
            self.logMessage.emit(f"[Dashboard] failed to clear pending: {e}")
