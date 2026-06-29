from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot

from gui.utils.watch_history_writer import WatchHistoryWriter, enqueue_watch_job
from gui.playback_guard import set_playback_active
from gui.watch_resume import last_position_ms_for_video
import javstory.harvest.database as _harvest_db

class PlayerModel(QObject):
    """
    QML 플레이어의 상태와 시청 데이터를 관리하는 백엔드 모델.
    재생 진척도, 시청 시간, 스킵 감지, 배우/장르 선호도 가중치를 실시간으로 처리합니다.
    """

    currentProductChanged = Signal()
    playbackStateChanged = Signal()
    ratingChanged = Signal(int)         # 별점 변경 알림 (QML 초기값 표시용)
    likeStateChanged = Signal(bool, bool)  # (liked, disliked) 변경 알림
    closePlayerRequested = Signal()     # Python 이벤트 필터 → QML 플레이어 닫기
    playbackProxyReady = Signal(str, str)  # original_path, proxy_path
    _watchSessionReady = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_product = ""
        self._is_playing = False
        self._current_rating = 0
        self._is_liked = False
        self._is_disliked = False
        self._player_open = False
        self._proxy_jobs: set[str] = set()
        WatchHistoryWriter.instance()
        self._watchSessionReady.connect(self._apply_watch_session_state)

    def _playback_proxy_path(self, video_path: Path) -> Path:
        try:
            stat = video_path.stat()
            key = f"{video_path.resolve()}|{stat.st_size}|{int(stat.st_mtime)}"
        except OSError:
            key = str(video_path)
        digest = hashlib.sha256(key.encode("utf-8", errors="ignore")).hexdigest()[:24]
        return Path(__file__).resolve().parents[2] / "data" / "cache" / "playback_proxy" / f"{digest}.mp4"

    @Slot(str, result=str)
    def playbackSourceFor(self, video_path: str) -> str:
        """Return a stable playback source; generate AVI/H264 repair proxy in background."""
        raw = str(video_path or "").strip()
        if not raw:
            return raw
        path = Path(raw)
        if path.suffix.lower() != ".avi" or not path.is_file():
            return raw
        proxy = self._playback_proxy_path(path)
        if proxy.is_file():
            return str(proxy)
        self._start_playback_proxy_job(path, proxy)
        return raw

    def _start_playback_proxy_job(self, source: Path, proxy: Path) -> None:
        from gui.playback_guard import is_playback_active

        if is_playback_active():
            return
        key = str(source.resolve())
        if key in self._proxy_jobs:
            return
        self._proxy_jobs.add(key)

        def _worker() -> None:
            tmp = proxy.with_name(f"{proxy.stem}.tmp{proxy.suffix}")
            try:
                from javstory.utils.ffmpeg_path import get_ffmpeg

                proxy.parent.mkdir(parents=True, exist_ok=True)
                cmd = [
                    get_ffmpeg(),
                    "-hide_banner",
                    "-y",
                    "-i",
                    str(source),
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0?",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-crf",
                    "20",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "copy",
                    "-movflags",
                    "+faststart",
                    str(tmp),
                ]
                proc = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    errors="replace",
                    check=False,
                )
                if proc.returncode == 0 and tmp.is_file() and tmp.stat().st_size > 0:
                    tmp.replace(proxy)
                    self.playbackProxyReady.emit(str(source), str(proxy))
                else:
                    try:
                        tmp.unlink(missing_ok=True)
                    except OSError:
                        pass
            except Exception:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
            finally:
                self._proxy_jobs.discard(key)

        threading.Thread(target=_worker, daemon=True, name="playback-proxy").start()

    @Slot(bool)
    def setPlayerOpen(self, is_open: bool):
        """QML playerLoader의 active 상태를 동기화한다."""
        self._player_open = bool(is_open)
        set_playback_active(self._player_open)

    @Slot()
    def closePlayer(self):
        """Python 이벤트 필터에서 ESC/Backspace 감지 시 호출 — closePlayerRequested 시그널 발생."""
        if self._player_open:
            self._player_open = False  # 중복 호출 방지
            self.closePlayerRequested.emit()

    # ── Properties ──────────────────────────────────────────

    @Property(str, notify=currentProductChanged)
    def currentProduct(self):
        return self._current_product

    @Property(int, notify=ratingChanged)
    def currentRating(self):
        return self._current_rating

    @Property(bool, notify=likeStateChanged)
    def isLiked(self):
        return self._is_liked

    @Property(bool, notify=likeStateChanged)
    def isDisliked(self):
        return self._is_disliked

    # ── 재생 세션 시작 ───────────────────────────────────────

    def _apply_watch_session_state(self, state: dict) -> None:
        if not isinstance(state, dict):
            return
        self._current_rating = int(state.get("rating") or 0)
        self._is_liked = bool(state.get("liked"))
        self._is_disliked = bool(state.get("disliked"))
        self.ratingChanged.emit(self._current_rating)
        self.likeStateChanged.emit(self._is_liked, self._is_disliked)

    @Slot(str, int)
    def startWatch(self, product_code: str, total_sec: int):
        """재생 시작 시 호출하여 세션을 초기화합니다."""
        self._current_product = product_code
        self.currentProductChanged.emit()
        enqueue_watch_job(
            "start_watch",
            product_code,
            payload={"total_sec": int(total_sec or 0)},
            done=lambda state: self._watchSessionReady.emit(state or {}),
        )

    # ── 진척도 업데이트 ─────────────────────────────────────

    @Slot(str, int, int, str)
    def updateProgress(self, product_code: str, position_ms: int, duration_sec: int, video_path: str):
        """
        재생 중 주기적으로 호출되어 현재 위치를 저장합니다.
        video_path가 비어 있으면 JSON 파트 맵은 건너뜁니다(레거시).
        90% 이상 시청 시 완료 처리 + 취향 점수 1 증가.
        """
        if not product_code:
            return
        enqueue_watch_job(
            "progress",
            product_code,
            payload={
                "position_ms": int(position_ms or 0),
                "duration_sec": int(duration_sec or 0),
                "video_path": str(video_path or ""),
            },
        )

    # ── 누적 시청 시간 업데이트 (30초마다) ─────────────────

    @Slot(str, int)
    def updateWatchDuration(self, product_code: str, elapsed_sec: int):
        """
        누적 시청 시간을 증가시킵니다. QML에서 30초마다 호출.
        """
        if not product_code or elapsed_sec <= 0:
            return
        enqueue_watch_job(
            "duration",
            product_code,
            payload={"elapsed_sec": int(elapsed_sec or 0)},
        )

    # ── 스킵 감지 ───────────────────────────────────────────

    @Slot(str, int, int)
    def recordSkip(self, product_code: str, from_ms: int, to_ms: int):
        """
        앞으로 5초 이상 건너뛸 때 스킵으로 기록합니다.
        QML의 onPositionChanged에서 이전 위치와 비교하여 호출.
        """
        if not product_code:
            return
        enqueue_watch_job(
            "skip",
            product_code,
            payload={"from_ms": int(from_ms or 0), "to_ms": int(to_ms or 0)},
        )

    # ── 명시적 피드백: 좋아요 ───────────────────────────────

    @Slot(str)
    def setLike(self, product_code: str):
        """좋아요 토글 + 취향 점수 +3."""
        if not product_code:
            return

        def _done(state):
            if not isinstance(state, dict):
                return
            self._is_liked = bool(state.get("liked"))
            self._is_disliked = bool(state.get("disliked"))
            self.likeStateChanged.emit(self._is_liked, self._is_disliked)

        enqueue_watch_job("like", product_code, done=_done)

    # ── 명시적 피드백: 싫어요 ───────────────────────────────

    @Slot(str)
    def setDislike(self, product_code: str):
        """싫어요 토글 + 취향 점수 -2."""
        if not product_code:
            return

        def _done(state):
            if not isinstance(state, dict):
                return
            self._is_liked = bool(state.get("liked"))
            self._is_disliked = bool(state.get("disliked"))
            self.likeStateChanged.emit(self._is_liked, self._is_disliked)

        enqueue_watch_job("dislike", product_code, done=_done)

    # ── 별점 ────────────────────────────────────────────────

    @Slot(str, int)
    def setRating(self, product_code: str, rating: int):
        """사용자가 부여한 별점(0~5)을 저장하고 취향 점수를 업데이트합니다."""
        if not product_code:
            return
        rating = max(0, min(5, int(rating or 0)))
        self._current_rating = rating
        self.ratingChanged.emit(rating)

        def _done(saved):
            if isinstance(saved, int) and saved != rating:
                self._current_rating = saved
                self.ratingChanged.emit(saved)

        enqueue_watch_job("rating", product_code, payload={"rating": rating}, done=_done)

    # ── 기존 호환 API ────────────────────────────────────────

    @Slot(str, str)
    def trackPreference(self, category_type: str, value: str):
        """
        배우(actor), 장르(genre), 제작사(maker) 선호도 점수를 직접 증가시킵니다.
        레거시 호환 및 QML 직접 호출용.
        """
        if not category_type or not value:
            return

        with _harvest_db.get_db_session_ctx() as session:
            pref = session.query(_harvest_db.UserPreference).filter_by(
                category_type=category_type,
                category_value=value,
                time_slot="all",
            ).first()

            if not pref:
                pref = _harvest_db.UserPreference(
                    category_type=category_type,
                    category_value=value,
                    score=1,
                    recent_score=1,
                    time_slot="all",
                    last_watched_at=datetime.datetime.now(),
                )
                session.add(pref)
            else:
                pref.score += 1
                pref.recent_score += 1
                pref.last_watched_at = datetime.datetime.now()

            session.commit()

    @Slot(str, result=int)
    def getRatingForProduct(self, product_code: str) -> int:
        """현재 저장된 별점을 반환합니다 (QML 초기값 표시용)."""
        if not product_code:
            return 0
        with _harvest_db.get_db_session_ctx() as session:
            h = session.query(_harvest_db.WatchHistory).filter_by(
                product_code=product_code
            ).first()
            return h.rating if h else 0

    # ── 마지막 재생 위치 ─────────────────────────────────────

    @Slot(str, int)
    def updateTotalDuration(self, product_code: str, total_sec: int):
        """영상 duration 확정 시 총 길이만 업데이트합니다 (session_count 변경 없음)."""
        if not product_code or total_sec <= 0:
            return
        enqueue_watch_job(
            "total_duration",
            product_code,
            payload={"total_sec": int(total_sec or 0)},
        )

    @Slot(str, str, result=int)
    def getLastPosition(self, product_code: str, video_path: str) -> int:
        """마지막 시청 위치(ms). video_path가 비면 레거시 last_position만 사용."""
        if not product_code:
            return 0
        try:
            with _harvest_db.get_db_session_ctx() as session:
                h = session.query(_harvest_db.WatchHistory).filter_by(
                    product_code=product_code
                ).first()
                if not h:
                    return 0
                return last_position_ms_for_video(
                    legacy_last_position=int(h.last_position or 0),
                    last_positions_json=getattr(h, "last_positions_json", None),
                    video_path=video_path or "",
                )
        except Exception:
            return 0

    # ── 자막 파일 탐색 ───────────────────────────────────────

    @Slot(str, result=str)
    def findSubtitleFiles(self, video_path: str) -> str:
        from javstory.library.subtitle_parser import find_subtitle_files_json

        return find_subtitle_files_json(video_path)

    @Slot(str, result=str)
    def loadSubtitleFile(self, path: str) -> str:
        from javstory.library.subtitle_parser import load_subtitle_cues_json

        return load_subtitle_cues_json(path)

