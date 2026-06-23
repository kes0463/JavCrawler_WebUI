"""ActressModel for JAVSTORY QML integration.

Exposes actress profile CRUD, image management, alias handling to QML.
Follows patterns from LibraryModel and settings_model.py.
"""

from PySide6.QtCore import (
    QObject, Property, Signal, Slot, QAbstractListModel, QModelIndex, Qt, QThread, QTimer
)
from typing import Any, List, Dict, Optional
import json
from pathlib import Path
from datetime import datetime, date

from javstory.config.app_config import DATA_ROOT
from javstory.harvest.database import get_db_session, Actress, ActressImage, ActressAlias
from javstory.utils.actress_profile import (
    save_actress_image,
    add_alias,
    resolve_actress_by_name,
    merge_actresses,
    aggregate_work_genres,
    batch_actress_work_counts,
    fetch_actress_library_works,
    load_actress_media,
    promote_gallery_image_to_profile,
    resolve_actress_media_path,
    rebuild_actress_works_for_actress,
    _format_debut_ym,
)

_PROFILE_NAME_KEYS = frozenset({
    "name_ko", "name_ja", "name_en", "korean", "japanese", "romaji",
})
import json  # for any serialization needs


def _normalize_local_path(file_path: str) -> str:
    s = (file_path or "").strip()
    if not s:
        return ""
    if s.lower().startswith("file:"):
        from PySide6.QtCore import QUrl
        local = QUrl(s).toLocalFile()
        return local or s
    return s


def _resolve_data_path(path: str) -> str:
    return resolve_actress_media_path(path)


_DATE_FIELDS = frozenset({"birth_date", "debut_date", "last_watched"})
_INT_FIELDS = frozenset({"height", "bust", "waist", "hip"})
_FLOAT_FIELDS = frozenset({"user_score", "favorite_intensity"})


