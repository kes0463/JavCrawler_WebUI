# JAVSTORY 프로젝트 개발 현황 리포트

**Grand Master Blueprint v20+** 기준의 현재 구현 진척도를 요약한 문서입니다.

## 📊 핵심 파이프라인 진척도 (Stage 1~8)

**Stage 0~3**은 기능·역할 기준으로 **모두 구현 완료**다. 초기 블루프린트·플랜과 **세부 스택·파일 구조·도구 선택**이 다를 뿐, “미구현”이 아니다(예: STT는 stable-ts 단일 경로, Harvest는 `Harvest/` 패키지 등).

| 단계 | 명칭 | 상태 | 주요 내용 |
| :--- | :--- | :---: | :--- |
| **Stage 0** | **Environment** | ✅ 구현 완료 | **AI 환경 구축 자동화** (`tools/setup_ai_env.py`) 및 GPU 가속 검증. |
| **Stage 1** | **Harvest** | ✅ 구현 완료 | `Harvest/` 패키지(크롤러·DB·번역·리싱크) + GUI 하베스트 뷰. **Grok 스토리 맥락 JSON**은 공통 모듈 `build_story_context_report_async`로 **수집 직후** 생성·캐시(`data/cache/story_context/`) — **구현 완료.** |
| **Stage 2** | **Refine** | ✅ 구현 완료 | DeepSeek 기반 무검열 번역 및 배우명 표준화. |
| **Stage 3** | **Queue/STT** | ✅ 구현 완료 | **Transcription**: **stable-ts** 단일 경로(`Transcription/engine`) 자막 생성·워커 연동(레거시 Whisper 엔진 미사용). |
| **Stage 4** | **Analyze** | ✅ 완료 | **v2.1 4단계 엔진** 공정 자동화 및 GUI 통합 완료. |
| **Stage 5** | **Build** | ✅ 완료 | SQLite DB 직접 연동 (master_db.js 폐기) |
| **Stage 6** | **Maintain** | ✅ 구현 완료 | 에러 복구 자동화 구현 완료 (`javstory/utils/error_recovery.py`, `error_watcher.py`, `gui/components/error_dashboard.py`). |
| **Stage 7** | **Watchdog** | ✅ 완료 | 24시간 무인 자동화 분석 루프 GUI 통합 완료. |
| **Stage 8** | **Match** | 🔄 대기 | 자막-스토리 정밀 매칭 및 인물 관계도 도출. |

## Transcription 모듈 — 구현 완료

SoT(참고): `.cursor/plans/transcription_stable-ts_이식_d9a90db7.plan.md` — 플랜 본문의 일부 진척 표기는 과거 스냅샷일 수 있으며, **아래 목록이 현재 코드 기준**이다.

- **완료:** STT (`engine.py`, `stable_ts_pipeline.py`), 레퍼런스·품번 필터 (`reference_collect.py`), 일본어 LLM 교정 (`correction_chunk.py` 등), JSON 파싱·백오프 (`json_extract.py`, `llm_backoff.py`), 배경 JSON (`background_context.py`), 스토리 맥락 Grok (`story_context_report.py`, `story_context_prompts.py`) — **공통 모듈 단일 구현 + Harvest(`Harvest/coordinator.run_crawler_for_video_path`) 직후 연동 구현 완료**, 한국어 청크 번역 (`ko_translation_chunk.py`), 오케스트레이터 (`subtitle_pipeline_orchestrator.run_for_product`: 배경 ∥ Grok 스토리 ∥ JA 교정 → KO `translate_ja_segments_to_ko_async` → `{stem}.ko.srt`).
- **의도적 비포함:** `scene_summary_verify.py`(자막·Ollama 씬 필드 교차 검증)는 **메인 오케스트레이터에 연결하지 않음** — 직접 import·실험용.
- **여지(선택):** `llm_backoff`의 HTTP `Retry-After` 직접 파싱 등.

---

## 🎨 GUI (V2) 구현 현황

- [x] **Mica 테마 및 프레임워크**: Win11 Fluent Design 기반 마스터 윈도우 구축 완료.
- [x] **대시보드 (Dashboard)**: 전체 공장 요약 및 통계 뷰.
- [x] **하베스트 (Harvest)**: 검색/수집·번역 통합 뷰.
- [x] **프로세싱 (Processing)**: 4단계 분석 시각화 및 자동화(공장 모드) 구축 완료.
- [x] **라이브러리 (Library)**: 통합 검색 필터 및 씬 탐색 — SQLite 직접 연동.
- [x] **세팅 (Settings)**: API 키 및 공장 루트 설정.

---

## 🛠 현재 진행 중인 작업 (Next Mission)

> [!IMPORTANT]
> **Stage 8: Match (자막-스토리 매칭)**
> - 자막-스토리 정밀 매칭 및 인물 관계도 도출.

---

## ⚠️ 폐기된 구성요소

| 구성 | 폐기일 |理由 |
|------|--------|------|
| **master_db.js** | 2026-04-25 | Desktop GUI로 통합 |
| **web/ (SPA 뷰어)** | 2026-04-25 | Desktop GUI로 통합 |
| **build_master_db.py** | 2026-04-25 | Desktop GUI로 통합 |

---

## 📝 특이 사항 및 리소스 관리

- **VRAM Safeguard**: 3080 Ti(12GB) 사양에 맞춰 모델이 중첩되지 않도록 순차 분석 로직이 파이프라인에 적용되어 있습니다.
- **번역 품질**: DeepSeek V3 및 Hermes 405B 폴백 체인을 통해 안정적인 무검열 한국어 메타데이터를 확보 중입니다.

---
*마지막 갱신: 2026-04-12 — Grok JSON(공통 모듈 + Harvest 직후) 구현 완료 반영 · Stage 0~3 구현 완료 문구 정리*
