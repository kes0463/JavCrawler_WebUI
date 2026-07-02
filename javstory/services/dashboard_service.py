from __future__ import annotations

import subprocess
import time
from typing import Any

from javstory.analytics.library_stats import get_library_stats
from javstory.harvest.database import JAVMetadata, get_db_session_ctx
from javstory.services.library_service import LibraryService


class DashboardService:
    _METRICS_CACHE: tuple[float, dict[str, Any]] | None = None
    _METRICS_TTL_SEC = 8.0

    def __init__(self, library: LibraryService | None = None) -> None:
        self._library = library or LibraryService()

    def summary(self) -> dict[str, Any]:
        lib = self._library.stats()
        watch = get_library_stats()
        pending_count = self._pending_count()
        metadata_rate = (
            round(lib["with_metadata"] / lib["total"] * 100, 1)
            if lib["total"] > 0
            else 0.0
        )
        return {
            "library": lib,
            "watch": watch,
            "pending_count": pending_count,
            "metadata_match_rate": metadata_rate,
        }

    def pending_items(self, *, limit: int = 200) -> list[dict[str, str]]:
        with get_db_session_ctx() as session:
            rows = (
                session.query(JAVMetadata.product_code, JAVMetadata.title_ko)
                .filter_by(analysis_status="pending")
                .order_by(JAVMetadata.updated_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "product_code": pc or "",
                    "title": (title or pc or "")[:60],
                }
                for pc, title in (rows or [])
            ]

    def cancel_pending(self, product_code: str) -> bool:
        code = (product_code or "").strip().upper()
        if not code:
            return False
        with get_db_session_ctx() as session:
            row = session.query(JAVMetadata).filter_by(product_code=code).first()
            if not row:
                return False
            row.analysis_status = "none"
            session.commit()
            return True

    def clear_pending(self) -> int:
        with get_db_session_ctx() as session:
            rows = session.query(JAVMetadata).filter_by(analysis_status="pending").all()
            for row in rows:
                row.analysis_status = "none"
            session.commit()
            return len(rows)

    def system_metrics(self) -> dict[str, Any]:
        now = time.time()
        if (
            DashboardService._METRICS_CACHE
            and (now - DashboardService._METRICS_CACHE[0]) < self._METRICS_TTL_SEC
        ):
            return dict(DashboardService._METRICS_CACHE[1])

        out: dict[str, Any] = {
            "gpu_name": "N/A",
            "gpu_usage_percent": 0,
            "gpu_total_gb": 0.0,
            "gpu_used_gb": 0.0,
            "cpu_percent": 0,
            "mem_percent": 0,
            "mem_used_gb": 0.0,
            "mem_total_gb": 0.0,
            "cpu_model": "CPU",
        }
        self._poll_gpu(out)
        self._poll_cpu(out)
        DashboardService._METRICS_CACHE = (now, dict(out))
        return out

    def _pending_count(self) -> int:
        with get_db_session_ctx() as session:
            return (
                session.query(JAVMetadata)
                .filter_by(analysis_status="pending")
                .count()
            )

    @staticmethod
    def _poll_gpu(out: dict[str, Any]) -> None:
        try:
            cp = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.used,utilization.gpu",
                    "--format=csv,nounits,noheader",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                check=False,
            )
            if cp.returncode != 0:
                return
            raw = (cp.stdout or "").strip()
            if not raw:
                return
            parts = [p.strip() for p in raw.split(",")]
            name = parts[0]
            total = float(parts[1])
            used = float(parts[2])
            util = int(float(parts[3])) if len(parts) > 3 else int(used / total * 100 if total else 0)
            out.update(
                {
                    "gpu_name": name,
                    "gpu_usage_percent": util,
                    "gpu_total_gb": round(total / 1024, 1),
                    "gpu_used_gb": round(used / 1024, 1),
                }
            )
        except Exception:
            pass

    @staticmethod
    def _poll_cpu(out: dict[str, Any]) -> None:
        try:
            import psutil

            out["cpu_percent"] = int(psutil.cpu_percent(interval=0))
            mem = psutil.virtual_memory()
            out["mem_percent"] = int(mem.percent)
            out["mem_used_gb"] = round(mem.used / (1024**3), 1)
            out["mem_total_gb"] = round(mem.total / (1024**3), 1)
            try:
                import platform

                out["cpu_model"] = platform.processor() or "CPU"
            except Exception:
                pass
        except ImportError:
            pass
