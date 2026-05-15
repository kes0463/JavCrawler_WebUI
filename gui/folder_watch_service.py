"""DB에 저장된 작품 폴더 연결의 존재 여부 감시 — 이동·삭제 시 알림 및 후보 경로 안내."""

from __future__ import annotations

import json
import os
import string
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, Property, QRunnable, QThreadPool, QTimer, Signal, Slot

from javstory.config.app_config import DATA_ROOT

try:
    from PySide6.QtCore import QFileSystemWatcher
except ImportError:
    QFileSystemWatcher = None  # type: ignore[misc, assignment]


def _disabled() -> bool:
    v = (os.environ.get("JAVSTORY_DISABLE_FOLDER_WATCH") or "").strip().lower()
    return v in {"1", "true", "yes", "on"}


_PAUSED_FILE = DATA_ROOT / "folder_watch_paused.json"


# 후보 폴더: 동영상만 크기에 포함, 직속·한 단계 하위만 스캔(풀 트리 순회 비용 방지)
MIN_CANDIDATE_VIDEO_BYTES = 1024**3  # 1 GiB


def _dir_video_total_bytes_shallow(d: Path) -> int:
    """폴더 직속 파일과 한 단계 하위 디렉터리 안 동영상 파일 크기 합계."""
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
    """동영상 합계가 `min_video_bytes` 이상이면 후보(동영상 없으면 False)."""
    return _dir_video_total_bytes_shallow(d) >= min_video_bytes


def _skip_scan_dir(path: Path) -> bool:
    """전체 디스크 스캔 시 진입하지 않을 디렉터리(이름만 비교)."""
    try:
        name = path.name.lower()
    except Exception:
        return True
    # OS·휴지통·대형 설치 트리 — 미디어 폴더로 쓰이기 어렵고 순회 비용만 큼
    if name in _SKIP_SCAN_DIR_NAMES:
        return True
    if name in ("node_modules", ".git", "__pycache__"):
        return True
    return False


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


# 폴더 후보 전체 디스크 검색 시 스킵하는 드라이브 (시스템/OS 디스크)
_SKIP_FOLDER_SEARCH_DRIVE_LETTERS = frozenset({"C", "D"})


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
    """전체 로컬 디스크(Windows: 각 드라이브 루트, 그 외: `/`)."""
    if sys.platform == "win32":
        return _windows_drive_roots()
    try:
        root = Path("/")
        return [root] if root.is_dir() else []
    except OSError:
        return []


def _drive_root_first(old_path: str | None, roots: list[Path]) -> list[Path]:
    """이전 경로와 같은 드라이브를 앞으로 두어 빨리 후보를 채운다. C/D 루트는 검색 제외."""
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
    """이전 DB 경로와 겹치는 상위 경로가 많을수록·같은 드라이브·같은 폴더명이면 위로."""
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
    """
    **로컬 디스크**(Windows: `C:\\`·`D:\\` 제외한 드라이브 루트부터 DFS)에서 폴더 이름에 품번이 포함된 경로를 찾는다.
    후보는 **직속·한 단계 하위** 동영상 크기 합이 **1GiB 이상**인 폴더만 포함한다.
    OS·휴지통 등 이름이 알려진 디렉터리는 진입하지 않는다.

    부하 한도는 `max_scan`(기본 대량, 환경변수 `JAVSTORY_FOLDER_WATCH_MAX_SCAN`으로 조정 가능).
    """
    pc = (product_code or "").strip().upper()
    if len(pc) < 2:
        return []
    limit = max_scan if max_scan is not None else _max_scan_limit()

    roots = _drive_root_first(old_path, _filesystem_search_roots())
    if not roots:
        return []

    t0 = time.perf_counter()

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
    out = ranked[:max_results]
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    _ = elapsed_ms  # kept for potential future profiling without logging
    return out


class _FolderCandidateSearchRunnable(QRunnable):
    """Heavy filesystem scan must not run on the Qt GUI thread."""

    def __init__(self, svc: "FolderMoveWatchService", pc: str, fp: str) -> None:
        super().__init__()
        self._svc = svc
        self._pc = pc
        self._fp = fp

    def run(self) -> None:
        cands = search_folder_candidates(self._pc, old_path=self._fp)
        self._svc._folder_search_done.emit(self._pc, self._fp, cands)


