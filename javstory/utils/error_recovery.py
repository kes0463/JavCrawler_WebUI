"""
Error Recovery Service - Stage 6 (에러 복구 자동화)

파이프라인(Harvest/STT/자막) 실패 작업을 `data/error/04_ERROR/`에 저장·재시도한다.
앱 부트 크래시는 `logs/crash_report.txt`(main.py)와 별도 — 여기서는 런타임 파이프라인만 다룬다.
"""

import json
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict, field
from enum import Enum
import aiofiles

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """실패 원인 분류"""
    NETWORK_ERROR = "NETWORK_ERROR"
    CRAWL_FAILED = "CRAWL_FAILED"
    STT_FAILED = "STT_FAILED"
    TRANSLATION_FAILED = "TRANSLATION_FAILED"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    API_RATE_LIMIT = "API_RATE_LIMIT"
    UNKNOWN = "UNKNOWN"


class PipelineStage(Enum):
    """파이프라인 단계"""
    HARVEST = "HARVEST"
    STT = "STT"
    SUBTITLE = "SUBTITLE"


# 재시도 전략 설정
RETRY_STRATEGY: Dict[ErrorType, Dict[str, Any]] = {
    ErrorType.NETWORK_ERROR: {"interval_minutes": 5, "max_retries": 3},
    ErrorType.CRAWL_FAILED: {"interval_minutes": 10, "max_retries": 2},
    ErrorType.STT_FAILED: {"interval_minutes": 30, "max_retries": 2},
    ErrorType.TRANSLATION_FAILED: {"interval_minutes": 60, "max_retries": 3},
    ErrorType.FILE_NOT_FOUND: {"interval_minutes": 0, "max_retries": 0},  # 수동 해결 필요
    ErrorType.API_RATE_LIMIT: {"interval_minutes": 15, "max_retries": 3},
    ErrorType.UNKNOWN: {"interval_minutes": 30, "max_retries": 2},
}


@dataclass
class ErrorTask:
    """에러 작업 데이터"""
    product_code: str
    stage: str  # HARVEST, STT, SUBTITLE
    error_type: str
    error_message: str
    failed_at: str
    retry_count: int = 0
    max_retries: int = 3
    next_retry_at: Optional[str] = None
    video_path: Optional[str] = None
    stack_trace: Optional[str] = None
    resolved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ErrorTask":
        return cls(**data)


@dataclass
class ErrorStats:
    """에러 통계"""
    total_errors: int = 0
    pending_retries: int = 0
    max_retries_exceeded: int = 0
    resolved: int = 0
    by_stage: Dict[str, int] = field(default_factory=dict)
    by_type: Dict[str, int] = field(default_factory=dict)


