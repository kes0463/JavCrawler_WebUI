"""좋아요 점수만 빠르게 재수집하는 워커 (번역/Grok/스냅샷 없음)."""
from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import QThread, Signal

from javstory.harvest.database import (
    record_favorite_crawl_failed as _record_favorite_crawl_failed,
    record_favorite_score_snapshot,
)


class FavoritesOnlyWorker(QThread):
    progress   = Signal(int, int)   # (current, total)
    finished   = Signal(int, int, int)   # (updated, zero, failed)
    itemUpdate = Signal(str, str, int, str)  # (sku, status, progress, message)
    logMessage = Signal(str)

    def __init__(self, product_codes: list[str], parent=None):
        super().__init__(parent)
        self._codes = [str(x or "").strip().upper() for x in (product_codes or []) if str(x or "").strip()]
        self._last_err: str = ""
        self._last_err_lock = threading.Lock()
        self._stop = False
        self._executor: ThreadPoolExecutor | None = None

    def stop(self) -> None:
        self._stop = True
        try:
            ex = self._executor
            if ex is not None:
                try:
                    ex.shutdown(wait=False, cancel_futures=True)  # type: ignore[call-arg]
                except TypeError:
                    ex.shutdown(wait=False)
        except Exception:
            pass

    @staticmethod
    def _harvest_concurrency() -> int:
        """Harvest와 동일: `JAVSTORY_HARVEST_CONCURRENCY` (기본 2, 1–5)."""
        raw = (os.environ.get("JAVSTORY_HARVEST_CONCURRENCY", "") or "").strip()
        if raw:
            try:
                n = int(raw)
            except ValueError:
                n = 2
        else:
            n = 2
        return max(1, min(5, n))

    def _dbg(self, msg: str) -> None:
        if os.environ.get("JAVSTORY_FAV_DEBUG", "").strip().lower() in ("1", "true", "yes", "on"):
            try:
                print(msg)
            except Exception:
                pass

    @staticmethod
    def _looks_invalid_page(info: object) -> bool:
        """
        스크레이퍼가 200을 받았더라도, 404 템플릿/리다이렉트 등으로
        실질 데이터가 비어 있을 수 있다.
        """
        try:
            title = str(getattr(info, "title", "") or "").strip()
            code = str(getattr(info, "code", "") or "").strip()
            return (not title) and (not code)
        except Exception:
            return True

    def _fetch_with_case_fallback(self, fetch_fn, pc: str, *, label: str) -> tuple[object | None, bool, str]:
        """
        1) lower()로 호출 후 결과가 무효면 upper()로 1회 폴백.
        반환: (info_or_none, ok, diag)
        """
        pc_u = (pc or "").strip().upper()
        pc_l = pc_u.lower()

        def _call(arg: str) -> object:
            return fetch_fn(arg)

        # 1차: lower()
        try:
            info = _call(pc_l)
            if info is not None and not self._looks_invalid_page(info):
                return info, True, f"{label} ok(lower)"
            self._dbg(f"[FavOnly][DBG] {pc_u} {label} invalid(lower) title/code empty")
        except Exception as e:
            with self._last_err_lock:
                self._last_err = f"{label}: {e}"
            self.logMessage.emit(f"[FavOnly] {pc_u} {label} 실패(lower): {e}")
            self._dbg(f"[FavOnly][DBG] {pc_u} {label} exc(lower): {e}")

        # 2차: upper()
        try:
            info2 = _call(pc_u)
            if info2 is not None and not self._looks_invalid_page(info2):
                return info2, True, f"{label} ok(upper)"
            self._dbg(f"[FavOnly][DBG] {pc_u} {label} invalid(upper) title/code empty")
            return info2, False, f"{label} invalid"
        except Exception as e2:
            with self._last_err_lock:
                self._last_err = f"{label}: {e2}"
            self.logMessage.emit(f"[FavOnly] {pc_u} {label} 실패(upper): {e2}")
            self._dbg(f"[FavOnly][DBG] {pc_u} {label} exc(upper): {e2}")
            return None, False, f"{label} exc"

    def _process_one(self, pc: str) -> tuple[str, str]:
        """
        반환: (결과 종류, 품번). 종류: "updated" | "zero" | "failed"
        """
        from javstory.harvest.scrapers.av123_scraper import fetch_video_info as av123_fetch
        from javstory.harvest.scrapers.missav123_scraper import fetch_video_info as missav_fetch
        from javstory.harvest.database import get_db_session_ctx, JAVMetadata, clear_favorite_crawl_failed

        if self._stop:
            return "failed", pc

        self.itemUpdate.emit(pc, "running", 5, "좋아요 수집 중…")

        score1, score2 = 0, 0
        d1, ok1, diag1 = self._fetch_with_case_fallback(av123_fetch, pc, label="123av")
        d2, ok2, diag2 = self._fetch_with_case_fallback(missav_fetch, pc, label="missav123")

        if d1 is not None:
            try:
                score1 = int(getattr(d1, "favourite_count", 0) or 0)
            except Exception:
                score1 = 0
        if d2 is not None:
            try:
                score2 = int(getattr(d2, "favourite_count", 0) or 0)
            except Exception:
                score2 = 0

        self._dbg(f"[FavOnly][DBG] {pc} {diag1} fav={score1} | {diag2} fav={score2}")

        total_score = score1 + score2
        if total_score == 0:
            if ok1 or ok2:
                clear_favorite_crawl_failed(pc)
                self.itemUpdate.emit(pc, "done", 100, "0점수 (기존 값 유지)")
                return "zero", pc
            self.itemUpdate.emit(pc, "error", 100, "좋아요 수집 실패")
            _record_favorite_crawl_failed(pc)
            return "failed", pc

        sources = f"123av:{score1},missav123:{score2}"
        with get_db_session_ctx() as session:
            row = session.query(JAVMetadata).filter_by(product_code=pc).first()
            if row:
                row.favorite_score = total_score
                row.favorite_sources = sources
                row.favorite_crawl_failed_at = None
                session.commit()

                record_favorite_score_snapshot(pc, total_score, sources)
                self.itemUpdate.emit(pc, "done", 100, f"갱신 완료 (♥ {total_score})")
                return "updated", pc
            self.itemUpdate.emit(pc, "error", 100, "DB에 품번이 없음")
            _record_favorite_crawl_failed(pc)
            return "failed", pc

    def run(self):
        total = len(self._codes)
        updated, zero, failed = 0, 0, 0

        if total <= 0:
            self.finished.emit(0, 0, 0)
            return

        workers = self._harvest_concurrency()
        done_cnt = 0

        try:
            self._executor = ThreadPoolExecutor(max_workers=workers)
            ex = self._executor
            futs = {ex.submit(self._process_one, pc): pc for pc in self._codes if not self._stop}

            for fut in as_completed(futs):
                if self._stop:
                    break
                pc = futs.get(fut, "")
                try:
                    kind, _pc = fut.result()
                    if kind == "updated":
                        updated += 1
                    elif kind == "zero":
                        zero += 1
                    else:
                        failed += 1
                except Exception as e:
                    with self._last_err_lock:
                        self._last_err = str(e)
                    self.logMessage.emit(f"[FavOnly] {pc} 실패: {e}")
                    failed += 1
                    try:
                        _record_favorite_crawl_failed(pc)
                    except Exception:
                        pass
                    try:
                        self.itemUpdate.emit(pc, "error", 100, f"예외: {e}")
                    except Exception:
                        pass

                done_cnt += 1
                self.progress.emit(done_cnt, total)
        finally:
            try:
                ex2 = self._executor
                if ex2 is not None:
                    try:
                        ex2.shutdown(wait=False, cancel_futures=True)  # type: ignore[call-arg]
                    except TypeError:
                        ex2.shutdown(wait=False)
            except Exception:
                pass
            self._executor = None

        with self._last_err_lock:
            if self._last_err:
                self.logMessage.emit(f"[FavOnly] 마지막 예외: {self._last_err}")
        self.finished.emit(updated, zero, failed)
