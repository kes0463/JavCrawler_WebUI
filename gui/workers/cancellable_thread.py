"""QThread base with cooperative cancel + optional child-process kill."""

from __future__ import annotations

import subprocess

from PySide6.QtCore import QThread

from gui.utils.process_kill import kill_popen


class CancellableQThread(QThread):
    """협력적 취소 플래그 + interruption + (선택) 자식 Popen 정리."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancelled = False
        self._proc: subprocess.Popen | None = None

    def stop(self) -> None:
        self._cancelled = True
        self.requestInterruption()
        self.kill_child_processes()

    def is_cancelled(self) -> bool:
        return bool(self._cancelled or self.isInterruptionRequested())

    def kill_child_processes(self) -> bool:
        """실행 중인 자식 프로세스가 있으면 트리 종료. Returns True if kill attempted."""
        return kill_popen(self._proc, force=True)

    def _set_active_proc(self, proc: subprocess.Popen | None) -> None:
        self._proc = proc

    def _clear_active_proc(self) -> None:
        self._proc = None
