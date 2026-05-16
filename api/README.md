# api/ — 동결 (Non-production)

**ADR**: [`docs/adr/0001-ui-stack-qml-only.md`](../docs/adr/0001-ui-stack-qml-only.md)

`frontend/` 연동용 FastAPI 서버입니다. **운영 진입점이 아닙니다.**

| 항목 | 내용 |
|------|------|
| 운영 UI | [`main.py`](../main.py) → `javstory`·`gui/models` 직접 호출 |
| 본 디렉터리 | 2026-05-16부터 **동결** — 신규 라우트·P3 읽기 연동·버그 수정 대상 아님 |
| 삭제 검토 | 동결 6~12개월 후 |

로컬 실행 (참고용):

```bash
uvicorn api.main:app --reload
```

CI·`start.bat`·릴리스에 포함되지 않습니다.
