---
description: JAV Story Analyzer 통합 데이터 분석 워크플로우
---

이 워크플로우는 **앱 시작(`main.py`)** 부터 영상 메타·STT·자막·라이브러리 확인까지의 전 과정을 설명합니다.  
모듈 경로·파이프라인 상세는 [`WORKFLOW_PIPELINES.md`](../../WORKFLOW_PIPELINES.md), 진입점 표는 [`docs/architecture/ENTRYPOINTS.md`](../../docs/architecture/ENTRYPOINTS.md)를 참고하세요.

---

### 0단계: 앱 시작 (데스크톱 GUI)

| 방법 | 명령 |
|------|------|
| Windows | `start.bat` |
| 직접 | `python main.py` (프로젝트 루트, `venv` 활성화 후) |

**부트 시퀀스 (`main.py`):**

```
main.py
  ├─ javstory.transcription.venv_bootstrap
  ├─ javstory.utils.dll_patcher / ffmpeg_path
  ├─ PySide6.QtWidgets.QApplication
  └─ gui.app.create_engine(app)
       ├─ javstory.harvest.database.init_db
       ├─ QQmlApplicationEngine → gui/qml/main.qml
       └─ gui/models/* → QML context (LibraryModel, ProcessingModel, …)
```

- **운영 UI:** PySide6 + QML (`gui/qml/views/`)
- **사용하지 않음:** `gui/main_window.py`, `gui/views/*.py` (PyQt6 Fluent, deprecated)

---

### 1단계: 하이브리드 메타데이터 수집

- **GUI:** `HarvestView.qml` → `gui/workers/harvest_worker.py`
- **진입점**: `javstory.harvest.coordinator.run_crawler_for_video_path(video_path, ...)`
- **크롤러**: `javstory.harvest.crawler.HybridJavCrawler` (Playwright + DrissionPage)
- **번역**: `javstory.harvest.translator.MetadataTranslator` — DeepSeek V3 / Hermes 405B 폴백 체인으로 무검열 한국어 번역
- **DB 적재**: `javstory.harvest.database.upsert_jav_metadata` → `data/db/jav_database.db`
- **배우명 표준화**: `javstory.utils.actress_resolver.ActressResolver`
- **Grok 스토리 JSON**: 수집 직후 `story_grok_module.run_story_grok_after_harvest` → `data/cache/story_context/{품번}_grok.json`

---

### 2단계: STT — 일본어 자막 생성

- **GUI:** `ProcessingView.qml` → `ProcessingModel` → `gui/workers/stt_worker.py`
- **진입점**: `javstory.transcription.engine.process_video_to_segments(video_path, output_dir, ...)`
- **엔진**: `stable-ts` + `faster-whisper` (레거시 Whisper 미사용)
- **출력**: 영상 옆 `{stem}.ja.srt`
- **캐시 동작**: `.ja.srt`가 이미 존재하면 STT 스킵

---

### 3단계: 자막 교정 + 한국어 번역

- **GUI:** `ProcessingView.qml` → `SubtitleWorker`
- **진입점**: `javstory.translation.subtitle_pipeline_orchestrator.SubtitlePipelineOrchestrator.run_for_product(product_code, ...)`
- **흐름**:
  1. Grok 캐시 로드 (`data/cache/story_context/{품번}_grok.json`)
  2. JA 교정 — Pass 1 (Grok 맥락) → Pass 2 (GLM) → `{stem}.ja.corrected.srt`
  3. KO 번역 — DeepSeek V3 계열 → `{stem}.ko.srt`
- **LLM 라우터**: `javstory.llm.engine.MultiTierRouter` (OpenRouter API)
- **실패 진단**: `docs/llm_troubleshooting.md`

---

### 4단계: 파이프라인 원스톱 실행

- **오케스트레이터**: `javstory.pipeline.orchestrator.run_product_pipeline_async(product_code, video_path, stages, ...)`
- **단계**: `PipelineStage.HARVEST` → `PipelineStage.STT` → `PipelineStage.SUBTITLE`
- **스킵 정책**: 산출물이 이미 존재하면 자동 스킵 (`--force`로 강제 재실행)
- **CLI**: `python scripts/run_product_pipeline.py ABC-123 --video "…" --stages all`

---

### 5단계: 결과 확인 및 관리

- **GUI:** `LibraryView.qml` / `LibraryDetail.qml` — `LibraryModel`
  - 폴더 바인딩, 재생(`PlayerView.qml`), 씬·메타 편집
- **canonical:** `%LOCALAPPDATA%\JAVSTORY\Library\{품번}\library_state.json`
- **파이프라인 실패 기록:** `data/error/04_ERROR/` (설정 → «실패 작업 폴더 열기»)
- **부트 크래시:** `logs/crash_report.txt` (`main.py` 예외 훅)

---

### 문서 동기화 (에이전트용)

| 주제 | SoT 문서 |
|------|----------|
| 진입점 | `docs/architecture/ENTRYPOINTS.md` |
| 파이프라인 | `WORKFLOW_PIPELINES.md` (본 파일의 상위 문서) |
| 데이터 계층 | `docs/DATA_SOT_LAYERS.md` |
| 레거시 GUI | `gui/DEPRECATED_PYQT6.md` |

**쓰지 말 것:** `gui_main_v2.py`, `gui_main.py` (삭제됨). GUI 실행은 항상 **`main.py`**.
