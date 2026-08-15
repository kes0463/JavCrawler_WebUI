"""재생 프록시 캐시 유지관리 — 용량 상한(LRU) + 나중에 볼 항목 보호.

정책:
- 캐시 총량이 상한(JAVSTORY_PLAYBACK_CACHE_MAX_GB, 기본 30GB)을 넘으면 오래 안 쓴
  프록시부터 삭제한다(LRU, 파일 mtime 기준. 재생 시 mtime을 갱신함).
- "나중에 볼(watch_later)"로 표시된 미시청 영상의 프록시는 시청 전까지 삭제 대상에서
  제외한다. 단, 등록 후 30일이 지나면 보호를 해제한다(상한 30일).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from javstory.harvest.database import WatchHistory, get_db_session_ctx
from javstory.harvest.product_repository import resolve_video_paths_for_playback
from javstory.library import playback_proxy

logger = logging.getLogger(__name__)

WATCH_LATER_PROTECT_DAYS = 30
# 이 시간(초) 이상 시청했거나 완료 표시된 영상은 "시청함"으로 간주 → 보호 해제.
WATCHED_SECONDS = 300


def _watch_later_protected_codes() -> list[str]:
    """보호 대상 품번: watch_later=True, 미시청, 등록 후 30일 이내."""
    codes: list[str] = []
    cutoff = datetime.now() - timedelta(days=WATCH_LATER_PROTECT_DAYS)
    try:
        with get_db_session_ctx() as session:
            rows = (
                session.query(WatchHistory)
                .filter(WatchHistory.watch_later.is_(True))
                .all()
            )
            for r in rows:
                watched = bool(r.is_completed) or int(r.watch_duration or 0) >= WATCHED_SECONDS
                if watched:
                    continue
                added = r.watch_later_added_at or r.created_at
                if added and added < cutoff:
                    continue  # 상한 30일 초과 → 보호 해제
                pc = (r.product_code or "").strip().upper()
                if pc:
                    codes.append(pc)
    except Exception as exc:  # pragma: no cover - DB 예외 방어
        logger.warning("watch_later 보호 목록 조회 실패: %s", exc)
    return codes


def compute_protected_digests() -> set[str]:
    """보호 대상 영상들의 프록시 캐시 digest(파일 stem) 집합."""
    protected: set[str] = set()
    for code in _watch_later_protected_codes():
        try:
            for path in resolve_video_paths_for_playback(code, None):
                if not path.is_file():
                    continue
                if not playback_proxy.needs_browser_proxy(path):
                    continue
                protected.add(playback_proxy.proxy_hls_dir(path).name)
        except Exception:
            continue
    return protected


def run_cache_maintenance() -> dict[str, int]:
    """보호 목록을 반영해 용량 상한을 강제한다(백그라운드 호출용)."""
    protected = compute_protected_digests()
    result = playback_proxy.evict_proxy_cache(protected)
    return result


def init_proxy_cache_maintenance() -> None:
    """library 레이어에 보호 목록 계산기를 주입(프록시 생성 후 자동 정리에 사용)."""
    playback_proxy.set_protected_digests_provider(compute_protected_digests)


def cache_stats() -> dict[str, int]:
    return playback_proxy.proxy_cache_stats()


def clear_cache() -> dict[str, int]:
    return playback_proxy.clear_proxy_cache()
