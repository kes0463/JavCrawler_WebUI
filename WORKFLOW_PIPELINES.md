# JAVSTORY 워크플로우 & 파이프라인 문서

이 문서는 레포지토리 `JAVSTORY`의 **실행 흐름(워크플로우)** 과 **주요 파이프라인 구성**을 코드 기준으로 정리한 운영 문서입니다.
(기준: 2026-04, Windows 환경, 구조 정리 후)

---

## 1) 프로젝트 구조 개요

```
JAVSTORY/
├── javstory/                    # 메인 패키지 (통합 네임스페이스)
│   ├── config/                  #   앱 설정, 시크릿 관리
│   ├── llm/                     #   LLM 라우터 (OpenRouter/Ollama)
│   ├── utils/                   #   공용 유틸리티
│   ├── harvest/                 #   메타 크롤링·번역·DB
│   ├── transcription/           #   STT (stable-ts)
│   ├── translation/             #   자막 교정·KO 번역
│   ├── library/                 #   라이브러리 도메인
│   │   ├── canonical/           #     정규 스키마·저장
│   │   ├── export/              #     번들·지문·master_db
│   │   ├── multipart/           #     멀티파트 탐지·SRT 병합
│   │   ├── stills/              #     스틸 추출
│   │   └── grok_merge/          #     Grok 초안 병합
│   └── pipeline/                #   전체 오케스트레이션
├── gui/                         # PyQt6 Fluent 데스크톱 GUI
│   ├── main_window.py
│   ├── theme_manager.py
│   ├── library_data.py
│   ├── components/              #   재사용 위젯
│   ├── views/                   #   5대 뷰 (Dashboard/Harvest/Processing/Library/Settings)
│   └── workers/                 #   백그라운드 QThread 워커
├── tests/                       # pytest 테스트
│   ├── unit/
│   ├── manual/
│   └── cli/
├── scripts/                     # CLI 도구
│   └── run_product_pipeline.py
├── gui_main_v2.py               # GUI 진입점
├── start.bat                    # venv 활성화 + GUI 실행
└── setup.bat                    # 최초 환경 설정
```

---

## 2) 전체 아키텍처 한눈에 보기

이 프로젝트는 **"영상 1개 = 품번 1개"** 를 중심으로 아래 파이프라인이 순차 연결됩니다.

```
┌─────────────────────────────────────────────────────────────────────┐
│                     품번 파이프라인 (메타 + 자막)                       │
│                                                                     │
│   ┌──────────┐    ┌──────────┐    ┌──────────────────────────┐     │
│   │ Harvest  │───▶│   STT    │───▶│       Subtitle           │     │
│   │ (크롤링) │    │(stable-ts)│   │ (JA 교정 → KO 번역)      │     │
│   └──────────┘    └──────────┘    └──────────────────────────┘     │
│        │               │                     │                      │
│        ▼               ▼                     ▼                      │
│   DB 메타데이터    {stem}.ja.srt    {stem}.corrected.srt             │
│   + Grok JSON                       {stem}.ko.srt                   │
└─────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    라이브러리 + Export                                │
│                                                                     │
│   canonical 스키마 → Grok 병합 → 스틸 추출 → SQLite DB 연동      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3) 엔트리포인트 (실행 시작점)

| 파일 | 역할 | 비고 |
|------|------|------|
| `gui_main_v2.py` | GUI 실행 | venv 부트스트랩 → CUDA DLL 패치 → PyQt6 앱 |
| `start.bat` | GUI 래퍼 | venv 활성화 후 `gui_main_v2.py` 실행 |
| `scripts/run_product_pipeline.py` | CLI 품번 파이프라인 | `--stages harvest,stt,subtitle` |

### GUI 부트 시퀀스

```
gui_main_v2.py
  ├─ javstory.transcription.venv_bootstrap → venv 재실행 (필요시)
  ├─ javstory.utils.dll_patcher            → CUDA DLL 경로 패치
  └─ gui.main_window.JAVStoryMainWindow    → PyQt6 Fluent 메인 윈도우
       ├─ gui.views.dashboard     (대시보드)
       ├─ gui.views.harvest       (수집)
       ├─ gui.views.processing    (전사/분석)
       ├─ gui.views.library       (라이브러리)
       └─ gui.views.settings      (설정)
