"""
Error Watcher - 04_ERROR 폴더 감시 및 재시도 스케줄러

실패한 작업을 모니터링하고 자동으로 재시도하는 백그라운드 서비스입니다.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict
import threading

from javstory.utils.error_recovery import (
    ErrorRecoveryService,
    get_error_recovery_service,
    ErrorStats
)

logger = logging.getLogger(__name__)


class ErrorWatcher:
    """
    에러 폴더 감시 및 재시도 스케줄러
    
    주요 기능:
    - 04_ERROR 폴더 주기적 모니터링
    - 재시도 시간 도달한 작업 자동 실행
    - 백그라운드 스레드에서 동작
    """
    
    def __init__(
        self,
        check_interval_seconds: int = 300,  # 5분마다 확인
        error_service: Optional[ErrorRecoveryService] = None
    ):
        """
        Args:
            check_interval_seconds: 에러 확인 간격 (초)
            error_service: ErrorRecoveryService 인스턴스
        """
        self.check_interval = check_interval_seconds
        self.error_service = error_service or get_error_recovery_service()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
    
    def start_watching(self):
        """에러 감시 시작 (백그라운드 스레드)"""
        if self._running:
            logger.warning("[ErrorWatcher] 이미 실행 중")
            return
        
        self._running = True
        self._stop_event.clear()
        
        self._thread = threading.Thread(
            target=self._watch_loop,
            daemon=True,
            name="ErrorWatcher"
        )
        self._thread.start()
        
        logger.info("[ErrorWatcher] 에러 감시 시작")
    
    def stop_watching(self):
        """에러 감시 중지"""
        if not self._running:
            return
        
        self._running = False
        self._stop_event.set()
        
        if self._thread:
            self._thread.join(timeout=10)
        
        logger.info("[ErrorWatcher] 에러 감시 중지")
    
    def _watch_loop(self):
        """백그라운드 감시 루프"""
        import time
        
        while self._running and not self._stop_event.is_set():
            try:
                # 비동기 코드를 동기 컨텍스트에서 실행
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    results = loop.run_until_complete(
                        self.error_service.check_and_retry_all()
                    )
                    
                    if results["pending"] > 0:
                        logger.info(
                            f"[ErrorWatcher] 재시도 결과: "
                            f"성공={results['succeeded']} | 실패={results['failed']} | "
                            f"대기={results['pending']}"
                        )
                finally:
                    loop.close()
                    
            except Exception as e:
                logger.error(f"[ErrorWatcher] 감시 루프 오류: {e}")
            
            # 지정된 간격 대기
            self._stop_event.wait(self.check_interval)
    
    async def get_stats(self) -> ErrorStats:
        """에러 통계 반환"""
        return await self.error_service.get_error_stats()
    
    async def force_retry_all(self) -> Dict[str, int]:
        """모든 대기 에러 즉시 재시도 (수동 트리거)"""
        return await self.error_service.check_and_retry_all()


class ErrorScheduler:
    """
    에러 재시도 스케줄러
    
    특정 시간에 맞춰 에러 재시도를 예약합니다.
    """
    
    def __init__(self, error_service: Optional[ErrorRecoveryService] = None):
        self.error_service = error_service or get_error_recovery_service()
        self._scheduled_tasks: Dict[str, asyncio.Task] = {}
    
    async def schedule_retry(
        self,
        product_code: str,
        delay_seconds: int
    ) -> str:
        """
        특정 시간 후 재시도 예약
        
        Args:
            product_code: 품번
            delay_seconds: 지연 시간 (초)
        
        Returns:
            작업 ID
        """
        task_id = f"{product_code}_{datetime.now().timestamp()}"
        
        async def delayed_retry():
            await asyncio.sleep(delay_seconds)
            pending = await self.error_service.get_pending_errors()
            
            for task in pending:
                if task.product_code == product_code and not task.resolved:
                    await self.error_service.retry_error_task(task)
                    break
        
        self._scheduled_tasks[task_id] = asyncio.create_task(delayed_retry())
        logger.info(f"[ErrorScheduler] 재시도 예약: {product_code} | {delay_seconds}초 후")
        
        return task_id
    
    def cancel_scheduled(self, task_id: str):
        """예약된 재시도 취소"""
        if task_id in self._scheduled_tasks:
            self._scheduled_tasks[task_id].cancel()
            del self._scheduled_tasks[task_id]
            logger.info(f"[ErrorScheduler] 예약 취소: {task_id}")


# 전역 인스턴스
_error_watcher: Optional[ErrorWatcher] = None
_error_scheduler: Optional[ErrorScheduler] = None


def get_error_watcher() -> ErrorWatcher:
    """ErrorWatcher 전역 인스턴스 반환"""
    global _error_watcher
    if _error_watcher is None:
        _error_watcher = ErrorWatcher()
    return _error_watcher


def get_error_scheduler() -> ErrorScheduler:
    """ErrorScheduler 전역 인스턴스 반환"""
    global _error_scheduler
    if _error_scheduler is None:
        _error_scheduler = ErrorScheduler()
    return _error_scheduler


# 파이프라인 통합을 위한 유틸리티 함수

async def capture_and_save_error(
    product_code: str,
    stage: str,
    error: Exception,
    video_path: Optional[str] = None
):
    """
    파이프라인에서 예외 발생 시 에러를 캡처하고 저장하는 유틸리티
    
    파이프라인 각 단계에서 try/except로 호출하여 에러를 자동 저장합니다.
    """
    from javstory.utils.error_recovery import PipelineStage
    
    stage_enum = PipelineStage(stage)
    service = get_error_recovery_service()
    
    import traceback
    stack_trace = traceback.format_exc()
    
    await service.save_error_task(
        product_code=product_code,
        stage=stage_enum,
        error=error,
        video_path=video_path,
        stack_trace=stack_trace
    )


def start_error_monitoring():
    """에러 모니터링 시작 (애플리케이션 시작 시 호출)"""
    watcher = get_error_watcher()
    watcher.start_watching()


def stop_error_monitoring():
    """에러 모니터링 중지 (애플리케이션 종료 시 호출)"""
    watcher = get_error_watcher()
    watcher.stop_watching()