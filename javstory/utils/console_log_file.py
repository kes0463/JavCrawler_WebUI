"""웹서버 콘솔 출력(stdout/stderr)을 회전 로그 파일에도 동시에 남긴다.

이 프로젝트 로그는 대부분 ``logging`` 모듈이 아니라 ``print()``/``safe_console_print()``로
찍힌다. `logging.Handler`를 붙이는 방식으로는 이걸 못 잡으므로, ``sys.stdout``/``sys.stderr``
자체를 감싸서 콘솔에 찍히는 그대로 파일에도 남긴다.

``start_web.bat``의 ``> webapi.log`` 리다이렉션은 실행할 때마다 덮어써서 이전 실행의
로그(예: 재시작 전에 났던 에러)가 사라진다 — 여기서는 크기 기준으로 회전시켜
재시작해도 과거 로그가 유지되게 한다.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any


class _RotatingLogSink:
    def __init__(self, path: Path, max_bytes: int, backup_count: int) -> None:
        self._path = path
        self._max_bytes = max_bytes
        self._backup_count = backup_count
        self._lock = threading.Lock()
        self._fh = open(path, "a", encoding="utf-8", errors="replace")

    def write(self, s: str) -> None:
        if not s:
            return
        with self._lock:
            try:
                self._fh.write(s)
                self._fh.flush()
                if self._max_bytes > 0 and self._fh.tell() >= self._max_bytes:
                    self._rollover()
            except Exception:
                pass

    def _rollover(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass
        try:
            for i in range(self._backup_count - 1, 0, -1):
                src = self._path.with_name(f"{self._path.name}.{i}")
                dst = self._path.with_name(f"{self._path.name}.{i + 1}")
                if src.exists():
                    if dst.exists():
                        dst.unlink()
                    src.rename(dst)
            if self._backup_count > 0 and self._path.exists():
                dst1 = self._path.with_name(f"{self._path.name}.1")
                if dst1.exists():
                    dst1.unlink()
                self._path.rename(dst1)
        except Exception:
            pass
        finally:
            self._fh = open(self._path, "a", encoding="utf-8", errors="replace")


class _TeeStream:
    """원래 스트림(콘솔)에 그대로 쓰면서 동시에 공유 sink에도 미러링."""

    def __init__(self, original: Any, sink: _RotatingLogSink) -> None:  # type: ignore[name-defined]
        self._original = original
        self._sink = sink

    def write(self, s: str) -> int:
        try:
            n = self._original.write(s)
        except Exception:
            n = None
        self._sink.write(s)
        return n if isinstance(n, int) else len(s or "")

    def flush(self) -> None:
        try:
            self._original.flush()
        except Exception:
            pass

    def __getattr__(self, name: str):
        return getattr(self._original, name)


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name, "") or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def install_stdout_file_tee(default_path: Path) -> Path | None:
    """stdout/stderr를 회전 로그 파일에 미러링. 이미 설치돼 있으면 아무것도 안 함.

    ``JAVSTORY_WEBAPI_LOG_DISABLE=1``이면 설치를 건너뛴다.
    ``JAVSTORY_WEBAPI_LOG_FILE``로 경로, ``JAVSTORY_WEBAPI_LOG_MAX_MB``(기본 20),
    ``JAVSTORY_WEBAPI_LOG_BACKUPS``(기본 5)로 회전 크기·보관 개수를 덮어쓸 수 있다.
    """
    if (os.environ.get("JAVSTORY_WEBAPI_LOG_DISABLE", "") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return None
    if getattr(sys.stdout, "_javstory_tee", False):
        return None

    raw_path = (os.environ.get("JAVSTORY_WEBAPI_LOG_FILE", "") or "").strip()
    path = Path(raw_path).expanduser().resolve() if raw_path else default_path
    max_mb = _env_int("JAVSTORY_WEBAPI_LOG_MAX_MB", 20)
    backups = _env_int("JAVSTORY_WEBAPI_LOG_BACKUPS", 5)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        sink = _RotatingLogSink(path, max(1, max_mb) * 1024 * 1024, max(0, backups))
        out = _TeeStream(sys.stdout, sink)
        err = _TeeStream(sys.stderr, sink)
        out._javstory_tee = True  # type: ignore[attr-defined]
        err._javstory_tee = True  # type: ignore[attr-defined]
        sys.stdout = out  # type: ignore[assignment]
        sys.stderr = err  # type: ignore[assignment]
        return path
    except Exception:
        return None
