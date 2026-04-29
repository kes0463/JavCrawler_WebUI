"""
폴더명 기반 품번 추출 및 Harvest 작업 계획 (플랜 `harvest-folder-sku`).

- 단일 폴더: 폴더 이름에서 품번 → 직하위 동영상(비재귀)과 연결
- 상위 폴더: 직하위 **각 하위 폴더**마다 동일 규칙으로 일괄 계획
- 폴더 여러 개: 각각 `plan_single_folder` 결과를 이어붙임
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from javstory.config.app_config import VIDEO_EXTENSIONS
from javstory.utils.product_code import (
    extract_product_code_from_folder_name,
    list_distinct_product_codes_from_folder_label,
)

_VIDEO_EXTS = tuple(e.lower() for e in VIDEO_EXTENSIONS)


def _list_videos_non_recursive(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(folder.iterdir()):
        if p.is_file() and p.suffix.lower() in _VIDEO_EXTS:
            out.append(p)
    return out


@dataclass
class PlannedHarvest:
    """`HarvestWorker` 엔트리 1건에 대응: (target, is_path, product_code)."""

    product_code: str
    crawl_target: str
    is_media_path: bool
    notes: list[str] = field(default_factory=list)


def _resolve_folder_sku(folder: Path) -> tuple[str | None, str | None]:
    """
    (품번, 오류 메시지). 오류 시 품번 None — 모호·추출 실패.
    """
    name = folder.name
    distinct = list_distinct_product_codes_from_folder_label(name)
    if len(distinct) > 1:
        return None, f"폴더명에 품번 후보가 여러 개입니다: {', '.join(distinct)}"
    if len(distinct) == 1:
        return distinct[0], None
    sku = extract_product_code_from_folder_name(folder)
    if sku:
        return sku, None
    return None, "폴더명에서 품번을 찾지 못했습니다."


def plan_single_folder(folder: Path) -> tuple[list[PlannedHarvest], list[str]]:
    """
    하나의 작품 폴더 → 0~1건 계획 + 경고 문자열 목록.
    직하위 동영상이 여러 개면 **이름순 첫 파일**을 사용(경고 추가).
    """
    folder = folder.expanduser().resolve()
    warnings: list[str] = []
    if not folder.is_dir():
        return [], [f"폴더가 아닙니다: {folder}"]

    sku, err = _resolve_folder_sku(folder)
    if err or not sku:
        return [], [f"{folder.name}: {err or '품번 없음'}"]

    videos = _list_videos_non_recursive(folder)
    if len(videos) > 1:
        warnings.append(
            f"{folder.name}: 동영상 {len(videos)}개 — 첫 파일 사용 ({videos[0].name})"
        )
    if videos:
        ph = PlannedHarvest(
            product_code=sku.upper(),
            crawl_target=str(videos[0].resolve()),
            is_media_path=True,
            notes=warnings.copy(),
        )
        return [ph], warnings
    # 영상 없음: 품번만 크롤
    warnings.append(f"{folder.name}: 동영상 없음 — 메타(크롤)만 수행")
    ph = PlannedHarvest(
        product_code=sku.upper(),
        crawl_target=sku.upper(),
        is_media_path=False,
        notes=warnings.copy(),
    )
    return [ph], warnings


def plan_parent_folder(parent: Path) -> tuple[list[PlannedHarvest], list[str]]:
    """상위 폴더 아래를 재귀적으로 스캔하여 작품 폴더를 일괄 계획한다."""
    parent = parent.expanduser().resolve()
    all_jobs: list[PlannedHarvest] = []
    global_warn: list[str] = []
    if not parent.is_dir():
        return [], [f"폴더가 아닙니다: {parent}"]

    # parent 자체도 후보로 포함
    jobs, w = plan_single_folder(parent)
    global_warn.extend(w)
    all_jobs.extend(jobs)

    # 너무 큰 트리를 실수로 선택했을 때의 비용을 줄이기 위한 기본 스킵(이름 기반).
    # 필요하면 상위에서 경로를 더 좁혀 선택하는 방식으로 운용.
    skip_names = {
        ".git",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
    }

    # DFS: symlink(또는 재파싱 포인트)로 인한 무한 루프/외부 트리 진입을 피한다.
    stack: list[Path] = [parent]
    seen: set[str] = set()
    while stack:
        cur = stack.pop()
        try:
            key = str(cur)
        except Exception:
            continue
        if key in seen:
            continue
        seen.add(key)

        try:
            children = sorted(cur.iterdir())
        except OSError:
            continue

        for ch in children:
            try:
                if not ch.is_dir():
                    continue
                if ch.name in skip_names:
                    continue
                # symlink directory skip
                if ch.is_symlink():
                    continue
            except OSError:
                continue

            jobs, w = plan_single_folder(ch)
            global_warn.extend(w)
            all_jobs.extend(jobs)
            stack.append(ch)

    return all_jobs, global_warn


def plan_folder_paths(paths: list[Path]) -> tuple[list[PlannedHarvest], list[str]]:
    """선택된 여러 폴더를 각각 `plan_single_folder`로 합친다."""
    all_jobs: list[PlannedHarvest] = []
    global_warn: list[str] = []
    for raw in paths:
        p = raw.expanduser().resolve()
        jobs, w = plan_single_folder(p)
        global_warn.extend(w)
        all_jobs.extend(jobs)
    return all_jobs, global_warn


def planned_to_worker_entries(jobs: list[PlannedHarvest]) -> list[tuple[str, bool, str | None]]:
    """`HarvestWorker`용 (target, is_path, product_code) 리스트."""
    out: list[tuple[str, bool, str | None]] = []
    for j in jobs:
        out.append((j.crawl_target, j.is_media_path, j.product_code))
    return out
