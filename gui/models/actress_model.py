"""ActressModel for JAVSTORY QML integration.

Exposes actress profile CRUD, image management, alias handling to QML.
Follows patterns from LibraryModel and settings_model.py.
"""

from PySide6.QtCore import (
    QObject, Property, Signal, Slot, QAbstractListModel, QModelIndex, Qt
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
    collect_actress_search_names,
    load_actress_media,
    promote_gallery_image_to_profile,
    resolve_actress_media_path,
    _format_debut_ym,
)
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
        return None

    def set_actresses(self, actresses: List[Dict]):
        self.beginResetModel()
        self._actresses = actresses
        self.endResetModel()


class ActressModel(QObject):
    """Main model for actress profiles. Exposed to QML."""

    # Signals
    actressListChanged = Signal()
    currentProfileChanged = Signal()
    toastMessage = Signal(str, str)  # message, level (success/info/warning/error)
    errorOccurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._list_model = ActressListModel(self)
        self._current_profile: Dict = {}
        self._is_loading = False
        self.reload()

    @Property(QObject, constant=True)
    def listModel(self) -> ActressListModel:
        return self._list_model

    @Property("QVariantMap", notify=currentProfileChanged)
    def currentProfile(self) -> Dict:
        return self._current_profile

    @Property(bool, notify=actressListChanged)
    def isLoading(self) -> bool:
        return self._is_loading

    _SORT_ORDERS = {
        "name":     lambda q: q.order_by(Actress.name_ko.asc().nullslast(), Actress.japanese.asc()),
        "favorite": lambda q: q.order_by(Actress.is_favorite.desc(), Actress.name_ko.asc().nullslast()),
        "score":    lambda q: q.order_by(Actress.user_score.desc().nullslast(), Actress.name_ko.asc().nullslast()),
        "recent":   lambda q: q.order_by(Actress.id.desc()),
    }

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
        self._reload_internal(sort="name")

    @Slot(str)
    def reloadSorted(self, sort: str):
        """Load actress list with specified sort key: name/favorite/score/recent."""
        self._sort_key = sort
        self._reload_internal(sort=sort)

    def _reload_internal(self, sort: str = "name", query: str = ""):
        self._is_loading = True
        try:
            session = get_db_session()
            try:
                qry = session.query(Actress)
                qry = self._apply_search_filter(qry, query)
                sorter = self._SORT_ORDERS.get(sort, self._SORT_ORDERS["name"])
                rows = sorter(qry).all()
                items = []
                for r in rows:
                    items.append({
                        "id": r.id,
                        "name_ko": r.name_ko or r.korean or "",
                        "name_ja": r.name_ja or r.japanese or "",
                        "japanese": r.japanese or "",
                        "profile_image_url": _resolve_data_path(r.profile_image_url or ""),
                        "user_score": getattr(r, "user_score", 0.0) or 0.0,
                        "is_favorite": getattr(r, "is_favorite", False),
                        "genres": getattr(r, "genres", "") or "",
                    })
                self._list_model.set_actresses(items)
                self.actressListChanged.emit()
            finally:
                session.close()
        except Exception as e:
            self.errorOccurred.emit(f"배우 목록 로드 실패: {e}")
            self.toastMessage.emit(f"배우 목록 로드 실패: {e}", "error")
        finally:
            self._is_loading = False

    @Slot(str)
    def filterList(self, query: str):
        """실시간 검색 필터 — 리스트 모델을 직접 갱신."""
        self._reload_internal(sort=self._current_sort, query=query)

    @property
    def _current_sort(self) -> str:
        return getattr(self, "_sort_key", "name")

    @Slot(int)
    def loadProfile(self, actress_id: int):
        """Load detailed profile for editing/viewing."""
        try:
            session = get_db_session()
            try:
                row = session.query(Actress).filter_by(id=actress_id).first()
                if not row:
                    self.toastMessage.emit("배우를 찾을 수 없습니다.", "warning")
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
                }

                # Load images from profile/ · gallery/ folders only
                media = load_actress_media(actress_id)
                profile["profile_image_url"] = _resolve_data_path(media.get("profile_image_url") or "")
                profile["gallery_images"] = [
                    {
                        **img,
                        "image_url": _resolve_data_path(img.get("image_url") or ""),
                    }
                    for img in (media.get("gallery_images") or [])
                ]
                profile["images"] = profile["gallery_images"]

                profile["aliases"] = []
                for alias in row.aliases or []:
                    profile["aliases"].append({
                        "alias_id": alias.alias_id,
                        "alias_name": alias.alias_name,
                        "alias_type": alias.alias_type or "stage",
                        "is_primary": alias.is_primary,
                    })

                self._current_profile = profile
                self.currentProfileChanged.emit()
            finally:
                session.close()
        except Exception as e:
            self.errorOccurred.emit(f"프로필 로드 실패: {e}")
            self.toastMessage.emit(f"프로필 로드 실패: {e}", "error")

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
                self.reload()  # refresh list
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

                _apply_profile_updates(actress, data if isinstance(data, dict) else dict(data or {}))

                actress.updated_at = datetime.now()
                session.commit()
                self.toastMessage.emit("프로필이 업데이트되었습니다.", "success")
                self.loadProfile(actress_id)
                self.reload()
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
            self.reload()
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
                self.reload()
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
                self.reload()
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
                return True
            finally:
                session.close()
        except Exception as e:
            self.toastMessage.emit(f"별명 삭제 실패: {e}", "error")
            return False

    def _fetch_library_works(self, actress_id: int) -> list:
        """내부: 배우 연관 작품 목록 (별명 포함 검색)."""
        from javstory.harvest.database import JAVMetadata, WatchHistory
        from sqlalchemy import or_

        session = get_db_session()
        try:
            actress = session.query(Actress).filter_by(id=actress_id).first()
            if not actress:
                return []

            names = collect_actress_search_names(actress)
            if not names:
                return []

            filters = []
            for name in names:
                like = f"%{name}%"
                filters += [
                    JAVMetadata.actors_ko.ilike(like),
                    JAVMetadata.actors_ja.ilike(like),
                    JAVMetadata.actors.ilike(like),
                    JAVMetadata.actors_romaji.ilike(like),
                ]

            rows = (
                session.query(JAVMetadata)
                .filter(or_(*filters))
                .order_by(JAVMetadata.release_date.desc())
                .limit(50)
                .all()
            )

            seen: set[str] = set()
            items: list[dict] = []
            for r in rows:
                pc = (r.product_code or "").strip()
                if not pc or pc in seen:
                    continue
                seen.add(pc)
                items.append({
                    "product_code": pc,
                    "title_ko": r.title_ko or r.title or "",
                    "titleKo": r.title_ko or r.title or "",
                    "actors_ko": r.actors_ko or "",
                    "actorsKo": r.actors_ko or "",
                    "genres_ko": r.genres_ko or r.genres or "",
                    "cover_path": r.cover_image_local_path or r.cover_image_url or "",
                    "coverPath": r.cover_image_local_path or r.cover_image_url or "",
                    "release_date": r.release_date or "",
                    "scene_count": 0,
                    "user_rating": 0,
                    "userRating": 0,
                    "user_liked": False,
                    "favorite_score": int(getattr(r, "favorite_score", 0) or 0),
                })

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

    @Slot(int, result=list)
    def getWorkGenres(self, actress_id: int) -> list:
        """출연 작품 genres_ko 집계 (빈도순)."""
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
            self.reload()
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
                    "user_score": getattr(r, "user_score", 0.0),
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
