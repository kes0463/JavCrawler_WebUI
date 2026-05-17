"""Subprocess / process-tree termination (ffmpeg, LADA, etc.)."""

from __future__ import annotations

import os
import subprocess


def kill_process_tree(pid: int, *, force: bool = True) -> bool:
    """
    종료 중인 워커의 자식 프로세스 트리를 정리한다.
    Windows: taskkill /T. Unix: terminate → kill.
    """
    if pid is None or int(pid) <= 0:
        return False
    pid = int(pid)
    try:
        if os.name == "nt":
            args = ["taskkill", "/T", "/PID", str(pid)]
            if force:
                args.insert(1, "/F")
            subprocess.run(
                args,
                creationflags=subprocess.CREATE_NO_WINDOW,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        import signal

        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                return False
        return True
    except Exception:
        return False


def kill_popen(proc: subprocess.Popen | None, *, force: bool = True) -> bool:
    if proc is None:
        return False
    try:
        if proc.poll() is not None:
            return False
        return kill_process_tree(proc.pid, force=force)
    except Exception:
        return False
