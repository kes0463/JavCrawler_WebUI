"""폴더 탐색기 모델: Windows 11 스타일 폴더 다중 선택 UI를 위한 백엔드."""

from __future__ import annotations

import os
import time
from pathlib import Path
import psutil

from PySide6.QtCore import (
    QObject, Property, Signal, Slot,
    QAbstractListModel, QModelIndex, Qt
)


class FolderItemModel(QAbstractListModel):
    """폴더 목록을 QML에 노출하는 리스트 모델."""
    NameRole = Qt.ItemDataRole.UserRole + 1
    PathRole = Qt.ItemDataRole.UserRole + 2
    ModifiedRole = Qt.ItemDataRole.UserRole + 3
    IsSelectedRole = Qt.ItemDataRole.UserRole + 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[dict] = []

    def roleNames(self):
        return {
            self.NameRole: b"name",
            self.PathRole: b"path",
            self.ModifiedRole: b"modified",
            self.IsSelectedRole: b"isSelected"
        }

    def rowCount(self, parent=QModelIndex()):
        return len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        item = self._items[index.row()]
        if role == self.NameRole: return item["name"]
        if role == self.PathRole: return item["path"]
        if role == self.ModifiedRole:
            # 포맷팅된 시간 반환
            mod = item["modified"]
            return time.strftime("%Y-%m-%d %H:%M", time.localtime(mod))
        if role == self.IsSelectedRole: return item["isSelected"]
        return None

    def updateItems(self, items: list[dict]):
        self.beginResetModel()
        self._items = items
        self.endResetModel()

    def setItemSelected(self, row: int, selected: bool):
        if 0 <= row < len(self._items):
            self._items[row]["isSelected"] = selected
            idx = self.index(row, 0)
            self.dataChanged.emit(idx, idx, [self.IsSelectedRole])


