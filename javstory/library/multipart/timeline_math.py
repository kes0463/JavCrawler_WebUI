"""작품 전체 논리 타임라인(초) ↔ 파트 인덱스·파트 내 로컬 시각 변환."""

from __future__ import annotations


def global_sec_to_part_and_local(global_sec: float, part_durations_sec: list[float]) -> tuple[int, float]:
    """
    합산 타임라인 상의 시각 → (파트 인덱스 0-based, 그 파트 내 초).
    경계는 앞 파트에 속함.
    """
    t = max(0.0, float(global_sec))
    if not part_durations_sec:
        return 0, t
    acc = 0.0
    for i, d in enumerate(part_durations_sec):
        dur = max(0.0, float(d))
        if t < acc + dur or i == len(part_durations_sec) - 1:
            return i, max(0.0, t - acc)
        acc += dur
    return len(part_durations_sec) - 1, 0.0


def part_local_to_global_sec(part_index: int, local_sec: float, part_durations_sec: list[float]) -> float:
    """파트 내 시각 → 논리 타임라인 전체 초."""
    if not part_durations_sec:
        return max(0.0, float(local_sec))
    n = len(part_durations_sec)
    pi = max(0, min(int(part_index), n - 1))
    off = sum(max(0.0, float(part_durations_sec[j])) for j in range(pi))
    return off + max(0.0, float(local_sec))
