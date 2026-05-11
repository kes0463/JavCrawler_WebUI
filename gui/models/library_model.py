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


def _preview_path_for(pc: str, e_root: Path | None, legacy_root: Path | None) -> str:
    code = (pc or "").strip().upper()
    if not code:
        return ""
    cand: list[Path] = []
    if e_root:
        cand.append(Path(e_root) / code / "Preview" / "preview.webp")
    if legacy_root:
        cand.append(Path(legacy_root) / code / "Preview" / "preview.webp")
    for p in cand:
        try:
            if p.is_file() and p.stat().st_size > 0:
                return str(p.resolve())
        except Exception:
            continue
    return ""


# ---------------------------------------------------------------------------
# 검색 토큰 문법 (#장르 AND, |로 OR 그룹, -#장르 NOT, "#"붙지 않은 토큰은 substring)
# ---------------------------------------------------------------------------

def _norm_token(s: str) -> str:
    return (s or "").strip().lower()


def _tokenize_search_expr(q: str) -> list[str]:
    """공백 구분 토큰화. 큰따옴표로 공백 포함 인용 허용."""
    out: list[str] = []
    buf: list[str] = []
    in_quote = False
    for ch in q or "":
        if ch == '"':
            in_quote = not in_quote
            continue
        if ch.isspace() and not in_quote:
            if buf:
                out.append("".join(buf))
                buf = []
            continue
        buf.append(ch)
    if buf:
        out.append("".join(buf))
    return [t for t in out if t]


def parse_search_expr(q: str) -> tuple[list[list[str]], set[str], list[str]]:
    """검색 문자열을 (genre_and_groups, genre_excludes, text_terms)로 분해.

    - `#xxx` → 장르 AND 토큰. `#a|#b`처럼 `|` 결합 시 OR 그룹 1개.
    - `-#xxx` 또는 `-xxx` (장르만, '#' 권장) → 제외 집합.
    - 그 외 토큰 → 자유 substring(소문자).
    """
    and_groups: list[list[str]] = []
    excludes: set[str] = set()
    text_terms: list[str] = []
    for tok in _tokenize_search_expr(q):
        t = tok.strip()
        if not t:
            continue
        if t.startswith("-"):
            rest = t[1:]
            if rest.startswith("#"):
                rest = rest[1:]
            if rest:
                excludes.add(_norm_token(rest))
            continue
        if t.startswith("#"):
            parts = [p for p in t.split("|") if p.strip()]
            group: list[str] = []
            for p in parts:
                p = p.strip()
                if p.startswith("#"):
                    p = p[1:]
                if p:
                    group.append(_norm_token(p))
            if group:
                and_groups.append(group)
            continue
        text_terms.append(_norm_token(t))
    return and_groups, excludes, text_terms


def _summary_genre_set(s: Any) -> set[str]:
    raw = getattr(s, "genres_ko", None) or ""
    return {_norm_token(g) for g in str(raw).split(",") if g and g.strip()}


def _summary_text_blob(s: Any) -> str:
    pc = getattr(s, "product_code", "") or ""
    tk = getattr(s, "title_ko", "") or ""
    tj = getattr(s, "title_ja", "") or ""
    ak = getattr(s, "actors_ko", "") or ""
    gk = getattr(s, "genres_ko", None) or ""
    mk = getattr(s, "maker_ko", None) or ""
    return f"{pc} {tk} {tj} {ak} {gk} {mk}".lower()


def match_summary(
    s: Any,
    genre_groups: list[list[str]],
    excludes: set[str],
    text_terms: list[str],
) -> bool:
    if genre_groups or excludes:
        gset = _summary_genre_set(s)
        for group in genre_groups:
            if not any(g in gset for g in group):
                return False
        if excludes and (excludes & gset):
            return False
    if text_terms:
        blob = _summary_text_blob(s)
        for term in text_terms:
            if term and term not in blob:
                return False
    return True


_RE_MONTH = re.compile(r"^\s*(\d{4})[-/.](\d{2})")


