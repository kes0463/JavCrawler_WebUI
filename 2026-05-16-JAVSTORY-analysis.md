# JAVSTORY 프로젝트 분석 보고서

> **작성일**: 2026-05-16  
> **분석 대상**: https://github.com/kes0463/JAVSTORY  
> **목적**: 커서(Cursor)를 활용한 추가 분석 및 수정을 위한 사전 이슈 정리  

---

## 📌 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 주요 언어 | Python (63.8%), QML (26.9%), TypeScript (6.8%), JavaScript (1.3%) |
| 기술 스택 | PySide6 + QML (GUI), SQLite + SQLAlchemy (DB), faster-whisper / stable-ts (STT), PySide6 (UI) |
| 아키텍처 | 7-Stage 파이프라인 (Harvest → Refine → Queue → Analyze → Build → Maintain → Watchdog) |
| 플랫폼 | Windows 전용 (Mica 효과, win32mica 사용) |

---

## 🔴 크리티컬 버그 (즉시 수정 필요)

### BUG-001: `currentThreadId` AttributeError — 앱 실행 불가 크래시

**파일**: `gui/models/translation_queue_model.py` (line 60)  
**증상**: 앱 시작 즉시 크래시 (`crash_report.txt` 기록됨)

```
AttributeError: 'PySide6.QtCore.QThread' object has no attribute 'currentThreadId'.
Did you mean: 'currentThread'?
```

**원인**: PySide6의 API 변경으로 `QThread.currentThreadId()`가 제거되거나 이름이 바뀜  
**위치**: `gui/models/translation_queue_model.py:60`

```python
# 현재 (오류)
"qt_thread": int(self.thread().currentThreadId()),

# 수정 방향
"qt_thread": int(self.thread().currentThread()),
# 또는 threading 모듈 활용
import threading
"qt_thread": threading.get_ident()
```

**우선순위**: 🔴 CRITICAL — 앱이 아예 실행되지 않음

---

## 🟠 주요 버그 및 문제점

### BUG-002: `requirements.txt` — 충돌하는 CUDA 의존성

**파일**: `requirements.txt`

```
nvidia-cublas-cu11   # CUDA 11용
nvidia-cudnn-cu11    # CUDA 11용
nvidia-cublas-cu12   # CUDA 12용
```

**문제**: cu11과 cu12 패키지를 동시에 선언. PyTorch는 하나의 CUDA 버전만 지원하므로, 설치 시 충돌 또는 중복 설치 발생.  
**추가 문제**: `torch`, `torchaudio`, `torchvision`의 버전이 고정되지 않아 재현 불가능한 환경이 만들어짐. GPU 사양(3080 Ti)에 맞는 버전 명시 필요.

**수정 방향**:
- `nvidia-cublas-cu11` / `nvidia-cudnn-cu11` 제거 (또는 cu12로 통일)
- `torch==2.x.x+cu121` 형태로 버전 고정
- `torch` 계열은 별도 `requirements-torch.txt` 또는 주석으로 설치 방법 분리

---

### BUG-003: `openai-whisper` + `stable-ts` 이중 선언 — 상호 충돌 위험

**파일**: `requirements.txt`

```
openai-whisper==20240930
stable-ts
```

**문제**: `progress_report.md`에서 "레거시 Whisper 엔진 미사용"이라고 명시했음에도 불구하고, `openai-whisper`가 여전히 requirements에 포함되어 있음.  
`stable-ts`는 내부적으로 whisper를 의존하지만, 버전 충돌이 발생할 수 있음.

**수정 방향**:
- `openai-whisper==20240930` 제거 (stable-ts가 자체적으로 관리하도록)
- 또는 `# 레거시 - stable-ts가 대체함` 주석 명시 후 실제 삭제

---

### BUG-004: `numpy<2.0` 제약 — 일부 라이브러리와 충돌 가능

**파일**: `requirements.txt`

```
numpy<2.0
```

**문제**: `torch`, `torchaudio`, `torchvision` 최신 버전은 NumPy 2.0을 지원하거나 요구할 수 있으며, `scenedetect`, `faster-whisper` 등도 상위 버전을 선호함. 하한선(lower bound)이 없어 numpy 1.x의 어떤 버전이 설치될지 보장할 수 없음.

**수정 방향**:
```
numpy>=1.24,<2.0
```

---

### BUG-005: DB 스키마 미마이그레이션 — `jav_metadata` 단일 테이블 구조 잔존

**파일**: `db_schema_v2_proposal.md`, 전체 DB 레이어

**문제**: `db_schema_v2_proposal.md`에서 정규화된 관계형 스키마(v2.0)를 제안했지만, 현재 구현은 여전히 단일 `jav_metadata` 테이블 방식. 이 상태에서 배우별 필터, 다중 파일, 씬 탐색 등 고급 기능 구현 시 심각한 성능 저하 및 데이터 무결성 문제 발생.  

