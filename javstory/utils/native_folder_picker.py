"""Native folder picker for localhost WebUI (webapi runs on the same machine)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def pick_folders(*, title: str = "폴더 선택 (Ctrl+클릭 다중 선택)", _in_subprocess: bool = False) -> list[str]:
    """Return absolute folder paths chosen by the user, or [] if cancelled."""
    if sys.platform == "win32" and not _in_subprocess:
        paths = _pick_folders_via_subprocess(title=title)
        if paths is not None:
            return paths

    if sys.platform == "win32":
        try:
            paths = _pick_folders_win32(title=title)
            if paths:
                return paths
        except Exception:
            pass

        try:
            paths = _pick_folders_pyside6(title=title)
            if paths:
                return paths
        except Exception:
            pass

    paths = _pick_folders_tk_panel(title=title)
    return paths


def _pick_folders_via_subprocess(title: str) -> list[str] | None:
    """Run picker in a fresh process (avoids uvicorn thread-pool COM issues)."""
    try:
        env = {
            **os.environ,
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
        result = subprocess.run(
            [sys.executable, "-m", "javstory.utils.native_folder_picker", title, "--isolated"],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=600,
        )
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout.strip())
            if isinstance(data, list):
                return [str(p) for p in data]
    except Exception:
        pass
    return None


def _pick_folders_tk_panel(*, title: str) -> list[str]:
    """Single window: add/remove multiple folders before confirming."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    paths: list[str] = []
    result: list[str] = []

    root = tk.Tk()
    root.title(title)
    root.geometry("560x380")
    root.attributes("-topmost", True)

    tk.Label(
        root,
        text="「폴더 추가」로 여러 폴더를 넣은 뒤 「확인」을 누르세요.",
        wraplength=520,
        justify="left",
    ).pack(anchor="w", padx=12, pady=(12, 6))

    frame = ttk.Frame(root)
    frame.pack(fill="both", expand=True, padx=12, pady=6)

    scrollbar = ttk.Scrollbar(frame)
    scrollbar.pack(side="right", fill="y")

    listbox = tk.Listbox(frame, yscrollcommand=scrollbar.set, selectmode=tk.EXTENDED)
    listbox.pack(side="left", fill="both", expand=True)
    scrollbar.config(command=listbox.yview)

    btn_row = ttk.Frame(root)
    btn_row.pack(fill="x", padx=12, pady=6)

    def refresh_list() -> None:
        listbox.delete(0, tk.END)
        for p in paths:
            listbox.insert(tk.END, p)

    def add_folder() -> None:
        path = filedialog.askdirectory(title="폴더 선택", mustexist=True, parent=root)
        if not path:
            return
        resolved = str(Path(path).resolve())
        if resolved not in paths:
            paths.append(resolved)
            refresh_list()

    def remove_selected() -> None:
        sel = list(listbox.curselection())
        if not sel:
            return
        for idx in reversed(sel):
            if 0 <= idx < len(paths):
                paths.pop(idx)
        refresh_list()

    def confirm() -> None:
        if not paths:
            if not messagebox.askyesno("확인", "선택된 폴더가 없습니다. 그대로 닫을까요?", parent=root):
                return
        result.extend(paths)
        root.destroy()

    def cancel() -> None:
        root.destroy()

    ttk.Button(btn_row, text="폴더 추가", command=add_folder).pack(side="left")
    ttk.Button(btn_row, text="선택 제거", command=remove_selected).pack(side="left", padx=6)

    action_row = ttk.Frame(root)
    action_row.pack(fill="x", padx=12, pady=(0, 12))
    ttk.Button(action_row, text="확인", command=confirm).pack(side="right")
    ttk.Button(action_row, text="취소", command=cancel).pack(side="right", padx=6)

    root.protocol("WM_DELETE_WINDOW", cancel)
    root.mainloop()
    return result


def _pick_folders_pyside6(*, title: str) -> list[str]:
    """Qt native folder dialog (Windows IFileOpenDialog via Qt)."""
    import pythoncom
    from PySide6.QtWidgets import QApplication, QFileDialog

    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    app = QApplication.instance() or QApplication([])
    try:
        dialog = QFileDialog()
        dialog.setWindowTitle(title)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, False)
        if dialog.exec() != QFileDialog.DialogCode.Accepted:
            return []
        selected = dialog.selectedFiles()
        return [str(Path(p).resolve()) for p in selected if p]
    finally:
        pythoncom.CoUninitialize()


