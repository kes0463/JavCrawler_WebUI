"""DB에 저장된 작품 폴더가 사라졌을 때 후보 경로 검색."""

from __future__ import annotations

import os
import string
import sys
from pathlib import Path

MIN_CANDIDATE_VIDEO_BYTES = 1024**3  # 1 GiB

_SKIP_SCAN_DIR_NAMES = frozenset(
    {
        "$recycle.bin",
        "system volume information",
        "recovery",
        "perflogs",
        "msocache",
        "intel",
        "amd",
        "nvidia",
        "windows",
        "program files",
        "program files (x86)",
        "programdata",
        "appdata",
        "application data",
        "cookies",
        "local settings",
        "documents and settings",
    }
)

_SKIP_FOLDER_SEARCH_DRIVE_LETTERS = frozenset({"C", "D"})


def _dir_video_total_bytes_shallow(d: Path) -> int:
    from javstory.library.video_ext import is_video_file

    total = 0
    try:
        for x in d.iterdir():
            if x.is_file() and is_video_file(x):
                try:
                    total += x.stat().st_size
                except OSError:
                    pass
            elif x.is_dir():
                try:
                    for y in x.iterdir():
                        if y.is_file() and is_video_file(y):
                            try:
                                total += y.stat().st_size
                            except OSError:
                                pass
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _dir_qualifies_as_candidate(d: Path, *, min_video_bytes: int = MIN_CANDIDATE_VIDEO_BYTES) -> bool:
    return _dir_video_total_bytes_shallow(d) >= min_video_bytes


def _skip_scan_dir(path: Path) -> bool:
    try:
        name = path.name.lower()
    except Exception:
        return True
    if name in _SKIP_SCAN_DIR_NAMES:
        return True
    if name in ("node_modules", ".git", "__pycache__"):
        return True
    return False


def _windows_drive_roots() -> list[Path]:
    roots: list[Path] = []
    for letter in string.ascii_uppercase:
        if letter in _SKIP_FOLDER_SEARCH_DRIVE_LETTERS:
            continue
        p = Path(f"{letter}:\\")
        try:
            if p.exists() and p.is_dir():
                roots.append(p)
        except OSError:
            continue
    return roots


def _filesystem_search_roots() -> list[Path]:
    if sys.platform == "win32":
        return _windows_drive_roots()
    try:
        root = Path("/")
        return [root] if root.is_dir() else []
    except OSError:
        return []


def _drive_root_first(old_path: str | None, roots: list[Path]) -> list[Path]:
    if not old_path or sys.platform != "win32":
        return list(roots)
    try:
        old = Path(old_path).expanduser()
        drv = old.drive
        if not drv:
            return list(roots)
        letter = drv.rstrip(":").upper()
        if letter in _SKIP_FOLDER_SEARCH_DRIVE_LETTERS:
            return list(roots)
        primary = Path(drv + "\\")
        rest = [r for r in roots if r.resolve() != primary.resolve()]
        if primary.exists() and primary.is_dir():
            return [primary] + rest
    except OSError:
        pass
    return list(roots)


def _rank_candidates_by_old_path(old_path: str | None, candidates: list[str]) -> list[str]:
    if not old_path or not candidates:
        return list(candidates)
    old_exp = Path(old_path).expanduser()
    old_parts = tuple(str(x).lower() for x in old_exp.parts)
    old_drive = old_parts[0] if old_parts else ""
    old_leaf = old_exp.name.lower()

    def sort_key(cand: str) -> tuple:
        try:
            cp = Path(cand)
            c_parts = tuple(str(x).lower() for x in cp.parts)
            c_drive = c_parts[0] if c_parts else ""
            common = 0
            for a, b in zip(old_parts, c_parts):
                if a == b:
                    common += 1
                else:
                    break
            same_drive = 1 if old_drive and c_drive == old_drive else 0
            same_leaf = 1 if cp.name.lower() == old_leaf else 0
            return (-same_drive, -common, -same_leaf, cand.lower())
        except Exception:
            return (0, 0, 0, cand.lower())

    return sorted(candidates, key=sort_key)


def _max_scan_limit() -> int:
    raw = (os.environ.get("JAVSTORY_FOLDER_WATCH_MAX_SCAN") or "").strip()
    if raw.isdigit():
        return max(1000, int(raw))
    return 800_000


def search_folder_candidates(
    product_code: str,
    *,
    old_path: str | None = None,
    max_scan: int | None = None,
    max_pool: int = 48,
    max_results: int = 15,
    max_depth: int = 14,
) -> list[str]:
    pc = (product_code or "").strip().upper()
    if len(pc) < 2:
        return []
    limit = max_scan if max_scan is not None else _max_scan_limit()

    roots = _drive_root_first(old_path, _filesystem_search_roots())
    if not roots:
        return []

    seen: set[str] = set()
    raw: list[str] = []
    scanned = 0
    pc_compact = pc.replace("-", "")

    for base in roots:
        if not base.is_dir():
            continue
        stack: list[tuple[Path, int]] = [(base, 0)]
        while stack and scanned < limit and len(raw) < max_pool:
            p, depth = stack.pop()
            scanned += 1
            try:
                if not p.is_dir():
                    continue
                nu = p.name.upper().replace("-", "")
                name_hit = pc in p.name.upper() or (pc_compact and pc_compact in nu)

                if name_hit:
                    try:
                        key = str(p.resolve())
                    except OSError:
                        continue
                    if key not in seen and _dir_qualifies_as_candidate(p):
                        seen.add(key)
                        raw.append(key)

                if depth < max_depth:
                    try:
                        for ch in sorted(p.iterdir()):
                            if ch.is_dir() and not _skip_scan_dir(ch):
                                stack.append((ch, depth + 1))
                    except OSError:
                        pass
            except OSError:
                continue

    ranked = _rank_candidates_by_old_path(old_path, raw)
    return ranked[:max_results]
