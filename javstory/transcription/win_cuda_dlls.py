"""
Windows: PyTorch(CUDA) 로드 전에 nvidia-* 휠의 bin을 add_dll_directory로 등록해야
torch.cuda.is_available()가 True가 되는 경우가 많다.

Transcription.engine 등이 stable_ts_pipeline보다 먼저 `import torch`를 하면
등록이 늦어져 CPU로만 인식될 수 있으므로, 이 모듈만 engine 최상단에서 선행 import한다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def add_windows_cuda_dll_paths() -> None:
    if sys.platform != "win32":
        return
    root = Path(__file__).resolve().parent.parent.parent
    venv_base = root / "venv"
    if not venv_base.is_dir():
        return
    site = venv_base / "Lib" / "site-packages"
    nvidia = site / "nvidia"
    if not nvidia.is_dir():
        return
    for sub in sorted(nvidia.iterdir()):
        if not sub.is_dir():
            continue
        dll_dir = sub / "bin"
        if dll_dir.is_dir():
            try:
                os.add_dll_directory(str(dll_dir))
            except (OSError, AttributeError):
                pass
