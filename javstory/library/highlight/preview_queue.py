"""백그라운드 Golden Preview(10×3초 몽타주) 생성 큐 — Qt 없이 WebAPI·하베스트에서 사용."""

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
    status: str  # queued|running|done|error
    progress: int = 0
    message: str = ""
    attempts: int = 0
    started_at_ms: int = 0
    updated_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))


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
            if job:
                if "progress" in kwargs:
                    kwargs["progress"] = max(
                        int(job.progress or 0),
                        int(kwargs["progress"] or 0),
                    )
                self._touch(job, **kwargs)

    def _update_job_message(self, job_id: str, *, message: str, progress_floor: int | None = None) -> None:
        with self._state_lock:
            job = self._jobs.get(job_id)
            if not job:
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
            [j for j in items if j.status == "queued"],
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
            "items": [self._job_to_dict(j, now_ms) for j in visible[:limit]],
        }

    def _job_to_dict(self, job: PreviewJobState, now_ms: int) -> dict[str, Any]:
        activity = self._job_activity(job, now_ms)
        started = int(job.started_at_ms or 0)
        elapsed_sec = max(0, (now_ms - started) // 1000) if started and job.status == "running" else 0
        return {
            "id": job.job_id,
            "product_code": job.product_code,
            "status": job.status,
            "progress": int(job.progress or 0),
            "message": job.message or "",
            "attempts": int(job.attempts or 0),
            "activity": activity,
            "started_at_ms": started,
            "updated_at_ms": int(job.updated_at_ms or 0),
            "elapsed_sec": elapsed_sec,
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
                elapsed = int(time.time() - start)
                mins, secs = divmod(elapsed, 60)
                # ffmpeg time= 미출력 구간(시크·디코드)용 최소 진행률 (~7%/분, 상한 78%)
                floor_p = min(78, 20 + elapsed // 8)
                self._update_job_message(
                    job_id,
                    message=f"인코딩 중… {mins}분 {secs:02d}초",
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
            job = self._queue.get()
            job_id = str(job["job_id"])
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

                def on_progress(p: int) -> None:
                    self._update_job(job_id, progress=int(p), message="인코딩 중…")

                def do_encode():
                    with ffmpeg_semaphore:
                        return create_golden_preview(
                            product_code=code,
                            video_path=vp,
                            output_path=webp,
                            seed=seed,
                            progress_callback=on_progress,
                            skip_webp=True,
                        )

                res = self._run_encode_with_heartbeat(job_id, do_encode)
                if res and res.is_file():
                    mark_up_to_date(
                        meta_path=meta_path,
                        inputs={"video": vp},
                        params=montage_preview_params(seed=seed, skip_webp=True),
                    )
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