def release_month_key(release_date: Any) -> str:
    """
    release_date(문자열)에서 YYYY-MM 월 키를 추출한다.
    - "2026-05-07", "2026/05/07", "2026.05.07" → "2026-05"
    - 실패/빈 값 → "unknown"
    """
    s = str(release_date or "").strip()
    if not s:
        return "unknown"
    m = _RE_MONTH.match(s)
    if not m:
        return "unknown"
    y = m.group(1)
    mm = m.group(2)
    try:
        mi = int(mm)
        if mi < 1 or mi > 12:
            return "unknown"
    except Exception:
        return "unknown"
    return f"{y}-{mm}"


def _build_watch_feedback_by_base() -> dict[str, dict]:
    """base 품번 → 사용자 평가(별점·하트)·최근 평가 시각."""
    out: dict[str, dict] = {}
    try:
        from javstory.harvest.database import get_db_session_ctx, WatchHistory
        from javstory.utils.product_code import strip_split_suffixes

        with get_db_session_ctx() as session:
            rows = session.query(WatchHistory).all()

        mn = datetime.datetime.min.replace(tzinfo=None)
        for wh in rows:
            raw = (wh.product_code or "").strip().upper()
            if not raw:
                continue
            try:
                base = strip_split_suffixes(raw) or raw
            except Exception:
                base = raw
            rating = int(wh.rating or 0)
            liked = bool(wh.liked)
            ua = getattr(wh, "updated_at", None) or mn

            rec = out.get(base)
            if not rec:
                out[base] = {"rating": rating, "liked": liked, "updated_at": ua}
            else:
                rec["rating"] = max(int(rec.get("rating") or 0), rating)
                rec["liked"] = bool(rec.get("liked")) or liked
                if ua > (rec.get("updated_at") or mn):
                    rec["updated_at"] = ua

        for _, rec in out.items():
            ua = rec.get("updated_at") or mn
            if ua and ua != mn:
                try:
                    rec["feedback_iso"] = ua.replace(microsecond=0).isoformat(sep=" ")
                except Exception:
                    rec["feedback_iso"] = ""
            else:
                rec["feedback_iso"] = ""
    except Exception:
        return {}
    return out


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
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, *, limit: int = 600, offset: int = 0, parent=None):
        super().__init__(parent)
        self._limit = int(limit)
        self._offset = int(offset)

    def run(self):
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
        self._filter_mode = 0  # 0:All, 1:Analyzed, 2:Pending, 3:Linked, 4:Subtitled, 5:내 평가, 6:하트만
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
            self._reload_worker.terminate()
            self._reload_worker.wait()

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
        s = next((x for x in self._all_summaries if x.product_code == product_code), None)
        if not s:
            try:
                from javstory.utils.product_code import strip_split_suffixes
                base = strip_split_suffixes((product_code or "").strip().upper()) or (product_code or "").strip().upper()
                s = next((x for x in self._all_summaries if strip_split_suffixes((x.product_code or "").strip().upper()) == base), None)
            except Exception: pass
        if not s: return


        fp_bind = getattr(s, "folder_path", None) or ""
        data = {
            "product_code": s.product_code,
            "title_ko": s.title_ko,
            "title_ja": s.title_ja,
            "actors_ko": s.actors_ko,
            "maker_ko": s.maker_ko,
            "release_date": s.release_date,
            "synopsis_ko": s.synopsis_ko,
            "genres_ko": s.genres_ko,
            "cover_path": s.cover_effective_path or s.cover_local_path or "",
            "scene_count": s.scene_count,
            "pipeline_stage": s.pipeline_stage,
            "has_canonical": s.has_canonical,
            "overall_summary": s.overall_summary_preview,
            "still_paths": [],
            "video_path": "",
            "is_hardcoded": s.is_hardcoded,
            "is_mopa": getattr(s, "is_mopa", False),
            "has_ja_srt": s.has_ja_srt,
            "has_ko_srt": s.has_ko_srt,
            "lamp_hardcoded": s.lamp_hardcoded,
            "lamp_mopa": getattr(s, "lamp_mopa", False),
            "folder_path": fp_bind,
            "digest_path": "",
            "highlight_path": "",
        }

        try:
            from javstory.library.paths import library_state_path
            p = library_state_path(s.product_code)
            if p.is_file():
                d = json.loads(p.read_text(encoding="utf-8"))
                data["grok_json"] = json.dumps(d.get("story_context", {}), ensure_ascii=False, indent=2)
                stills = []
                for sc in (d.get("scenes") or []):
                    if isinstance(sc, dict):
                        for sp in (sc.get("still_paths") or []):
                            stills.append(str(sp))
                data["still_paths"] = stills
        except Exception: pass

        try:
            from javstory.translation.story_grok_module import (
                story_context_cache_path,
                story_context_cache_dir,
                merge_story_context_tier,
            )
            tier = merge_story_context_tier(None)
            model = str(tier.get("model") or "")
            cp = story_context_cache_path(s.product_code, model)
            if not cp.is_file():
                # 모델 슬러그 변경(:online 제거 등)로 캐시 파일명이 달라질 수 있어,
                # 레거시 후보를 순차적으로 탐색한다.
                legacy_hints = [
                    "",
                    f"{model}:online" if model and ":online" not in model else "",
                    "x-ai/grok-4.1-fast:online",
                    "grok-4-fast:online",
                ]
                cp2 = None
                for hint in legacy_hints:
                    if not hint:
                        cand = story_context_cache_path(s.product_code, "")
                    else:
                        cand = story_context_cache_path(s.product_code, hint)
                    if cand.is_file():
                        cp2 = cand
                        break

                # 마지막 fallback: 동일 품번의 가장 최신 캐시(PC__*.json)를 사용
                if cp2 is None:
                    try:
                        pc_prefix = f"{(s.product_code or '').strip().upper()}__"
                        d = story_context_cache_dir()
                        matches = [p for p in d.glob(f"{pc_prefix}*.json") if p.is_file()]
                        if matches:
                            matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                            cp2 = matches[0]
                    except Exception:
                        cp2 = None

                if cp2 is not None:
                    cp = cp2
            if cp.is_file():
                gj = json.loads(cp.read_text(encoding="utf-8"))
                data["grok_verified"] = bool(gj.get("verification_ok") is True and gj.get("code_mismatch") is not True)
                data["grok_mismatch_reason"] = str(gj.get("mismatch_reason") or "")

                # 씬 데이터는 참고용으로라도 보이게 유지하되, UI에서 "미검증" 표시로 구분한다.
                scenes_raw = gj.get("scenes") or []
                grok_scenes = []
                for sc in scenes_raw:
                    if isinstance(sc, dict):
                        grok_scenes.append({
                            "time_range": sc.get("time_range", ""),
                            "scene_label": sc.get("scene_label", ""),
                            "scene_summary": sc.get("scene_summary", ""),
                        })
                data["grok_scenes_json"] = json.dumps(grok_scenes, ensure_ascii=False)
        except Exception: pass

        stills_set = set()
        if data.get("still_paths"):
            for p in data["still_paths"]: stills_set.add(str(Path(p).resolve()))

        try:
            from javstory.config.app_config import DATA_ROOT, E_MEDIA_ROOT, E_DATA_ROOT

            # 신규 HDD 루트: E:\App\JAVSTORY\data\works\{product_code}\...
            # 레거시 fallback:
            # - E:\App\JAVSTORY\data\{product_code}\... (초기 이행 버전)
            # - E:\App\JAVSTORY\data\media\{product_code}\... (이전 highlight 구현 시점)
            # - D:\App\JAVSTORY\data\media\{product_code}\... (프로젝트 내부 레거시)
            media_dir = Path(E_MEDIA_ROOT) / s.product_code
            legacy_e_flat_dir = Path(E_DATA_ROOT) / s.product_code
            legacy_e_media_dir = Path(E_DATA_ROOT) / "media" / s.product_code
            legacy_media_dir = Path(DATA_ROOT) / "media" / s.product_code

            bases = [media_dir, legacy_e_flat_dir, legacy_e_media_dir, legacy_media_dir]
            base = next((b for b in bases if b.is_dir()), None)

            if base is not None:
                snap_dir = base / "Snapshots"
                exts = ["*.jpg", "*.jpeg", "*.png", "*.webp"]
                found = []
                if snap_dir.is_dir():
                    for ext in exts: found.extend(snap_dir.glob(ext))
                else:
                    for ext in exts: found.extend(base.glob(ext))
                exclude_names = {"cover.jpg", "poster.jpg", "thumb.jpg", "cover.png", "poster.png", "cover.webp", "poster.webp"}
                for f in found:
                    if f.name.lower() not in exclude_names: stills_set.add(str(f.resolve()))
                
                # mp4 다이제스트 파일 점검 (새로운 digest 전용 폴더 우선 탐색)
                digest_file = base / "Digest" / "digest.mp4"
                if not digest_file.exists():
                    digest_file = snap_dir / "digest.mp4"
                if not digest_file.exists():
                    digest_file = base / "digest.mp4"
                if digest_file.is_file():
                    data["digest_path"] = str(digest_file.resolve())

            data["still_paths"] = sorted(list(stills_set))
        except Exception: pass

        # 하이라이트 영상 (HDD 저장소: E:\App\JAVSTORY\data\{product_code}\Highlight\)
        try:
            pc = (s.product_code or "").strip().upper()
            if pc:
                from javstory.config.app_config import E_MEDIA_ROOT, E_DATA_ROOT, DATA_ROOT
                highlight_dir = Path(E_MEDIA_ROOT) / pc / "Highlight"
                legacy_e_flat_highlight_dir = Path(E_DATA_ROOT) / pc / "Highlight"
                legacy_e_media_highlight_dir = Path(E_DATA_ROOT) / "media" / pc / "Highlight"
                legacy_highlight_dir = Path(DATA_ROOT) / "media" / pc / "Highlight"
                if not highlight_dir.is_dir():
                    if legacy_e_flat_highlight_dir.is_dir():
                        highlight_dir = legacy_e_flat_highlight_dir
                    elif legacy_e_media_highlight_dir.is_dir():
                        highlight_dir = legacy_e_media_highlight_dir
                    elif legacy_highlight_dir.is_dir():
                        highlight_dir = legacy_highlight_dir
                # 우선순위: highlight.mp4 → FINAL_HIGHLIGHT_840x640.mp4 (레거시) → 첫 mp4
                cand = [
                    highlight_dir / "highlight.mp4",
                    highlight_dir / "FINAL_HIGHLIGHT_840x640.mp4",
                ]
                hp = None
                for p in cand:
                    if p.is_file():
                        hp = p
                        break
                if hp is None and highlight_dir.is_dir():
                    mp4s = sorted(list(highlight_dir.glob("*.mp4")))
                    if mp4s:
                        hp = mp4s[0]
                if hp is not None and hp.is_file():
                    data["highlight_path"] = str(hp.resolve())
        except Exception:
            pass

        try:
            from gui.library_data import guess_video_path_for_product
            vp = guess_video_path_for_product(s.product_code, fp_bind or None)
            if vp:
                data["video_path"] = str(vp)
        except Exception: pass

        try:
            from javstory.harvest.database import (
                get_db_session_ctx,
                WatchHistory,
                favorite_score_delta_one,
            )

            with get_db_session_ctx() as sess:
                wh = sess.query(WatchHistory).filter_by(
                    product_code=s.product_code
                ).first()
                if wh:
                    data["watch_count"] = int(wh.session_count or 0)
                    data["watch_duration"] = int(wh.watch_duration or 0)
                    data["last_position"] = int(wh.last_position or 0)
                    data["user_rating"] = int(wh.rating or 0)
                    data["user_liked"] = bool(wh.liked)
                else:
                    data["user_rating"] = 0
                    data["user_liked"] = False
        except Exception:
            data["user_rating"] = 0
            data["user_liked"] = False

        fav_row = int(getattr(s, "favorite_score", 0) or 0)
        data["favorite_score"] = fav_row

        try:
            fd_days = int(getattr(self, "_favorite_delta_days", 0) or 0)
            if fd_days > 0:
                delta = favorite_score_delta_one(
                    str(s.product_code or ""),
                    fd_days,
                    fallback_score=fav_row,
                )
                if delta is not None:
                    data["favorite_site_delta"] = int(delta)
                    data["favorite_site_delta_days"] = fd_days
                    data["has_favorite_site_delta"] = True
                else:
                    data["favorite_site_delta"] = 0
                    data["favorite_site_delta_days"] = fd_days
                    data["has_favorite_site_delta"] = False
            else:
                data["favorite_site_delta"] = 0
                data["favorite_site_delta_days"] = 0
                data["has_favorite_site_delta"] = False
        except Exception:
            data["favorite_site_delta"] = 0
            data["favorite_site_delta_days"] = 0
            data["has_favorite_site_delta"] = False

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

    def _bind_folder_impl(self, product_code: str, folder_path: str, force: bool) -> bool:
        try:
            from javstory.utils.product_code import extract_product_code_from_path
            from javstory.harvest.database import get_db_session, JAVMetadata
            from gui.library_data import _first_video_in_dir, path_contains_self_subtitle_marker, path_contains_mopa_marker

            pc = (product_code or "").strip().upper()
            target_path = Path(folder_path)
            if not target_path.is_dir():
                self.toastMessage.emit(f"폴더가 없거나 디렉터리가 아닙니다: {folder_path}", "error")
                return False

            detected_pc = extract_product_code_from_path(target_path)
            if not detected_pc:
                v = _first_video_in_dir(target_path)
                if v:
                    detected_pc = extract_product_code_from_path(v)

            mismatch = not detected_pc or detected_pc.upper() != pc
            if mismatch and not force:
                self.toastMessage.emit(
                    f"선택한 폴더({target_path.name})가 품번 {pc}와 일치하지 않습니다. 강제 연결을 사용하세요.",
                    "error",
                )
                return False

            session = get_db_session()
            try:
                row = session.query(JAVMetadata).filter_by(product_code=pc).first()
                if row:
                    abs_path = str(target_path.resolve())
                    row.folder_path = abs_path
                    # 폴더 연결(영상 경로 확정) 시점에 1회 자체자막 마커 감지 후 DB 저장
                    try:
                        v = _first_video_in_dir(target_path)
                        row.is_hardcoded = bool(path_contains_self_subtitle_marker(v, abs_path, pc))
                        row.is_mopa = bool(path_contains_mopa_marker(v, abs_path))
                    except Exception:
                        pass
                    session.commit()
                    if mismatch and force:
                        self.toastMessage.emit(f"강제 연결 저장: {abs_path}", "warning")
                    else:
                        self.toastMessage.emit(f"폴더 경로가 저장되었습니다: {abs_path}", "success")
                    self.refreshProduct(pc)
                    self.summariesReloaded.emit()
                    QTimer.singleShot(
                        0,
                        lambda p=pc, fd=abs_path: self._maybe_auto_snapshots_after_folder_bind(p, fd),
                    )
                    return True
                self.toastMessage.emit(f"DB에 품번 {pc} 메타데이터가 없습니다.", "error")
                return False
            finally:
                session.close()
        except Exception as e:
            self.toastMessage.emit(f"폴더 연결 실패: {e}", "error")
            return False

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
        try:
            from javstory.harvest.database import get_db_session, JAVMetadata

            pc = (product_code or "").strip().upper()
            if not pc:
                return
            session = get_db_session()
            try:
                row = session.query(JAVMetadata).filter_by(product_code=pc).first()
                if row:
                    row.folder_path = None
                    session.commit()
                    self.toastMessage.emit("폴더 연결이 해제되었습니다.", "success")
                    self.refreshProduct(pc)
                    self.summariesReloaded.emit()
                else:
                    self.toastMessage.emit(f"DB에 품번 {pc}가 없습니다.", "warning")
            finally:
                session.close()
        except Exception as e:
            self.toastMessage.emit(f"연결 해제 실패: {e}", "error")

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
                    from javstory.translation.story_grok_module import load_cached_grok_json
                    grok = load_cached_grok_json(pc)
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
                            from javstory.config.app_config import SIMILARITY_EXCLUDED_GENRES
                            import os
                            env_ex = os.environ.get("JAVSTORY_SIMILARITY_EXCLUDED_GENRES", "")
                            if env_ex.strip():
                                excluded_set = set([x.strip() for x in env_ex.split(",") if x.strip()])
                            else:
                                excluded_set = SIMILARITY_EXCLUDED_GENRES
                            
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
        - 모델: x-ai/grok-4.1-fast:online (OpenRouter)
        - force=False면 기존 캐시가 있으면 스킵
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

        self.toastMessage.emit(f"[스토리 컨텍스트] {len(pcs)}개 캐시 생성 시작 (Grok 4.1 Fast)", "info")

        def _job():
            ok = 0
            skipped = 0
            fail = 0
            try:
                import asyncio
                from javstory.config.app_config import story_context_llm_tier
                from javstory.translation.story_grok_module import run_story_grok_after_harvest_async

                tier = story_context_llm_tier(model="x-ai/grok-4.1-fast:online")

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
                            from javstory.translation.story_grok_module import story_context_cache_path
                            p = story_context_cache_path(pc, str(tier.get("model") or ""))
                            if p.is_file():
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
        def _base_code(pc: str) -> str:
            try:
                from javstory.utils.product_code import strip_split_suffixes
                u = (pc or "").strip().upper()
                return strip_split_suffixes(u) or u
            except Exception: return (pc or "").strip().upper()

        genre_groups, genre_excludes, text_terms = parse_search_expr(self._search_query or "")
        has_query = bool(genre_groups or genre_excludes or text_terms)
        fm = self._filter_mode
        mf = (self._month_filter or "").strip()
        if self._unknown_only:
            mf = "unknown"
        filtered = []
        for s in self._all_summaries:
            # 필터 적용
            if fm == 1 and not getattr(s, "has_canonical", False): continue
            if fm == 2 and getattr(s, "has_canonical", False): continue
            if fm == 3 and not getattr(s, "folder_path", None): continue
            if fm == 4 and not (getattr(s, "has_ko_srt", False) or getattr(s, "has_ja_srt", False)): continue
            if mf:
                rk = release_month_key(getattr(s, "release_date", "") or "")
                if rk != mf:
                    continue

            if has_query and not match_summary(s, genre_groups, genre_excludes, text_terms):
                continue
            filtered.append(s)

        groups = {}
        for s in filtered:
            k = _base_code(getattr(s, "product_code", "") or "")
            groups.setdefault(k, []).append(s)

        stage_rank = {"none": 0, "harvest": 1, "transcription": 2, "translation": 3, "canonical": 4}

        def pick_rep(lst):
            def score(x):
                has_cover = 1 if (getattr(x, "cover_effective_path", None) or getattr(x, "cover_local_path", None)) else 0
                upd = getattr(x, "updated_at_iso", "") or ""
                return (has_cover, upd)
            return max(lst, key=score)

        merged_items = []
        try:
            from javstory.config.app_config import E_MEDIA_ROOT, DATA_ROOT
            e_root = Path(E_MEDIA_ROOT)
            legacy_root = Path(DATA_ROOT) / "media"
        except Exception:
            e_root = None
            legacy_root = None

        def preview_path_cached(base_pc: str) -> str:
            key = (base_pc or "").strip().upper()
            if not key:
                return ""
            hit = self._preview_path_cache.get(key)
            if hit is not None:
                return hit
            v = _preview_path_for(key, e_root, legacy_root)
            self._preview_path_cache[key] = v
            return v

        watch_map = _build_watch_feedback_by_base()

        mode = self._sort_mode
        eff_delta_days = int(self._favorite_delta_days or 0)
        if eff_delta_days <= 0 and mode in (11, 12):
            eff_delta_days = 7
        deltas_map: dict[str, int | None] = {}
        if eff_delta_days > 0:
            try:
                from javstory.harvest.database import favorite_score_deltas_for_period

                meta_by_code: dict[str, int] = {}
                for s2 in filtered:
                    pc2 = (getattr(s2, "product_code", "") or "").strip().upper()
                    if pc2:
                        meta_by_code[pc2] = int(getattr(s2, "favorite_score", 0) or 0)
                deltas_map = favorite_score_deltas_for_period(
                    meta_scores_by_code=meta_by_code,
                    period_days=eff_delta_days,
                )
            except Exception:
                deltas_map = {}

        for base_pc, lst in groups.items():
            rep = pick_rep(lst)
            max_scene = max((getattr(x, "scene_count", 0) or 0) for x in lst) if lst else 0
            max_stage = "none"
            for x in lst:
                st = getattr(x, "pipeline_stage", "none") or "none"
                if stage_rank.get(st, 0) > stage_rank.get(max_stage, 0): max_stage = st

            part_pcs: list[str] = []
            for x in lst:
                pcp = (getattr(x, "product_code", "") or "").strip().upper()
                if pcp and pcp not in part_pcs:
                    part_pcs.append(pcp)

            fd_acc: list[int] = []
            if eff_delta_days > 0 and deltas_map:
                for pcp in part_pcs:
                    dv = deltas_map.get(pcp)
                    if dv is not None:
                        fd_acc.append(int(dv))
            favorite_delta = sum(fd_acc) if fd_acc else None

            wm = watch_map.get(base_pc) or {}
            merged_items.append({
                "product_code": base_pc,
                "title_ko": getattr(rep, "title_ko", "") or "",
                "title_ja": getattr(rep, "title_ja", "") or "",
                "actors_ko": getattr(rep, "actors_ko", "") or "",
                "cover_path": getattr(rep, "cover_effective_path", None) or getattr(rep, "cover_local_path", None) or "",
                "preview_path": preview_path_cached(base_pc),
                "scene_count": max_scene,
                "pipeline_stage": max_stage,
                "release_date": getattr(rep, "release_date", "") or "",
                "has_canonical": any(bool(getattr(x, "has_canonical", False)) for x in lst),
                "part_count": len(lst),
                "is_hardcoded": any(bool(getattr(x, "is_hardcoded", False)) for x in lst),
                "has_ja_srt": any(bool(getattr(x, "has_ja_srt", False)) for x in lst),
                "has_ko_srt": any(bool(getattr(x, "has_ko_srt", False)) for x in lst),
                "lamp_hardcoded": any(bool(getattr(x, "lamp_hardcoded", False)) for x in lst),
                "lamp_mopa": any(bool(getattr(x, "lamp_mopa", False)) for x in lst),
                "updated_at_iso": max((getattr(x, "updated_at_iso", "") or "" for x in lst), default=""),
                "favorite_score": sum(int(getattr(x, "favorite_score", 0) or 0) for x in lst),
                "favorite_delta": favorite_delta,
                "user_rating": int(wm.get("rating") or 0),
                "user_liked": bool(wm.get("liked")),
                "user_feedback_iso": str(wm.get("feedback_iso") or ""),
            })

        if fm == 5:
            merged_items = [
                it
                for it in merged_items
                if int(it.get("user_rating") or 0) > 0 or bool(it.get("user_liked"))
            ]
        if fm == 6:
            merged_items = [it for it in merged_items if bool(it.get("user_liked"))]

        if mode == 0: merged_items.sort(key=lambda it: it.get("product_code", ""))
        elif mode == 1: merged_items.sort(key=lambda it: it.get("release_date", ""), reverse=True)
        elif mode == 2: merged_items.sort(key=lambda it: it.get("release_date", ""))
        elif mode == 3: merged_items.sort(key=lambda it: int(it.get("scene_count") or 0), reverse=True)
        elif mode == 4: merged_items.sort(key=lambda it: it.get("updated_at_iso", ""), reverse=True)
        elif mode == 5: merged_items.sort(key=lambda it: it.get("actors_ko", "") or "\uffff")
        elif mode == 6: merged_items.sort(key=lambda it: it.get("actors_ko", "") or "\uffff", reverse=True)
        elif mode == 7: merged_items.sort(key=lambda it: (0 if (it.get("has_ko_srt") or it.get("has_ja_srt") or it.get("lamp_hardcoded")) else 1, it.get("product_code", "")))
        elif mode == 8: merged_items.sort(key=lambda it: (0 if it.get("lamp_mopa") else 1, it.get("product_code", "")))
        elif mode == 9: merged_items.sort(key=lambda it: int(it.get("favorite_score") or 0), reverse=True)
        elif mode == 10: merged_items.sort(key=lambda it: int(it.get("favorite_score") or 0))
        elif mode == 11:
            merged_items.sort(
                key=lambda it: (0, int(it.get("favorite_delta") or 0))
                if it.get("favorite_delta") is not None
                else (-1, 0),
                reverse=True,
            )
        elif mode == 12:
            merged_items.sort(
                key=lambda it: (0, int(it.get("favorite_delta") or 0))
                if it.get("favorite_delta") is not None
                else (1, 0),
            )
        elif mode == 13:
            # 별점 높은 순, 미평가(0점)는 뒤로
            merged_items.sort(
                key=lambda it: (
                    0 if int(it.get("user_rating") or 0) > 0 else 1,
                    -int(it.get("user_rating") or 0),
                    it.get("product_code", ""),
                ),
            )

        self._works.refresh(merged_items)
        self.workCountChanged.emit()
