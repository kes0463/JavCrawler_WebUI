"""Headless embedding job queue for WebUI dashboard (Qt-free)."""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingJobState:
    job_id: str
    product_code: str
    model: str
    force: bool = False
    status: str = "queued"  # queued|running|done|error
    progress: int = 0
    message: str = ""
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    updated_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    started_at_ms: int = 0


class EmbeddingQueueManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_queue()
            return cls._instance

    def _init_queue(self) -> None:
        self._queue: queue.Queue[str] = queue.Queue()
        self._state_lock = threading.Lock()
        self._jobs: dict[str, EmbeddingJobState] = {}
        self._active_codes: set[str] = set()
        self._completed_total = 0
        self._failed_total = 0
        self._seq = 0
        self._last_activity_ms = int(time.time() * 1000)
        raw = (os.environ.get("JAVSTORY_EMBEDDING_QUEUE_CONCURRENCY", "") or "").strip()
        try:
            n = int(raw) if raw else 1
        except ValueError:
            n = 1
        n = max(1, min(4, n))
        self._workers: list[threading.Thread] = []
        for i in range(n):
            t = threading.Thread(
                target=self._worker_loop,
                daemon=True,
                name=f"EmbeddingWorker-{i + 1}",
            )
            t.start()
            self._workers.append(t)
        logger.info("Embedding queue started (%d worker(s)).", n)

    def _touch(self, job: EmbeddingJobState, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(job, k, v)
        job.updated_at_ms = int(time.time() * 1000)
        self._last_activity_ms = job.updated_at_ms

    def enqueue(
        self,
        product_code: str,
        *,
        model: str = "",
        force: bool = False,
    ) -> str | None:
        from javstory.library.embeddings.pipeline import (
            embeddings_enabled_from_env,
            embeddings_ollama_model_from_env,
        )
        from javstory.persona.library_search import normalize_product_code

        if not embeddings_enabled_from_env():
            return None
        pc = normalize_product_code(product_code)
        if not pc:
            return None
        m = (model or "").strip() or embeddings_ollama_model_from_env()

        with self._state_lock:
            for job in self._jobs.values():
                if (
                    job.product_code == pc
                    and job.model == m
                    and job.status in {"queued", "running"}
                ):
                    if force and not job.force:
                        job.force = True
                    return job.job_id

            if not force:
                from javstory.library.embeddings.priority_queue import _embedding_needs_build

                if not _embedding_needs_build(pc, model=m):
                    return None

            self._seq += 1
            job_id = f"emb-{pc}-{self._seq}-{int(time.time() * 1000)}"
            job = EmbeddingJobState(
                job_id=job_id,
                product_code=pc,
                model=m,
                force=bool(force),
                status="queued",
                message="대기 중",
            )
            self._jobs[job_id] = job
            self._active_codes.add(pc)
            self._queue.put(job_id)
            self._last_activity_ms = job.created_at_ms
            return job_id

    def enqueue_many(
        self,
        codes: list[str],
        *,
        model: str = "",
        force: bool = False,
    ) -> int:
        n = 0
        for raw in codes:
            if self.enqueue(raw, model=model, force=force):
                n += 1
        return n

    def remove_job(self, job_id: str) -> bool:
        with self._state_lock:
            job = self._jobs.get(job_id)
            if not job:
                return False
            if job.status == "running":
                return False
            self._jobs.pop(job_id, None)
            self._active_codes.discard(job.product_code)
            return True

    def clear_finished(self) -> int:
        removed = 0
        with self._state_lock:
            done_ids = [
                jid
                for jid, job in self._jobs.items()
                if job.status in {"done", "error"}
            ]
            for jid in done_ids:
                job = self._jobs.pop(jid, None)
                if job:
                    self._active_codes.discard(job.product_code)
                    removed += 1
        return removed

    def is_busy(self) -> bool:
        with self._state_lock:
            return any(j.status in {"queued", "running"} for j in self._jobs.values())

    def snapshot(self, *, limit: int = 40) -> dict[str, Any]:
        lim = max(1, min(100, int(limit or 40)))
        now = int(time.time() * 1000)
        with self._state_lock:
            jobs = list(self._jobs.values())
            pending = sum(1 for j in jobs if j.status == "queued")
            running = sum(1 for j in jobs if j.status == "running")
            items = sorted(
                jobs,
                key=lambda j: (
                    0 if j.status == "running" else 1 if j.status == "queued" else 2,
                    -j.updated_at_ms,
                ),
            )[:lim]
            item_rows = []
            for j in items:
                elapsed = 0
                if j.started_at_ms:
                    elapsed = max(0, (now - j.started_at_ms) // 1000)
                item_rows.append(
                    {
                        "id": j.job_id,
                        "product_code": j.product_code,
                        "model": j.model,
                        "force": j.force,
                        "status": j.status,
                        "progress": int(j.progress),
                        "message": j.message,
                        "elapsed_sec": elapsed,
                        "created_at_ms": j.created_at_ms,
                        "updated_at_ms": j.updated_at_ms,
                    }
                )
            return {
                "pending_count": pending,
                "running_count": running,
                "completed_total": self._completed_total,
                "failed_total": self._failed_total,
                "worker_count": len(self._workers),
                "seconds_since_activity": max(0, (now - self._last_activity_ms) // 1000),
                "items": item_rows,
            }

    def _worker_loop(self) -> None:
        while True:
            try:
                job_id = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                self._run_job(job_id)
            except Exception:
                logger.exception("Embedding worker error for %s", job_id)
            finally:
                self._queue.task_done()

    def _run_job(self, job_id: str) -> None:
        import asyncio

        with self._state_lock:
            job = self._jobs.get(job_id)
            if not job or job.status != "queued":
                return
            self._touch(
                job,
                status="running",
                progress=5,
                message="임베딩 생성 중",
                started_at_ms=int(time.time() * 1000),
            )
            pc = job.product_code
            model = job.model
            force = job.force

        def _log(msg: str) -> None:
            with self._state_lock:
                j = self._jobs.get(job_id)
                if j and j.status == "running":
                    self._touch(j, message=str(msg or "")[:200])

        ok = False
        err_msg = ""
        try:
            from javstory.library.embeddings.pipeline import build_and_store_embeddings_for_product
            from javstory.llm.ollama_serve import ensure_ollama_serve

            ensure_ollama_serve(wait_sec=3.0)

            async def _run() -> None:
                path = await build_and_store_embeddings_for_product(
                    pc,
                    model=model,
                    force=force,
                    logger_func=_log,
                )
                if path is None:
                    raise RuntimeError("임베딩 결과가 비어 있습니다")

            asyncio.run(_run())
            ok = True
        except Exception as e:
            err_msg = f"{type(e).__name__}: {e}"[:240]

        with self._state_lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            if ok:
                self._completed_total += 1
                self._touch(job, status="done", progress=100, message="완료")
            else:
                self._failed_total += 1
                self._touch(job, status="error", progress=100, message=err_msg or "실패")
            self._active_codes.discard(pc)


embedding_queue_manager = EmbeddingQueueManager()