class ErrorRecoveryService:
    """
    에러 복구 서비스
    
    주요 기능:
    - 에러 작업 저장 (04_ERROR 폴더)
    - 재시도 스케줄링
    - 자동 재시도 실행
    - 통계 제공
    """
    
    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or Path("data/error")
        self.error_dir = self.base_path / "04_ERROR"
        self._ensure_directories()
    
    def _ensure_directories(self):
        """필요한 디렉터리 생성"""
        for stage in PipelineStage:
            stage_dir = self.error_dir / stage.value.lower()
            stage_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[ErrorRecovery] 에러 디렉터리 초기화: {self.error_dir}")
    
    def _get_stage_dir(self, stage: PipelineStage) -> Path:
        """단계별 디렉터리 반환"""
        return self.error_dir / stage.value.lower()
    
    def _classify_error_type(self, error: Exception) -> ErrorType:
        """예외로부터 에러 유형 분류"""
        error_msg = str(error).lower()
        
        if "network" in error_msg or "connection" in error_msg or "timeout" in error_msg:
            return ErrorType.NETWORK_ERROR
        elif "crawl" in error_msg or "fetch" in error_msg:
            return ErrorType.CRAWL_FAILED
        elif "stt" in error_msg or "whisper" in error_msg or "transcription" in error_msg:
            return ErrorType.STT_FAILED
        elif "translation" in error_msg or "translate" in error_msg:
            return ErrorType.TRANSLATION_FAILED
        elif "file" in error_msg or "not found" in error_msg:
            return ErrorType.FILE_NOT_FOUND
        elif "rate" in error_msg or "limit" in error_msg:
            return ErrorType.API_RATE_LIMIT
        else:
            return ErrorType.UNKNOWN
    
    async def save_error_task(
        self,
        product_code: str,
        stage: PipelineStage,
        error: Exception,
        video_path: Optional[str] = None,
        stack_trace: Optional[str] = None
    ) -> ErrorTask:
        """
        에러 작업 저장
        
        Args:
            product_code: 품번
            stage: 파이프라인 단계
            error: 발생한 예외
            video_path: 영상 경로
            stack_trace: 스택 트레이스
        
        Returns:
            저장된 ErrorTask
        """
        error_type = self._classify_error_type(error)
        strategy = RETRY_STRATEGY.get(error_type, RETRY_STRATEGY[ErrorType.UNKNOWN])
        
        failed_at = datetime.now()
        next_retry = failed_at + timedelta(minutes=strategy["interval_minutes"])
        
        task = ErrorTask(
            product_code=product_code,
            stage=stage.value,
            error_type=error_type.value,
            error_message=str(error),
            failed_at=failed_at.isoformat(),
            retry_count=0,
            max_retries=strategy["max_retries"],
            next_retry_at=next_retry.isoformat() if strategy["max_retries"] > 0 else None,
            video_path=video_path,
            stack_trace=stack_trace
        )
        
        # 파일로 저장
        stage_dir = self._get_stage_dir(stage)
        filename = f"{product_code}__{error_type.value}__{failed_at.strftime('%Y%m%d_%H%M%S')}.json"
        filepath = stage_dir / filename

        try:
            from javstory.utils.structured_log import log_event

            log_event(
                "ERROR",
                "pipeline_error",
                str(error),
                product_code=product_code,
                stage=stage.value,
                error_type=error_type.value,
                error_file=str(filepath),
            )
        except Exception:
            pass
        
        async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(task.to_dict(), ensure_ascii=False, indent=2))
        
        logger.warning(
            f"[ErrorRecovery] 에러 저장: {product_code} | {stage.value} | "
            f"{error_type.value} | 재시도: {strategy['max_retries']}회"
        )
        
        return task
    
    async def get_pending_errors(self) -> List[ErrorTask]:
        """
        재시도 대기 중인 에러 목록 반환
        
        Returns:
            재시도 가능한 ErrorTask 목록
        """
        pending = []
        now = datetime.now()
        
        for stage in PipelineStage:
            stage_dir = self._get_stage_dir(stage)
            if not stage_dir.exists():
                continue
            
            for json_file in stage_dir.glob("*.json"):
                try:
                    async with aiofiles.open(json_file, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        task = ErrorTask.from_dict(json.loads(content))
                    
                    # 이미 해결되었거나 최대 재시도 초과 제외
                    if task.resolved:
                        continue
                    if task.retry_count >= task.max_retries:
                        continue
                    
                    # 재시도 시간 확인
                    if task.next_retry_at:
                        next_retry = datetime.fromisoformat(task.next_retry_at)
                        if now >= next_retry:
                            pending.append(task)
                    else:
                        pending.append(task)
                        
                except Exception as e:
                    logger.error(f"[ErrorRecovery] 에러 파일 읽기 실패: {json_file} - {e}")
        
        return pending
    
    async def retry_error_task(self, task: ErrorTask) -> bool:
        """
        에러 작업 재시도 실행
        
        Args:
            task: 재시도할 ErrorTask
        
        Returns:
            성공 여부
        """
        from javstory.pipeline.orchestrator import run_product_pipeline_async
        from javstory.pipeline.orchestrator import PipelineStage as OrigPipelineStage
        
        try:
            # 해당 단계 다시 실행
            stage_map = {
                "HARVEST": OrigPipelineStage.HARVEST,
                "STT": OrigPipelineStage.STT,
                "SUBTITLE": OrigPipelineStage.SUBTITLE,
            }
            
            stage = stage_map.get(task.stage)
            if not stage:
                logger.error(f"[ErrorRecovery] 알 수 없는 단계: {task.stage}")
                return False
            
            logger.info(f"[ErrorRecovery] 재시도 실행: {task.product_code} | {task.stage}")
            
            # 파이프라인 실행
            await run_product_pipeline_async(
                product_code=task.product_code,
                video_path=task.video_path,
                stages=stage.value,
                skip_if_outputs_exist=False,
                force=True
            )
            
            # 성공 시 해결됨으로 표시
            await self.mark_resolved(task)
            logger.info(f"[ErrorRecovery] 재시도 성공: {task.product_code}")
            return True
            
        except Exception as e:
            logger.error(f"[ErrorRecovery] 재시도 실패: {task.product_code} - {e}")
            # 재시도 횟수 증가
            await self._increment_retry(task)
            return False
    
    async def _increment_retry(self, task: ErrorTask):
        """재시도 횟수 증가 및 다음 재시도 시간 업데이트"""
        task.retry_count += 1
        
        if task.retry_count < task.max_retries:
            error_type = ErrorType(task.error_type)
            strategy = RETRY_STRATEGY.get(error_type, RETRY_STRATEGY[ErrorType.UNKNOWN])
            interval = strategy["interval_minutes"]
            
            next_retry = datetime.now() + timedelta(minutes=interval)
            task.next_retry_at = next_retry.isoformat()
            
            # 파일 업데이트
            await self._update_task_file(task)
    
    async def _update_task_file(self, task: ErrorTask):
        """Task 파일 업데이트"""
        for stage in PipelineStage:
            stage_dir = self._get_stage_dir(stage)
            if not stage_dir.exists():
                continue
            
            for json_file in stage_dir.glob(f"{task.product_code}__*.json"):
                try:
                    async with aiofiles.open(json_file, 'w', encoding='utf-8') as f:
                        await f.write(json.dumps(task.to_dict(), ensure_ascii=False, indent=2))
                    return
                except Exception:
                    continue
    
    async def mark_resolved(self, task: ErrorTask):
        """에러를 해결됨으로 표시"""
        task.resolved = True
        task.next_retry_at = None
        await self._update_task_file(task)
        logger.info(f"[ErrorRecovery] 해결됨 표시: {task.product_code}")
    
    async def get_error_stats(self) -> ErrorStats:
        """
        에러 통계 반환
        
        Returns:
            ErrorStats 객체
        """
        stats = ErrorStats()
        now = datetime.now()
        
        for stage in PipelineStage:
            stage_dir = self._get_stage_dir(stage)
            if not stage_dir.exists():
                continue
            
            for json_file in stage_dir.glob("*.json"):
                try:
                    async with aiofiles.open(json_file, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        task = ErrorTask.from_dict(json.loads(content))
                    
                    stats.total_errors += 1
                    
                    # 단계별 통계
                    stats.by_stage[task.stage] = stats.by_stage.get(task.stage, 0) + 1
                    
                    # 유형별 통계
                    stats.by_type[task.error_type] = stats.by_type.get(task.error_type, 0) + 1
                    
                    if task.resolved:
                        stats.resolved += 1
                    elif task.retry_count >= task.max_retries:
                        stats.max_retries_exceeded += 1
                    elif task.next_retry_at:
                        next_retry = datetime.fromisoformat(task.next_retry_at)
                        if now >= next_retry:
                            stats.pending_retries += 1
                    else:
                        stats.pending_retries += 1
                        
                except Exception as e:
                    logger.error(f"[ErrorRecovery] 통계 계산 오류: {json_file} - {e}")
        
        return stats
    
    async def check_and_retry_all(self) -> Dict[str, int]:
        """
        모든 대기 중인 에러를 확인하고 재시도
        
        Returns:
            {"succeeded": int, "failed": int, "pending": int}
        """
        pending = await self.get_pending_errors()
        
        results = {"succeeded": 0, "failed": 0, "pending": len(pending)}
        
        for task in pending:
            success = await self.retry_error_task(task)
            if success:
                results["succeeded"] += 1
            else:
                results["failed"] += 1
        
        logger.info(
            f"[ErrorRecovery] 일괄 재시도 완료: "
            f"성공={results['succeeded']} | 실패={results['failed']} | 대기={results['pending']}"
        )
        
        return results


# 전역 인스턴스
_error_recovery_service: Optional[ErrorRecoveryService] = None


def get_error_recovery_service() -> ErrorRecoveryService:
    """ErrorRecoveryService 전역 인스턴스 반환"""
    global _error_recovery_service
    if _error_recovery_service is None:
        _error_recovery_service = ErrorRecoveryService()
    return _error_recovery_service