def _parse_profile_date(value: Any) -> Optional[date]:
    """QML/문자열 입력 → Python date (SQLite Date 컬럼용)."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value).strip()
    if not s:
        return None
    if len(s) >= 10 and s[4:5] == "-" and s[7:8] == "-":
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            pass
    if len(s) >= 7 and s[4:5] == "-":
        try:
            return date(int(s[:4]), int(s[5:7]), 1)
        except ValueError:
            pass
    return None


def _coerce_profile_field(key: str, value: Any) -> Any:
    if key in _DATE_FIELDS:
        return _parse_profile_date(value)
    if key in _INT_FIELDS:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if key in _FLOAT_FIELDS:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        s = value.strip()
        return s if s else None
    return value


def _apply_profile_updates(actress: Actress, data: Dict) -> None:
    payload = dict(data) if data else {}
    for key, raw_value in payload.items():
        if not hasattr(actress, key) or key in ("id", "created_at", "updated_at"):
            continue
        setattr(actress, key, _coerce_profile_field(key, raw_value))

    if "name_ja" in payload:
        actress.japanese = actress.name_ja
    if "name_ko" in payload:
        actress.korean = actress.name_ko


class ActressListModel(QAbstractListModel):
    """List model for actress grid cards."""
    IdRole = Qt.UserRole + 1
    NameKoRole = Qt.UserRole + 2
    NameJaRole = Qt.UserRole + 3
    ProfileImageRole = Qt.UserRole + 4
    UserScoreRole = Qt.UserRole + 5
    IsFavoriteRole = Qt.UserRole + 6
    GenresRole = Qt.UserRole + 7
    WorkCountRole = Qt.UserRole + 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self._actresses: List[Dict] = []

    def roleNames(self) -> Dict[int, bytes]:
        return {
            self.IdRole: b"id",
            self.NameKoRole: b"nameKo",
            self.NameJaRole: b"nameJa",
            self.ProfileImageRole: b"profileImage",
            self.UserScoreRole: b"userScore",
            self.IsFavoriteRole: b"isFavorite",
            self.GenresRole: b"genres",
            self.WorkCountRole: b"workCount",
        }

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._actresses)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= len(self._actresses):
            return None
        item = self._actresses[index.row()]
        if role == self.IdRole:
            return item.get("id", 0)
        if role == self.NameKoRole:
            return item.get("name_ko", "")
        if role == self.NameJaRole:
            return item.get("name_ja", "") or item.get("japanese", "")
        if role == self.ProfileImageRole:
            return item.get("profile_image_url", "")
        if role == self.UserScoreRole:
            return float(item.get("user_score") or 0.0)
        if role == self.IsFavoriteRole:
            return bool(item.get("is_favorite", False))
        if role == self.GenresRole:
            return item.get("genres", "")
        if role == self.WorkCountRole:
            return int(item.get("work_count") or 0)
        return None

    def set_actresses(self, actresses: List[Dict]):
        self.beginResetModel()
        self._actresses = actresses
        self.endResetModel()

    def update_item(self, actress_id: int, item: Dict) -> bool:
        """목록에서 해당 배우 카드만 갱신 (전체 reset 없음)."""
        target_id = int(actress_id or 0)
        if target_id <= 0:
            return False
        for i, existing in enumerate(self._actresses):
            if int(existing.get("id") or 0) != target_id:
                continue
            self._actresses[i] = dict(item)
            idx = self.index(i)
            self.dataChanged.emit(idx, idx, [])
            return True
        return False


class _ActressWorksSortWorker(QThread):
    """작품수 정렬 — 메타데이터 전체 스캔을 UI 스레드 밖에서 수행."""

    finished = Signal(list)
    error = Signal(str)

    def __init__(self, query: str, ascending: bool, parent=None):
        super().__init__(parent)
        self._query = query
        self._ascending = ascending

    def run(self):
        try:
            from sqlalchemy.orm import joinedload

            session = get_db_session()
            try:
                qry = session.query(Actress).options(joinedload(Actress.aliases))
                qry = ActressModel._apply_search_filter(qry, self._query)
                rows = qry.all()
                counts = batch_actress_work_counts(session, rows)
                rows.sort(
                    key=lambda r: (counts.get(r.id, 0), (r.name_ko or r.korean or "")),
                    reverse=not self._ascending,
                )
                self.finished.emit(
                    ActressModel._rows_to_list_items(rows, counts)
                )
            finally:
                session.close()
        except Exception as e:
            self.error.emit(str(e))


class _ActressListReloadWorker(QThread):
    """배우 목록 로드 — DB 조회·정렬을 UI 스레드 밖에서 수행."""

    finished = Signal(list)
    error = Signal(str)

    def __init__(self, sort: str, ascending: bool, query: str, parent=None):
        super().__init__(parent)
        self._sort = sort
        self._ascending = ascending
        self._query = query

    def run(self):
        try:
            from sqlalchemy.orm import joinedload

            session = get_db_session()
            try:
                qry = session.query(Actress).options(joinedload(Actress.aliases))
                qry = ActressModel._apply_search_filter(qry, self._query)
                counts = None
                if self._sort == "works" and ActressModel._work_count_sort_available(session):
                    qry = ActressModel._apply_work_count_order(qry, self._ascending)
                    rows = qry.all()
                else:
                    rows = qry.all()
                    if self._sort == "works":
                        counts = batch_actress_work_counts(session, rows)
                    rows = ActressModel._order_actress_rows(
                        session, rows, self._sort, self._ascending
                    )
                self.finished.emit(
                    ActressModel._rows_to_list_items(rows, counts)
                )
            finally:
                session.close()
        except Exception as e:
            self.error.emit(str(e))


class _ActressProfileLoadWorker(QThread):
    """배우 상세 프로필 + 미디어 경로 수집."""

    finished = Signal(int, "QVariantMap")
    error = Signal(str)

    def __init__(self, actress_id: int, parent=None):
        super().__init__(parent)
        self._actress_id = int(actress_id or 0)

    def run(self):
        aid = self._actress_id
        if aid <= 0:
            self.error.emit("invalid actress id")
            return
        try:
            session = get_db_session()
            try:
                row = session.query(Actress).filter_by(id=aid).first()
                if not row:
                    self.error.emit("not found")
                    return

                profile = {
                    "id": row.id,
                    "name_ja": row.name_ja or row.japanese or "",
                    "name_ko": row.name_ko or row.korean or "",
                    "name_en": getattr(row, "name_en", "") or "",
                    "romaji": getattr(row, "romaji", "") or "",
                    "profile_image_url": _resolve_data_path(getattr(row, "profile_image_url", "") or ""),
                    "genres": getattr(row, "genres", "") or "",
                    "user_score": getattr(row, "user_score", 0.0) or 0.0,
                    "profile_text": getattr(row, "profile_text", "") or "",
                    "birth_date": str(getattr(row, "birth_date", "")) if getattr(row, "birth_date", None) else "",
                    "height": getattr(row, "height", 0) or 0,
                    "bust": getattr(row, "bust", 0) or 0,
                    "waist": getattr(row, "waist", 0) or 0,
                    "hip": getattr(row, "hip", 0) or 0,
                    "cup_size": getattr(row, "cup_size", "") or "",
                    "debut_date": _format_debut_ym(getattr(row, "debut_date", None)),
                    "debut_date_raw": str(getattr(row, "debut_date", "")) if getattr(row, "debut_date", None) else "",
                    "agency": getattr(row, "agency", "") or "",
                    "is_favorite": bool(getattr(row, "is_favorite", False)),
                    "favorite_intensity": getattr(row, "favorite_intensity", 0.0) or 0.0,
                    "strong_reaction_count": getattr(row, "strong_reaction_count", 0),
                    "watch_count": getattr(row, "watch_count", 0),
                    "last_watched": str(getattr(row, "last_watched", "")) if getattr(row, "last_watched", None) else "",
                    "memo": getattr(row, "memo", "") or "",
                    "aliases": [],
                }

                media = load_actress_media(aid)
                profile["profile_image_url"] = _resolve_data_path(media.get("profile_image_url") or "")
                profile["gallery_images"] = [
                    {
                        **img,
                        "image_url": _resolve_data_path(img.get("image_url") or ""),
                        "thumb_url": _resolve_data_path(
                            img.get("thumb_url") or img.get("image_url") or ""
                        ),
                    }
                    for img in (media.get("gallery_images") or [])
                ]
                profile["images"] = profile["gallery_images"]

                for alias in row.aliases or []:
                    profile["aliases"].append({
                        "alias_id": alias.alias_id,
                        "alias_name": alias.alias_name,
                        "alias_type": alias.alias_type or "stage",
                        "is_primary": alias.is_primary,
                    })

                self.finished.emit(aid, profile)
            finally:
                session.close()
        except Exception as e:
            self.error.emit(str(e))


class _ActressLibraryBundleWorker(QThread):
    """출연작 + 장르 집계."""

    finished = Signal(int, "QVariantMap")
    error = Signal(str)

    def __init__(self, actress_id: int, parent=None):
        super().__init__(parent)
        self._actress_id = int(actress_id or 0)

    def run(self):
        aid = self._actress_id
        if aid <= 0:
            self.finished.emit(aid, {"works": [], "genres": []})
            return
        try:
            session = get_db_session()
            try:
                from sqlalchemy.orm import joinedload
                from javstory.harvest.database import WatchHistory

                actress = (
                    session.query(Actress)
                    .options(joinedload(Actress.aliases))
                    .filter_by(id=aid)
                    .first()
                )
                if not actress:
                    self.finished.emit(aid, {"works": [], "genres": []})
                    return

                items = fetch_actress_library_works(session, actress)
                if items:
                    codes = [it["product_code"] for it in items]
                    watch_rows = session.query(WatchHistory).filter(
                        WatchHistory.product_code.in_(codes)
                    ).all()
                    watch_by_pc: dict[str, WatchHistory] = {}
                    for wh in watch_rows:
                        key = (wh.product_code or "").strip().upper()
                        if key:
                            watch_by_pc[key] = wh
                    for it in items:
                        wh = watch_by_pc.get(it["product_code"].upper())
                        rating = int(wh.rating or 0) if wh else 0
                        it["user_rating"] = rating
                        it["userRating"] = rating
                        it["user_liked"] = bool(wh.liked) if wh else False

                self.finished.emit(
                    aid,
                    {
                        "works": items,
                        "genres": aggregate_work_genres(items),
                    },
                )
            finally:
                session.close()
        except Exception as e:
            self.error.emit(str(e))


class _ActressWorksRebuildWorker(QThread):
    """이름·별명 변경 후 actress_works 재구축."""

    finished = Signal(int, int)

    def __init__(self, actress_id: int, *, source: str = "profile", parent=None):
        super().__init__(parent)
        self._actress_id = int(actress_id or 0)
        self._source = source

    def run(self):
        aid = self._actress_id
        if aid <= 0:
            self.finished.emit(aid, 0)
            return
        try:
            session = get_db_session()
            try:
                added = rebuild_actress_works_for_actress(session, aid, source=self._source)
                session.commit()
                self.finished.emit(aid, int(added or 0))
            finally:
                session.close()
        except Exception:
            self.finished.emit(aid, -1)


class ActressModel(QObject):
    """Main model for actress profiles. Exposed to QML."""

    # Signals
    actressListChanged = Signal()
    currentProfileChanged = Signal()
    sortStateChanged = Signal()
    toastMessage = Signal(str, str)  # message, level (success/info/warning/error)
    errorOccurred = Signal(str)
    libraryWorksBundleReady = Signal(int, "QVariantMap")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._list_model = ActressListModel(self)
        self._current_profile: Dict = {}
        self._is_loading = False
        self._works_sort_worker: _ActressWorksSortWorker | None = None
        self._list_reload_worker: _ActressListReloadWorker | None = None
        self._profile_load_worker: _ActressProfileLoadWorker | None = None
        self._library_bundle_worker: _ActressLibraryBundleWorker | None = None
        self._works_rebuild_worker: _ActressWorksRebuildWorker | None = None
        self._profile_load_token = 0
        self._library_bundle_token = 0
        self._sort_key = "name"
        self._sort_ascending = True
        self._filter_query = ""
        self._list_dirty = True
        self._actress_tab_visited = False

    @Property(QObject, constant=True)
    def listModel(self) -> ActressListModel:
        return self._list_model

    @Property("QVariantMap", notify=currentProfileChanged)
    def currentProfile(self) -> Dict:
        return self._current_profile

    @Property(bool, notify=actressListChanged)
    def isLoading(self) -> bool:
        return self._is_loading

    @Property(str, notify=sortStateChanged)
    def sortKey(self) -> str:
        return self._current_sort

    @Property(bool, notify=sortStateChanged)
    def sortAscending(self) -> bool:
        return self._current_sort_ascending

    _SORT_KEYS = ("name", "works", "favorite", "score", "recent")

    @staticmethod
    def _effective_user_score(row) -> float:
        """목록·정렬용 점수 — 상세 '관심도'와 수동 '시청 점수' 통합."""
        intensity = getattr(row, "favorite_intensity", None)
        manual = getattr(row, "user_score", None)
        if intensity is not None and float(intensity or 0) > 0:
            return float(intensity)
        if manual is not None and float(manual or 0) > 0:
            return float(manual)
        return 0.0

    @staticmethod
    def _effective_user_score_from_dict(data: Dict) -> float:
        intensity = (data or {}).get("favorite_intensity")
        manual = (data or {}).get("user_score")
        if intensity is not None and float(intensity or 0) > 0:
            return float(intensity)
        if manual is not None and float(manual or 0) > 0:
            return float(manual)
        return 0.0

    @staticmethod
    def _actress_recent_key(row) -> tuple:
        """최근추가 정렬 — updated_at 우선, 없으면 created_at, 마지막으로 id."""
        updated = getattr(row, "updated_at", None)
        created = getattr(row, "created_at", None)
        ts = updated or created
        row_id = int(getattr(row, "id", 0) or 0)
        if ts is not None:
            return (ts, row_id)
        return (datetime.min, row_id)

    @staticmethod
    def _profile_to_list_item(profile: Dict) -> Dict:
        return {
            "id": int(profile.get("id") or 0),
            "name_ko": profile.get("name_ko") or "",
            "name_ja": profile.get("name_ja") or "",
            "japanese": profile.get("name_ja") or profile.get("japanese") or "",
            "profile_image_url": profile.get("profile_image_url") or "",
            "user_score": ActressModel._effective_user_score_from_dict(profile),
            "is_favorite": bool(profile.get("is_favorite", False)),
            "genres": profile.get("genres") or "",
        }

    def _patch_list_item_from_current_profile(self) -> bool:
        """상세 프로필 로드 결과를 목록 카드 한 장에만 반영."""
        profile = self._current_profile or {}
        actress_id = int(profile.get("id") or 0)
        if actress_id <= 0:
            return False
        return self._list_model.update_item(
            actress_id, self._profile_to_list_item(profile)
        )

    def _profile_update_affects_sort(self, payload: Dict) -> bool:
        """현재 정렬 기준에 영향을 주는 필드가 바뀌면 전체 목록 재정렬이 필요."""
        keys = set((payload or {}).keys())
        sort = self._current_sort
        if sort == "name" and keys & {"name_ko", "name_ja", "korean", "japanese"}:
            return True
        if sort == "score" and keys & {"user_score", "favorite_intensity"}:
            return True
        if sort == "favorite" and keys & {"is_favorite", "favorite_intensity"}:
            return True
        if sort == "recent" and keys:
            return True
        if sort == "works" and keys & _PROFILE_NAME_KEYS:
            return True
        return False

    def _sync_list_after_profile_change(self, actress_id: int, payload: Dict) -> None:
        """프로필 저장 후 목록 동기화 — 정렬 영향 시 전체 reload, 아니면 카드 1개만."""
        if self._profile_update_affects_sort(payload):
            self._refresh_list()
        else:
            if not self._patch_list_item_from_current_profile():
                self._mark_list_dirty()

    @staticmethod
    def _row_work_count(row, counts: dict | None = None) -> int:
        if counts is not None:
            return int(counts.get(row.id, 0) or 0)
        return int(getattr(row, "work_count", 0) or 0)

    @staticmethod
    def _rows_to_list_items(rows: list, counts: dict | None = None) -> list:
        items = []
        for r in rows:
            items.append({
                "id": r.id,
                "name_ko": r.name_ko or r.korean or "",
                "name_ja": r.name_ja or r.japanese or "",
                "japanese": r.japanese or "",
                "profile_image_url": _resolve_data_path(r.profile_image_url or ""),
                "user_score": ActressModel._effective_user_score(r),
                "is_favorite": getattr(r, "is_favorite", False),
                "genres": getattr(r, "genres", "") or "",
                "work_count": ActressModel._row_work_count(r, counts),
            })
        return items

    @staticmethod
    def _work_count_sort_available(session) -> bool:
        """work_count 캐시 컬럼이 DB에 있고 백필된 상태인지."""
        try:
            row = (
                session.query(Actress.works_updated_at)
                .filter(Actress.works_updated_at.isnot(None))
                .limit(1)
                .first()
            )
            return row is not None
        except Exception:
            return False

    @staticmethod
    def _apply_work_count_order(qry, ascending: bool):
        from sqlalchemy import func

        name_key = func.coalesce(Actress.name_ko, Actress.korean, "")
        if ascending:
            return qry.order_by(Actress.work_count.asc(), name_key.asc())
        return qry.order_by(Actress.work_count.desc(), name_key.asc())

    @staticmethod
    def _order_actress_rows(session, rows: list, sort: str, ascending: bool) -> list:
        rows = list(rows or [])
        if sort == "works":
            counts = batch_actress_work_counts(session, rows)
            rows.sort(
                key=lambda r: (counts.get(r.id, 0), (r.name_ko or r.korean or "")),
                reverse=not ascending,
            )
            return rows

        reverse = not ascending
        if sort == "name":
            rows.sort(
                key=lambda r: (r.name_ko or r.korean or "", r.name_ja or r.japanese or ""),
                reverse=reverse,
            )
        elif sort == "favorite":
            rows.sort(
                key=lambda r: (bool(getattr(r, "is_favorite", False)), r.name_ko or r.korean or ""),
                reverse=reverse,
            )
        elif sort == "score":
            rows.sort(
                key=lambda r: (ActressModel._effective_user_score(r), r.name_ko or r.korean or ""),
                reverse=reverse,
            )
        elif sort == "recent":
            rows.sort(
                key=ActressModel._actress_recent_key,
                reverse=reverse,
            )
        else:
            rows.sort(
                key=lambda r: (r.name_ko or r.korean or "", r.name_ja or r.japanese or ""),
                reverse=reverse,
            )
        return rows

    @staticmethod
    def _apply_search_filter(qry, query: str):
        """이름·장르·별명(alias) 통합 검색."""
        q = (query or "").strip()
        if not q:
            return qry
        like = f"%{q}%"
        from sqlalchemy import or_
        alias_ids = (
            qry.session.query(ActressAlias.actress_id)
            .filter(ActressAlias.alias_name.ilike(like))
            .distinct()
        )
        return qry.filter(
            or_(
                Actress.name_ko.ilike(like),
                Actress.name_ja.ilike(like),
                Actress.japanese.ilike(like),
                Actress.name_en.ilike(like),
                Actress.korean.ilike(like),
                Actress.genres.ilike(like),
                Actress.id.in_(alias_ids),
            )
        )

    @Slot()
    def reload(self):
        """Load all actress profiles for grid (name sort)."""
        self._sort_key = "name"
        self._sort_ascending = True
        self.sortStateChanged.emit()
        self._reload_internal(sort="name", ascending=True)

    @Slot()
    def refreshList(self):
        """현재 정렬·검색 조건을 유지한 채 목록을 강제 갱신."""
        self._refresh_list()

    @Slot()
    def refreshListIfNeeded(self):
        """탭 재진입용 — 세션 내 첫 방문 또는 dirty일 때만 목록 갱신."""
        if self._actress_tab_visited and not self._list_dirty:
            return
        self._actress_tab_visited = True
        self._refresh_list()

    def _mark_list_dirty(self) -> None:
        self._list_dirty = True

    @Slot(str)
    def reloadSorted(self, sort: str):
        """Load actress list with specified sort key (legacy: ascending defaults)."""
        ascending = sort == "name"
        self._sort_key = sort
        self._sort_ascending = ascending
        self.sortStateChanged.emit()
        self._reload_internal(sort=sort, ascending=ascending)

    @Slot(str, bool)
    def reloadSortedEx(self, sort: str, ascending: bool):
        """Load actress list with sort key and direction."""
        self._sort_key = sort if sort in self._SORT_KEYS else "name"
        self._sort_ascending = bool(ascending)
        self.sortStateChanged.emit()
        self._reload_internal(sort=self._sort_key, ascending=self._sort_ascending)

    def _refresh_list(self):
        """현재 정렬·검색 조건을 유지한 채 목록만 갱신."""
        self._reload_internal(
            sort=self._current_sort,
            ascending=self._current_sort_ascending,
            query=self._filter_query,
        )

    def _reload_internal(self, sort: str = "name", ascending: bool = True, query: str = ""):
        if sort == "works":
            session = get_db_session()
            try:
                if not self._work_count_sort_available(session):
                    self._reload_works_sort_async(query, ascending)
                    return
            finally:
                session.close()
        self._reload_list_async(sort, ascending, query)

    def _is_list_reload_worker_running(self) -> bool:
        worker = self._list_reload_worker
        if worker is None:
            return False
        try:
            return worker.isRunning()
        except RuntimeError:
            self._list_reload_worker = None
            return False

    def _reload_list_async(self, sort: str, ascending: bool, query: str):
        if self._is_list_reload_worker_running():
            worker = self._list_reload_worker
            worker.requestInterruption()

        self._is_loading = True
        self.actressListChanged.emit()

        worker = _ActressListReloadWorker(sort, ascending, query, parent=self)
        worker.finished.connect(lambda items, w=worker: self._on_list_reload_done(items, w))
        worker.error.connect(lambda msg, w=worker: self._on_list_reload_error(msg, w))
        self._list_reload_worker = worker
        worker.start()

    def _on_list_reload_done(self, items: list, worker: _ActressListReloadWorker | None = None):
        if worker is not None and self._list_reload_worker is worker:
            self._list_reload_worker = None
        self._list_model.set_actresses(items)
        self._list_dirty = False
        self._is_loading = False
        self.actressListChanged.emit()

    def _on_list_reload_error(self, message: str, worker: _ActressListReloadWorker | None = None):
        if worker is not None and self._list_reload_worker is worker:
            self._list_reload_worker = None
        self._is_loading = False
        self.actressListChanged.emit()
        self.errorOccurred.emit(f"배우 목록 로드 실패: {message}")
        self.toastMessage.emit(f"배우 목록 로드 실패: {message}", "error")

    def _is_works_sort_worker_running(self) -> bool:
        worker = self._works_sort_worker
        if worker is None:
            return False
        try:
            return worker.isRunning()
        except RuntimeError:
            self._works_sort_worker = None
            return False

    def _reload_works_sort_async(self, query: str, ascending: bool):
        if self._is_works_sort_worker_running():
            worker = self._works_sort_worker
            worker.requestInterruption()

        self._is_loading = True
        self.actressListChanged.emit()

        worker = _ActressWorksSortWorker(query, ascending, parent=self)
        worker.finished.connect(lambda items, w=worker: self._on_works_sort_done(items, w))
        worker.error.connect(lambda msg, w=worker: self._on_works_sort_error(msg, w))
        self._works_sort_worker = worker
        worker.start()

    def _on_works_sort_done(self, items: list, worker: _ActressWorksSortWorker | None = None):
        if worker is not None and self._works_sort_worker is worker:
            self._works_sort_worker = None
        self._list_model.set_actresses(items)
        self._list_dirty = False
        self._is_loading = False
        self.actressListChanged.emit()

    def _on_works_sort_error(self, message: str, worker: _ActressWorksSortWorker | None = None):
        if worker is not None and self._works_sort_worker is worker:
            self._works_sort_worker = None
        self._is_loading = False
        self.actressListChanged.emit()
        self.errorOccurred.emit(f"배우 목록 로드 실패: {message}")
        self.toastMessage.emit(f"배우 목록 로드 실패: {message}", "error")

    @Slot(str)
    def filterList(self, query: str):
        """실시간 검색 필터 — 리스트 모델을 직접 갱신."""
        self._filter_query = (query or "").strip()
        self._reload_internal(
            sort=self._current_sort,
            ascending=self._current_sort_ascending,
            query=self._filter_query,
        )

    @property
    def _current_sort(self) -> str:
        return getattr(self, "_sort_key", "name")

    @property
    def _current_sort_ascending(self) -> bool:
        return getattr(self, "_sort_ascending", True)

    def _schedule_works_rebuild(self, actress_id: int, *, source: str = "profile") -> None:
        if self._works_rebuild_worker is not None:
            try:
                if self._works_rebuild_worker.isRunning():
                    return
            except RuntimeError:
                self._works_rebuild_worker = None

        worker = _ActressWorksRebuildWorker(actress_id, source=source, parent=self)
        worker.finished.connect(lambda _aid, _n, w=worker: self._on_works_rebuild_done(w))
        self._works_rebuild_worker = worker
        worker.start()

    def _on_works_rebuild_done(self, worker: _ActressWorksRebuildWorker | None = None) -> None:
        if worker is not None and self._works_rebuild_worker is worker:
            self._works_rebuild_worker = None
        self._mark_list_dirty()

    @Slot(int)
    def loadProfile(self, actress_id: int):
        """Load detailed profile for editing/viewing (비동기)."""
        self._profile_load_token += 1
        token = self._profile_load_token

        if self._profile_load_worker is not None:
            try:
                if self._profile_load_worker.isRunning():
                    self._profile_load_worker.requestInterruption()
            except RuntimeError:
                self._profile_load_worker = None

        worker = _ActressProfileLoadWorker(actress_id, parent=self)
        worker.finished.connect(
            lambda aid, profile, t=token, w=worker: self._on_profile_loaded(aid, profile, t, w)
        )
        worker.error.connect(
            lambda msg, t=token, w=worker: self._on_profile_load_error(msg, t, w)
        )
        self._profile_load_worker = worker
        worker.start()

    def _on_profile_loaded(
        self,
        actress_id: int,
        profile: Dict,
        token: int,
        worker: _ActressProfileLoadWorker | None = None,
    ) -> None:
        if token != self._profile_load_token:
            return
        if worker is not None and self._profile_load_worker is worker:
            self._profile_load_worker = None
        self._current_profile = profile
        self.currentProfileChanged.emit()

    def _on_profile_load_error(
        self,
        message: str,
        token: int,
        worker: _ActressProfileLoadWorker | None = None,
    ) -> None:
        if token != self._profile_load_token:
            return
        if worker is not None and self._profile_load_worker is worker:
            self._profile_load_worker = None
        if message == "not found":
            self.toastMessage.emit("배우를 찾을 수 없습니다.", "warning")
            return
        self.errorOccurred.emit(f"프로필 로드 실패: {message}")
        self.toastMessage.emit(f"프로필 로드 실패: {message}", "error")

    @Slot("QVariantMap", result=int)
    def addActress(self, data: Dict) -> int:
        """Create new actress profile. Returns new ID or -1 on failure."""
        try:
            session = get_db_session()
            try:
                actress = Actress(
                    japanese=data.get("name_ja", "").strip() or data.get("name_ko", "").strip(),
                    korean=data.get("name_ko", "").strip(),
                    name_ja=data.get("name_ja", "").strip(),
                    name_ko=data.get("name_ko", "").strip(),
                    name_en=data.get("name_en", "").strip(),
                    genres=data.get("genres", "").strip(),
                    profile_text=data.get("profile_text", "").strip(),
                    user_score=float(data.get("user_score", 0.0)),
                    birth_date=data.get("birth_date") or None,
                    height=int(data.get("height", 0) or 0) or None,
                    bust=int(data.get("bust", 0) or 0) or None,
                    waist=int(data.get("waist", 0) or 0) or None,
                    hip=int(data.get("hip", 0) or 0) or None,
                    cup_size=data.get("cup_size", "").strip() or None,
                    debut_date=data.get("debut_date") or None,
                    agency=data.get("agency", "").strip() or None,
                    is_favorite=bool(data.get("is_favorite", False)),
                    favorite_intensity=float(data.get("favorite_intensity", 5.0)),
                    memo=data.get("memo", "").strip() or None,
                    needs_review=False,
                )
                session.add(actress)
                session.commit()
                new_id = actress.id

                # Add primary alias if provided
                primary_name = data.get("name_ja") or data.get("name_ko")
                if primary_name:
                    add_alias(new_id, primary_name, "stage", is_primary=True)

                self.toastMessage.emit("새 배우 프로필이 추가되었습니다.", "success")
                self._refresh_list()  # refresh list
                return new_id
            finally:
                session.close()
        except Exception as e:
            self.errorOccurred.emit(f"배우 추가 실패: {e}")
            self.toastMessage.emit(f"배우 추가 실패: {e}", "error")
            return -1

    @Slot(int, "QVariantMap", result=bool)
    def updateProfile(self, actress_id: int, data: Dict) -> bool:
        """Update existing profile."""
        try:
            session = get_db_session()
            try:
                actress = session.query(Actress).filter_by(id=actress_id).first()
                if not actress:
                    return False

                payload = dict(data) if isinstance(data, dict) else dict(data or {})
                _apply_profile_updates(actress, payload)

                actress.updated_at = datetime.now()
                if _PROFILE_NAME_KEYS & payload.keys():
                    session.commit()
                    self.toastMessage.emit("프로필이 업데이트되었습니다.", "success")
                    self.loadProfile(actress_id)
                    self._sync_list_after_profile_change(actress_id, payload)
                    self._schedule_works_rebuild(actress_id, source="profile")
                    return True

                session.commit()
                self.toastMessage.emit("프로필이 업데이트되었습니다.", "success")
                self.loadProfile(actress_id)
                self._sync_list_after_profile_change(actress_id, payload)
                return True
            finally:
                session.close()
        except Exception as e:
            self.errorOccurred.emit(f"업데이트 실패: {e}")
            self.toastMessage.emit(f"업데이트 실패: {e}", "error")
            return False

    @Slot(int, str, bool, result="QString")
    def addImage(self, actress_id: int, file_path: str, is_profile: bool = False) -> str:
        """Add photo to profile/ or gallery/ folder."""
        local_path = _normalize_local_path(file_path)
        path = save_actress_image(
            actress_id=actress_id,
            source_path=local_path,
            is_profile=is_profile,
            sort_order=10,
        )
        if path:
            self.loadProfile(actress_id)
            self._sync_list_after_profile_change(actress_id, {"profile_image_url": path})
            return str(path)
        self.toastMessage.emit("사진 저장 실패 (파일을 확인하세요)", "error")
        return ""

    @Slot(int, int, result=bool)
    def setProfileImage(self, actress_id: int, image_id: int) -> bool:
        """갤러리 사진을 대표 사진(profile/)으로 복사."""
        try:
            session = get_db_session()
            try:
                img = session.query(ActressImage).filter_by(
                    image_id=image_id, actress_id=actress_id
                ).first()
                if not img:
                    self.toastMessage.emit("이미지를 찾을 수 없습니다.", "warning")
                    return False
                rel = img.image_url
            finally:
                session.close()

            if promote_gallery_image_to_profile(actress_id, rel):
                self.toastMessage.emit("대표 사진이 변경되었습니다.", "success")
                self.loadProfile(actress_id)
                self._sync_list_after_profile_change(actress_id, {"profile_image_url": rel})
                return True
            self.toastMessage.emit("대표 사진 설정 실패 (gallery/ 경로 확인)", "warning")
            return False
        except Exception as e:
            self.toastMessage.emit(f"대표 사진 설정 실패: {e}", "error")
            return False

    @Slot(int, str, result=bool)
    def setProfileFromGallery(self, actress_id: int, image_url: str) -> bool:
        """갤러리 경로(image_url)를 대표 사진으로 지정."""
        try:
            if promote_gallery_image_to_profile(actress_id, image_url):
                self.toastMessage.emit("대표 사진이 변경되었습니다.", "success")
                self.loadProfile(actress_id)
                self._sync_list_after_profile_change(actress_id, {"profile_image_url": image_url})
                return True
            self.toastMessage.emit("대표 사진 설정 실패 (gallery/ 경로 확인)", "warning")
            return False
        except Exception as e:
            self.toastMessage.emit(f"대표 사진 설정 실패: {e}", "error")
            return False

    @Slot(str, result=int)
    def findActressIdByName(self, name: str) -> int:
        """이름/별명으로 actress id 조회. 없으면 -1."""
        resolved = resolve_actress_by_name(name)
        return int(resolved) if resolved else -1

    @Slot(int, str, str, bool, result=bool)
    def addAlias(self, actress_id: int, alias_name: str, alias_type: str = "stage", is_primary: bool = False) -> bool:
        """Add alias."""
        success = add_alias(actress_id, alias_name, alias_type, is_primary)
        if success:
            self.loadProfile(actress_id)
        return success

    @Slot(int, int, result=bool)
    def removeAlias(self, actress_id: int, alias_id: int) -> bool:
        """Delete alias by alias_id."""
        try:
            session = get_db_session()
            try:
                alias = session.query(ActressAlias).filter_by(alias_id=alias_id).first()
                if not alias:
                    self.toastMessage.emit("별명을 찾을 수 없습니다.", "warning")
                    return False
                session.delete(alias)
                session.commit()
                self.toastMessage.emit("별명이 삭제되었습니다.", "success")
                self.loadProfile(actress_id)
                self._schedule_works_rebuild(actress_id, source="alias")
                self._mark_list_dirty()
                return True
            finally:
                session.close()
        except Exception as e:
            self.toastMessage.emit(f"별명 삭제 실패: {e}", "error")
            return False

    def _fetch_library_works(self, actress_id: int) -> list:
        """내부: 배우 연관 작품 목록 (별명 포함 검색)."""
        from javstory.harvest.database import WatchHistory
        from sqlalchemy.orm import joinedload

        session = get_db_session()
        try:
            actress = (
                session.query(Actress)
                .options(joinedload(Actress.aliases))
                .filter_by(id=actress_id)
                .first()
            )
            if not actress:
                return []

            items = fetch_actress_library_works(session, actress)
            if not items:
                return items

            codes = [it["product_code"] for it in items]
            watch_rows = session.query(WatchHistory).filter(
                WatchHistory.product_code.in_(codes)
            ).all()
            watch_by_pc: dict[str, WatchHistory] = {}
            for wh in watch_rows:
                key = (wh.product_code or "").strip().upper()
                if key:
                    watch_by_pc[key] = wh
            for it in items:
                wh = watch_by_pc.get(it["product_code"].upper())
                rating = int(wh.rating or 0) if wh else 0
                it["user_rating"] = rating
                it["userRating"] = rating
                it["user_liked"] = bool(wh.liked) if wh else False

            return items
        finally:
            session.close()

    @Slot(int, result=list)
    def getLibraryWorks(self, actress_id: int) -> list:
        """Return list of products featuring this actress (for detail view)."""
        try:
            return self._fetch_library_works(actress_id)
        except Exception as e:
            print(f"[ActressModel] getLibraryWorks error: {e}")
            return []

    @Slot(int)
    def requestLibraryWorksAndGenres(self, actress_id: int) -> None:
        """출연작 + 장르 집계를 백그라운드에서 로드하고 libraryWorksBundleReady 시그널로 반환."""
        aid = int(actress_id or 0)
        if aid <= 0:
            self.libraryWorksBundleReady.emit(aid, {"works": [], "genres": []})
            return

        self._library_bundle_token += 1
        token = self._library_bundle_token

        if self._library_bundle_worker is not None:
            try:
                if self._library_bundle_worker.isRunning():
                    self._library_bundle_worker.requestInterruption()
            except RuntimeError:
                self._library_bundle_worker = None

        worker = _ActressLibraryBundleWorker(aid, parent=self)
        worker.finished.connect(
            lambda id_, bundle, t=token, w=worker: self._on_library_bundle_ready(id_, bundle, t, w)
        )
        worker.error.connect(
            lambda _msg, t=token, w=worker: self._on_library_bundle_error(t, w)
        )
        self._library_bundle_worker = worker
        worker.start()

    def _on_library_bundle_ready(
        self,
        actress_id: int,
        bundle: dict,
        token: int,
        worker: _ActressLibraryBundleWorker | None = None,
    ) -> None:
        if token != self._library_bundle_token:
            return
        if worker is not None and self._library_bundle_worker is worker:
            self._library_bundle_worker = None
        self.libraryWorksBundleReady.emit(int(actress_id), bundle)

    def _on_library_bundle_error(
        self,
        token: int,
        worker: _ActressLibraryBundleWorker | None = None,
    ) -> None:
        if token != self._library_bundle_token:
            return
        if worker is not None and self._library_bundle_worker is worker:
            self._library_bundle_worker = None
        self.libraryWorksBundleReady.emit(0, {"works": [], "genres": []})

    @Slot(int, result="QVariantMap")
    def getLibraryWorksAndGenres(self, actress_id: int) -> dict:
        """동기 호환 — 가능하면 requestLibraryWorksAndGenres 사용."""
        try:
            works = self._fetch_library_works(actress_id)
            return {
                "works": works,
                "genres": aggregate_work_genres(works),
            }
        except Exception as e:
            print(f"[ActressModel] getLibraryWorksAndGenres error: {e}")
            return {"works": [], "genres": []}

    @Slot(int, result=list)
    def getWorkGenres(self, actress_id: int) -> list:
        """출연 작품 genres_ko 집계 (빈도순). 단독 호출 시 전체 스캔 발생 — 상세는 getLibraryWorksAndGenres 권장."""
        try:
            works = self._fetch_library_works(actress_id)
            return aggregate_work_genres(works)
        except Exception as e:
            print(f"[ActressModel] getWorkGenres error: {e}")
            return []

    @Slot(int, int, result=bool)
    def mergeActresses(self, keep_id: int, merge_id: int) -> bool:
        """keep_id에 merge_id 프로필을 합칩니다."""
        if keep_id == merge_id:
            self.toastMessage.emit("같은 배우는 합칠 수 없습니다.", "warning")
            return False
        ok = merge_actresses(keep_id, merge_id)
        if ok:
            self.toastMessage.emit("배우 프로필을 합쳤습니다.", "success")
            self.loadProfile(keep_id)
            self._refresh_list()
        else:
            self.toastMessage.emit("배우 합치기에 실패했습니다.", "error")
        return ok

    @Slot(str, result=list)
    def searchActresses(self, query: str = "") -> list:
        """Search actresses (used by popup and list)."""
        try:
            session = get_db_session()
            try:
                qry = session.query(Actress)
                qry = self._apply_search_filter(qry, query)
                rows = qry.order_by(Actress.name_ko.asc().nullslast()).limit(50).all()
                return [{
                    "id": r.id,
                    "name_ko": r.name_ko or r.korean or "",
                    "name_ja": r.name_ja or r.japanese or "",
                    "user_score": float(getattr(r, "user_score", 0.0) or 0.0),
                } for r in rows]
            finally:
                session.close()
        except Exception:
            return []


# Register for QML (will be done in app.py / main.qml in step 5)
if __name__ == "__main__":
    model = ActressModel()
    print("ActressModel initialized successfully")
    print("Available methods: reload, loadProfile, addActress, updateProfile, addImage, addAlias, searchActresses")
