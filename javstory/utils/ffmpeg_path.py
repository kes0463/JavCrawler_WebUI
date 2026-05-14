"""ffmpeg / ffprobe 실행 파일 경로를 견고하게 찾아주는 공용 리졸버.

해결 우선순위:
    1. 환경변수(`JAVSTORY_FFMPEG`, `JAVSTORY_FFPROBE`)로 명시된 절대 경로
    2. 시스템 `PATH`에서 `shutil.which` 로 탐색
    3. 프로젝트 번들 바이너리(`tools/lada/_internal/bin/ffmpeg(.exe)`)
    4. Windows 환경의 알려진 포터블 설치 경로 후보
    5. 마지막 폴백: 그냥 `"ffmpeg"` / `"ffprobe"` (PATH 의존)

결과는 프로세스 수명 동안 캐시한다. 캐시가 무효임을 발견하면(`reset_cache`) 다시 탐색한다.
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
from pathlib import Path
from typing import Optional

_LOCK = threading.Lock()
_CACHE: dict[str, str] = {}
_PATH_BOOTSTRAPPED = False


def _is_executable_file(p: Path) -> bool:
    try:
        return p.is_file() and os.access(str(p), os.X_OK)
    except Exception:
        return False


def _project_root() -> Path:
    # .../JAVSTORY/javstory/utils/ffmpeg_path.py  →  .../JAVSTORY
    return Path(__file__).resolve().parents[2]


def _bundled_candidates(name: str) -> list[Path]:
    exe = f"{name}.exe" if os.name == "nt" else name
    root = _project_root()
    return [
        root / "tools" / "lada" / "_internal" / "bin" / exe,
    ]


def _windows_portable_candidates(name: str) -> list[Path]:
    """Windows 환경에서 사용자가 흔히 설치하는 포터블 ffmpeg 위치들."""
    if os.name != "nt":
        return []
    exe = f"{name}.exe"
    paths: list[Path] = []
    seen: set[str] = set()

    def _push(p: Path) -> None:
        try:
            key = str(p).lower()
            if key in seen:
                return
            seen.add(key)
            paths.append(p)
        except Exception:
            pass

    for drive in ("C:", "D:", "E:"):
        for base in (
            r"\ffmpeg\bin",
            r"\ffmpeg\latest\bin",
            r"\Program Files\ffmpeg\bin",
            r"\Util\ffmpeg\bin",
            r"\App\Util\ffmpeg\bin",
            r"\Tools\ffmpeg\bin",
        ):
            _push(Path(drive + base) / exe)
    return paths


def _resolve(name: str, env_var: str) -> str:
    override = (os.environ.get(env_var, "") or "").strip().strip('"').strip("'")
    if override:
        p = Path(override)
        if p.is_dir():
            cand = p / (f"{name}.exe" if os.name == "nt" else name)
            if _is_executable_file(cand):
                return str(cand)
        elif _is_executable_file(p):
            return str(p)

    which = shutil.which(name)
    if which:
        return which

    for cand in _bundled_candidates(name) + _windows_portable_candidates(name):
        if _is_executable_file(cand):
            return str(cand)

    return name


def get_ffmpeg() -> str:
    """`ffmpeg` 실행 파일 경로(또는 PATH 의존 마지막 폴백 문자열)를 반환."""
    with _LOCK:
        cached = _CACHE.get("ffmpeg")
        if cached:
            return cached
        resolved = _resolve("ffmpeg", "JAVSTORY_FFMPEG")
        _CACHE["ffmpeg"] = resolved
        return resolved


def get_ffprobe() -> str:
    """`ffprobe` 실행 파일 경로(또는 PATH 의존 마지막 폴백 문자열)를 반환."""
    with _LOCK:
        cached = _CACHE.get("ffprobe")
        if cached:
            return cached
        resolved = _resolve("ffprobe", "JAVSTORY_FFPROBE")
        _CACHE["ffprobe"] = resolved
        return resolved


def reset_cache() -> None:
    """캐시를 초기화한다(환경변수 변경 등 런타임 변동 대응용)."""
    with _LOCK:
        _CACHE.clear()


def bootstrap_path_env() -> None:
    """PATH 의존 ffmpeg 호출을 위해 해석된 실행 파일 디렉터리를 PATH 앞쪽에 추가한다."""
    global _PATH_BOOTSTRAPPED
    with _LOCK:
        if _PATH_BOOTSTRAPPED:
            return

    try:
        dirs: list[str] = []
        seen: set[str] = set()
        for exe in (get_ffmpeg(), get_ffprobe()):
            p = Path(exe)
            if not p.is_absolute() or not _is_executable_file(p):
                continue
            parent = str(p.parent)
            key = os.path.normcase(os.path.normpath(parent))
            if key in seen:
                continue
            seen.add(key)
            dirs.append(parent)

        current_parts = [part for part in os.environ.get("PATH", "").split(os.pathsep) if part]
        current_keys = {os.path.normcase(os.path.normpath(part)) for part in current_parts}
        prepend = [
            part
            for part in dirs
            if os.path.normcase(os.path.normpath(part)) not in current_keys
        ]
        if prepend:
            os.environ["PATH"] = os.pathsep.join(prepend + current_parts)
    except Exception as exc:
        print(f"[ffmpeg_path] PATH bootstrap failed: {exc}", file=sys.stderr)
    finally:
        with _LOCK:
            _PATH_BOOTSTRAPPED = True


def describe() -> dict[str, str]:
    """현재 해석된 경로를 반환(로깅/디버깅용)."""
    return {"ffmpeg": get_ffmpeg(), "ffprobe": get_ffprobe()}
