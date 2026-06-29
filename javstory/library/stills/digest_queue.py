"""백그라운드 다이제스트 생성 큐 매니저."""

from __future__ import annotations

import logging
import os
import threading
import queue
from pathlib import Path

from javstory.library.stills.digest import create_digest_video
from javstory.utils.process_limit import ffmpeg_semaphore

logger = logging.getLogger(__name__)

class DigestQueueManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DigestQueueManager, cls).__new__(cls)
                cls._instance._init_queue()
            return cls._instance

    def _init_queue(self):
        self._queue = queue.Queue()
        self._workers = []
        # 데몬(daemon) 옵션 True: 앱이 종료되면 이 스레드도 미련 없이 즉시 죽음
        raw = (os.environ.get("JAVSTORY_DIGEST_QUEUE_WORKERS", "") or "").strip()
        try:
            n = int(raw) if raw else 4
        except ValueError:
            n = 4
        n = max(1, min(8, n))

        # NVIDIA CUDA 하드웨어 가속 기본 4병렬 (환경변수로 조절)
        for i in range(n):
            t = threading.Thread(target=self._worker_loop, daemon=True, name=f"DigestWorkerThread-{i+1}")
            t.start()
            self._workers.append(t)
        logger.info(f"🎥 백그라운드 다이제스트 스케줄러가 활성화되었습니다 (CUDA {n}병렬).")

    def push_job(self, video_path: Path | str, output_path: Path | str, product_code: str = "Unknown"):
        """
        렌더링 작업을 대기열 맨 뒤에 넣습니다. 
        호출이 0.001초 만에 끝나므로 메인(하베스트 등) 코드를 전혀 블로킹하지 않습니다.
        """
        job = {
            "video_path": Path(video_path),
            "output_path": Path(output_path),
            "product_code": product_code
        }
        self._queue.put(job)
        logger.info(f"📥 다이제스트 작업이 큐에 접수되었습니다 [{product_code}]. (대기 열: {self._queue.qsize()}개)")

    def _worker_loop(self):
        """큐를 무한정 지켜보면서 일거리가 들어오면 순서대로 구워내는 영구 루프 (별도 스레드에서만 돎)"""
        while True:
            # 큐에 아이템이 들어올 때까지 잠자며 기다림 (시스템 부하 0)
            job = self._queue.get()
            try:
                code = job["product_code"]
                vp = job["video_path"]
                op = job["output_path"]
                
                # 이미 구워져 있다면 패스
                if op.exists():
                    continue

                logger.info(f"🚀 [Queue] 다이제스트 인코딩 시작: {code} (대기 열: {self._queue.qsize()}개 남음)")

                with ffmpeg_semaphore:
                    create_digest_video(
                        video_path=vp,
                        output_path=op,
                        speed=60,
                        width=860,
                    )
                
                logger.info(f"✅ [Queue] 다이제스트 인코딩 완료: {code}")
            except Exception as e:
                logger.exception(f"❌ [Queue] 다이제스트 렌더링 중 치명적 에러 발생: {e}")
            finally:
                # 큐에게 작업 하나 끝났음을 보고함
                self._queue.task_done()

# 전역에서 쓸 수 있는 싱글턴 객체
digest_queue_manager = DigestQueueManager()
