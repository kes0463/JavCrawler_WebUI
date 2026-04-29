"""라이브러리 상세 — 씬 목록 QAbstractListModel (편집 세션용)."""

from __future__ import annotations

import uuid

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, Slot

from javstory.library.canonical.schema import SceneEntry
from javstory.library.stills.time_range import parse_time_range


class SceneEditModel(QAbstractListModel):
    SceneIdRole = Qt.ItemDataRole.UserRole + 1
    TimeRangeRole = Qt.ItemDataRole.UserRole + 2
    SceneLabelRole = Qt.ItemDataRole.UserRole + 3
    SceneSummaryRole = Qt.ItemDataRole.UserRole + 4
    ToneRole = Qt.ItemDataRole.UserRole + 5
    KeyTagsRole = Qt.ItemDataRole.UserRole + 6

    _ROLE_MAP = {
        SceneIdRole: "scene_id",
        TimeRangeRole: "time_range",
        SceneLabelRole: "scene_label",
        SceneSummaryRole: "scene_summary",
        ToneRole: "tone",
        KeyTagsRole: "key_tags",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[dict[str, str]] = []

    def roleNames(self):
        return {
            self.SceneIdRole: b"sceneId",
            self.TimeRangeRole: b"timeRange",
            self.SceneLabelRole: b"sceneLabel",
            self.SceneSummaryRole: b"sceneSummary",
            self.ToneRole: b"tone",
            self.KeyTagsRole: b"keyTags",
        }

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    @Slot(result=int)
    def entryCount(self) -> int:
        return len(self._rows)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._rows):
            return None
        row = self._rows[index.row()]
        key = self._ROLE_MAP.get(role)
        if key:
            return row.get(key, "") or ""
        return None

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or index.row() >= len(self._rows):
            return False
        key = self._ROLE_MAP.get(role)
        if not key:
            return False
        v = "" if value is None else str(value)
        self._rows[index.row()][key] = v
        self.dataChanged.emit(index, index, [role])
        return True

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable

    def load_entries(self, scenes: list[SceneEntry]) -> None:
        self.beginResetModel()
        self._rows = []
        seen: set[str] = set()
        for s in scenes:
            sid = (s.scene_id or "").strip() or self._gen_id(seen)
            seen.add(sid)
            tags = ", ".join(s.key_tags) if s.key_tags else ""
            self._rows.append(
                {
                    "scene_id": sid,
                    "time_range": s.time_range or "",
                    "scene_label": s.scene_label or "",
                    "scene_summary": s.scene_summary or "",
                    "tone": s.tone or "",
                    "key_tags": tags,
                }
            )
        self.endResetModel()

    def _gen_id(self, seen: set[str]) -> str:
        for _ in range(64):
            cand = f"manual_{uuid.uuid4().hex[:10]}"
            if cand not in seen:
                return cand
        return f"manual_{uuid.uuid4().hex}"

    def to_entries(self) -> list[SceneEntry]:
        out: list[SceneEntry] = []
        seen: set[str] = set()
        for r in self._rows:
            sid = (r.get("scene_id") or "").strip() or self._gen_id(seen)
            while sid in seen:
                sid = f"{sid}_{uuid.uuid4().hex[:4]}"
            seen.add(sid)

            tr = (r.get("time_range") or "").strip()
            tags_raw = (r.get("key_tags") or "").strip()
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

            a, b = parse_time_range(tr)
            start_sec = a
            end_sec = b
            if start_sec is not None and end_sec is not None and start_sec > end_sec:
                start_sec, end_sec = end_sec, start_sec

            out.append(
                SceneEntry(
                    scene_id=sid,
                    time_range=tr,
                    scene_label=(r.get("scene_label") or "").strip(),
                    scene_summary=(r.get("scene_summary") or "").strip(),
                    tone=(r.get("tone") or "").strip(),
                    key_tags=tags,
                    time_label=tr,
                    start_sec=start_sec,
                    end_sec=end_sec,
                    still_paths=[],
                    locked_fields=set(),
                    needs_still_refresh=False,
                )
            )
        return out

    @Slot()
    def appendEmptyRow(self):
        seen = {str(x.get("scene_id", "")).strip() for x in self._rows}
        sid = self._gen_id(seen)
        n = len(self._rows)
        self.beginInsertRows(QModelIndex(), n, n)
        self._rows.append(
            {
                "scene_id": sid,
                "time_range": "",
                "scene_label": "",
                "scene_summary": "",
                "tone": "",
                "key_tags": "",
            }
        )
        self.endInsertRows()

    @Slot(int)
    def removeRowAt(self, row: int):
        r = int(row)
        if r < 0 or r >= len(self._rows):
            return
        self.beginRemoveRows(QModelIndex(), r, r)
        del self._rows[r]
        self.endRemoveRows()

    @Slot(int, str, str)
    def setField(self, row: int, qml_field: str, value: str) -> None:
        """QML delegate에서 필드 갱신 (sceneId, timeRange, sceneLabel, sceneSummary, tone, keyTags)."""
        r = int(row)
        if r < 0 or r >= len(self._rows):
            return
        key = {
            "sceneId": "scene_id",
            "timeRange": "time_range",
            "sceneLabel": "scene_label",
            "sceneSummary": "scene_summary",
            "tone": "tone",
            "keyTags": "key_tags",
        }.get((qml_field or "").strip())
        if not key:
            return
        v = "" if value is None else str(value)
        self._rows[r][key] = v
        ix = self.index(r, 0)
        self.dataChanged.emit(ix, ix)
