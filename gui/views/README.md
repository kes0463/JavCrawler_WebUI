# `gui/views/` — Deprecated (PyQt6 Fluent)

**이 디렉터리는 운영 UI가 아닙니다.**

| 레거시 (여기) | 운영 (QML) |
|---------------|------------|
| `dashboard.py` | `gui/qml/views/DashboardView.qml` |
| `harvest.py` | `gui/qml/views/HarvestView.qml` |
| `processing.py` | `gui/qml/views/ProcessingView.qml` |
| `library.py` | `gui/qml/views/LibraryView.qml` + `LibraryDetail.qml` |
| `settings.py` | `gui/qml/views/SettingsView.qml` |

- 진입: [`gui/main_window.py`](../main_window.py) — [`main.py`](../../main.py)에서 **사용하지 않음**
- 신규 기능·버그 수정은 **QML + `gui/models/`** 에만 적용
- 레거시 코드는 참고·포팅 소스로만 두며, 삭제는 별도 정리 PR에서 진행

전체 진입점: [`docs/architecture/ENTRYPOINTS.md`](../../docs/architecture/ENTRYPOINTS.md)
