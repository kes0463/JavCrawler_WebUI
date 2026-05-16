"""Qt 스레드 판별 — PySide6에는 QThread 인스턴스.currentThreadId()가 없음."""

from __future__ import annotations

import threading

from PySide6.QtCore import QCoreApplication, QThread


def python_thread_ident() -> int:
    """로깅·디버그용 (stdlib, Qt 버전 무관)."""
    return threading.get_ident()


def is_on_app_main_thread(app: QCoreApplication | None = None) -> bool:
    """현재 코드가 GUI(앱) 스레드에서 실행 중인지."""
    application = app or QCoreApplication.instance()
    if application is None:
        return True
    return QThread.currentThread() is application.thread()


def thread_debug_fields(obj=None) -> dict[str, int | bool]:
    """NDJSON 등 디버그 로그용 — currentThreadId 사용 금지."""
    app = QCoreApplication.instance()
    on_main = is_on_app_main_thread(app)
    fields: dict[str, int | bool] = {
        "py_thread": python_thread_ident(),
        "on_main_qt_thread": on_main,
    }
    if obj is not None:
        try:
            fields["obj_on_main"] = obj.thread() is app.thread() if app else on_main
        except Exception:
            fields["obj_on_main"] = on_main
    return fields