class FolderMoveWatchService(QObject):
    """
    - 주기적으로 DB의 folder_path 존재 여부 확인
    - QFileSystemWatcher로 상위 디렉터리 변경 시 즉시 재검사 (Windows 한계 내에서만 경로 등록)
    - 경로가 사라지면 LibraryModel.folderBindingNeedsReview만 발생 — 자동 토스트·refresh 없음 (QML 확인)
    - 품번별 감시 일시중지: 전체 디스크 후보 검색·알림 재발송 생략 (DB folder_path 유지)
    """

    _folder_search_done = Signal(str, str, list)
    pausedRevisionChanged = Signal()

    def __init__(self, library_model: QObject, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._library = library_model
        self._paths: dict[str, str] = {}
        self._broken_notified: set[str] = set()
        self._paused_product_codes: set[str] = set()
        self._paused_revision: int = 0
        self._load_paused_product_codes()
        self._folder_search_done.connect(self._deliver_folder_binding_review)
        self._search_pool = QThreadPool(self)
        self._search_pool.setMaxThreadCount(2)
        self._watcher = QFileSystemWatcher(self) if QFileSystemWatcher else None
        if self._watcher:
            self._watcher.directoryChanged.connect(self._schedule_verify)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(450)
        self._debounce.timeout.connect(self.verify_bindings)

        self._poll = QTimer(self)
        self._poll.setInterval(60_000)
        self._poll.timeout.connect(self.verify_bindings)

    def _load_paused_product_codes(self) -> None:
        self._paused_product_codes = set()
        if not _PAUSED_FILE.is_file():
            return
        try:
            raw = json.loads(_PAUSED_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                for x in raw:
                    pc = str(x).strip().upper()
                    if pc:
                        self._paused_product_codes.add(pc)
        except Exception:
            self._paused_product_codes = set()

    def _persist_paused_product_codes(self) -> None:
        try:
            DATA_ROOT.mkdir(parents=True, exist_ok=True)
            arr = sorted(self._paused_product_codes)
            tmp = _PAUSED_FILE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(arr, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(_PAUSED_FILE)
        except Exception:
            pass

    def _bump_paused_revision(self) -> None:
        self._paused_revision += 1
        self.pausedRevisionChanged.emit()

    @Property(int, notify=pausedRevisionChanged)
    def pausedRevision(self) -> int:
        return self._paused_revision

    @Slot(str, result=bool)
    def isMonitoringPaused(self, product_code: str) -> bool:
        pc = (product_code or "").strip().upper()
        return pc in self._paused_product_codes if pc else False

    @Slot(str)
    def pauseMonitoringForProduct(self, product_code: str) -> None:
        pc = (product_code or "").strip().upper()
        if not pc:
            return
        self._paused_product_codes.add(pc)
        self._persist_paused_product_codes()
        self._broken_notified.discard(pc)
        self._bump_paused_revision()

    @Slot(str)
    def resumeMonitoringForProduct(self, product_code: str) -> None:
        pc = (product_code or "").strip().upper()
        if not pc:
            return
        self._paused_product_codes.discard(pc)
        self._persist_paused_product_codes()
        self._broken_notified.discard(pc)
        self._bump_paused_revision()
        QTimer.singleShot(0, self.verify_bindings)

    @Slot(str, str, list)
    def _deliver_folder_binding_review(self, pc: str, fp: str, cands: list) -> None:
        try:
            if (pc or "").strip().upper() in self._paused_product_codes:
                return
            rel = getattr(self._library, "folderBindingNeedsReview", None)
            if rel is not None:
                rel.emit(pc, fp, cands)
        except Exception as e:
            _ = e

    @Slot()
    def refresh_paths_from_db(self) -> None:
        """DB에서 folder_path 목록을 다시 읽고 감시 경로를 갱신한다."""
        if _disabled():
            return
        try:
            from javstory.harvest.database import get_db_session, JAVMetadata

            session = get_db_session()
            try:
                rows = session.query(JAVMetadata.product_code, JAVMetadata.folder_path).all()
                self._paths = {}
                for pc, fp in rows:
                    if not fp or not str(fp).strip():
                        continue
                    self._paths[(pc or "").strip().upper()] = str(Path(fp).expanduser())
            finally:
                session.close()
        except Exception as e:
            _ = e
            self._paths = {}

        self._rebuild_watcher_paths()
        if not self._poll.isActive():
            self._poll.start()

    def _rebuild_watcher_paths(self) -> None:
        if not self._watcher:
            return
        try:
            old = self._watcher.directories()
            if old:
                self._watcher.removePaths(old)
        except Exception:
            pass

        parents: set[str] = set()
        for fp in self._paths.values():
            try:
                p = Path(fp)
                if p.is_dir():
                    parents.add(str(p.resolve()))
                par = p.parent
                if par.is_dir():
                    parents.add(str(par.resolve()))
            except OSError:
                continue

        # Qt/Windows: 감시 경로 수가 많으면 실패할 수 있어 상한
        max_watch = 96
        for i, d in enumerate(sorted(parents)):
            if i >= max_watch:
                break
            try:
                self._watcher.addPath(d)
            except Exception:
                pass

    def _schedule_verify(self) -> None:
        self._debounce.start()

    @Slot()
    def verify_bindings(self) -> None:
        if _disabled():
            return
        for pc, fp in list(self._paths.items()):
            if pc in self._paused_product_codes:
                continue
            try:
                ok = Path(fp).is_dir()
            except OSError:
                ok = False
            if ok:
                if pc in self._broken_notified:
                    self._broken_notified.discard(pc)
                continue

            if pc in self._broken_notified:
                continue
            self._broken_notified.add(pc)

            self._search_pool.start(_FolderCandidateSearchRunnable(self, pc, fp))
