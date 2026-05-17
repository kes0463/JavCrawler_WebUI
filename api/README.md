# api/ — 동결 (Non-production)

**ADR**: [`docs/adr/0001-ui-stack-qml-only.md`](../docs/adr/0001-ui-stack-qml-only.md)

`frontend/` 연동용 FastAPI입니다. **운영 진입점이 아닙니다.**

## 기본 동작 (동결)

`uvicorn api.main:app` 실행 시:

| 경로 | 설명 |
|------|------|
| `GET /health` | 서버 생존 + `api_mode: frozen` |
| `GET /api/status` | 동결 안내 JSON |
| `/api/harvest/*` | **410 Gone** (명시적 거부) |
| `/api/library/*` | **미마운트** (404) |

Harvest는 `api/routes/harvest_frozen.py` 스텁만 연결됩니다.

## 레거시 API (지원 없음, 명시적 opt-in)

```bat
set JAVSTORY_ALLOW_FROZEN_API=1
uvicorn api.main:app --host 127.0.0.1 --port 8765
```

이때만 `library` + `harvest` 라이브 라우트가 마운트됩니다. 버그 수정·P3 연동 대상이 **아닙니다**.

Electron(`frontend/electron/main.cjs`)도 동일 env 없으면 API 서버를 **띄우지 않습니다**.

## 운영

| 항목 | 경로 |
|------|------|
| 앱 | [`main.py`](../main.py) → QML |
| 삭제 검토 | 동결 6~12개월 후 |

CI·`start.bat`·릴리스에 포함되지 않습니다.
