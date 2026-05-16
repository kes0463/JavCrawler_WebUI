# 저장소 레이아웃

## 루트에 두는 파일 (의도)

| 종류 | 예 |
|------|-----|
| 진입·설치 | `main.py`, `start.bat`, `setup.bat` |
| 의존성 | `requirements.txt`, `requirements-torch.txt`, `requirements-ci.txt`, `requirements-dev.txt` |
| 문서(핵심) | `INSTALL.md`, `TESTING.md`, `WORKFLOW_PIPELINES.md` |
| DB 마이그레이션 | `alembic.ini` |

## 루트에 있으면 안 되는 것 (로컬·gitignore)

`.gitignore`로 추적 제외:

- `*.txt` — 품번 샘플·디버그 덤프 (`DAZD-264.txt` 등)
- `*.log` — `whisper_debug.log`, `debug-*.log`, `out.log`
- `*.db` — `jav_database.db` (SoT: `data/db/jav_database.db`)

정리: 루트에 보이는 txt/log/db는 **삭제해도 되는 로컬 산출물**이거나 `data/`로 옮길 DB입니다.

## 코드 위치

| 영역 | 경로 |
|------|------|
| 운영 UI | `gui/qml/`, `gui/models/` |
| 도메인 | `javstory/` |
| 스크래퍼 | `javstory/harvest/scrapers/` (루트 `.py` 스크래퍼 아님) |
| 실험 UI (동결) | `frontend/`, `api/` |
| 설계·ADR | `docs/` |

상세 진입점: [architecture/ENTRYPOINTS.md](architecture/ENTRYPOINTS.md)
