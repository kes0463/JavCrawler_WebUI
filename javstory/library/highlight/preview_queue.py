"""백그라운드 Golden Preview(10×2초 몽타주) 생성 큐 — Qt 없이 WebAPI·하베스트에서 사용."""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from javstory.library.highlight.video_preview import (
    create_golden_preview,
    is_montage_preview_fresh,
    montage_preview_params,
)
from javstory.utils.derived_cache import mark_up_to_date
from javstory.utils.process_limit import ffmpeg_semaphore

logger = logging.getLogger(__name__)


@dataclass
class PreviewJobState:
    job_id: str
    product_code: str
    status: str  # queued|running|paused|done|error
    progress: int = 0
    message: str = ""
    attempts: int = 0
    started_at_ms: int = 0
    updated_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    segment_index: int = 0
    segment_total: int = 0
    source_position_sec: float = 0.0
    source_duration_sec: float = 0.0


def _stall_threshold_sec() -> int:
    raw = (os.environ.get("JAVSTORY_PREVIEW_STALL_SEC", "") or "").strip()
    try:
        n = int(raw) if raw else 120
    except ValueError:
        n = 120
    return max(45, min(900, n))


class PreviewQueueManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_queue()
            return cls._instance

    def _init_queue(self) -> None:
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._workers: list[threading.Thread] = []
        self._state_lock = threading.Lock()
        self._jobs: dict[str, PreviewJobState] = {}
        self._job_payloads: dict[str, dict[str, Any]] = {}
        self._paused_job_ids: set[str] = set()
        self._removed_job_ids: set[str] = set()
        self._encoding_job_ids: set[str] = set()
        self._harvest_paused = False
        self._user_paused = False
        self._completed_total = 0
        self._failed_total = 0
        self._seq = 0
        self._last_activity_ms = int(time.time() * 1000)
        raw = (os.environ.get("JAVSTORY_PREVIEW_QUEUE_WORKERS", "") or "").strip()
        try:
            n = int(raw) if raw else 1
        except ValueError:
            n = 1
        n = max(1, min(6, n))
        for i in range(n):
            t = threading.Thread(
                target=self._worker_loop,
                daemon=True,
                name=f"PreviewWorkerThread-{i + 1}",
            )
            t.start()
            self._workers.append(t)
        logger.info("Preview montage queue started (%d worker(s)).", n)
        threading.Thread(
            target=self._watchdog_loop,
            daemon=True,
            name="PreviewQueueWatchdog",
        ).start()

    def _bump_activity(self) -> None:
        self._last_activity_ms = int(time.time() * 1000)

    def _is_processing_paused(self) -> bool:
        return self._harvest_paused or self._user_paused

    def pause_for_harvest(self) -> None:
        with self._state_lock:
            self._harvest_paused = True
        logger.info("Preview queue paused (harvest running).")

    def resume_after_harvest(self) -> None:
        with self._state_lock:
            self._harvest_paused = False
        logger.info("Preview queue resumed (harvest finished).")

    def set_user_paused(self, paused: bool) -> None:
        with self._state_lock:
            self._user_paused = bool(paused)
            if self._user_paused:
                for job in self._jobs.values():
                    if job.status == "queued":
                        self._paused_job_ids.add(job.job_id)
                        self._touch(job, status="paused", message="일시정지됨")
            else:
                for jid in list(self._paused_job_ids):
                    job = self._jobs.get(jid)
                    self._paused_job_ids.discard(jid)
                    if job and job.status == "paused":
                        self._touch(job, status="queued", message="대기 중", progress=0)
        if paused:
            logger.info("Preview queue paused (user).")
        else:
            logger.info("Preview queue resumed (user).")

    def is_paused(self) -> bool:
        return self._is_processing_paused()

    def clear_finished(self) -> int:
        with self._state_lock:
            finished = [
                jid
                for jid, j in self._jobs.items()
                if j.status in {"done", "error"}
            ]
            for jid in finished:
                self._jobs.pop(jid, None)
                self._job_payloads.pop(jid, None)
                self._paused_job_ids.discard(jid)
                self._removed_job_ids.discard(jid)
            return len(finished)

    def remove_job(self, job_id: str) -> bool:
        jid = (job_id or "").strip()
        if not jid:
            return False
        with self._state_lock:
            job = self._jobs.get(jid)
            if not job:
                return False
            self._removed_job_ids.add(jid)
            self._paused_job_ids.discard(jid)
            self._job_payloads.pop(jid, None)
            if job.status in {"done", "error", "paused", "queued"}:
                self._jobs.pop(jid, None)
            elif job.status == "running":
                self._touch(job, message="취소 중…")
            return True

    def _is_job_paused(self, job_id: str) -> bool:
        return job_id in self._paused_job_ids

    def _discard_partial_preview(self, webp: Path) -> None:
        mp4 = webp.with_suffix(".mp4")
        meta = webp.with_suffix(webp.suffix + ".meta.json")
        for path in (webp, mp4, meta):
            try:
                if path.is_file():
                    path.unlink()
            except OSError:
                pass

    def pause_job(self, job_id: str) -> bool:
        jid = (job_id or "").strip()
        if not jid:
            return False
        with self._state_lock:
            job = self._jobs.get(jid)
            if not job or job.status not in {"queued", "running"}:
                return False
            self._paused_job_ids.add(jid)
            self._touch(
                job,
                status="paused",
                message="일시정지됨",
                progress=int(job.progress or 0),
            )
            return True

    def resume_job(self, job_id: str) -> bool:
        jid = (job_id or "").strip()
        if not jid:
            return False
        payload: dict[str, Any] | None = None
        requeue = False
        resume_running = False
        with self._state_lock:
            job = self._jobs.get(jid)
            if not job or job.status not in {"paused", "queued"}:
                return False
            self._paused_job_ids.discard(jid)
            self._removed_job_ids.discard(jid)
            if jid in self._encoding_job_ids:
                self._touch(job, status="running", message="재개됨")
                resume_running = True
            else:
                was_paused = job.status == "paused"
                self._touch(job, status="queued", message="대기 중", progress=0)
                payload = self._job_payloads.get(jid)
                requeue = was_paused and payload is not None
        if resume_running:
            return True
        if requeue and payload:
            self._queue.put(dict(payload))
            return True
        return True

    def resume_all_paused(self) -> int:
        with self._state_lock:
            self._user_paused = False
            paused_ids = [
                jid
                for jid, j in self._jobs.items()
                if j.status == "paused" or jid in self._paused_job_ids
            ]
        resumed = 0
        for jid in paused_ids:
            if self.resume_job(jid):
                resumed += 1
        return resumed

    def _next_job_id(self, product_code: str) -> str:
        with self._state_lock:
            self._seq += 1
            return f"{product_code}_{int(time.time() * 1000)}_{self._seq}"

    def _touch(self, job: PreviewJobState, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(job, k, v)
        job.updated_at_ms = int(time.time() * 1000)
        self._bump_activity()

    def _register_job(self, job_id: str, product_code: str, *, status: str, attempts: int = 0) -> None:
        with self._state_lock:
            self._jobs[job_id] = PreviewJobState(
                job_id=job_id,
                product_code=product_code,
                status=status,
                message="대기 중" if status == "queued" else "",
                attempts=attempts,
            )
            self._bump_activity()
            self._prune_jobs_locked()

    def _update_job(self, job_id: str, **kwargs: Any) -> None:
        with self._state_lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            if job_id in self._paused_job_ids:
                for key in (
                    "progress",
                    "segment_index",
                    "segment_total",
                    "source_position_sec",
                    "source_duration_sec",
                    "message",
                ):
                    kwargs.pop(key, None)
            if "progress" in kwargs:
                kwargs["progress"] = max(
                    int(job.progress or 0),
                    int(kwargs["progress"] or 0),
                )
            if kwargs:
                self._touch(job, **kwargs)

    def _update_job_message(self, job_id: str, *, message: str, progress_floor: int | None = None) -> None:
        with self._state_lock:
            job = self._jobs.get(job_id)
            if not job or job_id in self._paused_job_ids:
                return
            kwargs: dict[str, Any] = {"message": message}
            if progress_floor is not None:
                kwargs["progress"] = max(int(job.progress or 0), int(progress_floor))
            self._touch(job, **kwargs)

    def _prune_jobs_locked(self) -> None:
        """완료/실패 이력만 상한 유지 (대기·실행 중은 보존)."""
        if len(self._jobs) <= 800:
            return
        finished = sorted(
            (
                (jid, j)
                for jid, j in self._jobs.items()
                if j.status in {"done", "error"}
            ),
            key=lambda x: x[1].updated_at_ms,
        )
        remove = len(self._jobs) - 600
        for jid, _ in finished[:remove]:
            self._jobs.pop(jid, None)

    def _job_activity(self, job: PreviewJobState, now_ms: int) -> str:
        """active=하트비트 정상, stalled=오래 갱신 없음, waiting=큐 대기."""
        if job.status == "queued":
            return "waiting"
        if job.status == "paused":
            return "waiting"
        if job.status != "running":
            return "idle"
        age_sec = max(0, (now_ms - int(job.updated_at_ms or 0)) // 1000)
        if age_sec >= _stall_threshold_sec():
            return "stalled"
        return "active"

    def _processing_state(
        self,
        *,
        running: list[PreviewJobState],
        pending_qsize: int,
        now_ms: int,
    ) -> str:
        """active|idle|backlogged|stalled"""
        if running:
            acts = {self._job_activity(j, now_ms) for j in running}
            if acts == {"stalled"}:
                return "stalled"
            return "active"
        if pending_qsize <= 0:
            return "idle"
        idle_sec = max(0, (now_ms - self._last_activity_ms) // 1000)
        if idle_sec >= 180:
            return "backlogged"
        return "active"

    def snapshot(self, *, limit: int = 40) -> dict[str, Any]:
        now_ms = int(time.time() * 1000)
        pending_qsize = self._queue.qsize()
        with self._state_lock:
            items = list(self._jobs.values())
            completed = self._completed_total
            failed = self._failed_total
            last_activity_ms = self._last_activity_ms
        running = [j for j in items if j.status == "running"]
        queued = sorted(
            [j for j in items if j.status in {"queued", "paused"}],
            key=lambda j: j.updated_at_ms,
        )
        recent = sorted(
            [j for j in items if j.status in {"done", "error"}],
            key=lambda j: j.updated_at_ms,
            reverse=True,
        )[:12]
        show_queued = queued[: max(0, limit - len(running))]
        visible = running + show_queued + recent
        processing_state = self._processing_state(
            running=running,
            pending_qsize=pending_qsize,
            now_ms=now_ms,
        )
        sec_since = max(0, (now_ms - last_activity_ms) // 1000)
        return {
            "pending_count": pending_qsize,
            "running_count": len(running),
            "queued_count": len(queued),
            "completed_total": completed,
            "failed_total": failed,
            "worker_count": len(self._workers),
            "processing_state": processing_state,
            "last_activity_at_ms": last_activity_ms,
            "seconds_since_activity": sec_since,
            "stall_threshold_sec": _stall_threshold_sec(),
            "paused": self._is_processing_paused(),
            "harvest_paused": self._harvest_paused,
            "user_paused": self._user_paused,
            "items": [self._job_to_dict(j, now_ms) for j in visible[:limit]],
        }

    def _job_display_message(self, job: PreviewJobState) -> str:
        from javstory.library.highlight.video_preview import (
            PreviewProgressInfo,
            format_preview_progress_message,
        )

        if job.segment_total > 0 and job.segment_index > 0 and job.source_duration_sec > 0:
            return format_preview_progress_message(
                PreviewProgressInfo(
                    segment_index=int(job.segment_index),
                    segment_total=int(job.segment_total),
                    source_position_sec=float(job.source_position_sec),
                    source_duration_sec=float(job.source_duration_sec),
                ),
            )
        return job.message or ""

    def _job_to_dict(self, job: PreviewJobState, now_ms: int) -> dict[str, Any]:
        activity = self._job_activity(job, now_ms)
        started = int(job.started_at_ms or 0)
        elapsed_sec = max(0, (now_ms - started) // 1000) if started and job.status == "running" else 0
        status = job.status
        if status == "running" and job.job_id in self._paused_job_ids:
            status = "paused"
        elif status == "queued" and job.job_id in self._paused_job_ids:
            status = "paused"
        return {
            "id": job.job_id,
            "product_code": job.product_code,
            "status": status,
            "progress": int(job.progress or 0),
            "message": self._job_display_message(job),
            "attempts": int(job.attempts or 0),
            "activity": activity,
            "started_at_ms": started,
            "updated_at_ms": int(job.updated_at_ms or 0),
            "elapsed_sec": elapsed_sec,
            "segment_index": int(job.segment_index or 0),
            "segment_total": int(job.segment_total or 0),
            "source_position_sec": float(job.source_position_sec or 0.0),
            "source_duration_sec": float(job.source_duration_sec or 0.0),
        }

    def push_job(
        self,
        video_path: Path | str,
        output_webp_path: Path | str,
        product_code: str = "Unknown",
        *,
        seed: int = 0,
        attempts: int = 0,
        job_id: str | None = None,
    ) -> str:
        pc = (product_code or "").strip().upper() or "UNKNOWN"
        jid = job_id or self._next_job_id(pc)
        job = {
            "job_id": jid,
            "video_path": Path(video_path),
            "output_path": Path(output_webp_path),
            "product_code": pc,
            "seed": int(seed),
            "attempts": int(attempts),
        }
        self._register_job(jid, pc, status="queued", attempts=int(attempts))
        with self._state_lock:
            self._job_payloads[jid] = job
        self._queue.put(job)
        logger.info("Preview job queued [%s] (pending=%d).", pc, self._queue.qsize())
        return jid

    def push_if_stale(
        self,
        product_code: str,
        video_path: Path | str,
        output_webp_path: Path | str | None = None,
        *,
        seed: int = 0,
    ) -> bool:
        from javstory.config.app_config import E_MEDIA_ROOT

        pc = (product_code or "").strip().upper()
        vp = Path(video_path)
        if not pc or not vp.is_file():
            return False
        webp = (
            Path(output_webp_path)
            if output_webp_path
            else Path(E_MEDIA_ROOT) / pc / "Preview" / "preview.webp"
        )
        if is_montage_preview_fresh(webp_path=webp, video_path=vp):
            return False
        self.push_job(vp, webp, pc, seed=seed)
        return True

    def enqueue_stale_from_db(self, *, limit: int = 0) -> int:
        """DB를 스캔해 구버전/누락 프리뷰를 큐에 등록. limit=0 이면 env 한도 적용."""
        from javstory.config.app_config import E_MEDIA_ROOT
        from javstory.harvest.database import JAVMetadata, get_db_session
        from javstory.library.video_discovery import guess_video_path_for_product

        if limit <= 0:
            raw = (os.environ.get("JAVSTORY_PREVIEW_BACKFILL_LIMIT", "") or "").strip()
            try:
                limit = int(raw) if raw else 200
            except ValueError:
                limit = 200
            limit = max(0, min(5000, limit))

        session = get_db_session()
        queued = 0
        try:
            rows = session.query(JAVMetadata.product_code, JAVMetadata.folder_path).all()
        finally:
            try:
                session.close()
            except Exception:
                pass

        for idx, (pc_raw, folder_path) in enumerate(rows or []):
            if limit > 0 and queued >= limit:
                break
            pc = (pc_raw or "").strip().upper()
            if not pc:
                continue
            webp = Path(E_MEDIA_ROOT) / pc / "Preview" / "preview.webp"
            vp = guess_video_path_for_product(pc, folder_path or None)
            if not vp or not vp.is_file():
                continue
            if self.push_if_stale(pc, vp, webp):
                queued += 1
            if idx % 20 == 19:
                time.sleep(0.05)
        if queued:
            logger.info("Queued %d stale/missing preview job(s).", queued)
        return queued

    def _watchdog_loop(self) -> None:
        while True:
            time.sleep(60)
            try:
                self._watchdog_tick()
            except Exception:
                logger.exception("Preview queue watchdog error")

    def _watchdog_tick(self) -> None:
        now_ms = int(time.time() * 1000)
        orphan_ms = 45 * 60 * 1000
        with self._state_lock:
            running = [j for j in self._jobs.values() if j.status == "running"]
        for job in running:
            if now_ms - int(job.updated_at_ms or 0) > orphan_ms:
                self._update_job(
                    job.job_id,
                    status="error",
                    message="응답 없음 (45분+) — WebAPI 재시작 권장",
                )
                with self._state_lock:
                    self._failed_total += 1
                logger.error("Preview job orphaned: %s", job.product_code)

        pending = self._queue.qsize()
        if pending > 0 and not running and (now_ms - self._last_activity_ms) > 5 * 60 * 1000:
            logger.warning(
                "Preview queue may be stuck: pending=%d running=0 idle=%ds",
                pending,
                (now_ms - self._last_activity_ms) // 1000,
            )

    def _run_encode_with_heartbeat(self, job_id: str, encode_fn: Any) -> Any:
        stop = threading.Event()
        start = time.time()

        def heartbeat_loop() -> None:
            while not stop.wait(30):
                if self._is_job_paused(job_id):
                    continue
                elapsed = int(time.time() - start)
                mins, secs = divmod(elapsed, 60)
                # ffmpeg time= 미출력 구간(시크·디코드)용 최소 진행률 (~7%/분, 상한 78%)
                floor_p = min(78, 20 + elapsed // 8)
                with self._state_lock:
                    job = self._jobs.get(job_id)
                    keep_msg = bool(
                        job
                        and (
                            int(job.segment_total or 0) > 0
                            or (job.message and "구간" in job.message)
                        )
                    )
                    msg = (
                        self._job_display_message(job)
                        if keep_msg and job
                        else f"인코딩 중… {mins}분 {secs:02d}초"
                    )
                self._update_job_message(
                    job_id,
                    message=msg,
                    progress_floor=floor_p,
                )

        hb = threading.Thread(
            target=heartbeat_loop,
            daemon=True,
            name=f"PreviewHB-{job_id[:24]}",
        )
        hb.start()
        try:
            return encode_fn()
        finally:
            stop.set()

    def _worker_loop(self) -> None:
        while True:
            while self._is_processing_paused():
                time.sleep(0.5)
            try:
                job = self._queue.get(timeout=1)
            except queue.Empty:
                continue
            job_id = str(job["job_id"])
            if job_id in self._removed_job_ids:
                self._removed_job_ids.discard(job_id)
                with self._state_lock:
                    self._jobs.pop(job_id, None)
                self._queue.task_done()
                continue
            if job_id in self._paused_job_ids:
                self._update_job(job_id, status="paused", message="일시정지됨")
                self._queue.task_done()
                continue
            code = str(job["product_code"])
            attempts = int(job.get("attempts") or 0)
            try:
                vp = Path(job["video_path"])
                webp = Path(job["output_path"])
                seed = int(job.get("seed") or 0)
                if is_montage_preview_fresh(webp_path=webp, video_path=vp):
                    self._update_job(job_id, status="done", progress=100, message="이미 최신")
                    with self._state_lock:
                        self._completed_total += 1
                    continue
                webp.parent.mkdir(parents=True, exist_ok=True)
                meta_path = webp.with_suffix(webp.suffix + ".meta.json")
                now_ms = int(time.time() * 1000)
                self._update_job(
                    job_id,
                    status="running",
                    progress=0,
                    message="시작",
                    started_at_ms=now_ms,
                )
                logger.info("Preview montage encode start: %s", code)

                def on_progress(p: int, info=None) -> None:
                    if self._is_job_paused(job_id):
                        return
                    from javstory.library.highlight.video_preview import (
                        PreviewProgressInfo,
                        format_preview_progress_message,
                    )

                    seg_idx = int(getattr(info, "segment_index", 0) or 0) if info else 0
                    seg_tot = int(getattr(info, "segment_total", 0) or 0) if info else 0
                    pos = float(getattr(info, "source_position_sec", 0) or 0) if info else 0.0
                    dur = float(getattr(info, "source_duration_sec", 0) or 0) if info else 0.0
                    updates: dict[str, Any] = {"progress": int(p)}
                    if seg_tot > 0 and seg_idx > 0 and dur > 0:
                        pinfo = PreviewProgressInfo(
                            segment_index=seg_idx,
                            segment_total=seg_tot,
                            source_position_sec=pos,
                            source_duration_sec=dur,
                        )
                        updates.update(
                            segment_index=seg_idx,
                            segment_total=seg_tot,
                            source_position_sec=pos,
                            source_duration_sec=dur,
                            message=format_preview_progress_message(pinfo),
                        )
                    elif int(p) < 20:
                        updates["message"] = "준비 중…"
                    else:
                        updates["message"] = format_preview_progress_message(
                            PreviewProgressInfo(seg_idx, seg_tot, pos, dur)
                            if seg_tot > 0
                            else None,
                        )
                    self._update_job(job_id, **updates)

                def do_encode():
                    with ffmpeg_semaphore:
                        self._encoding_job_ids.add(job_id)
                        try:
                            return create_golden_preview(
                                product_code=code,
                                video_path=vp,
                                output_path=webp,
                                seed=seed,
                                progress_callback=on_progress,
                                skip_webp=True,
                            )
                        finally:
                            self._encoding_job_ids.discard(job_id)

                res = self._run_encode_with_heartbeat(job_id, do_encode)
                if job_id in self._removed_job_ids:
                    self._removed_job_ids.discard(job_id)
                    with self._state_lock:
                        self._jobs.pop(job_id, None)
                    logger.info("Preview montage encode cancelled: %s", code)
                    continue
                if self._is_job_paused(job_id):
                    self._discard_partial_preview(webp)
                    self._update_job(
                        job_id,
                        status="paused",
                        message="일시정지됨",
                    )
                    logger.info("Preview montage encode paused (discarded partial): %s", code)
                    continue
                if res and res.is_file():
                    mark_up_to_date(
                        meta_path=meta_path,
                        inputs={"video": vp},
                        params=montage_preview_params(seed=seed, skip_webp=True),
                    )
                    if webp.is_file() and webp.resolve() != res.resolve():
                        try:
                            webp.unlink()
                        except OSError:
                            pass
                    try:
                        from javstory.harvest.database import JAVMetadata, get_db_session
                        from javstory.library.file_flag_scanner import upsert_one_flag

                        session = get_db_session()
                        try:
                            row = (
                                session.query(JAVMetadata)
                                .filter(JAVMetadata.product_code == code)
                                .first()
                            )
                            upsert_one_flag(
                                code,
                                row.folder_path if row else None,
                                bool(row.is_hardcoded) if row else False,
                            )
                        finally:
                            session.close()
                    except Exception:
                        logger.exception("Preview flag refresh failed: %s", code)
                    self._update_job(job_id, status="done", progress=100, message="완료")
                    with self._state_lock:
                        self._completed_total += 1
                    logger.info("Preview montage encode done: %s", code)
                else:
                    self._update_job(job_id, status="error", message="생성 실패")
                    with self._state_lock:
                        self._failed_total += 1
                    logger.warning("Preview montage encode failed: %s", code)
            except Exception as exc:
                msg = str(exc)
                if attempts < 2 and "TimeoutExpired" in msg:
                    self._update_job(
                        job_id,
                        status="queued",
                        message=f"타임아웃 — 재시도 {attempts + 1}/2",
                    )
                    retry_job = dict(job)
                    retry_job["attempts"] = attempts + 1
                    self._queue.put(retry_job)
                    logger.warning(
                        "Preview montage timeout, requeued %s (attempt %d/2)",
                        code,
                        attempts + 1,
                    )
                else:
                    self._update_job(job_id, status="error", message=msg[:120])
                    with self._state_lock:
                        self._failed_total += 1
                    logger.exception("Preview montage encode error: %s", code)
            finally:
                self._queue.task_done()


preview_queue_manager = PreviewQueueManager()
