# ADR 0002: WebUI 2차 진입점 (React + webapi)

- **상태**: Accepted
- **날짜**: 2026-06-27
- **관련**: [ADR 0001 — QML 단일 스택](0001-ui-stack-qml-only.md)

## 맥락

브라우저 기반 WebUI가 제품 요구로 확정되었다. ADR 0001은 동결된 `api/`/`frontend` 실험 스택의 확장을 금지하고, 필요 시 `javstory` 위 **새 HTTP API** 설계를 권장했다.

## 결정

1. **운영 UI는 여전히 QML** ([`main.py`](../../main.py)) — 대체하지 않는다.
2. **WebUI = 2차 공식 진입점**
   - HTTP: [`webapi/`](../../webapi/) (FastAPI)
   - UI: [`frontend/`](../../frontend/) (React + TypeScript + Tailwind + Vite)
3. **동결 `api/`는 확장하지 않는다** — 참고·삭제 검토 대상 유지.
4. **도메인 로직**은 [`javstory/services/`](../../javstory/services/)에 두고 webapi 라우트는 얇게 유지한다.

## MVP 범위

- Library, Harvest (WebSocket), Dashboard (실 API)
- Processing / Insight / Mosaic / Settings: UI 셸만 (mock 또는 준비 중)

## 실행

```bat
start_web.bat
```

또는:

```bat
uvicorn webapi.main:app --host 127.0.0.1 --port 8765
cd frontend && npm run dev
```

## 결과

- QML과 WebUI 병행. 신규 HTTP 기능은 `webapi/`에만 추가.
- CI: `requirements-web.txt` + webapi import smoke.
