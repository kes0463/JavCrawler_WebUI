"""Native folder picker for localhost WebUI (webapi runs on the same machine)."""
from __future__ import annotations

import sys
from pathlib import Path


def pick_folders(*, title: str = "폴더 선택 (다중 선택 가능)") -> list[str]:
    """Return absolute folder paths chosen by the user, or [] if cancelled."""
    if sys.platform == "win32":
        try:
            paths = _pick_folders_win32(title=title)
            if paths:
                return paths
        except Exception:
            pass
    return _pick_folders_tkinter(title=title)


def _pick_folders_tkinter(*, title: str) -> list[str]:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        path = filedialog.askdirectory(title=title, mustexist=True, parent=root)
    finally:
        root.destroy()
    if not path:
        return []
    return [str(Path(path).resolve())]


def _pick_folders_win32(*, title: str) -> list[str]:
    import ctypes
    import ctypes.wintypes as wintypes

    ole32 = ctypes.OleDLL("ole32")
    shell32 = ctypes.OleDLL("shell32")

    ole32.CoInitialize(None)
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
        IID_IShellItem = GUID(
            0x43826D1E,
            0xE718,
            0x42EE,
            (0xBE, 0x55, 0xA1, 0xE2, 0x61, 0xC3, 0x7B, 0xFE),
        )
        IID_IShellItemArray = GUID(
            0xB63EA76D,
            0x1F85,
            0x456F,
            (0xA6, 0xC4, 0x0C, 0xBE, 0xD6, 0x89, 0x66, 0x71),
        )

        FOS_PICKFOLDERS = 0x20
        FOS_ALLOWMULTISELECT = 0x200
        FOS_FORCEFILESYSTEM = 0x40
        FOS_PATHMUSTEXIST = 0x800
        SIGDN_FILESYSPATH = 0x80058000

        dialog = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(
            ctypes.byref(CLSID_FileOpenDialog),
            None,
            1,  # CLSCTX_INPROC_SERVER
            ctypes.byref(IID_IFileOpenDialog),
            ctypes.byref(dialog),
        )
        if hr != 0 or not dialog.value:
            return []

        vtbl = ctypes.cast(
            ctypes.cast(dialog, ctypes.POINTER(ctypes.c_void_p))[0],
            ctypes.POINTER(ctypes.c_void_p),
        )

        SetOptions = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.c_uint)(vtbl[9])
        GetOptions = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint))(vtbl[10])
        SetTitle = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, wintypes.LPCWSTR)(vtbl[17])
        Show = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, wintypes.HWND)(vtbl[3])
        GetResults = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(vtbl[27])
        Release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])

        opts = ctypes.c_uint()
        GetOptions(dialog, ctypes.byref(opts))
        opts.value |= (
            FOS_PICKFOLDERS
            | FOS_ALLOWMULTISELECT
            | FOS_FORCEFILESYSTEM
            | FOS_PATHMUSTEXIST
        )
        SetOptions(dialog, opts.value)
        SetTitle(dialog, title)

        hr = Show(dialog, None)
        if hr != 0:  # cancelled
            Release(dialog)
            return []

        items = ctypes.c_void_p()
        hr = GetResults(dialog, ctypes.byref(items))
        Release(dialog)
        if hr != 0 or not items.value:
            return []

        arr_vtbl = ctypes.cast(
            ctypes.cast(items, ctypes.POINTER(ctypes.c_void_p))[0],
            ctypes.POINTER(ctypes.c_void_p),
        )
        GetCount = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint))(arr_vtbl[7])
        GetItemAt = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)
        )(arr_vtbl[8])
        arr_release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(arr_vtbl[2])

        count = ctypes.c_uint()
        GetCount(items, ctypes.byref(count))

        out: list[str] = []
        for i in range(count.value):
            item = ctypes.c_void_p()
            if GetItemAt(items, i, ctypes.byref(item)) != 0 or not item.value:
                continue
            item_vtbl = ctypes.cast(
                ctypes.cast(item, ctypes.POINTER(ctypes.c_void_p))[0],
                ctypes.POINTER(ctypes.c_void_p),
            )
            GetDisplayName = ctypes.WINFUNCTYPE(
                ctypes.HRESULT, ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(wintypes.LPWSTR)
            )(item_vtbl[5])
            item_release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(item_vtbl[2])

            psz = wintypes.LPWSTR()
            if GetDisplayName(item, SIGDN_FILESYSPATH, ctypes.byref(psz)) == 0 and psz.value:
                out.append(str(Path(psz.value).resolve()))
                ole32.CoTaskMemFree(psz)
            item_release(item)

        arr_release(items)
        return out
    finally:
        ole32.CoUninitialize()
