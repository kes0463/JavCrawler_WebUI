---
description: JAV Story Analyzer 통합 데이터 분석 워크플로우
---

이 워크플로우는 영상 파일로부터 메타데이터 수집, 번역, 오디오 전처리, 장면 분석 및 AI 하이엔드 스토리 분석까지의 전 과정을 설명합니다.

### 1단계: 하이브리드 메타데이터 수집 (Phase 1-3)
- **도구**: `core.hybrid_crawler.HybridJavCrawler`
- **프로세스**:
  - `Playwright`를 사용하여 `njavtv.com` 등에서 원본 데이터를 스크레이핑합니다.
  - 일본어 원문 제목, 시놉시스, 배우, 장르, 메이커 정보를 확보합니다.
  - `core.actress_resolver`를 통해 배우 이름을 한글/로마자로 변환합니다.

### 2단계: 무검열 번역 파이프라인 (Phase 5 - New)
- **도구**: `core.translator.MetadataTranslator`
- **프로세스**:
  - `METADATA_CONFIG` 설정에 따라 타이틀과 시놉시스를 한국어로 번역합니다.
  - **Gemini의 검열 위험**을 피하기 위해 `DeepSeek V3` 및 `Hermes 405B` 폴백 체인을 사용합니다.
  - 번역된 데이터는 DB의 `title`, `synopsis` 필드에 저장되고 원문은 `original_title`에 보전됩니다.

### 3단계: 병렬 미디어 분석 (Phase 4)
- **도구**: `core.analyzer_coordinator.run_parallel_analysis`
- **프로세스**:
  - **장면 분석 (`SceneAnalyzer`)**: `FFmpeg` 및 `PySceneDetect`를 사용하여 장면 변화를 감지하고 대표 썸네일(목표 24장)을 추출합니다.
  - **음성 인식 (`Whisper`)**: 로컬 GPU를 사용하여 영상 내 대사를 전체 타임스탬프와 함께 텍스트화(STT)합니다.

### 4단계: 스토리 매칭 및 AI 통합 분석 (Phase 4-5)
- **도구**: `core.story_matcher.StoryMatcher` 및 `core.ai_analyzer.AIAnalyzer`
- **프로세스**:
  - 추출된 텍스트 세그먼트를 각 장면의 시간대에 맞게 정렬(Align)합니다.
  - `AIAnalyzer`가 인물 관계(Relationship Mapping)를 분석하고 한국어 페르소나를 적용하여 장면별 3줄 요약을 생성합니다.
  - 모든 결과는 JSON 형태로 `jav_database.db`의 `extra_data` 및 `scene_summaries` 컬럼에 업데이트됩니다.

### 5단계: 결과 확인 및 관리
- **도구**: `gui.main_window.MainWindow` 또는 `check_db.py`
- **프로세스**:
  - GUI 목록에서 분석 상태(`done`)를 확인합니다.
  - `scripts/migrate_metadata_translations.py`를 통해 기존 데이터의 번역을 사후에 일괄 업데이트할 수도 있습니다.
