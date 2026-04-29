from PySide6.QtCore import QObject, Property, Signal, Slot
from javstory.harvest.database import get_db_session_ctx, WatchHistory, UserPreference
import datetime

class PlayerModel(QObject):
    """
    QML 플레이어의 상태와 시청 데이터를 관리하는 백엔드 모델.
    재생 진척도, 시청 시간, 스킵 감지, 배우/장르 선호도 가중치를 실시간으로 처리합니다.
    """

    currentProductChanged = Signal()
    playbackStateChanged = Signal()
    ratingChanged = Signal(int)         # 별점 변경 알림 (QML 초기값 표시용)
    likeStateChanged = Signal(bool, bool)  # (liked, disliked) 변경 알림

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_product = ""
        self._is_playing = False
        self._current_rating = 0
        self._is_liked = False
        self._is_disliked = False

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

    @Slot(str, int)
    def startWatch(self, product_code: str, total_sec: int):
        """재생 시작 시 호출하여 세션을 초기화합니다."""
        self._current_product = product_code
        self.currentProductChanged.emit()

        with get_db_session_ctx() as session:
            history = session.query(WatchHistory).filter_by(
                product_code=product_code
            ).first()
            if not history:
                history = WatchHistory(
                    product_code=product_code,
                    total_duration=total_sec,
                    session_count=1,
                    created_at=datetime.datetime.now(),
                )
                session.add(history)
            else:
                history.session_count = (history.session_count or 0) + 1
                if total_sec > 0:
                    history.total_duration = total_sec
                history.updated_at = datetime.datetime.now()
            session.commit()

            # 현재 별점 & 좋아요 상태 로드
            self._current_rating = history.rating or 0
            self._is_liked = bool(history.liked)
            self._is_disliked = bool(history.disliked)

        self.ratingChanged.emit(self._current_rating)
        self.likeStateChanged.emit(self._is_liked, self._is_disliked)

    # ── 진척도 업데이트 ─────────────────────────────────────

    @Slot(str, int, int)
    def updateProgress(self, product_code: str, position_ms: int, duration_sec: int):
        """
        재생 중 주기적으로 호출되어 현재 위치를 저장합니다.
        90% 이상 시청 시 완료 처리 + 취향 점수 1 증가.
        """
        if not product_code:
            return

        with get_db_session_ctx() as session:
            history = session.query(WatchHistory).filter_by(
                product_code=product_code
            ).first()
            if history:
                history.last_position = position_ms
                if duration_sec > 0:
                    progress = position_ms / (duration_sec * 1000)
                    if progress > 0.9 and not history.is_completed:
                        history.is_completed = True
                        # 완독 시 취향 점수 자동 반영
                        try:
                            from javstory.analytics.preference_engine import score_preferences
                            score_preferences(product_code, delta=2)
                        except Exception:
                            pass
                history.updated_at = datetime.datetime.now()
                session.commit()

    # ── 누적 시청 시간 업데이트 (30초마다) ─────────────────

    @Slot(str, int)
    def updateWatchDuration(self, product_code: str, elapsed_sec: int):
        """
        누적 시청 시간을 증가시킵니다. QML에서 30초마다 호출.
        """
        if not product_code or elapsed_sec <= 0:
            return

        with get_db_session_ctx() as session:
            history = session.query(WatchHistory).filter_by(
                product_code=product_code
            ).first()
            if history:
                history.watch_duration = (history.watch_duration or 0) + elapsed_sec
                history.updated_at = datetime.datetime.now()
                session.commit()

    # ── 스킵 감지 ───────────────────────────────────────────

    @Slot(str, int, int)
    def recordSkip(self, product_code: str, from_ms: int, to_ms: int):
        """
        앞으로 5초 이상 건너뛸 때 스킵으로 기록합니다.
        QML의 onPositionChanged에서 이전 위치와 비교하여 호출.
        """
        if not product_code:
            return
        jump_sec = (to_ms - from_ms) / 1000
        if jump_sec < 5:
            return

        with get_db_session_ctx() as session:
            history = session.query(WatchHistory).filter_by(
                product_code=product_code
            ).first()
            if history:
                history.skip_count = (history.skip_count or 0) + 1
                history.updated_at = datetime.datetime.now()
                session.commit()

    # ── 명시적 피드백: 좋아요 ───────────────────────────────

    @Slot(str)
    def setLike(self, product_code: str):
        """좋아요 토글 + 취향 점수 +3."""
        if not product_code:
            return

        with get_db_session_ctx() as session:
            history = session.query(WatchHistory).filter_by(
                product_code=product_code
            ).first()
            if not history:
                history = WatchHistory(
                    product_code=product_code,
                    created_at=datetime.datetime.now(),
                )
                session.add(history)

            new_liked = not bool(history.liked)
            history.liked = new_liked
            history.disliked = False  # 좋아요 누르면 싫어요 해제
            history.updated_at = datetime.datetime.now()
            session.commit()

            self._is_liked = new_liked
            self._is_disliked = False

        self.likeStateChanged.emit(self._is_liked, self._is_disliked)

        delta = 3 if self._is_liked else -3
        try:
            from javstory.analytics.preference_engine import score_preferences
            score_preferences(product_code, delta=delta)
        except Exception:
            pass

    # ── 명시적 피드백: 싫어요 ───────────────────────────────

    @Slot(str)
    def setDislike(self, product_code: str):
        """싫어요 토글 + 취향 점수 -2."""
        if not product_code:
            return

        with get_db_session_ctx() as session:
            history = session.query(WatchHistory).filter_by(
                product_code=product_code
            ).first()
            if not history:
                history = WatchHistory(
                    product_code=product_code,
                    created_at=datetime.datetime.now(),
                )
                session.add(history)

            new_disliked = not bool(history.disliked)
            history.disliked = new_disliked
            history.liked = False  # 싫어요 누르면 좋아요 해제
            history.updated_at = datetime.datetime.now()
            session.commit()

            self._is_disliked = new_disliked
            self._is_liked = False

        self.likeStateChanged.emit(self._is_liked, self._is_disliked)

        delta = -2 if self._is_disliked else 2
        try:
            from javstory.analytics.preference_engine import score_preferences
            score_preferences(product_code, delta=delta)
        except Exception:
            pass

    # ── 별점 ────────────────────────────────────────────────

    @Slot(str, int)
    def setRating(self, product_code: str, rating: int):
        """사용자가 부여한 별점(0~5)을 저장하고 취향 점수를 업데이트합니다."""
        if not product_code:
            return
        rating = max(0, min(5, rating))

        with get_db_session_ctx() as session:
            history = session.query(WatchHistory).filter_by(
                product_code=product_code
            ).first()
            if not history:
                history = WatchHistory(
                    product_code=product_code,
                    created_at=datetime.datetime.now(),
                )
                session.add(history)

            old_rating = history.rating or 0
            history.rating = rating
            history.updated_at = datetime.datetime.now()
            session.commit()

        self._current_rating = rating
        self.ratingChanged.emit(rating)

        # 별점 변화에 따른 취향 점수 delta 계산
        delta = 0
        if rating >= 4:
            delta = 3
        elif rating == 3:
            delta = 1
        elif rating <= 1 and old_rating > rating:
            delta = -1

        if delta != 0:
            try:
                from javstory.analytics.preference_engine import score_preferences
                score_preferences(product_code, delta=delta)
            except Exception:
                pass

    # ── 기존 호환 API ────────────────────────────────────────

    @Slot(str, str)
    def trackPreference(self, category_type: str, value: str):
        """
        배우(actor), 장르(genre), 제작사(maker) 선호도 점수를 직접 증가시킵니다.
        레거시 호환 및 QML 직접 호출용.
        """
        if not category_type or not value:
            return

        with get_db_session_ctx() as session:
            pref = session.query(UserPreference).filter_by(
                category_type=category_type,
                category_value=value,
                time_slot="all",
            ).first()

            if not pref:
                pref = UserPreference(
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
        with get_db_session_ctx() as session:
            h = session.query(WatchHistory).filter_by(
                product_code=product_code
            ).first()
            return h.rating if h else 0
