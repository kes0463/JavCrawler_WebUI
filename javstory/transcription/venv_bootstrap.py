"""
Windows: IDE/시스템 Python으로 실행하면 torch+cpu만 깔린 경우가 많아 CUDA가 항상 꺼진다.
프로젝트 루트에 venv\\Scripts\\python.exe 가 있으면 같은 argv로 재실행한다.
pytest -m 등 비표준 argv에서는 호출하지 말 것(진입점 스크립트에서만 호출).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def reexec_with_project_venv_if_needed() -> None:
    if sys.platform != "win32":
        return
    if getattr(sys, "frozen", False):
        return
    root = Path(__file__).resolve().parent.parent.parent
    venv_py = root / "venv" / "Scripts" / "python.exe"
    if not venv_py.is_file():
        return
    try:
        if Path(sys.executable).resolve() == venv_py.resolve():
            return
    except OSError:
        return
    os.execv(str(venv_py), [str(venv_py), *sys.argv])
