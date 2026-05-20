"""라이브러리 모델: 작품 목록/필터/정렬 + 상세 정보."""

from __future__ import annotations

import datetime
import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QObject, QTimer, Property, Signal, Slot,
    QAbstractListModel, QModelIndex, Qt,
)

from gui.models.detail_edit_draft import DetailEditDraft
from gui.models.scene_edit_model import SceneEditModel
from gui.models.library import (
    FolderBindHooks,
    LibraryDetailService,
    LibraryFolderBind,
    LibrarySortFilter,
    ListRebuildOptions,
    match_summary,
    parse_search_expr,
    release_month_key,
)
from gui.library_data import find_all_video_paths_for_product
from PySide6.QtCore import QThread
from dataclasses import asdict


def _extract_dialogue_lines(srt_text: str, *, max_lines: int = 80) -> str:
    """SRT 본문에서 시간코드/번호를 제거하고 텍스트 라인만 추출."""
    if not srt_text:
        return ""
    out: list[str] = []
    seen: set[str] = set()
    for raw in srt_text.splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.isdigit():
            continue
        if "-->" in s:
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= max_lines:
            break
    return "\n".join(out)


class _NoteGenWorker(QThread):
    """Gemini 번역 노트 생성 백그라운드 워커. 시그널: finished(kind, ok, payload)"""

    finished = Signal(str, bool, str)

    def __init__(self, kind: str, ctx: Any, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.ctx = ctx

    def run(self):
        import asyncio as _asyncio
        loop = _asyncio.new_event_loop()
        _asyncio.set_event_loop(loop)
        ok = False
        payload = ""
        try:
            from javstory.translation.translation_note_generator import (
                generate_work_translation_note_async,
                generate_actress_translation_note_async,
            )
            if self.kind == "work":
                payload = loop.run_until_complete(
                    generate_work_translation_note_async(self.ctx)
                ) or ""
            else:
                payload = loop.run_until_complete(
                    generate_actress_translation_note_async(self.ctx)
                ) or ""
            ok = True
        except Exception as e:
            ok = False
            payload = str(e)
        finally:
            try:
                loop.close()
            except Exception:
                pass
        self.finished.emit(self.kind, ok, payload)


class WorkListModel(QAbstractListModel):
    ProductCodeRole = Qt.ItemDataRole.UserRole + 1
    TitleKoRole = Qt.ItemDataRole.UserRole + 2
    TitleJaRole = Qt.ItemDataRole.UserRole + 3
    ActorsKoRole = Qt.ItemDataRole.UserRole + 4
    CoverPathRole = Qt.ItemDataRole.UserRole + 5
    PreviewPathRole = Qt.ItemDataRole.UserRole + 15
    SceneCountRole = Qt.ItemDataRole.UserRole + 6
    PipelineStageRole = Qt.ItemDataRole.UserRole + 7
    ReleaseDateRole = Qt.ItemDataRole.UserRole + 8
    HasCanonicalRole = Qt.ItemDataRole.UserRole + 9
    PartCountRole = Qt.ItemDataRole.UserRole + 10
    IsHardcodedRole = Qt.ItemDataRole.UserRole + 11
    HasJaSrtRole = Qt.ItemDataRole.UserRole + 12
    HasKoSrtRole = Qt.ItemDataRole.UserRole + 13
    LampHardcodedRole = Qt.ItemDataRole.UserRole + 14
    LampMopaRole = Qt.ItemDataRole.UserRole + 16
    FavoriteScoreRole = Qt.ItemDataRole.UserRole + 17
    FavoriteDeltaRole = Qt.ItemDataRole.UserRole + 18
    UserRatingRole = Qt.ItemDataRole.UserRole + 19
    UserLikedRole = Qt.ItemDataRole.UserRole + 20

    _ROLE_MAP = {
        ProductCodeRole: "product_code",
        TitleKoRole: "title_ko",
        TitleJaRole: "title_ja",
        ActorsKoRole: "actors_ko",
        CoverPathRole: "cover_path",
        PreviewPathRole: "preview_path",
        SceneCountRole: "scene_count",
        PipelineStageRole: "pipeline_stage",
        ReleaseDateRole: "release_date",
        HasCanonicalRole: "has_canonical",
        PartCountRole: "part_count",
        IsHardcodedRole: "is_hardcoded",
        HasJaSrtRole: "has_ja_srt",
        HasKoSrtRole: "has_ko_srt",
        LampHardcodedRole: "lamp_hardcoded",
        LampMopaRole: "lamp_mopa",
        FavoriteScoreRole: "favorite_score",
        FavoriteDeltaRole: "favorite_delta",
        UserRatingRole: "user_rating",
        UserLikedRole: "user_liked",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[dict] = []

    def roleNames(self):
        return {
            self.ProductCodeRole: b"productCode",
            self.TitleKoRole: b"titleKo",
            self.TitleJaRole: b"titleJa",
            self.ActorsKoRole: b"actorsKo",
            self.CoverPathRole: b"coverPath",
            self.PreviewPathRole: b"previewPath",
            self.SceneCountRole: b"sceneCount",
            self.PipelineStageRole: b"pipelineStage",
            self.ReleaseDateRole: b"releaseDate",
            self.HasCanonicalRole: b"hasCanonical",
            self.PartCountRole: b"partCount",
            self.IsHardcodedRole: b"isHardcoded",
            self.HasJaSrtRole: b"hasJaSrt",
            self.HasKoSrtRole: b"hasKoSrt",
            self.LampHardcodedRole: b"lampHardcoded",
            self.LampMopaRole: b"lampMopa",
            self.FavoriteScoreRole: b"favoriteScore",
            self.FavoriteDeltaRole: b"favoriteDelta",
            self.UserRatingRole: b"userRating",
            self.UserLikedRole: b"userLiked",
        }

    def rowCount(self, parent=QModelIndex()):
        return len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        key = self._ROLE_MAP.get(role)
        if key:
            return self._items[index.row()].get(key)
        return None

    def refresh(self, items: list[dict]):
        self.beginResetModel()
        self._items = items
        self.endResetModel()

    @Slot(int, result=str)
    def productCodeAt(self, idx: int) -> str:
        try:
            i = int(idx)
        except Exception:
            return ""
        if i < 0 or i >= len(self._items):
            return ""
        try:
            return str(self._items[i].get("product_code") or "")
        except Exception:
            return ""

    @Slot(result="QStringList")
    def allProductCodes(self):
        out = []
        try:
            for it in (self._items or []):
                pc = str((it or {}).get("product_code") or "").strip()
                if pc:
                    out.append(pc)
        except Exception:
            return []
        return out


class LibraryDetailObject(QObject):
    """단일 작품 상세 정보를 QML에 노출."""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: dict = {}

    def load(self, data: dict):
        self._data = data
        self.changed.emit()

    def _get(self, key, default=""):
        return self._data.get(key, default)

    @Property(str, notify=changed)
    def productCode(self): return self._get("product_code")
    @Property(str, notify=changed)
    def titleKo(self): return self._get("title_ko")
    @Property(str, notify=changed)
    def titleJa(self): return self._get("title_ja")
    @Property(str, notify=changed)
    def actorsKo(self): return self._get("actors_ko")
    @Property(str, notify=changed)
    def makerKo(self): return self._get("maker_ko")
    @Property(str, notify=changed)
    def releaseDate(self): return self._get("release_date")
    @Property(str, notify=changed)
    def synopsisKo(self): return self._get("synopsis_ko")
    @Property(str, notify=changed)
    def genresKo(self): return self._get("genres_ko")
    @Property(str, notify=changed)
    def coverPath(self): return self._get("cover_path")
    @Property(int, notify=changed)
    def sceneCount(self): return self._get("scene_count", 0)
    @Property(str, notify=changed)
    def pipelineStage(self): return self._get("pipeline_stage", "none")
    @Property(bool, notify=changed)
    def hasCanonical(self): return self._get("has_canonical", False)
    @Property(str, notify=changed)
    def overallSummary(self): return self._get("overall_summary", "")
    @Property(str, notify=changed)
    def grokJson(self): return self._get("grok_json", "")
    @Property(list, notify=changed)
    def stillPaths(self): return self._get("still_paths", [])
    @Property(str, notify=changed)
    def videoPath(self): return self._get("video_path", "")
    @Property(list, notify=changed)
    def videoPaths(self): return self._get("video_paths", [])
    @Property(str, notify=changed)
    def grokScenesJson(self): return self._get("grok_scenes_json", "[]")
    @Property(bool, notify=changed)
    def grokVerified(self): return self._get("grok_verified", False)
    @Property(str, notify=changed)
    def grokMismatchReason(self): return self._get("grok_mismatch_reason", "")
    @Property(bool, notify=changed)
    def isHardcoded(self): return self._get("is_hardcoded", False)
    @Property(bool, notify=changed)
    def hasJaSrt(self): return self._get("has_ja_srt", False)
    @Property(bool, notify=changed)
    def hasKoSrt(self): return self._get("has_ko_srt", False)
    @Property(bool, notify=changed)
    def lampHardcoded(self): return self._get("lamp_hardcoded", False)
    @Property(bool, notify=changed)
    def isMopa(self): return self._get("is_mopa", False)
    @Property(bool, notify=changed)
    def lampMopa(self): return self._get("lamp_mopa", False)
    @Property(str, notify=changed)
    def folderPath(self): return self._get("folder_path", "")
    @Property(str, notify=changed)
    def digestPath(self): return self._get("digest_path", "")
    @Property(str, notify=changed)
    def highlightPath(self): return self._get("highlight_path", "")
    @Property(int, notify=changed)
    def watchCount(self): return self._get("watch_count", 0)
    @Property(int, notify=changed)
    def watchDuration(self): return self._get("watch_duration", 0)
    @Property(int, notify=changed)
    def lastPosition(self): return self._get("last_position", 0)
    @Property(int, notify=changed)
    def favoriteScore(self): return int(self._get("favorite_score", 0) or 0)

    @Property(int, notify=changed)
    def userRating(self) -> int:
        return int(self._get("user_rating", 0) or 0)

    @Property(bool, notify=changed)
    def userLiked(self) -> bool:
        return bool(self._get("user_liked", False))

    @Property(bool, notify=changed)
    def hasFavoriteSiteDelta(self) -> bool:
        return bool(self._get("has_favorite_site_delta", False))

    @Property(int, notify=changed)
    def favoriteSiteDelta(self) -> int:
        return int(self._get("favorite_site_delta", 0) or 0)

    @Property(int, notify=changed)
    def favoriteSiteDeltaDays(self) -> int:
        return int(self._get("favorite_site_delta_days", 0) or 0)


class LibraryReloadWorker(QThread):
    """라이브러리 목록 로드 — 협력적 취소 지원."""

    finished = Signal(list)
    error = Signal(str)

    def __init__(self, *, limit: int = 600, offset: int = 0, parent=None):
        super().__init__(parent)
        self._limit = int(limit)
        self._offset = int(offset)
        self._cancelled = False

    def stop(self) -> None:
        self._cancelled = True
        self.requestInterruption()

    def is_cancelled(self) -> bool:
        return bool(self._cancelled or self.isInterruptionRequested())

    def run(self):
        if self.is_cancelled():
            return
        try:
            from javstory.harvest.database import get_db_session
            from gui.library_data import load_library_summaries_fast_paged
            with get_db_session() as session:
                summaries = load_library_summaries_fast_paged(
                    session, limit=self._limit, offset=self._offset
                )
                self.finished.emit(summaries)
        except Exception as e:
            self.error.emit(str(e))


class MetadataResyncWorker(QThread):
    """마스터 테이블 매핑(장르/배우/메이커)을 기준으로 jav_metadata의 ko/레거시 필드를 일괄 재동기화."""

    finished = Signal(dict)  # {"updated": {...}, "skipped": {...}, "unknown_samples": {...}}
    error = Signal(str)

    def __init__(self, *, product_codes: list[str] | None = None, parent=None):
        super().__init__(parent)
        self._product_codes = [str(x).strip().upper() for x in (product_codes or []) if str(x).strip()]

    def run(self):
        try:
            import re

            from javstory.harvest.database import Actress, Genre, JAVMetadata, Maker, get_db_session

            def _s(v) -> str:
                return ("" if v is None else str(v)).strip()

            def _clean_ws(s: str) -> str:
                s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
                s = re.sub(r"[ \t]+", " ", s)
                s = re.sub(r"\n{3,}", "\n\n", s)
                return s.strip()

            def _script_counts(s: str) -> dict:
                # 간단 스크립트 카운트(ko/ja 판단용). 외부 의존 없이 UI 배치에서만 사용.
                c = {"hangul": 0, "kana": 0, "cjk": 0, "latin": 0, "digit": 0, "other": 0}
                for ch in (s or ""):
                    o = ord(ch)
                    if 0xAC00 <= o <= 0xD7A3:
                        c["hangul"] += 1
                    elif (0x3040 <= o <= 0x309F) or (0x30A0 <= o <= 0x30FF):
                        c["kana"] += 1
                    elif 0x4E00 <= o <= 0x9FFF:
                        c["cjk"] += 1
                    elif (0x0030 <= o <= 0x0039):
                        c["digit"] += 1
                    elif (0x0041 <= o <= 0x005A) or (0x0061 <= o <= 0x007A):
                        c["latin"] += 1
                    else:
                        c["other"] += 1
                return c

            def _looks_like_ko(s: str) -> bool:
                c = _script_counts(s)
                # 한글이 조금이라도 있으면 ko로 간주(보수적으로).
                return c["hangul"] > 0

            def _looks_like_ja(s: str) -> bool:
                c = _script_counts(s)
                # 가나가 있으면 거의 일본어. 한자만 있는 경우도 있어 kana+cjk로 완화.
                return (c["kana"] > 0) or (c["cjk"] > 0 and c["hangul"] == 0)

            def _should_overwrite_ko_text_fields(cur_ko: str) -> bool:
                """
                제목/시놉시스처럼 '마스터 매핑'이 아닌 텍스트 필드는
                - 비었거나
                - 한국어가 아닌 것으로 보일 때만
                덮어쓴다.
                """
                cur_ko = _s(cur_ko)
                if not cur_ko:
                    return True
                if _looks_like_ko(cur_ko):
                    return False
                return _looks_like_ja(cur_ko) or True

            def _split_csv(s: str) -> list[str]:
                return [x.strip() for x in (s or "").split(",") if x.strip()]

            def _map_csv(src: str, mp: dict[str, str], unknown_samples: list[str]) -> str:
                out: list[str] = []
                for tok in _split_csv(src):
                    rep = (mp.get(tok) or "").strip()
                    if rep:
                        out.append(rep)
                    else:
                        out.append(tok)
                        if tok not in unknown_samples and len(unknown_samples) < 10:
                            unknown_samples.append(tok)
                return ", ".join(out).strip()

            updated = {"genres": 0, "actors": 0, "maker": 0, "title": 0, "synopsis": 0}
            skipped = {"genres": 0, "actors": 0, "maker": 0, "title": 0, "synopsis": 0}
            unknown_samples = {"genres": [], "actors": [], "maker": []}

            session = get_db_session()
            try:
                gmap = {(_s(r.japanese)): _s(r.korean) for r in session.query(Genre).all() if _s(r.japanese) and _s(r.korean)}
                amap = {(_s(r.japanese)): _s(r.korean) for r in session.query(Actress).all() if _s(r.japanese) and _s(r.korean)}
                mmap = {(_s(r.japanese)): _s(r.korean) for r in session.query(Maker).all() if _s(r.japanese) and _s(r.korean)}
                # 역매핑(ko->ja). 과거 재동기화로 레거시 필드가 ko로 덮였을 때도,
                # 마스터 변경을 다시 반영할 수 있도록 원본(ja) 토큰을 복원하는 데 사용한다.
                grev = {(_s(r.korean)): _s(r.japanese) for r in session.query(Genre).all() if _s(r.japanese) and _s(r.korean)}
                arev = {(_s(r.korean)): _s(r.japanese) for r in session.query(Actress).all() if _s(r.japanese) and _s(r.korean)}
                mrev = {(_s(r.korean)): _s(r.japanese) for r in session.query(Maker).all() if _s(r.japanese) and _s(r.korean)}

                def _restore_ja_csv_from_ko(src_ko: str, rev: dict[str, str]) -> str:
                    toks = _split_csv(src_ko)
                    if not toks:
                        return ""
                    out: list[str] = []
                    restored = 0
                    for t in toks:
                        jp = _s(rev.get(t) or "")
                        if jp:
                            out.append(jp)
                            restored += 1
                        else:
                            out.append(t)
                    # 절반 이상 복원되면 ja로 간주
                    if restored >= max(1, len(toks) // 2):
                        return ", ".join(out).strip()
                    return ""

                def _source_csv(ja_field: str, legacy_field: str, rev: dict[str, str]) -> str:
                    ja = _s(ja_field)
                    if ja:
                        return ja
                    legacy = _s(legacy_field)
                    if not legacy:
                        return ""
                    # 레거시가 일본어로 보이면 그대로 사용
                    if _looks_like_ja(legacy):
                        return legacy
                    # 레거시가 한국어로 보이면 역매핑으로 일본어 토큰 복원 시도
                    if _looks_like_ko(legacy):
                        restored = _restore_ja_csv_from_ko(legacy, rev)
                        if restored:
                            return restored
                    return legacy

                def _source_single(ja_field: str, legacy_field: str, rev: dict[str, str]) -> str:
                    ja = _s(ja_field)
                    if ja:
                        return ja
                    legacy = _s(legacy_field)
                    if not legacy:
                        return ""
                    if _looks_like_ja(legacy):
                        return legacy
                    if _looks_like_ko(legacy):
                        jp = _s(rev.get(legacy) or "")
                        if jp:
                            return jp
                    return legacy

                # SQLite + SQLAlchemy에서 streaming(yield_per) iterator를 돌리는 중간에 commit을 하면
                # 커서/연결이 끊기면서 "Cannot operate on a closed database"가 날 수 있다.
                # 안전하게 ID를 청크로 가져와 청크 단위로 처리/커밋한다.
                last_id = 0
                chunk_size = 200
                total_rows = 0
                total_commits = 0
                while True:
                    id_q = session.query(JAVMetadata.id).filter(JAVMetadata.id > last_id)
                    if self._product_codes:
                        id_q = id_q.filter(JAVMetadata.product_code.in_(self._product_codes))
                    ids = [r[0] for r in id_q.order_by(JAVMetadata.id.asc()).limit(chunk_size).all()]
                    if not ids:
                        break
                    last_id = int(ids[-1] or last_id)
                    total_rows += len(ids)

                    dirty = 0
                    for mid in ids:
                        row = session.query(JAVMetadata).filter_by(id=mid).first()
                        if not row:
                            continue

                        changed = False
                        # 장르
                        # 요청사항: DB 파일에서 마스터 테이블 값을 직접 수정한 뒤 "재동기화"를 누르면
                        # 항상 마스터 매핑 결과가 jav_metadata에 반영되도록, ko에 한글이 있어도 다시 계산/반영한다.
                        src = _source_csv(getattr(row, "genres_ja", None), getattr(row, "genres", None), grev)
                        if src:
                            mapped = _map_csv(src, gmap, unknown_samples["genres"])
                            if mapped and (_s(getattr(row, "genres_ko", None)) != mapped or _s(getattr(row, "genres", None)) != mapped):
                                row.genres_ko = mapped
                                row.genres = mapped
                                updated["genres"] += 1
                                changed = True
                            else:
                                skipped["genres"] += 1
                        else:
                            skipped["genres"] += 1

                        # 배우
                        src = _source_csv(getattr(row, "actors_ja", None), getattr(row, "actors", None), arev)
                        if src:
                            mapped = _map_csv(src, amap, unknown_samples["actors"])
                            if mapped and (_s(getattr(row, "actors_ko", None)) != mapped or _s(getattr(row, "actors", None)) != mapped):
                                row.actors_ko = mapped
                                row.actors = mapped
                                updated["actors"] += 1
                                changed = True
                            else:
                                skipped["actors"] += 1
                        else:
                            skipped["actors"] += 1

                        # 메이커(단일)
                        src = _source_single(getattr(row, "maker_ja", None), getattr(row, "maker", None), mrev)
                        if src:
                            mapped = _s(mmap.get(src) or "")
                            if not mapped:
                                mapped = src
                                if src not in unknown_samples["maker"] and len(unknown_samples["maker"]) < 10:
                                    unknown_samples["maker"].append(src)
                            if mapped and (_s(getattr(row, "maker_ko", None)) != mapped or _s(getattr(row, "maker", None)) != mapped):
                                row.maker_ko = mapped
                                row.maker = mapped
                                updated["maker"] += 1
                                changed = True
                            else:
                                skipped["maker"] += 1
                        else:
                            skipped["maker"] += 1

                        # 제목/시놉시스(규칙 기반 copy/정리: 레거시 필드만 정리해서 ko로 복구)
                        if _should_overwrite_ko_text_fields(getattr(row, "title_ko", None)):
                            src = _clean_ws(_s(getattr(row, "title", None)))
                            if src and _s(getattr(row, "title_ko", None)) != src:
                                row.title_ko = src
                                row.title = src
                                updated["title"] += 1
                                changed = True
                            else:
                                skipped["title"] += 1
                        else:
                            skipped["title"] += 1

                        if _should_overwrite_ko_text_fields(getattr(row, "synopsis_ko", None)):
                            src = _clean_ws(_s(getattr(row, "synopsis", None)))
                            if src and _s(getattr(row, "synopsis_ko", None)) != src:
                                row.synopsis_ko = src
                                row.synopsis = src
                                updated["synopsis"] += 1
                                changed = True
                            else:
                                skipped["synopsis"] += 1
                        else:
                            skipped["synopsis"] += 1

                        if changed:
                            dirty += 1

                    if dirty > 0:
                        session.commit()
                        total_commits += 1

            finally:
                session.close()

            self.finished.emit({"updated": updated, "skipped": skipped, "unknown_samples": unknown_samples})
        except Exception as e:
            self.error.emit(str(e))


class LibraryModel(QObject):
    _instance = None

    @staticmethod
    def instance() -> LibraryModel | None:
        return LibraryModel._instance

    # 검색 및 필터링 관련 시그널
    searchQueryChanged = Signal()
    filterModeChanged = Signal()
    sortModeChanged = Signal()
    favoriteDeltaDaysChanged = Signal()
    monthFilterChanged = Signal()
    monthFilterInputChanged = Signal()
    monthFilterErrorChanged = Signal()
    unknownOnlyChanged = Signal()
    workCountChanged = Signal()
    detailLoaded = Signal()
    summariesReloaded = Signal()  # DB 요약·연결 경로 갱신 시 (폴더 감시 목록 리프레시용)
    similarProductsReady = Signal(list)  # list of dicts
    similarBackTriggered = Signal()     # Signal to re-open similar popup on back

    # 품번, 사라진 경로, 후보 경로 목록 — 폴더 이동 감시에서 사용자 확인 팝업용
    folderBindingNeedsReview = Signal(str, str, list)
    
    # 스냅샷 추출 관련 시그널
    snapshotProgress = Signal(int, int) # current, total
    snapshotFinished = Signal(bool, str) # success, message
    logMessage = Signal(str)
    toastMessage = Signal(str, str)
    requestFolderSelection = Signal(str)
    isGeneratingDigestChanged = Signal()
    digestProgressChanged = Signal()
    isGeneratingHighlightChanged = Signal()
    highlightProgressChanged = Signal()
    isExtractingSnapshotsChanged = Signal()
    snapshotProgressMsgChanged = Signal()
    detailEditingChanged = Signal()
    translationNoteGeneratingChanged = Signal()
    isLoadingChanged = Signal()
    canLoadMoreChanged = Signal()
    loadedCountChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        LibraryModel._instance = self
        self._search_query = ""
        self._filter_mode = 0  # 0:All, 1:Analyzed, 2:Pending, 3:Linked, 4:Subtitled, 5:내 평가, 6:하트만, 7:스토리컨텍스트
        self._sort_mode = 0
        self._favorite_delta_days = 0  # 0:기간 ♥ 증감 표시 안 함, 7/30/90
        self._month_filter = ""  # ""=전체, "YYYY-MM"=특정 월, "unknown"=출시일 미상
        self._month_filter_input = ""
        self._month_filter_error = ""
        self._unknown_only = False
        self._all_summaries: list = []
        self._works = WorkListModel(self)
        self._detail = LibraryDetailObject(self)
        self._snapshot_worker = None
        self._digest_worker = None
        self._is_generating_digest = False
        self._digest_progress = 0
        self._highlight_worker = None
        self._is_generating_highlight = False
        self._highlight_progress = 0
        self._metadata_resync_worker = None
        self._is_extracting_snapshots = False
        self._snapshot_progress_msg = ""
        self._detail_editing = False
        self._edit_draft = DetailEditDraft(self)
        self._scene_edit = SceneEditModel(self)
        self._translation_note_generating = False
        self._note_gen_worker = None
        self._is_loading = False
        self._reload_worker = None
        # 전체 라이브러리를 한 번에 표시(페이지네이션 비활성)
        # gui.library_data.load_library_summaries_fast_paged 에서 limit<=0이면 q.all()로 전체 로드한다.
        self._page_size = 0
        self._page_offset = 0
        self._can_load_more = False
        self._is_loading_more = False
        # (base_pc -> preview_path) 캐시: `_rebuild()`에서 per-item disk stat 폭탄 방지용
        self._preview_path_cache: dict[str, str] = {}
        self._detail_history: list[str] = []
        # availableGenres() 빈도 집계 캐시 — _all_summaries 길이가 바뀌면 무효화
        self._genres_cache_sig: int = -1
        self._genres_cache: list[dict] = []


        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(180)
        self._debounce.timeout.connect(self._rebuild)

    @Property(QObject, constant=True)
    def works(self): return self._works

    @Property(QObject, constant=True)
    def detail(self): return self._detail

    @Property(QObject, constant=True)
    def editDraft(self): return self._edit_draft

    @Property(QObject, constant=True)
    def sceneEdit(self): return self._scene_edit

    @Property(bool, notify=detailEditingChanged)
    def detailEditing(self) -> bool:
        return self._detail_editing

    @Property(bool, notify=translationNoteGeneratingChanged)
    def translationNoteGenerating(self) -> bool:
        return bool(self._translation_note_generating)

    @Property(bool, notify=isLoadingChanged)
    def isLoading(self): return self._is_loading

    @Property(bool, notify=canLoadMoreChanged)
    def canLoadMore(self) -> bool:
        return bool(self._can_load_more and not self._is_loading and not self._is_loading_more)

    @Property(int, notify=loadedCountChanged)
    def loadedCount(self) -> int:
        try:
            return len(self._all_summaries or [])
        except Exception:
            return 0

    @Property(str, notify=searchQueryChanged)
    def searchQuery(self): return self._search_query
    @searchQuery.setter
    def searchQuery(self, v: str):
        if v != self._search_query:
            self._search_query = v
            self.searchQueryChanged.emit()
            self._debounce.start()

    @Property(int, notify=filterModeChanged)
    def filterMode(self): return self._filter_mode
    @filterMode.setter
    def filterMode(self, v: int):
        if v != self._filter_mode:
            self._filter_mode = v
            self.filterModeChanged.emit()
            self._rebuild()

    @Property(int, notify=sortModeChanged)
    def sortMode(self): return self._sort_mode
    @sortMode.setter
    def sortMode(self, v: int):
        if v != self._sort_mode:
            self._sort_mode = v
            self.sortModeChanged.emit()
            self._rebuild()

    @Property(int, notify=favoriteDeltaDaysChanged)
    def favoriteDeltaDays(self) -> int:
        return int(self._favorite_delta_days or 0)

    @favoriteDeltaDays.setter
    def favoriteDeltaDays(self, v: int):
        choices = {0, 7, 30, 90}
        try:
            nv = int(v)
        except Exception:
            nv = 0
        if nv not in choices:
            nv = 0
        if nv != self._favorite_delta_days:
            self._favorite_delta_days = nv
            self.favoriteDeltaDaysChanged.emit()
            self._rebuild()

    @Property(str, notify=monthFilterChanged)
    def monthFilter(self) -> str:
        return self._month_filter

    @monthFilter.setter
    def monthFilter(self, v: str):
        nv = str(v or "").strip()
        if nv != self._month_filter:
            self._month_filter = nv
            self.monthFilterChanged.emit()
            self._rebuild()

    @Property(str, notify=monthFilterInputChanged)
    def monthFilterInput(self) -> str:
        return self._month_filter_input

    @monthFilterInput.setter
    def monthFilterInput(self, v: str):
        nv = str(v or "")
        if nv != self._month_filter_input:
            self._month_filter_input = nv
            self.monthFilterInputChanged.emit()

    @Property(str, notify=monthFilterErrorChanged)
    def monthFilterError(self) -> str:
        return self._month_filter_error

    @Property(bool, notify=unknownOnlyChanged)
    def unknownOnly(self) -> bool:
        return bool(self._unknown_only)

    @unknownOnly.setter
    def unknownOnly(self, v: bool):
        nv = bool(v)
        if nv != self._unknown_only:
            self._unknown_only = nv
            self.unknownOnlyChanged.emit()
            self._rebuild()

    @Slot()
    def clearMonthFilter(self) -> None:
        self._month_filter_error = ""
        self.monthFilterErrorChanged.emit()
        self.monthFilterInput = ""
        self.monthFilter = ""
        self.unknownOnly = False

    @Slot()
    def applyMonthFilterInput(self) -> None:
        raw = (self._month_filter_input or "").strip()
        if not raw:
            self._month_filter_error = ""
            self.monthFilterErrorChanged.emit()
            self.monthFilter = ""
            return
        key = release_month_key(raw)
        if key == "unknown":
            self._month_filter_error = "형식 오류: YYYY-MM"
            self.monthFilterErrorChanged.emit()
            return
        self._month_filter_error = ""
        self.monthFilterErrorChanged.emit()
        self.monthFilter = key

    @Property(int, notify=workCountChanged)
    def workCount(self): return self._works.rowCount()

    @Property(bool, notify=isGeneratingDigestChanged)
    def isGeneratingDigest(self): return self._is_generating_digest
    @isGeneratingDigest.setter
    def isGeneratingDigest(self, v: bool):
        if v != self._is_generating_digest:
            self._is_generating_digest = v
            self.isGeneratingDigestChanged.emit()

    @Property(int, notify=digestProgressChanged)
    def digestProgress(self): return self._digest_progress
    @digestProgress.setter
    def digestProgress(self, v: int):
        if v != self._digest_progress:
            self._digest_progress = v
            self.digestProgressChanged.emit()

    @Property(bool, notify=isGeneratingHighlightChanged)
    def isGeneratingHighlight(self): return self._is_generating_highlight
    @isGeneratingHighlight.setter
    def isGeneratingHighlight(self, v: bool):
        if v != self._is_generating_highlight:
            self._is_generating_highlight = v
            self.isGeneratingHighlightChanged.emit()

    @Property(int, notify=highlightProgressChanged)
    def highlightProgress(self): return self._highlight_progress
    @highlightProgress.setter
    def highlightProgress(self, v: int):
        if v != self._highlight_progress:
            self._highlight_progress = v
            self.highlightProgressChanged.emit()

    @Property(bool, notify=isExtractingSnapshotsChanged)
    def isExtractingSnapshots(self): return self._is_extracting_snapshots
    @isExtractingSnapshots.setter
    def isExtractingSnapshots(self, v: bool):
        if v != self._is_extracting_snapshots:
            self._is_extracting_snapshots = v
            self.isExtractingSnapshotsChanged.emit()

    @Property(str, notify=snapshotProgressMsgChanged)
    def snapshotProgressMsg(self): return self._snapshot_progress_msg
    @snapshotProgressMsg.setter
    def snapshotProgressMsg(self, v: str):
        if v != self._snapshot_progress_msg:
            self._snapshot_progress_msg = v
            self.snapshotProgressMsgChanged.emit()

    # ── Slots ─────────────────────────────────────────

    @Slot()
    def reload(self):
        if self._is_loading:
            return
        
        self._is_loading = True
        self.isLoadingChanged.emit()

        if self._reload_worker and self._reload_worker.isRunning():
            from gui.utils.qt_worker import stop_qthread

            stop_qthread(self._reload_worker, context="LibraryReload")

        self._page_offset = 0
        self._can_load_more = True
        self.canLoadMoreChanged.emit()
        self.loadedCountChanged.emit()

        self._reload_worker = LibraryReloadWorker(limit=self._page_size, offset=self._page_offset, parent=self)
        self._reload_worker.finished.connect(self._on_reload_finished)
        self._reload_worker.error.connect(self._on_reload_error)
        self._reload_worker.start()

    def _on_reload_finished(self, summaries):
        self._all_summaries = list(summaries or [])
        self._page_offset = len(self._all_summaries)
        self._can_load_more = False
        self._is_loading = False
        self.isLoadingChanged.emit()
        self.canLoadMoreChanged.emit()
        self.loadedCountChanged.emit()
        # 로드 결과가 바뀌면 preview cache도 초기화
        self._preview_path_cache.clear()
        self._rebuild()
        self.summariesReloaded.emit()
        self.toastMessage.emit(f"{len(self._all_summaries)}건 로드 완료", "success")

    def _on_reload_error(self, err_msg):
        self._is_loading = False
        self.isLoadingChanged.emit()
        self._all_summaries = []
        self._preview_path_cache.clear()
        self._page_offset = 0
        self._can_load_more = True
        self.canLoadMoreChanged.emit()
        self.loadedCountChanged.emit()
        self._rebuild()
        self.summariesReloaded.emit()
        self.toastMessage.emit(f"라이브러리 로드 실패: {err_msg}", "error")

    @Slot()
    def loadMore(self) -> None:
        if self._is_loading or self._is_loading_more:
            return
        if not self._can_load_more:
            return

        self._is_loading_more = True
        self.canLoadMoreChanged.emit()

        w = LibraryReloadWorker(limit=self._page_size, offset=self._page_offset, parent=self)

        def _done(new_items):
            try:
                items = list(new_items or [])
                if items:
                    self._all_summaries.extend(items)
                    self._page_offset = len(self._all_summaries)
                # 페이지가 가득 안 찼으면 더 이상 없음
                self._can_load_more = bool(len(items) >= self._page_size)
            finally:
                self._is_loading_more = False
                self.canLoadMoreChanged.emit()
                self.loadedCountChanged.emit()
                self._rebuild()
                self.summariesReloaded.emit()
                try:
                    w.deleteLater()
                except Exception:
                    pass

        def _err(msg):
            self._is_loading_more = False
            self.canLoadMoreChanged.emit()
            self.toastMessage.emit(f"추가 로드 실패: {msg}", "error")
            try:
                w.deleteLater()
            except Exception:
                pass

        w.finished.connect(_done)
        w.error.connect(_err)
        w.start()

    @Slot(str)
    def loadDetail(self, product_code: str):
        # Navigation History: Push current SKU to history if it's different
        current_pc = self._detail.productCode
        if current_pc and current_pc != product_code:
            # Avoid duplicate consecutive entries
            if not self._detail_history or self._detail_history[-1] != current_pc:
                self._detail_history.append(current_pc)
                # Keep history reasonable (e.g., last 20)
                if len(self._detail_history) > 20:
                    self._detail_history.pop(0)

        self._loadDetailCore(product_code)

    def _loadDetailCore(self, product_code: str):
        s = LibraryDetailService.find_summary(self._all_summaries, product_code)
        if not s:
            return
        data = LibraryDetailService.build_detail_data(
            s,
            favorite_delta_days=int(self._favorite_delta_days or 0),
        )
        self._detail.load(data)
        self.detailLoaded.emit()

    @Slot()
    def clearDetailHistory(self):
        """Clear the navigation history when closing detail view completely."""
        self._detail_history.clear()

    @Slot(result=bool)
    def goBackDetail(self) -> bool:
        """Pop from history and load the previous product."""
        if self._detail_history:
            prev_pc = self._detail_history.pop()
            self._loadDetailCore(prev_pc)
            # Signal UI to re-open the similar popup
            self.similarBackTriggered.emit()
            return True
        return False


    @Slot()
    def resyncMetadataKo(self) -> None:
        """마스터 테이블 매핑 기반으로 genres/actors/maker + 레거시 필드 및 일부 텍스트(제목/시놉) 정리를 일괄 반영."""
        try:
            # QThread 객체가 deleteLater()로 삭제된 뒤에도 Python 참조가 남아있으면
            # RuntimeError: Internal C++ object already deleted 가 날 수 있어 방어적으로 처리한다.
            try:
                if self._metadata_resync_worker and self._metadata_resync_worker.isRunning():
                    self.toastMessage.emit("재동기화가 이미 실행 중입니다.", "info")
                    return
            except RuntimeError:
                self._metadata_resync_worker = None

            self.toastMessage.emit("재동기화를 시작합니다. (장르/배우/메이커/제목/시놉시스)", "info")
            w = MetadataResyncWorker(parent=self)
            self._metadata_resync_worker = w

            def _done(payload: dict):
                try:
                    up = payload.get("updated", {}) or {}
                    unk = payload.get("unknown_samples", {}) or {}
                    msg = (
                        f"재동기화 완료 · "
                        f"장르 {up.get('genres', 0)} / 배우 {up.get('actors', 0)} / 메이커 {up.get('maker', 0)} / "
                        f"제목 {up.get('title', 0)} / 시놉 {up.get('synopsis', 0)} 반영"
                    )
                    self.toastMessage.emit(msg, "success")

                    parts = []
                    if (unk.get("genres") or []):
                        parts.append("장르 미매핑: " + ", ".join((unk.get("genres") or [])[:5]))
                    if (unk.get("actors") or []):
                        parts.append("배우 미매핑: " + ", ".join((unk.get("actors") or [])[:5]))
                    if (unk.get("maker") or []):
                        parts.append("메이커 미매핑: " + ", ".join((unk.get("maker") or [])[:3]))
                    if parts:
                        self.toastMessage.emit(" / ".join(parts), "info")
                finally:
                    # 먼저 참조를 끊어, deleteLater 이후 재호출 시 '이미 삭제됨' 예외를 방지
                    if self._metadata_resync_worker is w:
                        self._metadata_resync_worker = None
                    # 전체 재동기화는 리스트 reload만으로는 현재 열려있는 상세 화면이 즉시 갱신되지 않을 수 있어
                    # 현재 상세 품번이 있으면 refreshProduct로 상세도 같이 갱신한다.
                    try:
                        cur_pc = (self._detail.productCode or "").strip().upper()
                        if cur_pc:
                            self.refreshProduct(cur_pc)
                    except Exception:
                        pass
                    try:
                        self.reload()
                    except Exception:
                        pass
                    try:
                        w.deleteLater()
                    except Exception:
                        pass

            def _err(err: str):
                try:
                    self.toastMessage.emit(f"재동기화 실패: {err}", "error")
                finally:
                    if self._metadata_resync_worker is w:
                        self._metadata_resync_worker = None
                    try:
                        w.deleteLater()
                    except Exception:
                        pass

            w.finished.connect(_done)
            w.error.connect(_err)
            w.start()
        except Exception as e:
            self.toastMessage.emit(f"재동기화 시작 실패: {e}", "error")

    @Slot(str)
    def resyncMetadataKoForProduct(self, product_code: str) -> None:
        pc = (product_code or "").strip().upper()
        if not pc:
            self.toastMessage.emit("품번이 없습니다.", "warning")
            return
        try:
            try:
                if self._metadata_resync_worker and self._metadata_resync_worker.isRunning():
                    self.toastMessage.emit("재동기화가 이미 실행 중입니다.", "info")
                    return
            except RuntimeError:
                self._metadata_resync_worker = None

            self.toastMessage.emit(f"{pc}: 메타데이터 재동기화를 시작합니다.", "info")
            w = MetadataResyncWorker(product_codes=[pc], parent=self)
            self._metadata_resync_worker = w

            def _done(payload: dict):
                try:
                    up = payload.get("updated", {}) or {}
                    msg = (
                        f"{pc}: 재동기화 완료 · "
                        f"장르 {up.get('genres', 0)} / 배우 {up.get('actors', 0)} / 메이커 {up.get('maker', 0)} / "
                        f"제목 {up.get('title', 0)} / 시놉 {up.get('synopsis', 0)} 반영"
                    )
                    self.toastMessage.emit(msg, "success")
                finally:
                    if self._metadata_resync_worker is w:
                        self._metadata_resync_worker = None
                    try:
                        self.refreshProduct(pc)
                    except Exception:
                        pass
                    try:
                        self.reload()
                    except Exception:
                        pass
                    try:
                        w.deleteLater()
                    except Exception:
                        pass

            def _err(err: str):
                try:
                    self.toastMessage.emit(f"{pc}: 재동기화 실패: {err}", "error")
                finally:
                    if self._metadata_resync_worker is w:
                        self._metadata_resync_worker = None
                    try:
                        w.deleteLater()
                    except Exception:
                        pass

            w.finished.connect(_done)
            w.error.connect(_err)
            w.start()
        except Exception as e:
            self.toastMessage.emit(f"{pc}: 재동기화 시작 실패: {e}", "error")

    @Slot(str)
    def openFolder(self, product_code: str):
        import os
        try:
            from javstory.harvest.database import get_db_session, JAVMetadata
            session = get_db_session()
            folder_to_open = None
            try:
                row = session.query(JAVMetadata).filter_by(product_code=product_code).first()
                if row and row.folder_path:
                    p = Path(row.folder_path)
                    if p.exists(): folder_to_open = p
            finally: session.close()
            if not folder_to_open:
                from javstory.library.paths import work_library_dir
                d = work_library_dir(product_code)
                if d.is_dir(): folder_to_open = d
            if folder_to_open: os.startfile(folder_to_open)
            else:
                self.toastMessage.emit("저장된 폴더 위치를 찾을 수 없습니다. 폴더를 직접 지정해 주세요.", "warning")
                self.requestFolderSelection.emit(product_code)
        except Exception as e: self.toastMessage.emit(f"폴더 열기 실패: {e}", "error")

    def _folder_bind_hooks(self) -> FolderBindHooks:
        return FolderBindHooks(
            toast=self.toastMessage.emit,
            refresh_product=self.refreshProduct,
            summaries_reloaded=self.summariesReloaded.emit,
            schedule_auto_snapshots=lambda p, fd: QTimer.singleShot(
                0,
                lambda p=p, fd=fd: self._maybe_auto_snapshots_after_folder_bind(p, fd),
            ),
        )

    def _bind_folder_impl(self, product_code: str, folder_path: str, force: bool) -> bool:
        return LibraryFolderBind.bind_folder(
            product_code,
            folder_path,
            force=force,
            hooks=self._folder_bind_hooks(),
        )

    @Slot(str, str)
    def bindFolder(self, product_code: str, folder_path: str):
        self._bind_folder_impl(product_code, folder_path, False)

    @Slot(str, str, bool, result=bool)
    def bindFolderForced(self, product_code: str, folder_path: str, force: bool) -> bool:
        """force=True면 품번 검증 불일치여도 저장."""
        return self._bind_folder_impl(product_code, folder_path, force)

    @Slot(str, str, result=list)
    def searchFolderBindingCandidates(self, product_code: str, old_path: str) -> list[str]:
        """라이브러리·미디어 루트에서 품번 폴더 후보 경로를 다시 검색한다 (팝업의 ‘다시 검색’용)."""
        from gui.folder_watch_service import search_folder_candidates

        pc = (product_code or "").strip().upper()
        op = (old_path or "").strip()
        return search_folder_candidates(pc, old_path=op if op else None)

    @Slot(str)
    def clearFolderBinding(self, product_code: str):
        LibraryFolderBind.clear_folder(product_code, self._folder_bind_hooks())

    @Slot(str, bool)
    def deleteFromLibrary(self, product_code: str, delete_files: bool = False):
        """
        라이브러리에서 작품 삭제.
        - 기본: DB 메타데이터 삭제(같은 base 품번의 분할 파트 포함)
        - 옵션: 로컬 산출물/미디어 폴더도 함께 삭제
        """
        try:
            from javstory.utils.product_code import strip_split_suffixes
            from javstory.harvest.database import get_db_session, JAVMetadata

            pc_raw = (product_code or "").strip().upper()
            if not pc_raw:
                self.toastMessage.emit("품번이 없습니다.", "warning")
                return
            base = strip_split_suffixes(pc_raw) or pc_raw

            session = get_db_session()
            try:
                # base 품번으로 묶인 모든 row 삭제 (멀티파트 포함)
                rows = session.query(JAVMetadata).all()
                targets = []
                for r in rows:
                    code = (getattr(r, "product_code", "") or "").strip().upper()
                    if not code:
                        continue
                    if (strip_split_suffixes(code) or code) == base:
                        targets.append(r)

                if not targets:
                    self.toastMessage.emit(f"DB에 품번 {base}가 없습니다.", "warning")
                    return

                for r in targets:
                    session.delete(r)
                session.commit()
            finally:
                try:
                    session.close()
                except Exception:
                    pass

            # 파일 삭제(선택)
            if bool(delete_files):
                try:
                    import shutil
                    from pathlib import Path
                    from javstory.config.app_config import E_MEDIA_ROOT, E_DATA_ROOT, DATA_ROOT
                    from javstory.library.paths import work_library_dir

                    dirs = [
                        work_library_dir(base),
                        Path(E_MEDIA_ROOT) / base,
                        Path(E_DATA_ROOT) / base,
                        Path(E_DATA_ROOT) / "media" / base,
                        Path(DATA_ROOT) / "media" / base,
                    ]
                    for d in dirs:
                        try:
                            if d.is_dir():
                                shutil.rmtree(d, ignore_errors=True)
                        except Exception:
                            continue
                except Exception as e:
                    self.toastMessage.emit(f"파일 삭제 중 일부 실패: {e}", "warning")

            # UI 갱신
            try:
                self._all_summaries = [s for s in (self._all_summaries or []) if (s.product_code or "").strip().upper() != base]
            except Exception:
                pass
            self.reload()
            self.toastMessage.emit(
                f"삭제 완료: {base}" + (" (파일 포함)" if delete_files else ""),
                "success",
            )
        except Exception as e:
            self.toastMessage.emit(f"삭제 실패: {e}", "error")

    @Slot(str)
    def refreshProduct(self, product_code: str):
        try:
            pc = (product_code or "").strip().upper()
            if not pc: return
            found = False
            for i, s in enumerate(self._all_summaries):
                if s.product_code == pc:
                    from gui.library_data import row_to_summary
                    from javstory.harvest.database import get_db_session, JAVMetadata
                    session = get_db_session()
                    try:
                        row = session.query(JAVMetadata).filter_by(product_code=pc).first()
                        if row:
                            new_s = row_to_summary(row)
                            self._all_summaries[i] = new_s
                            found = True
                    finally: session.close()
                    break
            
            if found:
                # 2. 현재 상세 페이지(DetailView)가 해당 품번이면 즉시 다시 로드하여 UI 갱신
                if self._detail.productCode == pc:
                    self.loadDetail(pc)
                # 3. 전체 목록 재구성 필터링 반영
                self._rebuild()
        except Exception as e:
            _ = e

    def _set_detail_editing(self, v: bool) -> None:
        if bool(v) != self._detail_editing:
            self._detail_editing = bool(v)
            self.detailEditingChanged.emit()

    @Slot()
    def beginDetailEdit(self):
        pc = (self._detail.productCode or "").strip().upper()
        if not pc:
            self.toastMessage.emit("품번이 없습니다.", "warning")
            return
        try:
            from javstory.harvest.database import get_db_session, JAVMetadata, Actress

            actress_note = ""
            actress_target_ja = ""
            session = get_db_session()
            try:
                row = session.query(JAVMetadata).filter_by(product_code=pc).first()
                if not row:
                    self.toastMessage.emit(f"DB에 품번 {pc}가 없습니다.", "error")
                    return
                self._edit_draft.load_from_row(row)
                # 첫 일본어 배우 1명의 노트만 편집 대상으로 노출
                first_ja = ""
                src = (row.actors_ja or "").strip()
                if src:
                    parts = [x.strip() for x in src.split(",") if x.strip()]
                    if parts:
                        first_ja = parts[0]
                if first_ja:
                    a = session.query(Actress).filter_by(japanese=first_ja).first()
                    if a is not None:
                        actress_note = (getattr(a, "translation_note", None) or "")
                        actress_target_ja = first_ja
            finally:
                session.close()

            from javstory.library.detail_persist import load_canonical_for_product

            st = load_canonical_for_product(pc)
            self._scene_edit.load_entries(st.scenes)
            self._edit_draft.set_translation_notes(
                work_note=st.translation_note or "",
                actress_note=actress_note,
                actress_target_ja=actress_target_ja,
            )

            self._set_detail_editing(True)
        except Exception as e:
            self.toastMessage.emit(f"편집 시작 실패: {e}", "error")

    @Slot()
    def cancelDetailEdit(self):
        pc = (self._detail.productCode or "").strip().upper()
        self._set_detail_editing(False)
        if not pc:
            return
        try:
            from javstory.harvest.database import get_db_session, JAVMetadata, Actress
            from javstory.library.detail_persist import load_canonical_for_product

            actress_note = ""
            actress_target_ja = ""
            session = get_db_session()
            try:
                row = session.query(JAVMetadata).filter_by(product_code=pc).first()
                if row:
                    self._edit_draft.load_from_row(row)
                    src = (row.actors_ja or "").strip()
                    if src:
                        parts = [x.strip() for x in src.split(",") if x.strip()]
                        if parts:
                            actress_target_ja = parts[0]
                            a = session.query(Actress).filter_by(japanese=parts[0]).first()
                            if a is not None:
                                actress_note = (getattr(a, "translation_note", None) or "")
            finally:
                session.close()
            st = load_canonical_for_product(pc)
            self._scene_edit.load_entries(st.scenes)
            self._edit_draft.set_translation_notes(
                work_note=st.translation_note or "",
                actress_note=actress_note,
                actress_target_ja=actress_target_ja,
            )
        except Exception as e:
            _ = e

    def _set_translation_note_generating(self, v: bool) -> None:
        if bool(v) != self._translation_note_generating:
            self._translation_note_generating = bool(v)
            self.translationNoteGeneratingChanged.emit()

    @Slot(str)
    def generateWorkTranslationNote(self, productCode: str):
        """Gemini로 작품 번역 노트 초안 생성 → editDraft.translationNote에 채움."""
        pc = (productCode or "").strip().upper()
        if not pc:
            self.toastMessage.emit("품번이 없습니다.", "warning")
            return
        if self._translation_note_generating:
            return

        try:
            from javstory.translation.translation_note_generator import WorkNoteContext
            from javstory.harvest.database import get_db_session, JAVMetadata
        except Exception as e:
            self.toastMessage.emit(f"노트 생성 모듈 로드 실패: {e}", "error")
            return

        ctx = WorkNoteContext(product_code=pc)
        try:
            session = get_db_session()
            try:
                row = session.query(JAVMetadata).filter_by(product_code=pc).first()
                if row:
                    ctx.title_ja = (row.title_ja or row.original_title or "") or ""
                    ctx.title_ko = (row.title_ko or row.title or "") or ""
                    ctx.actress_ko = (row.actors_ko or row.actors or "") or ""
                    ctx.actress_ja = row.actors_ja or ""
                    ctx.maker = (row.maker_ko or row.maker or "") or ""
                    ctx.genres = (row.genres_ko or row.genres or "") or ""
                    ctx.synopsis = (row.synopsis_ko or row.synopsis or "") or ""
            finally:
                session.close()
        except Exception:
            pass

        try:
            from javstory.library.detail_persist import load_canonical_for_product
            st = load_canonical_for_product(pc)
            ctx.overall_summary = st.overall_summary or ""
        except Exception:
            pass

        try:
            ctx.sample_dialogue_ja = self._sample_ja_subtitle_lines(pc, max_lines=80)
        except Exception:
            ctx.sample_dialogue_ja = ""

        self._set_translation_note_generating(True)
        worker = _NoteGenWorker("work", ctx, self)
        worker.finished.connect(self._on_note_gen_finished)
        self._note_gen_worker = worker
        worker.start()

    @Slot(str)
    def generateActressTranslationNote(self, japaneseName: str):
        """Gemini로 배우 번역 노트 초안 생성 → editDraft.actressTranslationNote에 채움."""
        ja = (japaneseName or "").strip()
        if not ja:
            self.toastMessage.emit("배우 일본어 표기가 없습니다.", "warning")
            return
        if self._translation_note_generating:
            return

        try:
            from javstory.translation.translation_note_generator import ActressNoteContext
            from javstory.harvest.database import get_db_session, JAVMetadata, Actress
        except Exception as e:
            self.toastMessage.emit(f"노트 생성 모듈 로드 실패: {e}", "error")
            return

        ctx = ActressNoteContext(japanese=ja)
        try:
            session = get_db_session()
            try:
                a = session.query(Actress).filter_by(japanese=ja).first()
                if a is not None:
                    ctx.korean = a.korean or ""
                    ctx.romaji = a.romaji or ""
                # 같은 배우의 최근 작품 제목 샘플링(최대 12개)
                rows = (
                    session.query(JAVMetadata)
                    .filter(JAVMetadata.actors_ja.ilike(f"%{ja}%"))
                    .order_by(JAVMetadata.release_date.desc())
                    .limit(12)
                    .all()
                )
                titles: list[str] = []
                for r in rows:
                    t = (r.title_ja or r.original_title or r.title_ko or r.title or "").strip()
                    if t:
                        titles.append(f"- {r.product_code}: {t}")
                if titles:
                    ctx.sample_titles = "\n".join(titles)
            finally:
                session.close()
        except Exception:
            pass

        self._set_translation_note_generating(True)
        worker = _NoteGenWorker("actress", ctx, self)
        worker.finished.connect(self._on_note_gen_finished)
        self._note_gen_worker = worker
        worker.start()

    def _on_note_gen_finished(self, kind: str, ok: bool, payload: str):
        self._set_translation_note_generating(False)
        if not ok:
            self.toastMessage.emit(f"번역 노트 생성 실패: {payload}", "error")
            return
        if not (payload or "").strip():
            self.toastMessage.emit("번역 노트가 비어 있습니다.", "warning")
            return
        if kind == "work":
            self._edit_draft.translationNote = payload
            self.toastMessage.emit("작품 번역 노트 초안 생성 완료(저장 버튼으로 확정)", "success")
        elif kind == "actress":
            self._edit_draft.actressTranslationNote = payload
            self.toastMessage.emit("배우 번역 노트 초안 생성 완료(저장 버튼으로 확정)", "success")

    def _sample_ja_subtitle_lines(self, product_code: str, *, max_lines: int = 80) -> str:
        """해당 작품의 일본어 자막에서 대사 샘플을 추출(노트 생성 컨텍스트용)."""
        try:
            from gui.library_data import find_all_video_paths_for_product
            from javstory.library.multipart.srt_timeline import sibling_srt_for_video
        except Exception:
            return ""
        paths = find_all_video_paths_for_product(product_code) or []
        for vp in paths:
            try:
                sp = sibling_srt_for_video(Path(vp))
                if sp and sp.is_file():
                    txt = sp.read_text(encoding="utf-8", errors="ignore")
                    return _extract_dialogue_lines(txt, max_lines=max_lines)
            except Exception:
                continue
        return ""

    @Slot(result=bool)
    def saveDetailEdit(self) -> bool:
        pc = (self._edit_draft.productCode or "").strip().upper()
        if not pc:
            self.toastMessage.emit("품번이 없습니다.", "warning")
            return False
        try:
            from javstory.harvest.database import get_db_session, JAVMetadata, Actress
            from javstory.library.detail_persist import persist_metadata_row_and_sync_files

            session = get_db_session()
            try:
                row = session.query(JAVMetadata).filter_by(product_code=pc).first()
                if not row:
                    self.toastMessage.emit(f"DB에 품번 {pc}가 없습니다.", "error")
                    return False
                self._edit_draft.apply_to_row(row)
                # 배우 노트(첫 배우만 편집) 저장
                target_ja = (self._edit_draft.actressNoteTargetJa or "").strip()
                if target_ja:
                    a = session.query(Actress).filter_by(japanese=target_ja).first()
                    if a is not None:
                        a.translation_note = (self._edit_draft.actressTranslationNote or "") or None
                session.commit()
                session.refresh(row)
                scenes = self._scene_edit.to_entries()
                persist_metadata_row_and_sync_files(
                    pc,
                    row,
                    scenes_override=scenes,
                    translation_note_override=str(self._edit_draft.translationNote or ""),
                )
            finally:
                session.close()

            self._set_detail_editing(False)
            self.refreshProduct(pc)
            self.toastMessage.emit("저장되었습니다.", "success")
            return True
        except Exception as e:
            self.toastMessage.emit(f"저장 실패: {e}", "error")
            return False

    @Slot(str)
    def findSimilarProducts(self, productCode: str):
        """특정 품번 기준 유사 작품 Top 10을 검색하여 similarProductsReady 시그널로 전달."""
        pc = (productCode or "").strip().upper()
        if not pc:
            return

        def _job():
            try:
                from javstory.library.embeddings.similarity import find_similar_products
                from javstory.harvest.database import get_db_session, JAVMetadata
                from gui.library_data import row_to_summary
                import os

                model = (os.environ.get("JAVSTORY_EMBEDDINGS_OLLAMA_MODEL", "") or "").strip() or "nomic-embed-text"
                
                # 1. 기준 작품 메타데이터 조회 (공통 요소 분석용)
                session = get_db_session()
                query_row = session.query(JAVMetadata).filter_by(product_code=pc).first()
                query_genres = set()
                query_actors = set()
                query_maker = ""
                if query_row:
                    query_genres = set([x.strip() for x in (query_row.genres_ko or "").split(",") if x.strip()])
                    query_actors = set([x.strip() for x in (query_row.actors_ko or "").split(",") if x.strip()])
                    query_maker = (query_row.maker_ko or query_row.maker or "").strip()
                
                # [추가] Grok 스토리 컨텍스트 로드 (문맥 분석용)
                query_grok_text = ""
                try:
                    from javstory.config.app_config import library_story_context_batch_tier
                    from javstory.translation.story_grok_module import load_cached_grok_json_flexible

                    grok = load_cached_grok_json_flexible(pc, library_story_context_batch_tier())
                    if grok:
                        query_grok_text = " ".join([
                            str(grok.get("overall_summary") or ""),
                            str(grok.get("synopsis_short") or ""),
                            " ".join([str(s.get("scene_summary") or "") for s in (grok.get("scenes") or [])])
                        ])
                except Exception:
                    pass


                # 2. 유사 품번 검색
                results = find_similar_products(pc, model=model, top_k=10)
                if not results:
                    session.close()
                    self.similarProductsReady.emit([])
                    return

                # 3. 검색된 품번들의 메타데이터를 DB에서 조회하여 Summary로 변환
                final_list = []
                try:
                    for r in results:
                        row = session.query(JAVMetadata).filter_by(product_code=r.product_code).first()
                        if row:
                            summary = row_to_summary(row)
                            d = asdict(summary)
                            d["similarity_score"] = float(r.score)
                            
                            # 공통 요소 분석 (Reasoning)
                            res_genres = set([x.strip() for x in (row.genres_ko or "").split(",") if x.strip()])
                            res_actors = set([x.strip() for x in (row.actors_ko or "").split(",") if x.strip()])
                            res_maker = (row.maker_ko or row.maker or "").strip()
                            
                            reasons = []
                            if query_maker and query_maker == res_maker:
                                reasons.append(f"동일 제작사({query_maker})")
                            
                            common_actors = query_actors.intersection(res_actors)
                            if common_actors:
                                actors_str = ", ".join(list(common_actors)[:2])
                                reasons.append(f"동일 배우({actors_str})")
                                
                            common_genres = query_genres.intersection(res_genres)
                            # [고도화] 너무 일반적인 장르(독점, 고화질 등)는 공통 장르 분석에서 제외
                            from javstory.config.app_config import similarity_excluded_genres_from_env
                            excluded_set = similarity_excluded_genres_from_env()
                            
                            common_genres = {g for g in common_genres if g not in excluded_set}


                            if common_genres:
                                genres_str = ", ".join(list(sorted(common_genres))[:2])
                                reasons.append(f"공통 장르({genres_str})")

                            # [추가] 테마 키워드 기반 문맥 분석
                            from javstory.config.app_config import SIMILARITY_THEME_KEYWORDS
                            def _get_search_text(r, extra=""):
                                return " ".join([str(r.title_ko or ""), str(r.synopsis_ko or ""), str(r.genres_ko or ""), extra]).replace(" ", "")
                            
                            q_search = _get_search_text(query_row, query_grok_text)
                            r_search = _get_search_text(row) # 결과쪽은 성능상 DB 메타만 우선 참조
                            
                            common_themes = [kw for kw in SIMILARITY_THEME_KEYWORDS if kw.replace(" ", "") in q_search and kw.replace(" ", "") in r_search]
                            
                            # [고도화] 구체적인 근거 설명 생성
                            main_reasons = []
                            if query_maker and query_maker == res_maker: main_reasons.append(f"제작사({query_maker})")
                            if common_actors: main_reasons.append(f"배우({', '.join(list(common_actors)[:1])})")
                            if common_genres: main_reasons.append(f"장르({', '.join(list(sorted(common_genres))[:1])})")
                            
                            explanation = ""
                            if main_reasons:
                                explanation = " · ".join(main_reasons) + "가 동일하고, "
                            
                            # 임베딩 기반 상세 분석 이유 추가
                            emb_reasons = r.match_reasons or []
                            if common_themes:
                                emb_reasons.append(f"'{', '.join(common_themes[:2])}' 테마")
                                
                            if emb_reasons:
                                explanation += f"{' 및 '.join(emb_reasons)} 중심의 전개가 매우 유사합니다."
                            else:
                                explanation += "전반적인 스토리의 흐름과 분위기가 흡사합니다."
                            
                            d["reasoning"] = explanation
                            final_list.append(d)

                finally:
                    session.close()

                self.similarProductsReady.emit(final_list)
            except Exception as e:
                print(f"[LibraryModel] findSimilarProducts error: {e}")
                self.similarProductsReady.emit([])

        threading.Thread(target=_job, daemon=True).start()

    @Slot(result=bool)
    def saveSceneEditsOnly(self) -> bool:
        """DB 메타는 건드리지 않고 씬 배열만 library_state + Grok 캐시에 저장."""
        pc = (self._detail.productCode or "").strip().upper()
        if not pc:
            self.toastMessage.emit("품번이 없습니다.", "warning")
            return False
        if not self._detail_editing:
            self.toastMessage.emit("편집 모드에서만 사용할 수 있습니다.", "warning")
            return False
        try:
            from javstory.library.detail_persist import persist_scenes_only

            persist_scenes_only(pc, self._scene_edit.to_entries())
            self.refreshProduct(pc)
            self.toastMessage.emit("씬 저장 완료", "success")
            return True
        except Exception as e:
            self.toastMessage.emit(f"씬 저장 실패: {e}", "error")
            return False

    @Slot(str, str, str, result=bool)
    def insertNewMaker(self, ja: str, ko: str, en: str) -> bool:
        ja, ko, en = (ja or "").strip(), (ko or "").strip(), (en or "").strip()
        if not ja and not ko:
            self.toastMessage.emit("메이커 일본어 또는 한국어를 입력하세요.", "warning")
            return False
        slug = en or ko or ja
        jp = ja or ko
        try:
            from javstory.harvest.database import get_db_session, Maker

            session = get_db_session()
            try:
                existing = session.query(Maker).filter_by(japanese=jp).first()
                if existing:
                    self.toastMessage.emit("같은 일본어 이름의 메이커가 이미 있습니다.", "warning")
                    return False
                session.add(Maker(japanese=jp, korean=ko or None, english=en or None, slug=slug))
                session.commit()
                self._edit_draft.makerJa = jp
                self._edit_draft.makerKo = ko
                self._edit_draft.makerEn = en
                self._edit_draft.makerZhCn = ""
                self._edit_draft.makerZhTw = ""
            finally:
                session.close()
            self.toastMessage.emit("메이커가 추가되었습니다.", "success")
            return True
        except Exception as e:
            self.toastMessage.emit(f"메이커 추가 실패: {e}", "error")
            return False

    @Slot(str, result=list)
    def searchMakers(self, query: str):
        try:
            from sqlalchemy import or_

            from javstory.harvest.database import get_db_session, Maker

            q = (query or "").strip()
            session = get_db_session()
            try:
                qry = session.query(Maker)
                if q:
                    like = f"%{q}%"
                    qry = qry.filter(
                        or_(Maker.japanese.like(like), Maker.korean.like(like), Maker.english.like(like)),
                    )
                rows = qry.order_by(Maker.japanese.asc()).limit(80).all()
                return [
                    {"japanese": r.japanese or "", "korean": r.korean or "", "english": r.english or "", "slug": r.slug or ""}
                    for r in rows
                ]
            finally:
                session.close()
        except Exception as e:
            _ = e
            return []

    @Slot(str, str, str)
    def applyMakerFields(self, ja: str, ko: str, en: str):
        self._edit_draft.makerJa = (ja or "").strip()
        self._edit_draft.makerKo = (ko or "").strip()
        self._edit_draft.makerEn = (en or "").strip()

    @Slot(str, str, str, str, str)
    def setDraftTitles(self, ko: str, ja: str, en: str, zhcn: str, zhtw: str):
        self._edit_draft.titleKo = (ko or "").strip()
        self._edit_draft.titleJa = (ja or "").strip()
        self._edit_draft.titleEn = (en or "").strip()
        self._edit_draft.titleZhCn = (zhcn or "").strip()
        self._edit_draft.titleZhTw = (zhtw or "").strip()

    @Slot(str, str, str, str, str)
    def setDraftSynopses(self, ko: str, ja: str, en: str, zhcn: str, zhtw: str):
        self._edit_draft.synopsisKo = (ko or "").strip()
        self._edit_draft.synopsisJa = (ja or "").strip()
        self._edit_draft.synopsisEn = (en or "").strip()
        self._edit_draft.synopsisZhCn = (zhcn or "").strip()
        self._edit_draft.synopsisZhTw = (zhtw or "").strip()

    @Slot(str, str)
    def insertNewGenre(self, ja: str, ko: str):
        ja, ko = (ja or "").strip(), (ko or "").strip()
        if not ja:
            self.toastMessage.emit("장르 일본어를 입력하세요.", "warning")
            return
        try:
            from javstory.harvest.database import Genre, get_db_session

            session = get_db_session()
            try:
                if session.query(Genre).filter_by(japanese=ja).first():
                    self.toastMessage.emit("같은 일본어 장르가 이미 있습니다.", "warning")
                    return
                session.add(Genre(japanese=ja, korean=ko or None, english=None))
                session.commit()
                cur = (self._edit_draft.genresKo or "").strip()
                add = ko or ja
                self._edit_draft.genresKo = (cur + ", " + add).strip(", ").strip() if cur else add
            finally:
                session.close()
            self.toastMessage.emit("장르가 추가되었습니다.", "success")
        except Exception as e:
            self.toastMessage.emit(f"장르 추가 실패: {e}", "error")

    @Slot(result=list)
    def availableGenres(self):
        """`_all_summaries`에 등장한 한국어 장르 빈도(상위 200). [{name, count}]."""
        sig = len(self._all_summaries or [])
        if sig == self._genres_cache_sig and self._genres_cache:
            return self._genres_cache
        counts: dict[str, int] = {}
        for s in self._all_summaries or []:
            raw = getattr(s, "genres_ko", None) or ""
            for g in str(raw).split(","):
                name = (g or "").strip()
                if not name:
                    continue
                counts[name] = counts.get(name, 0) + 1
        items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:200]
        self._genres_cache = [{"name": n, "count": c} for n, c in items]
        self._genres_cache_sig = sig
        return self._genres_cache

    @Slot(str, str)
    def addGenreToken(self, name: str, mode: str):
        """검색창에 `#name` 토큰을 추가/병합. mode ∈ {'and','or','not'}."""
        nm = (name or "").strip()
        if not nm:
            return
        m = (mode or "and").strip().lower()
        if m not in ("and", "or", "not"):
            m = "and"
        cur = (self._search_query or "").strip()
        tokens = _tokenize_search_expr(cur)

        def _quote(g: str) -> str:
            return f'"{g}"' if any(ch.isspace() for ch in g) else g

        nm_norm = _norm_token(nm)

        def _strip_tok(t: str) -> set[str]:
            res: set[str] = set()
            t2 = t
            negative = t2.startswith("-")
            if negative:
                t2 = t2[1:]
            for p in t2.split("|"):
                p = p.strip()
                if p.startswith("#"):
                    p = p[1:]
                if p:
                    res.add(_norm_token(p))
            return res

        new_tokens: list[str] = []
        for t in tokens:
            if not t:
                continue
            owners = _strip_tok(t)
            if nm_norm in owners:
                continue
            new_tokens.append(t)
        tokens = new_tokens

        if m == "not":
            tokens.append(f"-#{_quote(nm)}")
        elif m == "or":
            attached = False
            for i in range(len(tokens) - 1, -1, -1):
                t = tokens[i]
                if t.startswith("#"):
                    tokens[i] = t + f"|#{_quote(nm)}"
                    attached = True
                    break
            if not attached:
                tokens.append(f"#{_quote(nm)}")
        else:
            tokens.append(f"#{_quote(nm)}")

        new_q = " ".join(tokens).strip()
        if new_q != self._search_query:
            self._search_query = new_q
            self.searchQueryChanged.emit()
            self._debounce.start()

    @Slot(str)
    def removeGenreToken(self, name: str):
        """검색창에서 `name`이 들어간 모든 장르 토큰을 제거(OR 그룹 내 부분 제거 포함)."""
        nm = (name or "").strip()
        if not nm:
            return
        nm_norm = _norm_token(nm)
        cur = (self._search_query or "").strip()
        if not cur:
            return
        tokens = _tokenize_search_expr(cur)
        out: list[str] = []
        changed = False

        def _strip_quotes(s: str) -> str:
            s = s.strip()
            if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
                return s[1:-1]
            return s

        for t in tokens:
            negative = t.startswith("-")
            body = t[1:] if negative else t
            if not body.startswith("#") and "|" not in body:
                out.append(t)
                continue
            parts = [p.strip() for p in body.split("|") if p.strip()]
            if not parts:
                out.append(t)
                continue
            kept: list[str] = []
            for p in parts:
                p2 = p
                if p2.startswith("#"):
                    p2 = p2[1:]
                p2u = _strip_quotes(p2)
                if _norm_token(p2u) == nm_norm:
                    changed = True
                    continue
                kept.append(p)
            if not kept:
                changed = True
                continue
            rebuilt = "|".join(kept)
            if negative:
                rebuilt = "-" + rebuilt
            out.append(rebuilt)

        if not changed:
            return
        new_q = " ".join(out).strip()
        if new_q != self._search_query:
            self._search_query = new_q
            self.searchQueryChanged.emit()
            self._debounce.start()

    @Slot(str, result=list)
    def searchGenres(self, query: str):
        try:
            from sqlalchemy import or_

            from javstory.harvest.database import Genre, get_db_session

            q = (query or "").strip()
            session = get_db_session()
            try:
                qry = session.query(Genre)
                if q:
                    like = f"%{q}%"
                    qry = qry.filter(or_(Genre.japanese.like(like), Genre.korean.like(like), Genre.english.like(like)))
                rows = qry.order_by(Genre.japanese.asc()).limit(120).all()
                return [{"japanese": r.japanese or "", "korean": r.korean or "", "english": r.english or ""} for r in rows]
            finally:
                session.close()
        except Exception as e:
            _ = e
            return []

    @Slot(str)
    def appendGenreKo(self, label_ko: str):
        lab = (label_ko or "").strip()
        if not lab:
            return
        cur = (self._edit_draft.genresKo or "").strip()
        parts = [x.strip() for x in cur.split(",") if x.strip()]
        if lab not in parts:
            parts.append(lab)
        self._edit_draft.genresKo = ", ".join(parts)

    @Slot(str)
    def removeGenreChip(self, remove_label: str):
        remove_label = (remove_label or "").strip()
        cur = (self._edit_draft.genresKo or "").strip()
        parts = [x.strip() for x in cur.split(",") if x.strip() and x.strip() != remove_label]
        self._edit_draft.genresKo = ", ".join(parts)

    @Slot(str, str)
    def insertNewActress(self, ja: str, ko: str):
        ja, ko = (ja or "").strip(), (ko or "").strip()
        if not ja:
            self.toastMessage.emit("배우 일본어를 입력하세요.", "warning")
            return
        try:
            from javstory.harvest.database import Actress, get_db_session

            session = get_db_session()
            try:
                if session.query(Actress).filter_by(japanese=ja).first():
                    self.toastMessage.emit("같은 일본어 이름의 배우가 이미 있습니다.", "warning")
                    return
                session.add(Actress(japanese=ja, korean=ko or None, romaji=None))
                session.commit()
                add_ko = ko or ja
                self._edit_draft.append_actor_parallel(add_ko, ja, "", "")
            finally:
                session.close()
            self.toastMessage.emit("배우가 추가되었습니다.", "success")
        except Exception as e:
            self.toastMessage.emit(f"배우 추가 실패: {e}", "error")

    @Slot(str, result=list)
    def searchActresses(self, query: str):
        try:
            from sqlalchemy import or_

            from javstory.harvest.database import Actress, get_db_session

            q = (query or "").strip()
            session = get_db_session()
            try:
                qry = session.query(Actress)
                if q:
                    like = f"%{q}%"
                    qry = qry.filter(or_(Actress.japanese.like(like), Actress.korean.like(like), Actress.romaji.like(like)))
                rows = qry.order_by(Actress.japanese.asc()).limit(120).all()
                return [{"japanese": r.japanese or "", "korean": r.korean or "", "romaji": r.romaji or ""} for r in rows]
            finally:
                session.close()
        except Exception as e:
            _ = e
            return []

    @Slot(str)
    def appendActorKo(self, label_ko: str):
        """레거시: 한국어 표시만 추가(ja/로마자 등은 비움). 피커에서는 appendActorFromPick 사용."""
        lab = (label_ko or "").strip()
        if not lab:
            return
        self._edit_draft.append_actor_parallel(lab, "", "", "")

    @Slot(str, str, str)
    def appendActorFromPick(self, label_ko: str, japanese: str, romaji: str):
        """마스터 배우 목록에서 선택 시 한국어 표시 + 일본어·로마자·영문(en=로마자) 슬롯 기록."""
        ro = romaji or ""
        self._edit_draft.append_actor_parallel(
            label_ko or "",
            japanese or "",
            ro,
            ro,
        )

    @Slot(str)
    def removeActorChip(self, remove_label: str):
        self._edit_draft.remove_actor_by_ko_label(remove_label or "")

    @Slot(str, str)
    def generateSnapshots(self, product_code: str, video_path: str):
        if self._snapshot_worker and self._snapshot_worker.isRunning(): return
        from javstory.config.app_config import E_MEDIA_ROOT, DATA_ROOT

        base_root = Path(E_MEDIA_ROOT)
        try:
            base_root.mkdir(parents=True, exist_ok=True)
        except Exception:
            base_root = Path(DATA_ROOT) / "media"

        output_dir = base_root / product_code / "Snapshots"
        
        self.isExtractingSnapshots = True
        self.snapshotProgressMsg = "추출 준비 중..."

        from gui.workers.snapshot_worker import SnapshotWorker
        self._snapshot_worker = SnapshotWorker(product_code, video_path, str(output_dir))
        self._snapshot_worker.progress.connect(self._on_snapshot_progress)
        self._snapshot_worker.finished.connect(self._on_snapshot_finished)
        self._snapshot_worker.start()

    def _on_snapshot_progress(self, curr, total):
        self.snapshotProgress.emit(curr, total)
        self.snapshotProgressMsg = f"추출 중... ({curr}/{total})"

    def _on_snapshot_finished(self, success, message):
        self.isExtractingSnapshots = False
        self.snapshotFinished.emit(success, message)
        if success: self.loadDetail(self._detail.productCode)

    @Slot(str, str)
    def generateDigest(self, product_code: str, video_path: str):
        if self._digest_worker and self._digest_worker.isRunning(): return
        from javstory.config.app_config import E_MEDIA_ROOT, DATA_ROOT
        
        self.isGeneratingDigest = True
        self.digestProgress = 0
        
        # 전용 digest 폴더 아래에 digest.mp4 생성
        base_root = Path(E_MEDIA_ROOT)
        try:
            base_root.mkdir(parents=True, exist_ok=True)
        except Exception:
            base_root = Path(DATA_ROOT) / "media"

        output_dir = base_root / product_code / "Digest"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "digest.mp4"
        
        from gui.workers.digest_worker import DigestWorker
        self._digest_worker = DigestWorker(product_code, video_path, str(output_path))
        self._digest_worker.finished.connect(self._on_digest_finished)
        self._digest_worker.progressUpdated.connect(self._on_digest_progress)
        self._digest_worker.start()
        self.toastMessage.emit("🎥 다이제스트 타임랩스 추출을 시작합니다...", "info")

    @Slot(str, str)
    def generateHighlight(self, product_code: str, video_path: str):
        pc = (product_code or "").strip().upper()
        if not pc:
            self.toastMessage.emit("품번이 없습니다.", "warning")
            return

        # 전역 큐에 등록 (동시 실행 2개 제한)
        try:
            from gui.models.highlight_queue_model import HighlightQueueController
            q = HighlightQueueController.instance()
            if q:
                q.enqueue(pc, video_path)
            else:
                self.toastMessage.emit("하이라이트 큐 모델을 찾을 수 없습니다.", "error")
        except Exception as e:
            self.toastMessage.emit(f"하이라이트 큐 등록 실패: {e}", "error")

    @Slot(int)
    def _on_highlight_progress(self, percent: int):
        self.highlightProgress = percent

    def _on_highlight_finished(self, success, message):
        self.isGeneratingHighlight = False
        if success:
            self.toastMessage.emit(message, "success")
            self.loadDetail(self._detail.productCode)  # 완료되면 UI 갱신 (highlightPath 업데이트)
        else:
            self.toastMessage.emit(message, "error")

    @Slot(int)
    def _on_digest_progress(self, percent: int):
        self.digestProgress = percent

    def _on_digest_finished(self, success, message):
        self.isGeneratingDigest = False
        if success:
            self.toastMessage.emit(message, "success")
            self.loadDetail(self._detail.productCode) # 완료되면 UI 갱신 (digestPath 업데이트)
        else:
            self.toastMessage.emit(message, "error")

    def _maybe_auto_snapshots_after_folder_bind(self, product_code: str, folder_abs: str) -> None:
        """폴더 연결 직후 Snapshots 가 비어 있으면 연결 폴더의 영상에서 스냅샷 자동 추출."""
        try:
            pc = (product_code or "").strip().upper()
            if not pc:
                return
            from gui.library_data import guess_video_path_for_product
            from javstory.config.app_config import DATA_ROOT, E_MEDIA_ROOT, E_DATA_ROOT

            vp = guess_video_path_for_product(pc, folder_abs)
            if vp is None or not vp.is_file():
                return

            snap_dirs = [
                Path(E_MEDIA_ROOT) / pc / "Snapshots",
                Path(E_DATA_ROOT) / pc / "Snapshots",
                Path(E_DATA_ROOT) / "media" / pc / "Snapshots",
                Path(DATA_ROOT) / "media" / pc / "Snapshots",
            ]
            for snap_dir in snap_dirs:
                if snap_dir.is_dir():
                    n = 0
                    for pattern in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
                        n += len(list(snap_dir.glob(pattern)))
                    if n > 0:
                        return

            self.toastMessage.emit("스냅샷이 없어 영상에서 자동 추출을 시작합니다.", "info")
            self.generateSnapshots(pc, str(vp))
        except Exception as e:
            _ = e

    @Slot(str, str)
    def startSTTForDetail(self, product_code: str, folder_path: str):
        """상세 화면에서 해당 작품의 모든 영상에 대해 전사(STT) 시작."""
        vps = find_all_video_paths_for_product(product_code, folder_path)
        if not vps:
            self.toastMessage.emit("동영상 파일을 찾을 수 없습니다.", "warning")
            return

        from gui.models.processing_model import ProcessingModel
        pm = ProcessingModel.instance()
        if not pm:
            self.toastMessage.emit("전사 모델을 찾을 수 없습니다.", "error")
            return
        
        if pm.isRunning:
            self.toastMessage.emit("이미 다른 작업이 진행 중입니다.", "warning")
            return

        paths = [str(p) for p in vps]
        pm.addFiles(paths)
        pm.startQueueStt()
        self.toastMessage.emit(f"{len(paths)}건의 전사를 시작합니다.", "success")

    @Slot(str, str)
    def startSubtitleForDetail(self, product_code: str, folder_path: str):
        """상세 화면에서 해당 작품의 모든 영상에 대해 자막 생성(교정+번역) 시작."""
        vps = find_all_video_paths_for_product(product_code, folder_path)
        if not vps:
            self.toastMessage.emit("동영상 파일을 찾을 수 없습니다.", "warning")
            return

        from gui.models.processing_model import ProcessingModel
        pm = ProcessingModel.instance()
        if not pm:
            self.toastMessage.emit("전사 모델을 찾을 수 없습니다.", "error")
            return

        if pm.isRunning:
            self.toastMessage.emit("이미 다른 작업이 진행 중입니다.", "warning")
            return

        # 큐에 추가할 때, 자막 파일(.ja.srt)이 있는지 확인하여 있는 것만 진행할 수도 있고, 
        # ProcessingModel에서 알아서 체크하도록 할 수도 있음. 
        # 여기서는 일단 체크된 파일들을 큐에 넣고 startQueueSubtitle() 호출.
        paths = [str(p) for p in vps]
        pm.addFiles(paths)
        pm.startQueueSubtitle()
        self.toastMessage.emit(f"{len(paths)}건의 자막 생성을 시작합니다.", "success")

    @Slot("QVariantList")
    def enqueueMosaicRemoval(self, product_codes):
        """라이브러리(다중 선택)에서 선택한 작품들의 영상들을 MosaicQueue(LADA)에 등록."""
        pcs = []
        try:
            for pc in (product_codes or []):
                s = str(pc or "").strip().upper()
                if s:
                    pcs.append(s)
        except Exception:
            pcs = []
        if not pcs:
            self.toastMessage.emit("선택된 작품이 없습니다.", "warning")
            return

        try:
            from javstory.harvest.database import get_db_session, JAVMetadata
            from gui.library_data import guess_video_path_for_product
            from gui.models.mosaic_queue_model import MosaicQueueController

            q = MosaicQueueController.instance()
            if not q:
                self.toastMessage.emit("모자이크 제거 큐 모델을 찾을 수 없습니다.", "error")
                return

            # DB에서 folder_path를 한번에 조회
            folder_map: dict[str, str] = {}
            session = get_db_session()
            try:
                try:
                    # SQLAlchemy in_가 가능하면 사용
                    rows = session.query(JAVMetadata.product_code, JAVMetadata.folder_path).filter(
                        JAVMetadata.product_code.in_(pcs)  # type: ignore[attr-defined]
                    ).all()
                except Exception:
                    rows = []
                    for pc in pcs:
                        row = session.query(JAVMetadata.product_code, JAVMetadata.folder_path).filter_by(product_code=pc).first()
                        if row:
                            rows.append(row)
                for pc_raw, fp in (rows or []):
                    k = (pc_raw or "").strip().upper()
                    if k:
                        folder_map[k] = (fp or "").strip()
            finally:
                try:
                    session.close()
                except Exception:
                    pass

            added = 0
            missing = []
            for pc in pcs:
                folder_path = folder_map.get(pc, "") or ""
                vps = find_all_video_paths_for_product(pc, folder_path)
                if not vps:
                    try:
                        vp = guess_video_path_for_product(pc, folder_path or None)
                        if vp and vp.is_file():
                            vps = [vp]
                    except Exception:
                        vps = []

                if not vps:
                    missing.append(pc)
                    continue

                for p in vps:
                    q.enqueue(pc, str(p))
                    added += 1

            if missing:
                self.toastMessage.emit(
                    f"[모자이크 제거] 영상 없음: {len(missing)}개 (예: {', '.join(missing[:6])})",
                    "warning",
                )
            if added > 0:
                self.toastMessage.emit(
                    f"[모자이크 제거] {added}건 큐 등록 (대시보드에서 '시작'을 눌러 실행)", "success"
                )
        except Exception as e:
            self.toastMessage.emit(f"[모자이크 제거] 큐 등록 실패: {e}", "error")

    @Slot("QVariantList", bool)
    def createStoryContextCacheForProducts(self, product_codes, force: bool = False) -> None:
        """
        라이브러리(다중 선택)에서 선택한 작품들의 Grok 스토리 컨텍스트 캐시를 생성한다.
        - 모델: x-ai/grok-4.3:online (OpenRouter)
        - 저장 파일: `{품번}_grok.json` (레거시 캐시만 있으면 스킵)
        """
        pcs: list[str] = []
        try:
            for pc in (product_codes or []):
                s = str(pc or "").strip().upper()
                if s:
                    pcs.append(s)
        except Exception:
            pcs = []
        if not pcs:
            self.toastMessage.emit("선택된 작품이 없습니다.", "warning")
            return

        self.toastMessage.emit(f"[스토리 컨텍스트] {len(pcs)}개 캐시 생성 시작 (Grok 4.3 :online)", "info")

        def _job():
            ok = 0
            skipped = 0
            fail = 0
            try:
                import asyncio
                from javstory.config.app_config import library_story_context_batch_tier
                from javstory.translation.story_grok_module import run_story_grok_after_harvest_async

                tier = library_story_context_batch_tier()

                for pc in pcs:
                    try:
                        # per-item asyncio.run to avoid cross-thread event loop reuse issues
                        asyncio.run(
                            run_story_grok_after_harvest_async(
                                product_code=pc,
                                logger_func=print,
                                story_context_tier=tier,
                                force_refresh=bool(force),
                            )
                        )
                        # run_story_grok_after_harvest_async 자체가 "이미 존재"면 스킵 로그를 남기고 return하는데,
                        # 여기서는 간단히 파일 존재 여부로 결과를 추정한다.
                        try:
                            from javstory.translation.story_grok_module import (
                                load_cached_grok_json_flexible,
                                story_context_cache_path_grok,
                            )

                            p = story_context_cache_path_grok(pc)
                            if p.is_file() or load_cached_grok_json_flexible(pc, tier):
                                ok += 1
                            else:
                                skipped += 1
                        except Exception:
                            ok += 1
                    except Exception:
                        fail += 1
            finally:
                self.toastMessage.emit(
                    f"[스토리 컨텍스트] 완료: 성공 {ok} / 실패 {fail} (스킵 포함 가능)",
                    "success" if fail == 0 else "warning",
                )

        threading.Thread(target=_job, daemon=True).start()

    @Slot("QVariantList", bool)
    def createEmbeddingsForProducts(self, product_codes, force: bool = False) -> None:
        """
        라이브러리(다중 선택)에서 선택한 작품들의 임베딩 캐시를 생성한다.
        - model: JAVSTORY_EMBEDDINGS_OLLAMA_MODEL (기본 nomic-embed-text)
        - 스토리 컨텍스트 캐시/자막/씬(있으면)을 포함해 문서를 만든다.
        """
        pcs: list[str] = []
        try:
            for pc in (product_codes or []):
                s = str(pc or "").strip().upper()
                if s:
                    pcs.append(s)
        except Exception:
            pcs = []
        if not pcs:
            self.toastMessage.emit("선택된 작품이 없습니다.", "warning")
            return

        model = (os.environ.get("JAVSTORY_EMBEDDINGS_OLLAMA_MODEL", "") or "").strip() or "nomic-embed-text"
        self.toastMessage.emit(f"[임베딩] {len(pcs)}개 생성 시작 (model={model})", "info")

        def _job():
            ok = 0
            skipped = 0
            fail = 0
            try:
                import asyncio
                from javstory.library.embeddings.pipeline import build_and_store_embeddings_for_product

                for pc in pcs:
                    try:
                        path = asyncio.run(
                            build_and_store_embeddings_for_product(
                                pc,
                                model=model,
                                include_subtitles=True,
                                force=bool(force),
                                logger_func=None,
                            )
                        )
                        if path:
                            ok += 1
                        else:
                            skipped += 1
                    except Exception:
                        fail += 1
            finally:
                self.toastMessage.emit(
                    f"[임베딩] 완료: 생성 {ok} / 스킵 {skipped} / 실패 {fail} (model={model})",
                    "success" if fail == 0 else "warning",
                )

        threading.Thread(target=_job, daemon=True).start()

    @Slot(result="QVariantList")
    def availableReleaseMonths(self):
        """
        라이브러리 내 release_date에서 YYYY-MM 목록을 만들고 반환한다.
        반환 형식: [{"key":"2026-05","label":"2026-05","count":123}, ...] + {"key":"unknown","label":"미상",...}
        """
        counts: dict[str, int] = {}
        try:
            for s in (self._all_summaries or []):
                k = release_month_key(getattr(s, "release_date", "") or "")
                counts[k] = int(counts.get(k, 0) or 0) + 1
        except Exception:
            counts = {}

        months = [k for k in counts.keys() if k not in ("unknown", "")]
        months.sort(reverse=True)  # 최신월 우선

        out: list[dict] = []
        for k in months:
            out.append({"key": k, "label": k, "count": int(counts.get(k) or 0)})

        # 미상은 항상 포함(있을 때만)
        unk = int(counts.get("unknown") or 0)
        if unk > 0:
            out.append({"key": "unknown", "label": "미상", "count": unk})
        return out

    def _rebuild(self):
        merged_items = LibrarySortFilter.rebuild(
            ListRebuildOptions(
                all_summaries=self._all_summaries,
                search_query=self._search_query,
                filter_mode=self._filter_mode,
                month_filter=self._month_filter,
                unknown_only=self._unknown_only,
                sort_mode=self._sort_mode,
                favorite_delta_days=self._favorite_delta_days,
                preview_path_cache=self._preview_path_cache,
            )
        )
        self._works.refresh(merged_items)
        self.workCountChanged.emit()
