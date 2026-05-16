# PyQt6 Fluent 스택 (Deprecated)

JAVSTORY 데스크톱 **운영 UI = PySide6 + QML** (`main.py` → `gui/app.py`).

아래는 **qfluentwidgets / PyQt6** 기반 이전 GUI입니다. `main.py` 부트 경로에 포함되지 않습니다.

| 모듈 | 역할 |
|------|------|
| `gui/main_window.py` | Fluent `JAVStoryMainWindow` |
| `gui/views/*.py` | 5대 위젯 뷰 |
| `gui/theme_manager.py` | Fluent 테마 |
| `gui/components/*` (PyQt6 import) | 큐·카드·다이얼로그 등 위젯 전용 |

**PySide6를 쓰는** `gui/models/`, `gui/workers/`, `gui/app.py`, `gui/qml/` 은 운영 코드입니다.

→ [`docs/architecture/ENTRYPOINTS.md`](../docs/architecture/ENTRYPOINTS.md)