**구체적 위험**:
- 배우명 오타 시 동일 배우가 복수의 레코드로 분산
- CD1/CD2 같은 다중 파일 처리 불가
- 씬 탐색(스마트 점프 플레이어) 기능 구현 불가 상태

**수정 방향**: `db_schema_v2_proposal.md`의 마이그레이션 전략(하이브리드 모드 → 일괄 이전)을 실행해야 함. Alembic 등 마이그레이션 도구 도입 검토.

---

### BUG-006: `build_master_db.py`, `web/`, `master_db.js` — 폐기 선언 후 파일 잔존

**파일**: `build_master_db.py` (루트에 존재)

**문제**: `progress_report.md`에서 2026-04-25부로 폐기(deprecated) 선언했으나 저장소에 파일이 그대로 남아 있음. 커서나 AI가 이 파일을 참조하여 혼란을 일으킬 수 있음.

**수정 방향**:
- 해당 파일들을 `_deprecated/` 폴더로 이동하거나 완전 삭제
- `.gitignore`에 추가하거나 태그/브랜치로 아카이빙

---

## 🟡 구조적 문제 및 기술 부채

### ISSUE-001: 루트 디렉터리 파일 난립 — 프로젝트 구조 혼란

**현상**: 루트에 `.py`, `.txt`, `.md`, `.json`, `.ini`, `.bat` 파일 20개 이상이 혼재.  
특히 품번 텍스트 파일(`DAZD-264.txt`, `GS-1352.txt`, `MIMK-267.txt`, `VRTM-131.txt`)이 루트에 위치하는 것은 설계 의도가 불분명함.

**수정 방향**:
```
루트/
├── javstory/config/ ← app_config.py, secrets_manager (.env / keyring)
├── scripts/         ← setup.bat, start.bat (이미 scripts/ 폴더 있으나 bat 파일은 루트에)
├── docs/            ← 모든 .md 파일 (이미 docs/ 폴더 있으나 md 파일들은 루트에)
├── data/samples/    ← DAZD-264.txt 등 샘플 품번 파일
└── docs/deprecated/   ← 레거시 config.json.example 등
```

---

### ISSUE-002: `av123_scraper.py`, `missav123_scraper.py`, `avwiki.py` — 루트 레벨 스크래퍼

**파일**: `av123_scraper.py`, `missav123_scraper.py`, `avwiki.py`

**문제**: 루트에 독립 스크래퍼 파일이 존재하는데, 이미 `javstory/Harvest/` 패키지가 있음. 이 파일들이 Harvest 패키지와의 관계(독립 실행용인지, 레거시인지, 테스트용인지)가 명확하지 않음. 중복 로직이 있을 가능성이 높음.

**수정 방향**: Harvest 패키지 내로 통합하거나 `_deprecated/`로 이동. 역할 명시 주석 추가.

---

### ISSUE-003: `gui_main_v2.py` — 루트 레벨 진입점과 `gui/` 패키지 분리

**상태 (2026-05):** **해결** — 운영 진입점은 `main.py` → `gui/app.py`(QML) 단일. `gui_main_v2.py` 삭제됨. PyQt6 `gui/main_window.py`·`gui/views/*` 는 deprecated — `docs/architecture/ENTRYPOINTS.md`.

**이전 문제**: 진입점이 `gui_main_v2.py`이고 PyQt6 Fluent와 QML이 병존.

**수정 방향**: 진입점을 `main.py` 또는 `__main__.py`로 통일하고, 버전 정보는 코드 내 상수로 관리.

---

### ISSUE-004: `config.json` — 민감 정보 노출 위험

**상태 (2026-05):** **해결** — 루트 `config.json`·`javstory_player.ini` 는 코드 미참조 확인 후 제거. 샘플만 `docs/deprecated/*.example` 보관. 운영 설정은 `.env` + `javstory/config/app_config.py` + keyring.

**이전 문제**: 루트 JSON/INI가 SoT와 혼동될 수 있었음. API 키는 `keyring` / `OPENROUTER_API_KEY` 만 사용.

---

### ISSUE-005: Windows 전용 의존성 — 크로스 플랫폼 빌드 불가

**파일**: `requirements.txt`, `setup.bat`, `start.bat`

**문제**: `win32mica` (Windows Mica 효과), `.bat` 스크립트 등이 Windows에 강하게 결합되어 있음. macOS/Linux에서는 설치 자체가 실패함.

**수정 방향**:
- `requirements.txt`에 플랫폼 조건부 의존성 명시:
  ```
  win32mica; sys_platform == "win32"
  ```
- `setup.sh` (Linux/macOS용) 스크립트 추가 또는 `Makefile`로 통일

---

### ISSUE-006: `Modelfile` — Ollama 모델 설정이 루트에 방치

**파일**: `Modelfile`

**문제**: Ollama용 `Modelfile`이 루트에 있음. 어떤 모델을 사용하는지, 어떻게 적용하는지에 대한 문서나 연결 스크립트가 없음.

