"""백그라운드 폴더 연결 감시 (WebAPI·비-Qt 환경)."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from javstory.folder_watch.candidates import search_folder_candidates
from javstory.folder_watch.inbox import upsert_inbox_item
from javstory.folder_watch.paused import is_monitoring_paused, load_paused_product_codes

_instance: "FolderWatchBackgroundService | None" = None
_instance_lock = threading.Lock()


def _disabled() -> bool:
    v = (os.environ.get("JAVSTORY_DISABLE_FOLDER_WATCH") or "").strip().lower()
    return v in {"1", "true", "yes", "on"}


class FolderWatchBackgroundService:
    def __init__(self) -> None:
        self._paths: dict[str, str] = {}
        self._broken_notified: set[str] = set()
        self._revision = 0
        self._state_lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._search_sem = threading.Semaphore(2)

    @property
    def revision(self) -> int:
        with self._state_lock:
            return self._revision

    def _bump_revision(self) -> None:
        with self._state_lock:
            self._revision += 1

    def notify_change(self) -> None:
        """인박스·일시중지 등 외부 변경 시 revision 갱신."""
        self._bump_revision()

    def start(self) -> None:
        if _disabled() or self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="folder-watch-bg")
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def refresh_paths_from_db(self) -> None:
        if _disabled():
            return
        paths: dict[str, str] = {}
        try:
            from javstory.harvest.database import JAVMetadata, get_db_session

            session = get_db_session()
            try:
                rows = session.query(JAVMetadata.product_code, JAVMetadata.folder_path).all()
                for pc, fp in rows:
                    if not fp or not str(fp).strip():
                        continue
                    paths[(pc or "").strip().upper()] = str(Path(fp).expanduser())
            finally:
                session.close()
        except Exception:
            paths = {}
        with self._state_lock:
            self._paths = paths

    def verify_bindings(self) -> None:
        if _disabled():
            return
        paused = load_paused_product_codes()
        with self._state_lock:
            snapshot = list(self._paths.items())
            broken = set(self._broken_notified)

        for pc, fp in snapshot:
            if pc in paused:
                continue
            try:
                ok = Path(fp).is_dir()
            except OSError:
                ok = False
            if ok:
                with self._state_lock:
                    self._broken_notified.discard(pc)
                continue
            with self._state_lock:
                if pc in self._broken_notified:
                    continue
                self._broken_notified.add(pc)
            threading.Thread(
                target=self._handle_broken_binding,
                args=(pc, fp),
                daemon=True,
                name=f"folder-watch-search-{pc}",
            ).start()

    def _handle_broken_binding(self, product_code: str, old_path: str) -> None:
        if is_monitoring_paused(product_code):
            return
        with self._search_sem:
            if is_monitoring_paused(product_code):
                return
            try:
                cands = search_folder_candidates(product_code, old_path=old_path)
            except Exception:
                cands = []
        upsert_inbox_item(product_code, old_path, cands)
        self._bump_revision()

    def clear_broken_flag(self, product_code: str) -> None:
        pc = (product_code or "").strip().upper()
        if not pc:
            return
        with self._state_lock:
            self._broken_notified.discard(pc)

    def _loop(self) -> None:
        time.sleep(2.5)
        while self._running:
            try:
                self.refresh_paths_from_db()
                self.verify_bindings()
            except Exception:
                pass
            for _ in range(60):
                if not self._running:
                    return
                time.sleep(1)


def get_folder_watch_service() -> FolderWatchBackgroundService:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = FolderWatchBackgroundService()
        return _instance
