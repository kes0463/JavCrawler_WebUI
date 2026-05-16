# 이슈 현황 (2026-05-16 분석 대비)

[2026-05-16-JAVSTORY-analysis.md](archive/2026-05-16-JAVSTORY-analysis.md) 항목을 **현재 HEAD** 기준으로 갱신합니다.

---

## requirements.txt

| 분석 항목 | 현재 상태 |
|-----------|-----------|
| CUDA 11 + 12 동시 선언 | **해결됨** — `requirements.txt`에 NVIDIA 패키지 없음. GPU는 [`requirements-torch.txt`](../requirements-torch.txt) **cu12만** |
| openai-whisper + stable-ts 이중 | **해결됨** — `openai-whisper` 직접 핀 **제거**. `stable-ts`가 transitive로 관리 |
| numpy 제약 느슨함 | **완화됨** — `numpy>=1.26.0,<2.0` (하한 명시) |

설치: `pip install -r requirements.txt` 후 GPU 시 `pip install -r requirements-torch.txt` ([INSTALL.md](../INSTALL.md)).

---

## DB 스키마 (v2)

| 분석 주장 | 현재 상태 |
|-----------|-----------|
| 단일 `jav_metadata`만 존재 | **부분 정정** — P1–P3 완료: Alembic, `products` / `video_files`, hydrate, `resolve_video_paths_for_playback` |
| Alembic 미도입 | **해결됨** — [ALEMBIC_MILESTONE.md](ALEMBIC_MILESTONE.md) |
| 배우·씬 N:M 정규화 없음 | **의도적 보류 (P4)** — [DB_V2_DESIGN.md](DB_V2_DESIGN.md) §8. `jav_metadata` TEXT + `actresses` 테이블로 당분간 운영 |

**운영 플래그**: `JAVSTORY_DB_V2_READ=1` 시 L2 `video_files` 읽기 ([P3_VERIFY.md](P3_VERIFY.md)).

대용량 라이브러리 성능 이슈가 **배우별 전 작품 필터·DB-only 씬 검색** 등으로 구체화되면 P4 설계 착수.

---

## 프로젝트 구조

| 분석 주장 | 현재 상태 |
|-----------|-----------|
| 루트 `av123_scraper.py` 등 | **해당 없음** — 스크래퍼는 [`javstory/harvest/scrapers/`](../javstory/harvest/scrapers/) (예: `favorites_only_worker`에서 사용 중) |
| 루트 `.py` 과다 | **정상** — 실행 진입점은 [`main.py`](../main.py) 하나 ([ENTRYPOINTS.md](architecture/ENTRYPOINTS.md)) |
| 루트 `.txt` / `.md` / `.log` 혼잡 | **로컬 산출물** — `.gitignore`가 루트 `*.txt`, `*.log`, `*.db` 등 제외. 샘플 품번 txt·디버그 로그는 저장소에 커밋하지 않음 ([REPO_LAYOUT.md](REPO_LAYOUT.md)) |
| `frontend/` + `api/` | **동결** — [ADR 0001](adr/0001-ui-stack-qml-only.md) |

---

## 중간 (Medium) — 2026-05 갱신

| 항목 | 상태 |
|------|------|
| Windows 전용 (`win32mica`, `.bat`) | **문서화** — [PLATFORM.md](PLATFORM.md). `win32mica`는 `sys_platform == "win32"` 조건부 설치. Linux는 `scripts/start.sh` + `JAVSTORY_DISABLE_MICA=1` |
| 루트 `Modelfile` | **정리** — [`config/ollama/`](../config/ollama/README.md), `scripts/ollama_create_model.*` |
| `crash_report.txt`만 | **보강** — `logs/javstory.jsonl` NDJSON (`boot_crash`, `pipeline_error`). 파이프라인 상세는 기존 `data/error/04_ERROR/` |

---

## 아직 열린 항목 (참고)

- PySide6 상한 미고정 시 마이너 API 변경 리스크 → `PySide6>=6.7.2,<6.9` 유지
- P4 junction / `product_locals` — 기능 요구 시
- Settings UI에서 `JAVSTORY_DB_V2_READ` 토글 — 선택
