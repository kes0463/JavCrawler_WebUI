"""QThread shutdown: cooperative cancel → child kill → limited terminate."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QThread

from javstory.utils.common import log_ts

# 부트·UI 워커 기본: 협력적 대기 후 자식/ffmpeg 정리, 그래도 안 되면 제한적 terminate
DEFAULT_COOPERATIVE_MS = 8_000
DEFAULT_POST_KILL_MS = 2_000
DEFAULT_POST_TERMINATE_MS = 1_500


class StopMethod(str, Enum):
    ALREADY_STOPPED = "already_stopped"
    COOPERATIVE = "cooperative"
    CHILD_KILL = "child_kill"
    TERMINATE = "terminate"
    STILL_RUNNING = "still_running"


@dataclass(frozen=True)
class WorkerStopResult:
    stopped: bool
    method: StopMethod

    def log_label(self) -> str:
        return self.method.value


def stop_qthread(
    worker: QThread | None,
    *,
    context: str = "",
    cooperative_timeout_ms: int = DEFAULT_COOPERATIVE_MS,
    post_kill_wait_ms: int = DEFAULT_POST_KILL_MS,
    post_terminate_wait_ms: int = DEFAULT_POST_TERMINATE_MS,
    allow_terminate: bool = True,
) -> WorkerStopResult:
    """
    1) stop() + requestInterruption() — 협력적 취소 플래그
    2) wait(cooperative_timeout_ms)
    3) kill_child_processes() (있으면) + 짧은 wait
    4) allow_terminate 시 QThread.terminate() + 짧은 wait (최후 수단)
  """
    if worker is None:
        return WorkerStopResult(True, StopMethod.ALREADY_STOPPED)
    if not worker.isRunning():
        return WorkerStopResult(True, StopMethod.ALREADY_STOPPED)

    ctx = f" ({context})" if context else ""
    name = type(worker).__name__

    if hasattr(worker, "stop"):
        try:
            worker.stop()
        except Exception:
            pass
    else:
        try:
            worker.requestInterruption()
        except Exception:
            pass

    try:
        worker.requestInterruption()
    except Exception:
        pass

    if worker.wait(cooperative_timeout_ms):
        log_ts(f"[Qt] {name}{ctx} stopped cooperatively")
        return WorkerStopResult(True, StopMethod.COOPERATIVE)

    killed = False
    if hasattr(worker, "kill_child_processes"):
        try:
            killed = bool(worker.kill_child_processes())
        except Exception:
            killed = False

    if killed and worker.wait(post_kill_wait_ms):
        log_ts(f"[Qt] {name}{ctx} stopped after child process kill")
        return WorkerStopResult(True, StopMethod.CHILD_KILL)

    if allow_terminate:
        log_ts(
            f"[Qt] {name}{ctx} still running after {cooperative_timeout_ms}ms "
            f"— limited QThread.terminate()",
        )
        try:
            from javstory.utils.structured_log import log_event

            log_event(
                "WARNING",
                "qt_worker_force_terminate",
                f"{name}{ctx}",
                worker=name,
                context=context,
            )
        except Exception:
            pass
        try:
            worker.terminate()
        except Exception:
            pass
        if worker.wait(post_terminate_wait_ms):
            log_ts(f"[Qt] {name}{ctx} stopped after terminate")
            return WorkerStopResult(True, StopMethod.TERMINATE)

    log_ts(
        f"[Qt] {name}{ctx} still running "
        f"(cooperative={cooperative_timeout_ms}ms, terminate={'yes' if allow_terminate else 'no'})",
    )
    return WorkerStopResult(False, StopMethod.STILL_RUNNING)
