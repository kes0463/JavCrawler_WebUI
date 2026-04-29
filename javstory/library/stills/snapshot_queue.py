"""백그라운드 스냅샷 추출 전담 큐 매니저."""

from __future__ import annotations

import logging
import os
import threading
import queue
from pathlib import Path

from javstory.library.stills.extract import extract_snapshots_auto_adaptive
from javstory.utils.derived_cache import is_up_to_date, mark_up_to_date
from javstory.utils.perf_log import perf_span
from javstory.utils.process_limit import ffmpeg_semaphore

logger = logging.getLogger(__name__)

class SnapshotQueueManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SnapshotQueueManager, cls).__new__(cls)
                cls._instance._init_queue()
            return cls._instance

    def _init_queue(self):
        self._queue = queue.Queue()
        self._workers = []
        raw = (os.environ.get("JAVSTORY_SNAPSHOT_QUEUE_WORKERS", "") or "").strip()
        try:
            n = int(raw) if raw else 4
        except ValueError:
            n = 4
        n = max(1, min(8, n))

        # RTX 3080Ti 환경 기준 기본 4병렬 (환경변수로 조절)
        for i in range(n):
            t = threading.Thread(target=self._worker_loop, daemon=True, name=f"SnapshotWorkerThread-{i+1}")
            t.start()
            self._workers.append(t)
        logger.info(f"📸 하드웨어 가속 스냅샷 파이프라인이 활성화되었습니다 ({n}병렬).")

    def push_job(self, video_path: Path | str, output_dir: Path | str, product_code: str = "Unknown"):
        """스냅샷 추출 작업을 대기열에 넣습니다. (Non-blocking)"""
        job = {
            "video_path": Path(video_path),
            "output_dir": Path(output_dir),
            "product_code": product_code
        }
        self._queue.put(job)
        logger.info(f"📥 스냅샷 작업 접수: {product_code}. (대기: {self._queue.qsize()}개)")

    def _worker_loop(self):
        while True:
            job = self._queue.get()
            try:
                code = job["product_code"]
                vp = job["video_path"]
                od = job["output_dir"]
                
                logger.info(f"🚀 [Snapshot-Queue] 추출 시작: {code}")
                meta_path = Path(od) / ".snapshot.meta.json"
                params = {"prefix": "snapshot", "quality": 85}

                # target_count는 내부에서 duration 기반으로 결정되지만,
                # 워커 스킵 판정을 위해 현재 결과로부터 유추(기존 파일 개수) + 메타 동등성만 사용.
                existing = list(Path(od).glob("snapshot_*.jpg"))
                if existing and is_up_to_date(meta_path=meta_path, inputs={"video": Path(vp)}, params=params):
                    logger.info(f"⏭️ [Snapshot-Queue] 스킵(최신): {code} ({len(existing)}개)")
                else:
                    with ffmpeg_semaphore:
                        with perf_span(
                            "snapshots.extract",
                            product_code=str(code),
                            video=str(vp),
                            out_dir=str(od),
                            via="snapshot_queue",
                        ):
                            # extract_snapshots_auto_adaptive 내부에서 자동으로 CUDA 가속 사용 시도함
                            extract_snapshots_auto_adaptive(vp, od)
                    mark_up_to_date(meta_path=meta_path, inputs={"video": Path(vp)}, params=params)
                logger.info(f"✅ [Snapshot-Queue] 추출 완료: {code}")
            except Exception as e:
                logger.exception(f"❌ [Snapshot-Queue] 에러 발생: {e}")
            finally:
                self._queue.task_done()

# 전역 싱글턴 객체
snapshot_queue_manager = SnapshotQueueManager()