class FolderExplorerModel(QObject):
    """폴더 탐색기 메인 모델: 네비게이션, 히스토리, 다중 선택 관리."""
    currentPathChanged = Signal()
    canGoBackChanged = Signal()
    canGoForwardChanged = Signal()
    selectionCountChanged = Signal()
    viewModeChanged = Signal()
    folderConfirmed = Signal(list)  # list[str]

    def __init__(self, parent=None):
        super().__init__(parent)
        # 초기 경로는 홈 디렉토리
        self._current_path = str(Path.home().resolve())
        self._history = [self._current_path]
        self._history_index = 0
        self._selected_paths: set[str] = set()
        self._view_mode = 0  # 0: 큰 아이콘, 1: 목록(자세히)
        
        self._drives_cache = self._get_drives()
        self._favorites_cache = self._get_favorites()
        
        self._folder_model = FolderItemModel(self)
        self._refresh_model()

    # ── Properties ────────────────────────────────────

    @Property(str, notify=currentPathChanged)
    def currentPath(self):
        return self._current_path

    @Property(bool, notify=canGoBackChanged)
    def canGoBack(self):
        return self._history_index > 0

    @Property(bool, notify=canGoForwardChanged)
    def canGoForward(self):
        return self._history_index < len(self._history) - 1

    @Property(int, notify=selectionCountChanged)
    def selectionCount(self):
        return len(self._selected_paths)

    @Property(int, notify=viewModeChanged)
    def viewMode(self):
        return self._view_mode

    @viewMode.setter
    def viewMode(self, v: int):
        if self._view_mode != v:
            self._view_mode = v
            self.viewModeChanged.emit()

    @Property(QObject, constant=True)
    def folderModel(self):
        return self._folder_model

    @Property(list, constant=True)
    def drives(self):
        return self._drives_cache

    @Property(list, constant=True)
    def favorites(self):
        return self._favorites_cache

    def _get_drives(self):
        """시스템 드라이브 목록 반환 (캐싱용)."""
        res = []
        try:
            # psutil.disk_partitions(all=False)는 실제 마운트된 드라이브만 가져옴
            for part in psutil.disk_partitions(all=False):
                if 'cdrom' in part.opts or part.fstype == '':
                    continue
                res.append({
                    "name": part.device.rstrip('\\'),
                    "path": str(Path(part.mountpoint).resolve()),
                    "label": f"Local Disk ({part.device.rstrip('\\')})"
                })
        except Exception:
            pass
        return res

    def _get_favorites(self):
        """자주 가기 목록 (캐싱용)."""
        home = Path.home()
        items = [
            {"name": "Home", "path": str(home.resolve()), "icon": "🏠"},
            {"name": "Desktop", "path": str((home / "Desktop").resolve()), "icon": "💻"},
            {"name": "Downloads", "path": str((home / "Downloads").resolve()), "icon": "📥"},
            {"name": "Documents", "path": str((home / "Documents").resolve()), "icon": "📄"},
            {"name": "Pictures", "path": str((home / "Pictures").resolve()), "icon": "🖼️"},
            {"name": "Videos", "path": str((home / "Videos").resolve()), "icon": "🎬"},
        ]
        return [i for i in items if Path(i["path"]).is_dir()]

    # ── Slots ─────────────────────────────────────────

    @Slot(str)
    def cdInto(self, path: str):
        """특정 폴더로 이동."""
        try:
            p = Path(path).resolve()
            if not p.is_dir():
                return
            
            path_str = str(p)
            if path_str == self._current_path:
                return

            # 히스토리 중간에서 이동 시 이후 분기 삭제
            if self._history_index < len(self._history) - 1:
                self._history = self._history[:self._history_index + 1]
            
            self._history.append(path_str)
            self._history_index += 1
            self._current_path = path_str
            
            self._refresh_model()
            self._emit_nav_signals()
        except Exception:
            pass

    @Slot()
    def goBack(self):
        """뒤로 가기."""
        if self._history_index > 0:
            self._history_index -= 1
            self._current_path = self._history[self._history_index]
            self._refresh_model()
            self._emit_nav_signals()

    @Slot()
    def goForward(self):
        """앞으로 가기."""
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self._current_path = self._history[self._history_index]
            self._refresh_model()
            self._emit_nav_signals()

    @Slot()
    def goUp(self):
        """상위 폴더로 이동."""
        p = Path(self._current_path).parent
        if p != Path(self._current_path):
            self.cdInto(str(p))

    @Slot(int)
    def toggleSelection(self, row: int):
        """항목 선택 토글."""
        if row < 0 or row >= self._folder_model.rowCount():
            return
            
        item = self._folder_model._items[row]
        path = item["path"]
        
        if path in self._selected_paths:
            self._selected_paths.remove(path)
            self._folder_model.setItemSelected(row, False)
        else:
            self._selected_paths.add(path)
            self._folder_model.setItemSelected(row, True)
            
        self.selectionCountChanged.emit()

    @Slot()
    def clearSelection(self):
        """선택 해제."""
        self._selected_paths.clear()
        for i in range(self._folder_model.rowCount()):
            self._folder_model.setItemSelected(i, False)
        self.selectionCountChanged.emit()

    @Slot()
    def confirmSelection(self):
        """선택 완료 시그널 발생."""
        paths = sorted(list(self._selected_paths))
        self.folderConfirmed.emit(paths)

    # ── Internal ──────────────────────────────────────

    def _refresh_model(self):
        """현재 경로의 폴더 목록 갱신."""
        items = []
        try:
            with os.scandir(self._current_path) as it:
                for entry in it:
                    try:
                        if entry.is_dir():
                            full_path = str(Path(entry.path).resolve())
                            items.append({
                                "name": entry.name,
                                "path": full_path,
                                "modified": entry.stat().st_mtime,
                                "isSelected": full_path in self._selected_paths
                            })
                    except (PermissionError, OSError):
                        continue
            # 이름 순 정렬
            items.sort(key=lambda x: x["name"].lower())
        except Exception:
            pass
        self._folder_model.updateItems(items)

    def _emit_nav_signals(self):
        self.currentPathChanged.emit()
        self.canGoBackChanged.emit()
        self.canGoForwardChanged.emit()
