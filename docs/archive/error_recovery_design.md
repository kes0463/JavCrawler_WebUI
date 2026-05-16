# Stage 6: 에러 복구 자동화 (Error Recovery Automation)

## 1. 개요

Stage 6은前面 파이프라인 단계(Harvest → STT → 자막 번역)에서 실패한 작업을 자동으로 복구하는 유지보수 단계입니다.

## 2. 핵심 기능

### 2.1 에러 폴더 관리
- **위치**: `data/error/04_ERROR/`
- **구조**:
  ```
  04_ERROR/
  ├── harvest/
  │   └── {품번}__{실패원인}__{타임스탬프}.json
  ├── stt/
  │   └── {품번}__{실패원인}__{타임스탬프}.json
  └── subtitle/
      └── {품번}__{실패원인}__{타임스탬프}.json
  ```

### 2.2 실패 원인 분류
| 코드 | 원인 | 재시도 전략 |
|------|------|------------|
| `NETWORK_ERROR` | 네트워크 실패 | 5분 후 재시도 (최대 3회) |
| `CRAWL_FAILED` | 크롤링 실패 | 10분 후 재시도 (최대 2회) |
| `STT_FAILED` | 음성 인식 실패 | 30분 후 재시도 (최대 2회) |
| `TRANSLATION_FAILED` | 번역 실패 | 1시간 후 재시도 (최대 3회) |
| `FILE_NOT_FOUND` | 파일 없음 | 수동 해결 필요 |
| `API_RATE_LIMIT` | API 한도 초과 | 대기 후 재시도 |
| `UNKNOWN` | 알 수 없는 오류 | 알림 후 대기 |

### 2.3 재시도 스케줄러
- **간격**: 실패 유형에 따라 다름
- **최대 재시도 횟수**: 유형별 상이
- **백오프策略**: 지수적 증가 (5분 → 10분 → 30분 → 1시간)

### 2.4 알림 시스템
- GUI 대시보드에 에러 상태 표시
- 재시도 횟수 초과 시 사용자에게 알림

## 3. 데이터 구조

### ErrorTask JSON
```json
{
  "product_code": "ABC-123",
  "stage": "HARVEST|STT|SUBTITLE",
  "error_type": "NETWORK_ERROR",
  "error_message": "Connection timeout",
  "failed_at": "2026-04-25T10:30:00",
  "retry_count": 0,
  "max_retries": 3,
  "next_retry_at": "2026-04-25T10:35:00",
  "video_path": "D:/media/ABC-123.mp4",
  "stack_trace": "..."
}
```

## 4. 모듈 설계

### 4.1 ErrorRecoveryService
- **파일**: `javstory/utils/error_recovery.py`
- **역할**: 에러 작업 관리, 재시도 로직 실행

### 4.2 ErrorWatcher
- **파일**: `javstory/utils/error_watcher.py`
- **역할**: 04_ERROR 폴더 모니터링

### 4.3 ErrorDashboard Widget
- **파일**: `gui/components/error_dashboard.py`
- **역할**: GUI에 에러 상태 표시

## 5. API

### ErrorRecoveryService
```python
class ErrorRecoveryService:
    async def save_error_task(self, task: ErrorTask) -> None
    async def get_pending_errors(self) -> List[ErrorTask]
    async def retry_error_task(self, task_id: str) -> bool
    async def mark_resolved(self, task_id: str) -> None
    async def get_error_stats(self) -> ErrorStats
```

### ErrorWatcher
```python
class ErrorWatcher:
    def start_watching(self) -> None
    def stop_watching(self) -> None
    async def check_and_retry(self) -> None
```

## 6. GUI 연동

- **위치**: 대시보드 우측 패널
- **표시 항목**:
  - 현재 대기 중인 에러 작업 수
  - 재시도 예정 작업
  - 실패 횟수 초과 작업
  - "지금 재시도" 버튼