"""
배경 배치 워커 — 앱 유휴 시 자동 취향 동기화

run_preference_sync(): 전체 시청 이력을 순회하며 preference 점수를 재계산
decay_and_sync(): recent_score 감쇠 + 전체 preference sync (배치용)
"""
from __future__ import annotations

import threading
from typing import Callable


def run_preference_sync(
    progress_callback: Callable[[int, int], None] | None = None
) -> int:
    """
    시청 이력이 있는 모든 작품의 preference 점수를 동기화합니다.
    이미 점수가 있는 항목은 건너뜁니다(is_completed=True인 항목만 처리).

    Args:
        progress_callback: (current, total) 호출 가능 객체 (UI 진행률 표시용)

    Returns:
        처리된 작품 수
    """
    from javstory.harvest.database import get_db_session_ctx, WatchHistory
    from javstory.analytics.preference_engine import score_preferences, get_time_slot

    with get_db_session_ctx() as session:
        # 완독 또는 별점 3 이상인 시청 이력만 처리
        histories = session.query(WatchHistory).filter(
            (WatchHistory.is_completed == True) | (WatchHistory.rating >= 3)
        ).all()
        codes_with_context = [
            (h.product_code, h.rating or 0, h.liked or False, h.disliked or False)
            for h in histories
        ]

    total = len(codes_with_context)
    count = 0
    for idx, (pc, rating, liked, disliked) in enumerate(codes_with_context):
        try:
            # 별점 기반 delta 계산
            if disliked:
                delta = -2
            elif liked or rating >= 4:
                delta = 3
            elif rating >= 3:
                delta = 2
            else:
                delta = 1
            score_preferences(pc, delta=delta)
            count += 1
        except Exception:
            pass
        if progress_callback:
            try:
                progress_callback(idx + 1, total)
            except Exception:
                pass

    return count


def decay_and_sync(
    progress_callback: Callable[[int, int], None] | None = None
) -> dict:
    """
    1) recent_score 감쇠 (7일 이상 미시청 항목)
    2) 전체 preference 동기화

    Returns:
        {"synced": int, "decayed": bool}
    """
    from javstory.analytics.preference_engine import decay_recent_scores

    try:
        decay_recent_scores()
        decayed = True
    except Exception:
        decayed = False

    synced = run_preference_sync(progress_callback=progress_callback)
    return {"synced": synced, "decayed": decayed}


def run_batch_in_thread(
    done_callback: Callable[[dict], None] | None = None
) -> threading.Thread:
    """
    배치를 백그라운드 스레드에서 실행합니다.

    Args:
        done_callback: 완료 시 결과 dict를 받아 호출될 콜백

    Returns:
        실행 중인 Thread 객체
    """
    def _worker():
        try:
            result = decay_and_sync()
        except Exception as e:
            result = {"synced": 0, "decayed": False, "error": str(e)}
        if done_callback:
            try:
                done_callback(result)
            except Exception:
                pass

    t = threading.Thread(target=_worker, daemon=True, name="preference-batch")
    t.start()
    return t
