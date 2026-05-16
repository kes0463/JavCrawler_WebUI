# LLM / OpenRouter 자막 파이프라인 문제 해결

자막 교정·한국어 번역 단계에서 **모든 OpenRouter 티어가 실패**하거나 **검열(Refusal)** 되면 `AllTiersExhaustedError`가 발생합니다. STT 중단(`STTCancelled`)과는 별개입니다.

## 환경 체크리스트

1. **OpenRouter API 키**
   - 환경 변수 `OPENROUTER_API_KEY` 또는 레거시 `JAVSTORY_OPENROUTER_API_KEY`
   - 설정 화면에서 keyring에 저장한 키
2. **`.env` 모델·프로필** (선택, 미설정 시 앱 기본값)
   - `JAVSTORY_CORRECTION_PASS1_MODEL` / `JAVSTORY_CORRECTION_PASS2_MODEL`
   - `JAVSTORY_TRANSLATION_OPENROUTER_MODEL`
   - `JAVSTORY_TRANSLATION_PROFILE`
3. **스토리 컨텍스트 캐시**
   - Pass1은 Grok JSON 캐시(`data/cache/story_context/{품번}_grok.json`)를 사용
   - `JAVSTORY_CORRECTION_USE_STORY_CONTEXT_CACHE=0` 이면 레거시 프롬프트 경로
4. **터미널 `[Router]` 로그**
   - 티어별 모델명·재시도·검열 메시지 확인

## 증상별 대응

| 증상 | 가능 원인 | 조치 |
|------|-----------|------|
| UI: OpenRouter 티어 전부 실패 | 키 없음·만료·모델 거절 | 키 재입력, 모델명·티어 순서 확인 |
| `[Censored]` 반복 후 실패 | 검열 모델만 사용 | `.env`에서 무검열/다른 티어로 변경 |
| JA 자막 없음 | STT 미완료 | 처리 탭에서 STT 먼저 실행 |
| 작업 중단 메시지 | 사용자 취소 | `STTCancelled` — 키/모델 문제 아님 |

## 부트 크래시 vs 파이프라인 실패

- **부트 크래시**: `logs/crash_report.txt` (`main.py` 훅)
- **파이프라인 실패·재시도 큐**: `data/error/04_ERROR/` (`javstory.utils.error_recovery`)

설정 화면 하단 **«실패 작업 폴더 열기»** 로 `04_ERROR`를 열 수 있습니다.

## Ollama CPU 부하 (로컬 번역)

로컬 Ollama 사용 시 CPU 사용률이 높으면 `.env` 예:

```bash
OLLAMA_NUM_THREAD=2
OLLAMA_THREADS=2
JAVSTORY_TRANSLATION_CONCURRENCY=1
```

서버: `ollama serve` 전에 스레드 제한. 더 작은 모델(예: 4B)로 교체하면 부하가 줄어듭니다.  
상세 메모: [archive/ollama_cpu_optimization.md](archive/ollama_cpu_optimization.md)