**수정 방향**: `scripts/` 또는 `config/ollama/`로 이동하고, README나 설정 문서에 사용법 명시.

---

## 🟢 개선 제안 (기능/아키텍처)

### SUGGEST-001: `requirements.txt` 분리

현재 단일 파일에 GUI, AI/ML, 크롤링, 개발 도구가 혼재. 환경 목적에 따라 분리 권장:

```
requirements/
├── base.txt          ← 핵심 공통 (SQLAlchemy, requests, python-dotenv 등)
├── gui.txt           ← PySide6, win32mica, darkdetect
├── ai.txt            ← torch, faster-whisper, stable-ts, openai
├── scraper.txt       ← playwright, DrissionPage, cloudscraper, curl-cffi
└── dev.txt           ← pytest, rich (이미 requirements-dev.txt 있음)
```

---

### SUGGEST-002: DB 마이그레이션 도구 도입

현재 스키마 변경을 수동으로 관리 중. SQLAlchemy가 이미 포함되어 있으므로 Alembic 도입을 권장:

```bash
pip install alembic
alembic init alembic
```

버전 관리된 마이그레이션으로 `jav_metadata` → v2 정규화 스키마 전환 추적 가능.

---

### SUGGEST-003: PySide6 버전 고정

`requirements.txt`에 `PySide6`만 선언되어 있어, 최신 버전 설치 시 `currentThreadId` 같은 API 변경으로 인한 크래시가 반복될 수 있음.

```
PySide6==6.7.x  # 또는 검증된 최신 버전
```

---

### SUGGEST-004: `crash_report.txt` → 자동화된 에러 로깅으로 전환

현재 크래시가 루트의 텍스트 파일로 기록됨. 이미 `gui/components/error_dashboard.py`가 구현되어 있으므로, 크래시 보고서를 구조화된 로그(JSON, `data/logs/`)로 자동 저장하는 방식으로 개선 권장.

---

### SUGGEST-005: `추후_기능_제안.md`, `최적화_추천_범위.md` — 이슈 트래커로 이전

아이디어성 문서들이 파일로 관리되고 있음. GitHub Issues 또는 Projects로 이전하면 우선순위 관리와 진행 상황 추적이 용이해짐.

---

## 📋 수정 우선순위 요약

| 우선순위 | ID | 제목 | 예상 작업량 |
|----------|----|------|------------|
| 🔴 즉시 | BUG-001 | `currentThreadId` 크래시 수정 | 소 (1줄 수정) |
| 🟠 높음 | BUG-002 | CUDA 의존성 충돌 정리 | 소 |
| 🟠 높음 | BUG-003 | whisper 이중 선언 제거 | 소 |
| 🟠 높음 | BUG-005 | DB v2 스키마 마이그레이션 실행 | 대 |
| 🟡 중간 | BUG-004 | numpy 버전 범위 보강 | 소 |
| 🟡 중간 | BUG-006 | 폐기 파일 정리 | 소 |
| 🟡 중간 | ISSUE-001 | 루트 디렉터리 정리 | 중 |
| ~~🟡 중간~~ | ISSUE-004 | config.json 보안 처리 | ✅ deprecated 이전 |
| 🟢 낮음 | ISSUE-002 | 루트 스크래퍼 파일 통합 | 중 |
| 🟢 낮음 | ISSUE-003 | 진입점 파일명 통일 | 소 |
| 🟢 낮음 | ISSUE-005 | 플랫폼 조건부 의존성 | 소 |
| 🟢 개선 | SUGGEST-001 | requirements 분리 | 중 |
| 🟢 개선 | SUGGEST-002 | Alembic 마이그레이션 도구 도입 | 중 |
| 🟢 개선 | SUGGEST-003 | PySide6 버전 고정 | 소 |

---

## 🗂️ 커서(Cursor)에게 전달할 추가 분석 요청 사항

아래 파일/모듈은 직접 코드를 확인하지 못했으므로 커서가 심층 분석하기를 권장합니다:

1. **`gui/models/translation_queue_model.py`** — BUG-001 수정 및 전체 스레드 안전성 검토
2. **`javstory/Harvest/`** — av123_scraper.py, missav123_scraper.py와의 코드 중복 여부 확인
3. **`javstory/utils/error_recovery.py`** — 현재 크래시(BUG-001)가 이 모듈에서 잡히지 않는 이유 분석
4. **`gui/app.py`** — `create_engine()` 함수 전체 흐름 및 초기화 순서 검토
5. **`data/db/`** — 현재 SQLite 스키마 덤프 및 v2 제안 스키마와의 차이 분석
6. **`core/scene_analysis_v2/`** — Stage 4 분석 엔진의 VRAM Safeguard 로직 구현 여부 확인
7. **`javstory/library/embeddings/`** — 벡터 스토어 구현체가 현재 GUI와 실제로 연결되어 있는지 확인