def _pick_folders_win32(*, title: str) -> list[str]:
    import ctypes
    import ctypes.wintypes as wintypes
    import pythoncom
    from ctypes import HRESULT, POINTER, byref, c_long, c_void_p

    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    ole32 = ctypes.OleDLL("ole32")

    try:
        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", wintypes.BYTE * 8),
            ]

        CLSID_FileOpenDialog = GUID(
            0xDC1C5A9C,
            0xE88A,
            0x4DDE,
            (0xB5, 0xA1, 0x43, 0x8F, 0x65, 0x41, 0xD7, 0x3C),
        )
        IID_IFileOpenDialog = GUID(
            0xD57C7288,
            0xD4AD,
            0x4768,
            (0xBE, 0x02, 0x9D, 0x96, 0x95, 0x32, 0x53, 0x2C),
        )

        FOS_PICKFOLDERS = 0x20
        FOS_ALLOWMULTISELECT = 0x200
        FOS_FORCEFILESYSTEM = 0x40
        FOS_PATHMUSTEXIST = 0x800
        FOS_FILEMUSTEXIST = 0x1000
        FOS_NOCHANGEDIR = 0x8
        FOS_ALLNONSTORAGEITEMS = 0x80
        SIGDN_FILESYSPATH = 0x80058000
        HRESULT_CANCELLED = 0x800704C7

        ole32.CoCreateInstance.argtypes = [
            POINTER(GUID), c_void_p, wintypes.DWORD, POINTER(GUID), POINTER(c_void_p),
        ]
        ole32.CoCreateInstance.restype = c_long

        dialog = c_void_p()
        hr = ole32.CoCreateInstance(
            byref(CLSID_FileOpenDialog),
            None,
            1,
            byref(IID_IFileOpenDialog),
            byref(dialog),
        )
        if hr != 0 or not dialog.value:
            raise OSError(hr, "CoCreateInstance failed")

        vtbl = ctypes.cast(
            ctypes.cast(dialog, POINTER(c_void_p))[0],
            POINTER(c_void_p),
        )

        SetOptions = ctypes.WINFUNCTYPE(HRESULT, c_void_p, ctypes.c_uint)(vtbl[9])
        GetOptions = ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(ctypes.c_uint))(vtbl[10])
        SetTitle = ctypes.WINFUNCTYPE(HRESULT, c_void_p, wintypes.LPCWSTR)(vtbl[17])
        Show = ctypes.WINFUNCTYPE(HRESULT, c_void_p, wintypes.HWND)(vtbl[3])
        GetResults = ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(c_void_p))(vtbl[26])
        Release = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)(vtbl[2])

        opts = ctypes.c_uint()
        GetOptions(dialog, byref(opts))
        opts.value |= (
            FOS_PICKFOLDERS
            | FOS_ALLOWMULTISELECT
            | FOS_FORCEFILESYSTEM
            | FOS_PATHMUSTEXIST
            | FOS_NOCHANGEDIR
        )
        opts.value &= ~(FOS_FILEMUSTEXIST | FOS_ALLNONSTORAGEITEMS)
        hr = SetOptions(dialog, opts.value)
        if hr != 0:
            Release(dialog)
            return []

        SetTitle(dialog, title)
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        hr = Show(dialog, hwnd)
        if hr == HRESULT_CANCELLED or hr < 0:
            Release(dialog)
            return []

        items = c_void_p()
        hr = GetResults(dialog, byref(items))
        Release(dialog)
        if hr != 0 or not items.value:
            return []

        arr_vtbl = ctypes.cast(
            ctypes.cast(items, POINTER(c_void_p))[0],
            POINTER(c_void_p),
        )
        GetCount = ctypes.WINFUNCTYPE(HRESULT, c_void_p, POINTER(ctypes.c_uint))(arr_vtbl[7])
        GetItemAt = ctypes.WINFUNCTYPE(HRESULT, c_void_p, ctypes.c_uint, POINTER(c_void_p))(arr_vtbl[8])
        arr_release = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)(arr_vtbl[2])

        count = ctypes.c_uint()
        GetCount(items, byref(count))

        out: list[str] = []
        for i in range(count.value):
            item = c_void_p()
            if GetItemAt(items, i, byref(item)) != 0 or not item.value:
                continue
            item_vtbl = ctypes.cast(
                ctypes.cast(item, POINTER(c_void_p))[0],
                POINTER(c_void_p),
            )
            GetDisplayName = ctypes.WINFUNCTYPE(
                HRESULT, c_void_p, ctypes.c_uint, POINTER(wintypes.LPWSTR),
            )(item_vtbl[5])
            item_release = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)(item_vtbl[2])

            psz = wintypes.LPWSTR()
            if GetDisplayName(item, SIGDN_FILESYSPATH, byref(psz)) == 0 and psz.value:
                out.append(str(Path(psz.value).resolve()))
                ole32.CoTaskMemFree(psz)
            item_release(item)

        arr_release(items)
        return out
    finally:
        pythoncom.CoUninitialize()


def main() -> None:
    """CLI for Electron/subprocess: prints JSON array of paths to stdout."""
    title = "Harvest 큐에 추가할 폴더 선택 (Ctrl+클릭 다중 선택)"
    isolated = False
    args = sys.argv[1:]
    if args and args[-1] == "--isolated":
        isolated = True
        args = args[:-1]
    if args:
        title = args[0]
    paths = pick_folders(title=title, _in_subprocess=isolated)
    # Windows 콘솔(cp949)과 Electron(utf-8) 불일치로 한글 경로가 깨지지 않게
    # stdout 버퍼에 UTF-8 바이트를 직접 기록한다.
    payload = json.dumps(paths, ensure_ascii=False) + "\n"
    try:
        sys.stdout.buffer.write(payload.encode("utf-8"))
        sys.stdout.buffer.flush()
    except Exception:
        sys.stdout.write(payload)
        sys.stdout.flush()


if __name__ == "__main__":
    main()
