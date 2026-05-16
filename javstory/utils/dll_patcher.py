"""
Windows: PyTorch/CUDA 휠 DLL을 로드하기 전에 `os.add_dll_directory` + PATH 선행 주입.
GUI(`main.py`) 및 CUDA 의존 모듈이 Qt 등보다 먼저 로드되기 전에 호출한다.
"""
from __future__ import annotations

import os
import site
import sys

_PATCHED = False


def apply_dll_patch() -> None:
    global _PATCHED
    if _PATCHED:
        return
    if sys.platform != "win32":
        return

    print("[DLL-Patcher] Initializing NVIDIA CUDA DLL patch phase (v3.0)...")

    current_site_packages = site.getsitepackages()
    search_paths: list[str] = []
    executable_dir = os.path.dirname(sys.executable)
    potential_venv_sp = os.path.join(executable_dir, "Lib", "site-packages")
    if os.path.exists(potential_venv_sp):
        search_paths.append(potential_venv_sp)
    search_paths.extend(current_site_packages)

    unique_paths: list[str] = []
    for p in search_paths:
        if p not in unique_paths and os.path.exists(p):
            unique_paths.append(p)

    added_count = 0
    injected_dirs: set[str] = set()

    for sp in unique_paths:
        nvidia_base = os.path.join(sp, "nvidia")
        if not os.path.exists(nvidia_base):
            continue

        print(f"[DLL-Patcher] Scanning NVIDIA libraries in: {sp}")
        try:
            for sub in sorted(os.listdir(nvidia_base)):
                sub_path = os.path.join(nvidia_base, sub)
                if os.path.isdir(sub_path):
                    dll_path = os.path.join(sub_path, "bin")
                    if os.path.exists(dll_path) and dll_path not in injected_dirs:
                        print(f"[DLL-Patcher]   -> {sub} [Injected]")
                        try:
                            os.add_dll_directory(dll_path)
                            os.environ["PATH"] = dll_path + os.pathsep + os.environ.get("PATH", "")
                            injected_dirs.add(dll_path)
                            added_count += 1
                        except Exception as de:
                            print(f"[DLL-Patcher]      Failed to inject {sub}: {de}")
        except Exception as le:
            print(f"[DLL-Patcher]   Error scanning {nvidia_base}: {le}")

    if added_count > 0:
        print(f"[DLL-Patcher] Successfully patched {added_count} NVIDIA DLL paths.")
        _PATCHED = True
    else:
        print("[DLL-Patcher] No local NVIDIA DLL paths found. CUDA-dependent wheels may fall back to CPU.")
