"""Ensure local Ollama (`ollama serve`) is available for embeddings / local LLM."""

from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

_OLLAMA_SERVE_PROC: subprocess.Popen | None = None
_OLLAMA_SERVE_LOG_PATH: Path | None = None
_START_LOCK = threading.Lock()


def ollama_base_url() -> str:
    try:
        from javstory.config.app_config import OLLAMA_BASE_URL

        return (os.environ.get("JAVSTORY_OLLAMA_URL", "") or "").strip() or OLLAMA_BASE_URL
    except Exception:
        return (os.environ.get("JAVSTORY_OLLAMA_URL", "") or "").strip() or "http://localhost:11434"


def should_auto_start_ollama() -> bool:
    raw = (os.environ.get("JAVSTORY_AUTO_OLLAMA_SERVE", "") or "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    try:
        from javstory.library.embeddings.pipeline import embeddings_enabled_from_env

        if embeddings_enabled_from_env():
            return True
    except Exception:
        pass
    try:
        from javstory.config.app_config import resolve_translation_llm_tier

        tier = resolve_translation_llm_tier()
        return str(tier.get("provider") or "").lower() == "ollama"
    except Exception:
        return False


def ollama_is_responding(base_url: str | None = None, *, timeout_sec: float = 0.6) -> bool:
    try:
        import httpx

        url = (base_url or ollama_base_url()).rstrip("/") + "/api/version"
        r = httpx.get(url, timeout=httpx.Timeout(timeout_sec, connect=min(0.4, timeout_sec)))
        return 200 <= r.status_code < 500
    except Exception:
        return False


def find_ollama_exe() -> str | None:
    exe = shutil.which("ollama")
    if exe:
        return exe
    try:
        if sys.platform == "win32":
            local = os.environ.get("LOCALAPPDATA", "") or ""
            if local:
                p = Path(local) / "Programs" / "Ollama" / "ollama.exe"
                if p.is_file():
                    return str(p)
    except Exception:
        pass
    return None


def _ollama_log_path() -> Path | None:
    try:
        base = (os.environ.get("LOCALAPPDATA", "") or "").strip()
        if not base:
            return None
        d = Path(base) / "JAVSTORY" / "logs"
        d.mkdir(parents=True, exist_ok=True)
        return d / "ollama-serve.log"
    except Exception:
        return None


def _cleanup_ollama_child() -> None:
    global _OLLAMA_SERVE_PROC
    p = _OLLAMA_SERVE_PROC
    _OLLAMA_SERVE_PROC = None
    if not p:
        return
    try:
        if p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass
            try:
                p.wait(timeout=2.0)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
    except Exception:
        pass


def ensure_ollama_serve(
    *,
    wait_sec: float = 3.0,
    force: bool = False,
) -> bool:
    """
    Make sure Ollama responds on the configured URL.

    Returns True if reachable (already up, or started and became ready).
    When force=False, respects should_auto_start_ollama().
    """
    global _OLLAMA_SERVE_PROC, _OLLAMA_SERVE_LOG_PATH

    base = ollama_base_url()
    if ollama_is_responding(base):
        return True
    if not force and not should_auto_start_ollama():
        return False

    with _START_LOCK:
        if ollama_is_responding(base):
            return True

        if _OLLAMA_SERVE_PROC is None or _OLLAMA_SERVE_PROC.poll() is not None:
            exe = find_ollama_exe()
            if not exe:
                return False
            try:
                _OLLAMA_SERVE_LOG_PATH = _ollama_log_path()
                stdout = stderr = subprocess.DEVNULL
                if _OLLAMA_SERVE_LOG_PATH:
                    try:
                        logf = open(_OLLAMA_SERVE_LOG_PATH, "a", encoding="utf-8")  # noqa: SIM115
                        stdout = logf
                        stderr = logf
                    except Exception:
                        stdout = stderr = subprocess.DEVNULL
                _OLLAMA_SERVE_PROC = subprocess.Popen(
                    [exe, "serve"],
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                )
                atexit.register(_cleanup_ollama_child)
            except Exception:
                _OLLAMA_SERVE_PROC = None
                return False

        deadline = time.monotonic() + max(0.0, float(wait_sec))
        while time.monotonic() < deadline:
            if ollama_is_responding(base, timeout_sec=0.5):
                return True
            time.sleep(0.2)
        return ollama_is_responding(base, timeout_sec=0.8)
