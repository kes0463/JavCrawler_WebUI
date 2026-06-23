"""WatchHistory DB 쓰기를 UI 스레드 밖에서 배치 처리."""

from __future__ import annotations

import datetime
import queue
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

import javstory.harvest.database as _harvest_db
from gui.watch_resume import merge_last_positions_json, normalize_watch_video_key


@dataclass
class _Job:
    kind: str
    product_code: str
    payload: dict[str, Any] = field(default_factory=dict)
    done: Callable[[Any], None] | None = None


class WatchHistoryWriter:
    """싱글톤 백그라운드 큐 — PlayerModel Slot에서 동기 commit 하지 않도록 한다."""

    _instance: "WatchHistoryWriter | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._queue: queue.Queue[_Job | None] = queue.Queue()
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="watch-history-writer",
        )
        self._thread.start()

    @classmethod
    def instance(cls) -> "WatchHistoryWriter":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def submit(self, job: _Job) -> None:
        self._queue.put(job)

    def _loop(self) -> None:
        while True:
            job = self._queue.get()
            if job is None:
                break
            try:
                result = self._dispatch(job)
                if job.done:
                    job.done(result)
            except Exception:
                if job.done:
                    job.done(None)
            finally:
                self._queue.task_done()

    def _dispatch(self, job: _Job) -> Any:
        pc = (job.product_code or "").strip()
        if not pc:
            return None
        kind = job.kind
        payload = job.payload or {}

        if kind == "start_watch":
            return self._start_watch(pc, int(payload.get("total_sec") or 0))
        if kind == "progress":
            self._update_progress(
                pc,
                int(payload.get("position_ms") or 0),
                int(payload.get("duration_sec") or 0),
                str(payload.get("video_path") or ""),
            )
            return None
        if kind == "duration":
            self._update_duration(pc, int(payload.get("elapsed_sec") or 0))
            return None
        if kind == "skip":
            self._record_skip(pc, int(payload.get("from_ms") or 0), int(payload.get("to_ms") or 0))
            return None
        if kind == "like":
            return self._toggle_like(pc)
        if kind == "dislike":
            return self._toggle_dislike(pc)
        if kind == "rating":
            return self._set_rating(pc, int(payload.get("rating") or 0))
        if kind == "total_duration":
            self._update_total_duration(pc, int(payload.get("total_sec") or 0))
            return None
        return None

    @staticmethod
    def _start_watch(product_code: str, total_sec: int) -> dict[str, Any]:
        with _harvest_db.get_db_session_ctx() as session:
            history = session.query(_harvest_db.WatchHistory).filter_by(
                product_code=product_code
            ).first()
            if not history:
                history = _harvest_db.WatchHistory(
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
            return {
                "rating": int(history.rating or 0),
                "liked": bool(history.liked),
                "disliked": bool(history.disliked),
            }

    @staticmethod
    def _update_progress(
        product_code: str,
        position_ms: int,
        duration_sec: int,
        video_path: str,
    ) -> None:
        vkey = normalize_watch_video_key(video_path or "")
        with _harvest_db.get_db_session_ctx() as session:
            history = session.query(_harvest_db.WatchHistory).filter_by(
                product_code=product_code
            ).first()
            if not history:
                return
            history.last_position = position_ms
            if vkey:
                history.last_positions_json = merge_last_positions_json(
                    getattr(history, "last_positions_json", None),
                    vkey,
                    position_ms,
                )
            if duration_sec > 0:
                progress = position_ms / (duration_sec * 1000)
                if progress > 0.9 and not history.is_completed:
                    history.is_completed = True
                    try:
                        from javstory.analytics.preference_engine import score_preferences

                        score_preferences(product_code, delta=2)
                    except Exception:
                        pass
            history.updated_at = datetime.datetime.now()
            session.commit()

    @staticmethod
    def _update_duration(product_code: str, elapsed_sec: int) -> None:
        if elapsed_sec <= 0:
            return
        with _harvest_db.get_db_session_ctx() as session:
            history = session.query(_harvest_db.WatchHistory).filter_by(
                product_code=product_code
            ).first()
            if history:
                history.watch_duration = (history.watch_duration or 0) + elapsed_sec
                history.updated_at = datetime.datetime.now()
                session.commit()

    @staticmethod
    def _record_skip(product_code: str, from_ms: int, to_ms: int) -> None:
        jump_sec = (to_ms - from_ms) / 1000
        if jump_sec < 5:
            return
        with _harvest_db.get_db_session_ctx() as session:
            history = session.query(_harvest_db.WatchHistory).filter_by(
                product_code=product_code
            ).first()
            if history:
                history.skip_count = (history.skip_count or 0) + 1
                history.updated_at = datetime.datetime.now()
                session.commit()

    @staticmethod
    def _toggle_like(product_code: str) -> dict[str, bool]:
        with _harvest_db.get_db_session_ctx() as session:
            history = session.query(_harvest_db.WatchHistory).filter_by(
                product_code=product_code
            ).first()
            if not history:
                history = _harvest_db.WatchHistory(
                    product_code=product_code,
                    created_at=datetime.datetime.now(),
                )
                session.add(history)
            new_liked = not bool(history.liked)
            history.liked = new_liked
            history.disliked = False
            history.updated_at = datetime.datetime.now()
            session.commit()
        delta = 3 if new_liked else -3
        try:
            from javstory.analytics.preference_engine import score_preferences

            score_preferences(product_code, delta=delta)
        except Exception:
            pass
        return {"liked": new_liked, "disliked": False}

    @staticmethod
    def _toggle_dislike(product_code: str) -> dict[str, bool]:
        with _harvest_db.get_db_session_ctx() as session:
            history = session.query(_harvest_db.WatchHistory).filter_by(
                product_code=product_code
            ).first()
            if not history:
                history = _harvest_db.WatchHistory(
                    product_code=product_code,
                    created_at=datetime.datetime.now(),
                )
                session.add(history)
            new_disliked = not bool(history.disliked)
            history.disliked = new_disliked
            history.liked = False
            history.updated_at = datetime.datetime.now()
            session.commit()
        delta = -2 if new_disliked else 2
        try:
            from javstory.analytics.preference_engine import score_preferences

            score_preferences(product_code, delta=delta)
        except Exception:
            pass
        return {"liked": False, "disliked": new_disliked}

    @staticmethod
    def _set_rating(product_code: str, rating: int) -> int:
        rating = max(0, min(5, int(rating or 0)))
        with _harvest_db.get_db_session_ctx() as session:
            history = session.query(_harvest_db.WatchHistory).filter_by(
                product_code=product_code
            ).first()
            if not history:
                history = _harvest_db.WatchHistory(
                    product_code=product_code,
                    created_at=datetime.datetime.now(),
                )
                session.add(history)
            old_rating = int(history.rating or 0)
            history.rating = rating
            history.updated_at = datetime.datetime.now()
            session.commit()
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
        return rating

    @staticmethod
    def _update_total_duration(product_code: str, total_sec: int) -> None:
        if total_sec <= 0:
            return
        with _harvest_db.get_db_session_ctx() as session:
            history = session.query(_harvest_db.WatchHistory).filter_by(
                product_code=product_code
            ).first()
            if history:
                history.total_duration = total_sec
                history.updated_at = datetime.datetime.now()
                session.commit()


def enqueue_watch_job(
    kind: str,
    product_code: str,
    *,
    payload: dict[str, Any] | None = None,
    done: Callable[[Any], None] | None = None,
) -> None:
    WatchHistoryWriter.instance().submit(
        _Job(kind=kind, product_code=product_code, payload=payload or {}, done=done)
    )
