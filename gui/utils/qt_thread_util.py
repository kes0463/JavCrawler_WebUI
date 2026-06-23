"""Qt 스레드 판별 — PySide6에는 QThread 인스턴스.currentThreadId()가 없음."""

from __future__ import annotations

import threading

from PySide6.QtCore import QCoreApplication, QThread


def python_thread_ident() -> int:
    return threading.get_ident()


def is_on_app_main_thread(app: QCoreApplication | None = None) -> bool:
    """현재 코드가 GUI(앱) 스레드에서 실행 중인지."""
    application = app or QCoreApplication.instance()
    if application is None:
        return True
    return QThread.currentThread() is application.thread()