```

---

## 4) 품번 파이프라인 오케스트레이터

### 핵심 모듈

- **파일**: `javstory/pipeline/orchestrator.py`
- **함수**: `run_product_pipeline_async(...)`
- **단계**: `PipelineStage.HARVEST` → `PipelineStage.STT` → `PipelineStage.SUBTITLE`

### 동작 개요

```python
await run_product_pipeline_async(
    product_code="ABC-123",
    video_path="D:/media/ABC-123.mp4",
    stages="all",                    # 또는 {PipelineStage.STT, PipelineStage.SUBTITLE}
    skip_if_outputs_exist=True,      # 산출물 존재 시 스킵
    force=False,                     # True면 스킵 무시
)
```

### 단계별 스킵 판단

`get_pipeline_status()`가 산출물 존재를 점검합니다.

| 단계 | 스킵 조건 |
|------|-----------|
| **Harvest** | DB에 해당 품번 메타 존재 (`title_ko` / `title_ja` / `original_title`) |
| **STT** | 영상 옆에 `{stem}.ja.srt` 존재 |
| **Subtitle** | `{stem}.ko.srt` 존재 |

> `video_path` 없이 품번만 넘기면 STT/자막 존재 여부는 판단하지 않습니다.

---

## 5) Harvest 단계 (메타 수집 → DB)

```
javstory.harvest.coordinator.run_crawler_for_video_path(video_path, ...)
  │
  ├─ javstory.harvest.crawler.HybridJavCrawler    # Playwright + DrissionPage 크롤링
  ├─ javstory.harvest.translator.MetadataTranslator # DeepSeek 기반 KO 번역
  ├─ javstory.harvest.database.upsert_jav_metadata  # SQLite DB 적재
  ├─ javstory.utils.actress_resolver.ActressResolver # 배우명 표준화
  ├─ javstory.utils.assets_handler                   # 커버/자산 다운로드
  └─ story_grok_module.run_story_grok_after_harvest   # Grok 스토리 JSON 캐시
       └─ data/cache/story_context/{품번}.json
```

### 입력/출력

- **입력**: 영상 경로 또는 품번 문자열
- **출력**: `data/db/jav_database.db`에 `JAVMetadata` upsert + Grok 캐시 JSON

---

## 6) STT 단계 (stable-ts → `.ja.srt`)

```
javstory.transcription.engine.process_video_to_segments(video_path, output_dir, ...)
  │
  ├─ javstory.transcription.win_cuda_dlls    # Windows CUDA DLL 경로 등록
  ├─ javstory.transcription.stable_ts_pipeline.run_stable_ts(...)
  │    └─ stable-ts + faster-whisper 기반 음성 인식
  └─ 결과: {stem}.ja.srt (영상 옆)
```

### 핵심 규칙

- 최종 출력은 **영상 옆** `{stem}.ja.srt`
- 이미 `.ja.srt`가 존재하면 STT를 건너뛰고 기존 파일을 로드 (캐시 동작)
- stable-ts 고정 경로 사용 (레거시 Whisper 미사용)

---

## 7) Subtitle 단계 (JA 교정 + KO 번역)

### 오케스트레이터

- **파일**: `javstory/translation/subtitle_pipeline_orchestrator.py`
- **클래스**: `SubtitlePipelineOrchestrator`
- **메서드**: `run_for_product(product_code, **kwargs)`

### 실행 흐름

```
SubtitlePipelineOrchestrator.run_for_product(product_code, ...)
  │
  │  ① 데이터 로드 (LLM 호출 없음)
  ├─ _load_grok_cache()         → data/cache/story_context/{품번}.json
  ├─ _build_background_from_db()→ DB 메타에서 배경 JSON 직접 생성
  │
  │  ② JA 교정 (직렬)
  ├─ _correct_ja_chunks()
  │    └─ correction_chunk.correct_ja_segments_async()
  │         Pass 1: Grok 맥락 기반 교정 (일본어 고유명사·맥락)
  │         Pass 2: GLM 기반 문법 교정
  │         [선택] Pass 3: Claude 폴리싱
  │    └─ 결과: {stem}.corrected.srt
  │
  │  ③ KO 번역 (직렬, 교정 결과 사용)
  └─ _translate_ko_chunks()
       └─ ko_translation_chunk.translate_ja_segments_to_ko_async()
            배경(DB) + Grok 힌트 + 씬톤 활용
       └─ 결과: {stem}.ko.srt
