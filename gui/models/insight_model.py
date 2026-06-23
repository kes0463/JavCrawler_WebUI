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
    tasteDrift      : JSON 문자열 {series, legend, drift_note, ...}
    actorCollections: JSON 문자열 {actors, has_data, ...}
    weeklyDigest      : JSON 문자열 {lines, week_label, ...}
    isBatchRunning  : bool
    batchProgress   : int (0~100)

Slots:
    refresh()           : 단계별 전체 재조회 (UI는 phase마다 1회 갱신)
    ensureTabData(int)  : 탭 진입 시 해당 구간만 보장
    runBatch()          : 백그라운드 배치 sync 실행
"""
from __future__ import annotations

import json
import threading
from typing import Any

from PySide6.QtCore import QObject, QTimer, Property, Signal, Slot


class InsightModel(QObject):

    topActorsChanged    = Signal()
    topGenresChanged    = Signal()
    topMakersChanged    = Signal()
    todayRecsChanged    = Signal()
    libraryStatsChanged = Signal()
    recentTrendChanged  = Signal()
    monthlyGenresChanged = Signal()
    tasteDriftChanged = Signal()
    batchRunningChanged  = Signal()
    batchProgressChanged = Signal()
    libraryDistributionChanged = Signal()
    tasteVectorChanged = Signal()
    nextWatchRecsChanged = Signal()
    hiddenGemsChanged = Signal()
    favoriteActorPicksChanged = Signal()
    actorCollectionsChanged = Signal()
    watchHeatmapChanged = Signal()
    personaCardChanged = Signal()
    personaRegeneratingChanged = Signal()
    personaChatMessagesChanged = Signal()
    personaChatRunningChanged = Signal()
    personaChatTonePresetChanged = Signal()
    personaChatMemoryChanged = Signal()
    pipelineReportChanged = Signal()
    weeklyDigestChanged = Signal()
    allDataChanged = Signal()
    logMessage          = Signal(str)
    personaChatTokenReceived = Signal(str)
    personaChatResponseCompleted = Signal(str)
    personaChatErrorOccurred = Signal(str)
    personaChatCancelledOccurred = Signal()  # QML이 취소 상태를 반영할 때 사용

    _refreshReady = Signal(object)
    _refreshError = Signal(str)
    _batchDone    = Signal(object)
    _personaReady = Signal(str)
    _personaError = Signal(str)
    _personaFinished = Signal()
    _personaChatReady = Signal(object)
    _personaChatToken = Signal(str)
    _personaChatStreamCompleted = Signal(str)
    _personaChatError = Signal(str)
    _personaChatCancelled = Signal()
    _personaChatFinished = Signal()

    _PHASE_CORE = "core"
    _PHASE_TRENDS = "trends"
    _PHASE_RECOMMEND = "recommend"
    _PHASE_COLLECTION = "collection"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._top_actors     = "[]"
        self._top_genres     = "[]"
        self._top_makers     = "[]"
        self._today_recs     = "[]"
        self._library_stats  = "{}"
        self._recent_trend   = "{}"
        self._monthly_genres = "[]"
        self._taste_drift = "{}"
        self._library_distribution = "{}"
        self._taste_vector = "{}"
        self._next_watch_recs = "[]"
        self._hidden_gems = "[]"
        self._favorite_actor_picks = "[]"
        self._actor_collections = "{}"
        self._watch_heatmap = "{}"
        self._persona_card = "{}"
        self._persona_card_object: dict[str, Any] = {}
        self._persona_chat_history: list[dict[str, str]] = self._load_persona_chat_history()
        self._persona_chat_messages = json.dumps(self._persona_chat_history, ensure_ascii=False)
        self._persona_chat_worker = None
        self._persona_chat_service = None  # PersonaChatService 재사용 인스턴스
        self._persona_chat_tone_preset = "recommend"
        self._persona_chat_memory_json = "{}"
        self._persona_chat_request_id = 0
        self._persona_chat_cancel_requested = False
        self._pipeline_report = "{}"
        self._weekly_digest = "{}"
        self._batch_running  = False
        self._batch_progress = 0
        self._refresh_running = False
        self._persona_regenerating = False
        self._persona_chat_running = False
        self._phase_loaded: set[str] = set()
        self._pending_full_refresh = False
        self._pending_phases: list[str] = []

        self._refreshReady.connect(self._on_refresh_ready)
        self._refreshError.connect(lambda msg: self.logMessage.emit(msg))
        self._batchDone.connect(self._on_batch_done)
        self._personaReady.connect(self._apply_persona)
        self._personaError.connect(lambda msg: self.logMessage.emit(msg))
        self._personaFinished.connect(self._finish_persona_regeneration)
        self._personaChatReady.connect(self._apply_persona_chat_message)
        self._personaChatToken.connect(self._apply_persona_chat_token)
        self._personaChatStreamCompleted.connect(self._apply_persona_chat_stream_completed)
        self._personaChatError.connect(self._apply_persona_chat_error)
        self._personaChatCancelled.connect(self._apply_persona_chat_cancelled)
        self._personaChatFinished.connect(self._finish_persona_chat)

        QTimer.singleShot(2000, self._start_initial_load)
        QTimer.singleShot(2500, self.refreshPersonaChatMemory)

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

    @Property(str, notify=tasteDriftChanged)
    def tasteDrift(self):
        return self._taste_drift

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

    @Property(str, notify=hiddenGemsChanged)
    def hiddenGems(self):
        return self._hidden_gems

    @Property(str, notify=favoriteActorPicksChanged)
    def favoriteActorPicks(self):
        return self._favorite_actor_picks

    @Property(str, notify=actorCollectionsChanged)
    def actorCollections(self):
        return self._actor_collections

    @Property(str, notify=watchHeatmapChanged)
    def watchHeatmap(self):
        return self._watch_heatmap

    @Property(str, notify=personaCardChanged)
    def personaCard(self):
        return self._persona_card

    @Property("QVariantMap", notify=personaCardChanged)
    def personaCardObject(self):
        return self._persona_card_object

    @Property(str, notify=pipelineReportChanged)
    def pipelineReport(self):
        return self._pipeline_report

    @Property(str, notify=weeklyDigestChanged)
    def weeklyDigest(self):
        return self._weekly_digest

    @Property(bool, notify=personaRegeneratingChanged)
    def isPersonaRegenerating(self):
        return self._persona_regenerating

    @Property(str, notify=personaChatMessagesChanged)
    def personaChatMessages(self):
        return self._persona_chat_messages

    @Property(bool, notify=personaChatRunningChanged)
    def isPersonaChatRunning(self):
        return self._persona_chat_running

    @Property(str, notify=personaChatTonePresetChanged)
    def personaChatTonePreset(self):
        return self._persona_chat_tone_preset

    @personaChatTonePreset.setter
    def personaChatTonePreset(self, value: str) -> None:
        preset = str(value or "recommend").strip() or "recommend"
        if preset == self._persona_chat_tone_preset:
            return
        self._persona_chat_tone_preset = preset
        service = self._persona_chat_service
        if service is not None:
            service.tone_preset = preset
        self.personaChatTonePresetChanged.emit()

    @Property(str, notify=personaChatMemoryChanged)
    def personaChatMemoryJson(self):
        return self._persona_chat_memory_json

    def _sync_persona_chat_memory(self) -> None:
        try:
            if self._persona_chat_service is not None:
                payload = json.dumps(
                    self._persona_chat_service.enhanced_memory_store.memory_snapshot_for_ui(),
                    ensure_ascii=False,
                )
            else:
                from javstory.persona.persona_memory import EnhancedPersonaMemory
                from javstory.persona.persona_chat import ENHANCED_PERSONA_MEMORY_PATH

                store = EnhancedPersonaMemory()
                store.load_from_json(str(ENHANCED_PERSONA_MEMORY_PATH))
                payload = json.dumps(
                    store.memory_snapshot_for_ui(),
                    ensure_ascii=False,
                )
        except Exception:
            payload = "{}"
        if payload != self._persona_chat_memory_json:
            self._persona_chat_memory_json = payload
            self.personaChatMemoryChanged.emit()

    # ── 데이터 수집 (백그라운드) ───────────────────────────────────────────

    @staticmethod
    def _excluded_genres() -> set[str]:
        from javstory.config.app_config import similarity_excluded_genres_from_env

        return similarity_excluded_genres_from_env()

    @staticmethod
    def _json_object(value: str) -> dict[str, Any]:
        try:
            parsed = json.loads(value or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _persist_persona_feedback(feedback: str, persona: dict[str, Any]) -> None:
        from datetime import datetime
        from javstory.config.app_config import DATA_ROOT

        value = str(feedback or "").strip().lower()
        if value not in {"positive", "negative"}:
            raise ValueError(f"invalid persona feedback: {feedback}")

        path = DATA_ROOT / "cache" / "persona_feedback.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "feedback": value,
            "persona_type": str(persona.get("persona_type") or ""),
            "summary": str(persona.get("summary") or persona.get("body") or "")[:500],
            "input_fingerprint": str(persona.get("input_fingerprint") or ""),
            "semantic_fingerprint": str(persona.get("semantic_fingerprint") or ""),
            "generated_at": str(persona.get("generated_at") or ""),
            "source": str(persona.get("source") or ""),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    @classmethod
    def _fetch_phase(cls, phase: str) -> dict[str, str]:
        excluded = cls._excluded_genres()
        dump = lambda o: json.dumps(o, ensure_ascii=False)

        if phase == cls._PHASE_CORE:
            from javstory.analytics.preference_engine import (
                get_top_actors,
                get_top_genres,
                get_top_makers,
                compute_recent_trend,
            )
            from javstory.analytics.library_stats import get_library_stats, get_monthly_genre_trend
            from javstory.analytics.persona_card import get_persona_card
            from javstory.analytics.pipeline_stats import get_pipeline_report
            from javstory.analytics.weekly_digest import get_weekly_digest

            return {
                "actors": dump(get_top_actors(5)),
                "genres": dump(get_top_genres(8, excluded=excluded)),
                "makers": dump(get_top_makers(5)),
                "stats": dump(get_library_stats()),
                "trend": dump(compute_recent_trend(excluded_genres=excluded)),
                "persona": dump(get_persona_card(cache_only=True)),
                "pipeline": dump(get_pipeline_report(30)),
                "monthly": dump(get_monthly_genre_trend(3)),
                "weekly_digest": dump(get_weekly_digest()),
            }

        if phase == cls._PHASE_TRENDS:
            from javstory.analytics.library_stats import (
                compute_taste_vector,
                get_watch_heatmap,
                get_preference_timeline,
            )

            return {
                "taste": dump(compute_taste_vector()),
                "heatmap": dump(get_watch_heatmap()),
                "taste_drift": dump(
                    get_preference_timeline("month", 6, top_genres=5, excluded=excluded),
                ),
            }

        if phase == cls._PHASE_RECOMMEND:
            from javstory.analytics.preference_engine import get_recommendations
            from javstory.analytics.actor_content_recommender import recommend_favorite_actor_content
            from javstory.analytics.library_stats import (
                get_today_recommendation,
                get_unwatched_gems,
            )

            return {
                "recs": dump(get_today_recommendation(6)),
                "next_watch": dump(get_recommendations(5, use_embeddings=False)),
                "hidden_gems": dump(get_unwatched_gems(6)),
                "favorite_actor_picks": dump(recommend_favorite_actor_content(6)),
            }

        if phase == cls._PHASE_COLLECTION:
            from javstory.analytics.library_stats import (
                get_actor_collection_stats,
                get_library_distribution,
            )

            return {
                "dist": dump(get_library_distribution()),
                "actor_collections": dump(get_actor_collection_stats(12)),
            }

        return {}

    def _run_phases(self, phases: list[str], *, full: bool) -> None:
        if self._refresh_running:
            if full:
                self._pending_full_refresh = True
            else:
                for p in phases:
                    if p not in self._pending_phases:
                        self._pending_phases.append(p)
            return
        self._refresh_running = True
        if full:
            self._phase_loaded.clear()

        def _worker() -> None:
            try:
                for phase in phases:
                    data = self._fetch_phase(phase)
                    self._refreshReady.emit({"phase": phase, "data": data, "full": full})
            except Exception as e:
                self._refreshError.emit(f"[InsightModel] refresh 실패: {e}")
            finally:
                self._refresh_running = False
                if self._pending_phases:
                    queued = self._pending_phases
                    self._pending_phases = []
                    QTimer.singleShot(50, lambda: self._run_phases(queued, full=False))
                elif self._pending_full_refresh:
                    self._pending_full_refresh = False
                    QTimer.singleShot(100, lambda: self.refresh())

        threading.Thread(target=_worker, daemon=True, name="insight-refresh").start()

    def _start_initial_load(self) -> None:
        self._run_phases([self._PHASE_CORE], full=False)

    def _schedule_deferred_phases(self) -> None:
        pending: list[str] = []
        if self._PHASE_RECOMMEND not in self._phase_loaded:
            pending.append(self._PHASE_RECOMMEND)
        if self._PHASE_COLLECTION not in self._phase_loaded:
            pending.append(self._PHASE_COLLECTION)
        if pending:
            self._run_phases(pending, full=False)

    # ── Slots ────────────────────────────────────────────────────────────────

    @Slot()
    def refresh(self):
        """전체 데이터를 단계별로 재조회합니다 (페이즈마다 UI 1회 갱신)."""
        self._run_phases(
            [
                self._PHASE_CORE,
                self._PHASE_TRENDS,
                self._PHASE_RECOMMEND,
                self._PHASE_COLLECTION,
            ],
            full=True,
        )

    @Slot(int)
    def ensureTabData(self, tab_index: int) -> None:
        """인사이트 탭 전환 시 해당 탭 데이터만 선로드."""
        if tab_index == 1 and self._PHASE_TRENDS not in self._phase_loaded:
            self._run_phases([self._PHASE_TRENDS], full=False)
        elif tab_index == 2 and self._PHASE_RECOMMEND not in self._phase_loaded:
            self._run_phases([self._PHASE_RECOMMEND], full=False)
        elif tab_index == 3 and self._PHASE_COLLECTION not in self._phase_loaded:
            self._run_phases([self._PHASE_COLLECTION], full=False)

    def _get_or_create_chat_service(self):
        """PersonaChatService 인스턴스를 지연 생성하고 재사용한다.

        메인 스레드에서만 호출할 것. 인스턴스를 미리 확보한 뒤
        백그라운드 스레드에 레퍼런스로 넘겨야 스레드 안전하다.
        """
        if self._persona_chat_service is None:
            from javstory.persona.persona_chat import PersonaChatService

            self._persona_chat_service = PersonaChatService()
            self._persona_chat_service.tone_preset = self._persona_chat_tone_preset
        return self._persona_chat_service

    @Slot(str)
    def setPersonaChatTonePreset(self, preset: str) -> None:
        self.personaChatTonePreset = preset

    @Slot()
    def refreshPersonaChatMemory(self) -> None:
        self._sync_persona_chat_memory()

    @Slot()
    def ensurePersonaChatReady(self) -> None:
        """페르소나 챗 탭 진입 시 llama-server를 백그라운드에서 미리 띄운다."""
        def _worker() -> None:
            try:
                from javstory.llm.llamacpp_backend import ensure_llamacpp_server_ready
                from javstory.persona.persona_chat import persona_chat_model_from_env

                preset = persona_chat_model_from_env()
                ensure_llamacpp_server_ready({"model": preset, "provider": "llamacpp"})
            except Exception as exc:
                self.logMessage.emit(f"[InsightModel] 페르소나 챗 워밍업 실패: {exc}")

        threading.Thread(target=_worker, daemon=True, name="persona-chat-prewarm").start()

    @Slot(str, int)
    def removePersonaMemoryNote(self, category: str, index: int) -> None:
        try:
            service = self._get_or_create_chat_service()
            if service.enhanced_memory_store.remove_note(category, index):
                from javstory.persona.persona_chat import ENHANCED_PERSONA_MEMORY_PATH

                service.enhanced_memory_store.save_to_json(str(ENHANCED_PERSONA_MEMORY_PATH))
        except Exception:
            pass
        self._sync_persona_chat_memory()

    @Slot()
    def clearPersonaChat(self) -> None:
        self._persona_chat_history = []
        try:
            from javstory.persona.persona_chat import ENHANCED_PERSONA_MEMORY_PATH
            from javstory.persona.persona_memory import EnhancedPersonaMemory

            # 통합 메모리 초기화 (단일 파일)
            blank = EnhancedPersonaMemory()
            blank.save_to_json(str(ENHANCED_PERSONA_MEMORY_PATH))

            # 재사용 중인 서비스 인스턴스의 인메모리 스토어도 함께 초기화
            if self._persona_chat_service is not None:
                self._persona_chat_service.enhanced_memory_store.clear_all()
        except Exception:
            pass
        self._sync_persona_chat_messages()
        self._sync_persona_chat_memory()

    @Slot(str)
    @Slot(str, bool)
    def sendPersonaChatMessage(self, message: str, use_streaming: bool = False) -> None:
        text = (message or "").strip()
        if not text or self._persona_chat_running:
            return

        history = list(self._persona_chat_history)
        self._append_persona_chat_message("user", text)
        self._persona_chat_request_id += 1
        request_id = self._persona_chat_request_id
        self._persona_chat_cancel_requested = False
        self._persona_chat_running = True
        self.personaChatRunningChanged.emit()

        if use_streaming:
            try:
                from javstory.insight.insight_model import StreamingChatWorker

                # 서비스 인스턴스를 메인 스레드에서 확보해 재사용
                worker = StreamingChatWorker(text, history=history, service=self._get_or_create_chat_service())
                self._persona_chat_worker = worker
                worker.token_received.connect(
                    lambda token, rid=request_id: self._handle_persona_chat_token(rid, token)
                )
                worker.response_completed.connect(
                    lambda content, rid=request_id: self._handle_persona_chat_completed(rid, content)
                )
                worker.error_occurred.connect(
                    lambda msg, rid=request_id: self._handle_persona_chat_error(rid, msg)
                )
                worker.cancelled.connect(
                    lambda rid=request_id: self._handle_persona_chat_cancelled(rid)
                )
                worker.finished.connect(
                    lambda rid=request_id: self._handle_persona_chat_finished(rid)
                )
                worker.finished.connect(lambda w=worker: self._clear_persona_chat_worker(w))
                worker.start()
            except Exception as e:
                self._personaChatError.emit(str(e))
                self._personaChatFinished.emit()
            return

        # 서비스 인스턴스를 메인 스레드에서 미리 확보 (스레드 안전)
        # _worker 내부에서 생성하면 매 요청마다 enhanced memory 파일 I/O 와
        # EroticPersonaEngine 재초기화가 발생하므로 여기서 재사용 인스턴스를 넘긴다.
        service = self._get_or_create_chat_service()

        def _worker():
            try:
                response = service.chat(text, history=history)
                content = (
                    ((response.get("choices") or [{}])[0].get("message") or {}).get("content")
                    if isinstance(response, dict)
                    else ""
                )
                self._personaChatReady.emit({"role": "assistant", "content": content or ""})
            except Exception as e:
                self._personaChatError.emit(str(e))
            finally:
                self._personaChatFinished.emit()

        threading.Thread(target=_worker, daemon=True, name="insight-persona-chat").start()

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
                self._personaFinished.emit()

        threading.Thread(target=_worker, daemon=True, name="insight-persona").start()

    @Slot(str)
    def submitPersonaFeedback(self, feedback: str) -> None:
        """현재 페르소나 카드에 대한 사용자 피드백을 JSONL로 저장합니다."""
        try:
            self._persist_persona_feedback(feedback, self._persona_card_object)
            label = "맞아요" if str(feedback).strip().lower() == "positive" else "아니에요"
            self.logMessage.emit(f"[InsightModel] 페르소나 피드백 저장: {label}")
        except Exception as e:
            self.logMessage.emit(f"[InsightModel] 페르소나 피드백 저장 실패: {e}")

    def _apply_persona(self, persona_json: str) -> None:
        persona_obj = self._json_object(persona_json)
        if persona_json != self._persona_card or persona_obj != self._persona_card_object:
            self._persona_card = persona_json
            self._persona_card_object = persona_obj
            self.personaCardChanged.emit()
            self.allDataChanged.emit()

    def _finish_persona_regeneration(self) -> None:
        if self._persona_regenerating:
            self._persona_regenerating = False
            self.personaRegeneratingChanged.emit()

    @staticmethod
    def _load_persona_chat_history() -> list[dict[str, str]]:
        try:
            from javstory.persona.persona_chat import ENHANCED_PERSONA_MEMORY_PATH
            from javstory.persona.persona_memory import EnhancedPersonaMemory, PersonaChatMemory

            memory = EnhancedPersonaMemory()
            memory.load_from_json(str(ENHANCED_PERSONA_MEMORY_PATH))
            messages = memory.load_recent_messages()
            if messages:
                return InsightModel._format_loaded_persona_chat_history(messages)
            return InsightModel._format_loaded_persona_chat_history(PersonaChatMemory().load_recent_messages())
        except Exception:
            return []

    @staticmethod
    def _format_loaded_persona_chat_history(messages: list[dict[str, str]]) -> list[dict[str, str]]:
        try:
            from javstory.persona.persona_chat import _format_chat_response_text
        except Exception:
            _format_chat_response_text = None

        out: list[dict[str, str]] = []
        for item in messages or []:
            if not isinstance(item, dict):
                continue
            msg = dict(item)
            if msg.get("role") == "assistant" and callable(_format_chat_response_text):
                msg["content"] = _format_chat_response_text(str(msg.get("content") or ""))
            out.append(msg)
        return out

    def _sync_persona_chat_messages(self) -> None:
        self._persona_chat_messages = json.dumps(self._persona_chat_history, ensure_ascii=False)
        self.personaChatMessagesChanged.emit()

    def _append_persona_chat_message(self, role: str, content: str, *, status: str = "ok") -> None:
        text = (content or "").strip()
        if not text:
            return
        self._persona_chat_history.append({"role": role, "content": text, "status": status})
        self._persona_chat_history = self._persona_chat_history[-40:]
        self._sync_persona_chat_messages()

    def _upsert_streaming_assistant_message(self, content: str, *, status: str = "streaming") -> None:
        text = str(content or "")
        if not text:
            return
        if self._persona_chat_history and self._persona_chat_history[-1].get("role") == "assistant":
            self._persona_chat_history[-1]["content"] = text
            self._persona_chat_history[-1]["status"] = status
        else:
            self._persona_chat_history.append({"role": "assistant", "content": text, "status": status})
        self._persona_chat_history = self._persona_chat_history[-40:]
        self._sync_persona_chat_messages()

    def _apply_persona_chat_message(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        self._append_persona_chat_message(
            str(payload.get("role") or "assistant"),
            str(payload.get("content") or ""),
            status=str(payload.get("status") or "ok"),
        )

    def _apply_persona_chat_token(self, token: str) -> None:
        current = ""
        if self._persona_chat_history and self._persona_chat_history[-1].get("role") == "assistant":
            current = str(self._persona_chat_history[-1].get("content") or "")
        self._upsert_streaming_assistant_message(current + str(token or ""), status="streaming")

    def _apply_persona_chat_stream_completed(self, content: str) -> None:
        text = str(content or "")
        current = ""
        if self._persona_chat_history and self._persona_chat_history[-1].get("role") == "assistant":
            current = str(self._persona_chat_history[-1].get("content") or "")
        user_message = ""
        if self._persona_chat_history:
            for row in reversed(self._persona_chat_history):
                if row.get("role") == "user":
                    user_message = str(row.get("content") or "")
                    break
        from javstory.persona.persona_chat import _is_recommendation_request, _prefer_streamed_over_final

        if _is_recommendation_request(user_message):
            text = str(content or "")
        else:
            text = _prefer_streamed_over_final(current, text, user_message=user_message)
        if text:
            self._upsert_streaming_assistant_message(text, status="ok")
        elif self._persona_chat_history and self._persona_chat_history[-1].get("role") == "assistant":
            self._persona_chat_history[-1]["status"] = "ok"
            self._sync_persona_chat_messages()

    def _apply_persona_chat_error(self, msg: str) -> None:
        user_message = "응답 생성 중 오류가 발생했습니다."
        raw = str(msg or "")
        if "exceeds the available context size" in raw or "컨텍스트" in raw:
            user_message = (
                "요청 컨텍스트가 현재 모델 한도를 넘어 응답을 만들지 못했습니다. "
                "컨텍스트를 더 줄여 다시 시도합니다."
            )
        self._append_persona_chat_message("assistant", user_message, status="error")
        self.logMessage.emit(f"[InsightModel] 페르소나 챗 실패: {msg}")

    def _apply_persona_chat_cancelled(self) -> None:
        """스트리밍 취소 시 마지막 streaming 메시지를 cancelled 상태로 마킹한다."""
        if not self._persona_chat_history:
            return
        last = self._persona_chat_history[-1]
        if last.get("role") == "assistant" and last.get("status") == "streaming":
            last["status"] = "cancelled"
            content = str(last.get("content") or "").rstrip()
            last["content"] = (content + "\n_(취소됨)_") if content else "_(취소됨)_"
            self._sync_persona_chat_messages()
        elif last.get("role") == "user":
            self._append_persona_chat_message("assistant", "_(취소됨)_", status="cancelled")

    def _is_current_persona_chat_request(self, request_id: int) -> bool:
        return int(request_id or 0) == int(self._persona_chat_request_id or 0)

    def _handle_persona_chat_token(self, request_id: int, token: str) -> None:
        if not self._is_current_persona_chat_request(request_id) or self._persona_chat_cancel_requested:
            return
        self.personaChatTokenReceived.emit(token)
        self._personaChatToken.emit(token)

    def _handle_persona_chat_completed(self, request_id: int, content: str) -> None:
        if not self._is_current_persona_chat_request(request_id) or self._persona_chat_cancel_requested:
            return
        self.personaChatResponseCompleted.emit(content)
        self._personaChatStreamCompleted.emit(content)

    def _handle_persona_chat_error(self, request_id: int, msg: str) -> None:
        if not self._is_current_persona_chat_request(request_id) or self._persona_chat_cancel_requested:
            return
        self.personaChatErrorOccurred.emit(msg)
        self._personaChatError.emit(msg)

    def _handle_persona_chat_cancelled(self, request_id: int) -> None:
        if not self._is_current_persona_chat_request(request_id):
            return
        self.personaChatCancelledOccurred.emit()
        self._personaChatCancelled.emit()
        self._finish_persona_chat()

    def _handle_persona_chat_finished(self, request_id: int) -> None:
        if not self._is_current_persona_chat_request(request_id):
            return
        self._personaChatFinished.emit()

    def _clear_persona_chat_worker(self, worker: object) -> None:
        if self._persona_chat_worker is worker:
            self._persona_chat_worker = None

    @Slot()
    def cancelPersonaChat(self) -> None:
        """진행 중인 스트리밍 응답을 취소한다."""
        if not self._persona_chat_running and self._persona_chat_worker is None:
            return
        self._persona_chat_cancel_requested = True
        if self._persona_chat_worker is not None:
            self._persona_chat_worker.cancel()
        self._apply_persona_chat_cancelled()
        self.personaChatCancelledOccurred.emit()
        self._finish_persona_chat()

    def _finish_persona_chat(self) -> None:
        if self._persona_chat_running:
            self._persona_chat_running = False
            self.personaChatRunningChanged.emit()
        self._sync_persona_chat_memory()

    def _on_refresh_ready(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        phase = str(payload.get("phase") or "")
        results: dict[str, Any] = payload.get("data") or {}
        if phase:
            self._phase_loaded.add(phase)
        self._apply_phase(results)
        full = bool(payload.get("full"))
        if phase == self._PHASE_CORE and not full:
            QTimer.singleShot(100, lambda: self._run_phases([self._PHASE_TRENDS], full=False))
        elif phase == self._PHASE_TRENDS and not full:
            QTimer.singleShot(200, self._schedule_deferred_phases)

    def _apply_phase(self, results: dict[str, Any]) -> None:
        """UI 스레드: 한 페이즈의 변경만 반영 후 allDataChanged 1회."""
        mapping: list[tuple[str, str, Signal]] = [
            ("actors", "_top_actors", self.topActorsChanged),
            ("genres", "_top_genres", self.topGenresChanged),
            ("makers", "_top_makers", self.topMakersChanged),
            ("stats", "_library_stats", self.libraryStatsChanged),
            ("trend", "_recent_trend", self.recentTrendChanged),
            ("recs", "_today_recs", self.todayRecsChanged),
            ("monthly", "_monthly_genres", self.monthlyGenresChanged),
            ("taste_drift", "_taste_drift", self.tasteDriftChanged),
            ("dist", "_library_distribution", self.libraryDistributionChanged),
            ("taste", "_taste_vector", self.tasteVectorChanged),
            ("next_watch", "_next_watch_recs", self.nextWatchRecsChanged),
            ("hidden_gems", "_hidden_gems", self.hiddenGemsChanged),
            ("favorite_actor_picks", "_favorite_actor_picks", self.favoriteActorPicksChanged),
            ("actor_collections", "_actor_collections", self.actorCollectionsChanged),
            ("heatmap", "_watch_heatmap", self.watchHeatmapChanged),
            ("persona", "_persona_card", self.personaCardChanged),
            ("pipeline", "_pipeline_report", self.pipelineReportChanged),
            ("weekly_digest", "_weekly_digest", self.weeklyDigestChanged),
        ]
        changed = False
        persona_changed = False
        for key, attr, _sig in mapping:
            if key not in results:
                continue
            val = results[key]
            if key == "persona":
                persona_obj = self._json_object(str(val or "{}"))
                if self._persona_card != val or self._persona_card_object != persona_obj:
                    self._persona_card = val
                    self._persona_card_object = persona_obj
                    persona_changed = True
                    changed = True
                continue
            if getattr(self, attr) != val:
                setattr(self, attr, val)
                changed = True
        if changed:
            if persona_changed:
                self.personaCardChanged.emit()
            self.allDataChanged.emit()

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

            run_batch_in_thread(done_callback=lambda r: self._batchDone.emit(r))
        except Exception as e:
            self.logMessage.emit(f"[InsightModel] 배치 실패: {e}")
            self._batch_running = False
            self.batchRunningChanged.emit()

    def _on_batch_done(self, result: dict) -> None:
        if result.get("skipped"):
            self._batch_running = False
            self.batchRunningChanged.emit()
            return
        synced = result.get("synced", 0)
        self.logMessage.emit(f"[InsightModel] 배치 완료 — {synced}건 동기화")
        self._batch_running = False
        self._batch_progress = 100
        self.batchRunningChanged.emit()
        self.batchProgressChanged.emit()
        QTimer.singleShot(500, self.refresh)
