"""분할 영상 파일명에서 파트 순서 추출·같은 폴더 그룹 제안."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


# Part1, part_2, cd1, CD2, 上巻/下巻, discA, _A., -B-, 등
_PART_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("part_n", re.compile(r"(?i)(?:^|[^a-z])(?:part|pt)\s*[_\-]?\s*(\d{1,2})(?:[^0-9]|$)")),
    ("cd_n", re.compile(r"(?i)(?:^|[^a-z])cd\s*[_\-]?\s*(\d{1,2})(?:[^0-9]|$)")),
    ("disc_n", re.compile(r"(?i)(?:^|[^a-z])disc\s*[_\-]?\s*(\d{1,2})(?:[^0-9]|$)")),
    ("vol_n", re.compile(r"(?i)(?:^|[^a-z])vol\.?\s*(\d{1,2})(?:[^0-9]|$)")),
    ("ue_jou", re.compile(r"(上巻|下巻|前編|後編)")),
    ("letter", re.compile(r"(?i)(?:^|[^a-z])[_\-]([A-D])\b")),
]


def part_sort_key(stem: str) -> tuple[int, float, str]:
    """
    정렬 키: (매칭 우선순위 낮을수록 앞, 파트 번호, 자연스러운 이름).
    파트 미검출 시 (999, 999.0, stem) 로 맨 뒤.
    """
    name = stem
    for pi, (_, pat) in enumerate(_PART_PATTERNS):
        m = pat.search(name)
        if not m:
            continue
        g = m.group(1)
        if g in ("上巻", "前編"):
            return (pi, 0.0, name)
        if g in ("下巻", "後編"):
            return (pi, 1.0, name)
        try:
            n = float(g)
            return (pi, n, name)
        except ValueError:
            pass
    return (999, 999.0, name)


def sort_video_parts(paths: list[Path]) -> list[Path]:
    """같은 작품 후보끼리 파일명 규칙으로 순서 정렬."""
    return sorted(paths, key=lambda p: part_sort_key(p.stem))


@dataclass
class PartGroupSuggestion:
    """UI 제안용 — 같은 디렉터리에서 다중 영상이 멀티파트일 수 있음."""

    directory: Path
    video_paths: list[Path]
    reason: str


def suggest_groups_in_directories(paths: list[Path]) -> list[PartGroupSuggestion]:
    """같은 부모 폴더에 동영상이 2개 이상이면 그룹 후보."""
    from javstory.library.video_ext import is_video_file

    by_parent: dict[Path, list[Path]] = defaultdict(list)
    for p in paths:
        if not p.is_file():
            continue
        if not is_video_file(p):
            continue
        by_parent[p.parent.resolve()].append(p.resolve())

    out: list[PartGroupSuggestion] = []
    for parent, plist in by_parent.items():
        if len(plist) < 2:
            continue
        sorted_p = sort_video_parts(plist)
        out.append(
            PartGroupSuggestion(
                directory=parent,
                video_paths=sorted_p,
                reason="같은 폴더에 동영상 2개 이상 — 파트 분할 작품일 수 있음",
            )
        )
    return out


def explain_part_order(path: Path) -> str:
    """디버그/툴팁용 짧은 설명."""
    k = part_sort_key(path.stem)
    if k[0] >= 999:
        return "파트 패턴 미검출 (파일명 정렬)"
    return f"파트 키 rank={k[0]} idx={k[1]}"
