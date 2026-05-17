"""
InsightModel — QML 취향 분석 뷰용 Python 백엔드 모델

Properties:
    topActors       : JSON 문자열 [{"name", "score", "recent_score"}, ...]
    topGenres       : JSON 문자열 [{"name", "score"}, ...]
    topMakers       : JSON 문자열 [{"name", "score"}, ...]
    todayRecs       : JSON 문자열 [{"product_code", "title_ko", "cover_path", "rec_score"}, ...]
    libraryStats    : JSON 문자열 {"total", "completed", "avg_rating", ...}
    recentTrend     : JSON 문자열 {"actors": [...], "genres": [...]}
    monthlyGenres   : JSON 문자열 [{"month", "genres": [...]}, ...]
    isBatchRunning  : bool
    batchProgress   : int (0~100)

Slots:
    refresh()       : 모든 데이터 재조회
    runBatch()      : 백그라운드 배치 sync 실행
"""
from __future__ import annotations

import json
import threading
from PySide6.QtCore import QObject, QTimer, Property, Signal, Slot


class InsightModel(QObject):

    topActorsChanged    = Signal()
    topGenresChanged    = Signal()
    topMakersChanged    = Signal()
    todayRecsChanged    = Signal()
    libraryStatsChanged = Signal()
    recentTrendChanged  = Signal()
    monthlyGenresChanged = Signal()
    batchRunningChanged  = Signal()
    batchProgressChanged = Signal()
    libraryDistributionChanged = Signal()
    tasteVectorChanged = Signal()
    nextWatchRecsChanged = Signal()
    watchHeatmapChanged = Signal()
    personaCardChanged = Signal()
    personaRegeneratingChanged = Signal()
    pipelineReportChanged = Signal()
    logMessage          = Signal(str)

    # 백그라운드 → UI 스레드 데이터 전달용 내부 시그널
    # Signal은 cross-thread emit 시 자동으로 QueuedConnection을 사용하므로 thread-safe
    _refreshReady = Signal(object)
    _refreshError = Signal(str)
    _batchDone    = Signal(object)
    _personaReady = Signal(str)
    _personaError = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._top_actors     = "[]"
        self._top_genres     = "[]"
        self._top_makers     = "[]"
        self._today_recs     = "[]"
        self._library_stats  = "{}"
        self._recent_trend   = "{}"
        self._monthly_genres = "[]"
        self._library_distribution = "{}"
        self._taste_vector = "{}"
        self._next_watch_recs = "[]"
        self._watch_heatmap = "{}"
        self._persona_card = "{}"
        self._pipeline_report = "{}"
        self._batch_running  = False
        self._batch_progress = 0
        self._refresh_running = False
        self._persona_regenerating = False

        self._refreshReady.connect(self._apply_refresh)
        self._refreshError.connect(lambda msg: self.logMessage.emit(msg))
        self._batchDone.connect(self._on_batch_done)
        self._personaReady.connect(self._apply_persona)
        self._personaError.connect(lambda msg: self.logMessage.emit(msg))

        # 앱 시작 2초 후 최초 조회
        QTimer.singleShot(2000, self.refresh)

    # ── Properties ──────────────────────────────────────────────────────────

    @Property(str, notify=topActorsChanged)
    def topActors(self):
        return self._top_actors

    @Property(str, notify=topGenresChanged)
    def topGenres(self):
        return self._top_genres

    @Property(str, notify=topMakersChanged)
    def topMakers(self):
        return self._top_makers

    @Property(str, notify=todayRecsChanged)
    def todayRecs(self):
        return self._today_recs

    @Property(str, notify=libraryStatsChanged)
    def libraryStats(self):
        return self._library_stats

    @Property(str, notify=recentTrendChanged)
    def recentTrend(self):
        return self._recent_trend

    @Property(str, notify=monthlyGenresChanged)
    def monthlyGenres(self):
        return self._monthly_genres

    @Property(bool, notify=batchRunningChanged)
    def isBatchRunning(self):
        return self._batch_running

    @Property(int, notify=batchProgressChanged)
    def batchProgress(self):
        return self._batch_progress

    @Property(str, notify=libraryDistributionChanged)
    def libraryDistribution(self):
        return self._library_distribution

    @Property(str, notify=tasteVectorChanged)
    def tasteVector(self):
        return self._taste_vector

    @Property(str, notify=nextWatchRecsChanged)
    def nextWatchRecs(self):
        return self._next_watch_recs

    @Property(str, notify=watchHeatmapChanged)
    def watchHeatmap(self):
        return self._watch_heatmap

    @Property(str, notify=personaCardChanged)
    def personaCard(self):
        return self._persona_card

    @Property(str, notify=pipelineReportChanged)
    def pipelineReport(self):
        return self._pipeline_report

    @Property(bool, notify=personaRegeneratingChanged)
    def isPersonaRegenerating(self):
        return self._persona_regenerating

    # ── Slots ────────────────────────────────────────────────────────────────

    @Slot()
    def refresh(self):
        """모든 취향 분석 데이터를 백그라운드 스레드에서 재조회합니다."""
        if self._refresh_running:
            return
        self._refresh_running = True

        def _worker():
            try:
                import os
                from javstory.analytics.preference_engine import (
                    get_top_actors, get_top_genres, get_top_makers, compute_recent_trend
                )
                from javstory.analytics.preference_engine import get_recommendations
                from javstory.analytics.library_stats import (
                    get_library_stats, get_today_recommendation, get_monthly_genre_trend,
                    get_library_distribution, compute_taste_vector, get_watch_heatmap,
                )
                from javstory.analytics.persona_card import get_persona_card
                from javstory.analytics.pipeline_stats import get_pipeline_report

                # 설정의 "제외할 장르" 값을 공용으로 적용 (env 변수는 저장 시 반영됨)
                _raw = os.environ.get("JAVSTORY_SIMILARITY_EXCLUDED_GENRES", "")
                excluded_genres: set[str] = {
                    g.strip() for g in _raw.split(",") if g.strip()
                }

                results = {
                    "actors":  json.dumps(get_top_actors(5), ensure_ascii=False),
                    "genres":  json.dumps(get_top_genres(8, excluded=excluded_genres), ensure_ascii=False),
                    "makers":  json.dumps(get_top_makers(5), ensure_ascii=False),
                    "stats":   json.dumps(get_library_stats(), ensure_ascii=False),
                    "trend":   json.dumps(compute_recent_trend(excluded_genres=excluded_genres), ensure_ascii=False),
                    "recs":    json.dumps(get_today_recommendation(6), ensure_ascii=False),
                    "next_watch": json.dumps(get_recommendations(5), ensure_ascii=False),
                    "taste":   json.dumps(compute_taste_vector(), ensure_ascii=False),
                    "heatmap": json.dumps(get_watch_heatmap(), ensure_ascii=False),
                    "persona": json.dumps(get_persona_card(), ensure_ascii=False),
                    "pipeline": json.dumps(get_pipeline_report(30), ensure_ascii=False),
                    "monthly": json.dumps(get_monthly_genre_trend(3), ensure_ascii=False),
                    "dist":    json.dumps(get_library_distribution(), ensure_ascii=False),
                }
                self._refreshReady.emit(results)
            except Exception as e:
                self._refreshError.emit(f"[InsightModel] refresh 실패: {e}")
            finally:
                self._refresh_running = False

        threading.Thread(target=_worker, daemon=True, name="insight-refresh").start()

    @Slot()
    def regeneratePersona(self):
        """페르소나만 강제 재생성 (Grok/캐노니컬/자막 샘플링 + Ollama)."""
        if self._persona_regenerating:
            return
        self._persona_regenerating = True
        self.personaRegeneratingChanged.emit()

        def _worker():
            try:
                from javstory.analytics.persona_card import get_persona_card
                payload = json.dumps(get_persona_card(force_refresh=True), ensure_ascii=False)
                self._personaReady.emit(payload)
            except Exception as e:
                self._personaError.emit(f"[InsightModel] 페르소나 재생성 실패: {e}")
            finally:
                self._persona_regenerating = False
                self.personaRegeneratingChanged.emit()

        threading.Thread(target=_worker, daemon=True, name="insight-persona").start()

    def _apply_persona(self, persona_json: str) -> None:
        if persona_json != self._persona_card:
            self._persona_card = persona_json
            self.personaCardChanged.emit()

    def _apply_refresh(self, results: dict) -> None:
        """UI 스레드에서 프로퍼티에 반영합니다 (_refreshReady 시그널로 호출)."""
        if results["actors"] != self._top_actors:
            self._top_actors = results["actors"]
            self.topActorsChanged.emit()
        if results["genres"] != self._top_genres:
            self._top_genres = results["genres"]
            self.topGenresChanged.emit()
        if results["makers"] != self._top_makers:
            self._top_makers = results["makers"]
            self.topMakersChanged.emit()
        if results["stats"] != self._library_stats:
            self._library_stats = results["stats"]
            self.libraryStatsChanged.emit()
        if results["trend"] != self._recent_trend:
            self._recent_trend = results["trend"]
            self.recentTrendChanged.emit()
        if results["recs"] != self._today_recs:
            self._today_recs = results["recs"]
            self.todayRecsChanged.emit()
        if results["monthly"] != self._monthly_genres:
            self._monthly_genres = results["monthly"]
            self.monthlyGenresChanged.emit()
        if results["dist"] != self._library_distribution:
            self._library_distribution = results["dist"]
            self.libraryDistributionChanged.emit()
        if results.get("taste") != self._taste_vector:
            self._taste_vector = results.get("taste", "{}")
            self.tasteVectorChanged.emit()
        if results.get("next_watch") != self._next_watch_recs:
            self._next_watch_recs = results.get("next_watch", "[]")
            self.nextWatchRecsChanged.emit()
        if results.get("heatmap") != self._watch_heatmap:
            self._watch_heatmap = results.get("heatmap", "{}")
            self.watchHeatmapChanged.emit()
        if results.get("persona") != self._persona_card:
            self._persona_card = results.get("persona", "{}")
            self.personaCardChanged.emit()
        if results.get("pipeline") != self._pipeline_report:
            self._pipeline_report = results.get("pipeline", "{}")
            self.pipelineReportChanged.emit()

    @Slot()
    def runBatch(self):
        """백그라운드 preference 배치 동기화를 실행합니다."""
        if self._batch_running:
            return
        self._batch_running = True
        self._batch_progress = 0
        self.batchRunningChanged.emit()
        self.batchProgressChanged.emit()

        try:
            from javstory.analytics.batch_worker import run_batch_in_thread
            # _on_done은 백그라운드 스레드에서 호출되므로 _batchDone 시그널로 전달
            run_batch_in_thread(done_callback=lambda r: self._batchDone.emit(r))
        except Exception as e:
            self.logMessage.emit(f"[InsightModel] 배치 실패: {e}")
            self._batch_running = False
            self.batchRunningChanged.emit()

    def _on_batch_done(self, result: dict) -> None:
        """UI 스레드에서 배치 완료를 처리합니다 (_batchDone 시그널로 호출)."""
        synced = result.get("synced", 0)
        self.logMessage.emit(f"[InsightModel] 배치 완료 — {synced}건 동기화")
        self._batch_running = False
        self._batch_progress = 100
        self.batchRunningChanged.emit()
        self.batchProgressChanged.emit()
        QTimer.singleShot(500, self.refresh)
