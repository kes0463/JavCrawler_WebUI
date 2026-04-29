"""FFmpeg 전역 리소스 제한을 위한 세마포어 유틸리티."""

import threading
import os

class FFmpegSemaphore:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(FFmpegSemaphore, cls).__new__(cls)
                # 환경변수에서 동시 실행 수 로드 (기본값 2)
                raw = (os.environ.get("JAVSTORY_FFMPEG_CONCURRENCY", "") or "").strip()
                try:
                    n = int(raw) if raw else 2
                except ValueError:
                    n = 2
                # 최소 1개는 보장
                n = max(1, n)
                cls._instance._semaphore = threading.Semaphore(n)
                cls._instance._max_parallel = n
            return cls._instance

    def acquire(self, timeout=None):
        return self._semaphore.acquire(timeout=timeout)

    def release(self):
        self._semaphore.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    @property
    def max_parallel(self):
        return self._max_parallel

# 전역 싱글턴
ffmpeg_semaphore = FFmpegSemaphore()
