"""품번별 폴더 감시 일시중지."""

from __future__ import annotations

import json
import threading

from javstory.config.app_config import DATA_ROOT

_PAUSED_FILE = DATA_ROOT / "folder_watch_paused.json"
_lock = threading.Lock()
_cache: set[str] | None = None


def _load() -> set[str]:
    global _cache
    with _lock:
        if _cache is not None:
            return set(_cache)
        codes: set[str] = set()
        if _PAUSED_FILE.is_file():
            try:
                raw = json.loads(_PAUSED_FILE.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    for x in raw:
                        pc = str(x).strip().upper()
                        if pc:
                            codes.add(pc)
            except Exception:
                codes = set()
        _cache = codes
        return set(codes)


def _persist(codes: set[str]) -> None:
    global _cache
    with _lock:
        _cache = set(codes)
        try:
            DATA_ROOT.mkdir(parents=True, exist_ok=True)
            arr = sorted(codes)
            tmp = _PAUSED_FILE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(arr, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(_PAUSED_FILE)
        except Exception:
            pass


def load_paused_product_codes() -> set[str]:
    return _load()


def is_monitoring_paused(product_code: str) -> bool:
    pc = (product_code or "").strip().upper()
    return pc in _load() if pc else False


def pause_monitoring(product_code: str) -> None:
    pc = (product_code or "").strip().upper()
    if not pc:
        return
    codes = _load()
    codes.add(pc)
    _persist(codes)


def resume_monitoring(product_code: str) -> None:
    pc = (product_code or "").strip().upper()
    if not pc:
        return
    codes = _load()
    codes.discard(pc)
    _persist(codes)


def invalidate_cache() -> None:
    global _cache
    with _lock:
        _cache = None
