"""PySide6 스레드 유틸 — currentThreadId 회귀 방지."""

from __future__ import annotations

import sys

import pytest

pytest.importorskip("PySide6")


def test_translation_queue_controller_init_no_crash():
    from PySide6.QtWidgets import QApplication
    from gui.models.translation_queue_model import TranslationQueueController

    app = QApplication.instance() or QApplication(sys.argv)
    ctrl = TranslationQueueController()
    assert ctrl.count == 0


def test_qthread_instance_has_no_current_thread_id():
    from PySide6.QtCore import QThread

    t = QThread()
    assert not hasattr(t, "currentThreadId")


def test_is_on_app_main_thread():
    from PySide6.QtWidgets import QApplication
    from gui.utils.qt_thread_util import is_on_app_main_thread

    app = QApplication.instance() or QApplication(sys.argv)
    assert is_on_app_main_thread(app) is True
