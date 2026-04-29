from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


def _perf_log_path() -> Path:
    try:
        from javstory.config.app_config import DATA_ROOT

        root = Path(DATA_ROOT)
    except Exception:
        root = Path(".")
    return (root / "cache" / "perf" / "spans.jsonl").resolve()


def log_perf(event: str, **fields: Any) -> None:
    """
    경량 퍼포먼스/진단 이벤트를 JSONL로 기록.
    실패해도 앱 동작을 방해하지 않는다.
    """
    try:
        p = _perf_log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts_ms": int(time.time() * 1000),
            "event": str(event),
            **fields,
        }
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        return


@contextmanager
def perf_span(event: str, **fields: Any) -> Iterator[None]:
    t0 = time.perf_counter()
    log_perf(event + ".start", **fields)
    ok = True
    err: str | None = None
    try:
        yield
    except Exception as e:  # pragma: no cover
        ok = False
        err = str(e)
        raise
    finally:
        ms = int((time.perf_counter() - t0) * 1000)
        log_perf(event + ".end", ok=ok, elapsed_ms=ms, error=err, **fields)

