---
description: JAV Story Analyzer 통합 데이터 분석 워크플로우
---

이 워크플로우는 영상 파일로부터 메타데이터 수집, 번역, STT, 자막 교정/번역까지의 전 과정을 설명합니다.
상세 모듈 경로 및 아키텍처는 `WORKFLOW_PIPELINES.md`를 참고하세요.

---

### 1단계: 하이브리드 메타데이터 수집

- **진입점**: `javstory.harvest.coordinator.run_crawler_for_video_path(video_path, ...)`
- **크롤러**: `javstory.harvest.crawler.HybridJavCrawler` (Playwright + DrissionPage)
- **번역**: `javstory.harvest.translator.MetadataTranslator` — DeepSeek V3 / Hermes 405B 폴백 체인으로 무검열 한국어 번역
- **DB 적재**: `javstory.harvest.database.upsert_jav_metadata` → `data/db/jav_database.db`
- **배우명 표준화**: `javstory.utils.actress_resolver.ActressResolver`
- **Grok 스토리 JSON**: 수집 직후 `story_grok_module.run_story_grok_after_harvest` 실행 → `data/cache/story_context/{품번}.json`

---

### 2단계: STT — 일본어 자막 생성

- **진입점**: `javstory.transcription.engine.process_video_to_segments(video_path, output_dir, ...)`
- **엔진**: `stable-ts` + `faster-whisper` (레거시 Whisper 미사용)
- **출력**: 영상 옆 `{stem}.ja.srt`
- **캐시 동작**: `.ja.srt`가 이미 존재하면 STT 스킵

---

### 3단계: 자막 교정 + 한국어 번역

- **진입점**: `javstory.translation.subtitle_pipeline_orchestrator.SubtitlePipelineOrchestrator.run_for_product(product_code, ...)`
- **흐름**:
  1. Grok 캐시 로드 (`data/cache/story_context/{품번}.json`)
  2. JA 교정 — Pass 1 (Grok 맥락 기반) → Pass 2 (GLM 문법 교정) → 출력: `{stem}.ja.corrected.srt`
  3. KO 번역 — DeepSeek V3 기반 → 출력: `{stem}.ko.srt`
- **LLM 라우터**: `javstory.llm.engine.MultiTierRouter` (OpenRouter API)

---

### 4단계: 파이프라인 원스톱 실행

- **오케스트레이터**: `javstory.pipeline.orchestrator.run_product_pipeline_async(product_code, video_path, stages, ...)`
- **단계**: `PipelineStage.HARVEST` → `PipelineStage.STT` → `PipelineStage.SUBTITLE`
- **스킵 정책**: 산출물이 이미 존재하면 자동 스킵 (`--force`로 강제 재실행)

---

### 5단계: 결과 확인 및 관리

- **GUI**: `gui_main_v2.py` → `gui.main_window.JAVStoryMainWindow`
  - 라이브러리 뷰에서 분석 상태 및 씬 탐색
- **CLI**: `python scripts/run_product_pipeline.py ABC-123 --video "D:/media/ABC-123.mp4" --stages all`