```

### 산출물 네이밍 규칙

| 입력 | 교정 출력 | 번역 출력 |
|------|-----------|-----------|
| `foo.ja.srt` | `foo.ja.corrected.srt` | `foo.ko.srt` |
| `foo.srt` | `foo.corrected.srt` | `foo.ko.srt` |

> `.ja.ko.srt` 이중 접미사 방지: stem에서 `.ja`와 `.corrected`를 제거한 뒤 `.ko.srt`를 붙입니다.

### LLM 티어 체인

```
교정 Pass 1 → pass1_tier (기본: Grok 계열)
교정 Pass 2 → pass2_tier (기본: GLM/DeepSeek 계열)
교정 Pass 3 → pass3_tier (선택: Claude, enable_pass3=True)
KO 번역     → translation_tier (기본: DeepSeek V3)
```

모든 LLM 호출은 `javstory.llm.engine.MultiTierRouter`를 통해 OpenRouter API로 라우팅됩니다.

---

## 8) 라이브러리 & Export

### 도메인 레이어

- **파일**: `javstory/library/service.py` (고수준 API)
- **스키마**: `javstory/library/canonical/schema.py` (`LibraryCanonical`, `SceneEntry`)
- **저장**: `javstory/library/canonical/store.py` → `%LOCALAPPDATA%\JAVSTORY\Library\library_state.json`

### 기능 모듈

| 모듈 | 역할 |
|------|------|
| `library/canonical/` | 정규 스키마 정의, 파일 기반 상태 저장/로드 |
| `library/export/` | 번들 생성, 지문(fingerprint), SQLite 동기화 |
| `library/multipart/` | 멀티파트 영상 탐지, SRT 타임라인 병합, 파트별 duration 프로빙 |
| `library/stills/` | 영상에서 대표 스틸 이미지 추출 (등간격 분할, 시간 범위) |
| `library/grok_merge/` | Grok 초안 JSON을 canonical 스키마에 병합 |

### Export 흐름

```
javstory.library.service.run_export()
  └─ canonical 스키마 → SQLite DB 동기화
```

---

## 9) GUI 워커 연결

GUI의 백그라운드 작업은 `gui/workers/` 아래의 QThread 워커로 처리됩니다.

| 워커 | 대상 | 호출 모듈 |
|------|------|-----------|
| `harvest_worker.py` | Harvest 크롤링 | `javstory.harvest.coordinator` |
| `stt_worker.py` | STT 전사 | `javstory.transcription.engine` |
| `subtitle_worker.py` | 자막 교정/번역 | `javstory.translation.subtitle_pipeline_orchestrator` |
| `pipeline_worker.py` | 원스톱 파이프라인 | `javstory.pipeline.orchestrator` |

```
gui.views.harvest     → HarvestWorker     → javstory.harvest.coordinator
gui.views.processing  → STTWorker         → javstory.transcription.engine
                      → SubtitleWorker    → javstory.translation.*
gui.components.*      → PipelineWorker    → javstory.pipeline.orchestrator
```

---

## 10) 데이터 레이아웃

`javstory/config/app_config.py`에 정의된 디렉터리 구조:

```
data/
├── db/
│   └── jav_database.db          # SQLAlchemy + SQLite (JAVMetadata 등)
├── media/                       # 커버 이미지, 자산 파일
└── cache/
    ├── story_context/           # Grok 스토리 JSON 캐시 ({품번}.json)
    └── reference/               # 레퍼런스 캐시
```

---

## 11) 운영 워크플로우 추천

### "품번 1개" 원스톱 (GUI)

1. **하베스트 뷰**에서 품번 검색/수집
2. **프로세싱 뷰**에서 영상 선택 → STT + 자막 실행
3. **라이브러리 뷰**에서 결과 확인

### "품번 1개" 원스톱 (CLI)

```bash
python scripts/run_product_pipeline.py ABC-123 \
    --video "D:/media/ABC-123.mp4" \
    --stages all
```

### 스킵/캐시 정책

재실행이 안전합니다:
- Harvest: DB 메타 있으면 스킵
- STT: `.ja.srt` 있으면 스킵
- Subtitle: `.ko.srt` 있으면 스킵
- `--force` 플래그로 강제 재실행 가능

---

## 12) 관련 파일 빠른 링크

| 역할 | 경로 |
|------|------|
| 품번 파이프라인 오케스트레이터 | `javstory/pipeline/orchestrator.py` |
| 자막 오케스트레이터 | `javstory/translation/subtitle_pipeline_orchestrator.py` |
| STT 진입점 (stable-ts) | `javstory/transcription/engine.py` |
| Harvest 코디네이터 | `javstory/harvest/coordinator.py` |
| LLM 라우터 | `javstory/llm/engine.py` |
| 앱 설정 | `javstory/config/app_config.py` |
| 라이브러리 서비스 | `javstory/library/service.py` |
| GUI 런처 | `gui_main_v2.py` |
| CLI 파이프라인 | `scripts/run_product_pipeline.py` |
| 웹 빌더 | `build_master_db.py` |
