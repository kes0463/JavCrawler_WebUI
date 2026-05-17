"""qt_worker.stop_qthread — cooperative cancel, optional limited terminate."""

from __future__ import annotations

import sys
import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QThread
from gui.utils.qt_worker import StopMethod, stop_qthread


class _CooperativeWorker(QThread):
    def __init__(self):
        super().__init__()
        self._stop = False

    def stop(self) -> None:
        self._stop = True
        self.requestInterruption()

    def run(self) -> None:
        while not self._stop and not self.isInterruptionRequested():
            time.sleep(0.05)


class _StubbornWorker(QThread):
    def run(self) -> None:
        while True:
            time.sleep(0.05)


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_stop_qthread_cooperative(qapp):
    w = _CooperativeWorker()
    w.start()
    result = stop_qthread(w, cooperative_timeout_ms=3000)
    assert result.stopped is True
    assert result.method == StopMethod.COOPERATIVE
    assert not w.isRunning()


def test_stop_qthread_limited_terminate(qapp):
    w = _StubbornWorker()
    w.start()
    result = stop_qthread(
        w,
        cooperative_timeout_ms=200,
        post_kill_wait_ms=100,
        post_terminate_wait_ms=500,
        allow_terminate=True,
    )
    assert result.stopped is True
    assert result.method == StopMethod.TERMINATE
    assert not w.isRunning()
