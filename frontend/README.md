# frontend/ — 동결 (Non-production)

**ADR**: [`docs/adr/0001-ui-stack-qml-only.md`](../docs/adr/0001-ui-stack-qml-only.md)

React + Vite + Electron 실험 UI입니다. **운영 앱이 아닙니다.**

| 항목 | 내용 |
|------|------|
| 운영 UI | [`main.py`](../main.py) → PySide6 + [`gui/qml/`](../gui/qml/) |
| 본 디렉터리 | 2026-05-16부터 **동결** — 신규 기능·버그 수정 대상 아님 |
| 삭제 검토 | 동결 6~12개월 후 (ADR 검토 예정일 참고) |

로컬로 띄우려면 (개발자 참고용, 지원 없음):

```bash
cd frontend && npm install && npm run dev
# 별도 터미널: uvicorn api.main:app --reload
```
