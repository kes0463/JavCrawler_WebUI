"""작품 품번 기준 로컬 영상 파일 탐색(GUI 비의존)."""

from __future__ import annotations

from pathlib import Path

from javstory.library.paths import work_library_dir


def scan_videos_in_dir(d: Path, depth: int = 0) -> list[Path]:
    """디렉터리 내 동영상 파일(하위 폴더 최대 depth 2)."""
    if not d.is_dir():
        return []
    from javstory.library.video_ext import is_video_file

    found: list[Path] = []
    try:
        files = sorted(d.iterdir())
        for p in files:
            if p.is_file() and is_video_file(p):
                found.append(p)
        if depth < 2:
            for p in files:
                if p.is_dir():
                    found.extend(scan_videos_in_dir(p, depth + 1))
    except OSError:
        pass
    return found


def first_video_in_dir(d: Path, depth: int = 0) -> Path | None:
    res = scan_videos_in_dir(d, depth)
    return res[0] if res else None


def video_search_dirs(product_code: str, folder_path: str | None = None) -> list[Path]:
    """품번 관련 영상을 찾을 후보 디렉터리 목록."""
    pc = (product_code or "").strip().upper()
    if not pc:
        return []
    from javstory.config.app_config import E_DATA_ROOT, E_MEDIA_ROOT, MEDIA_ROOT

    search_dirs: list[Path] = []
    if folder_path and Path(folder_path).is_dir():
        search_dirs.append(Path(folder_path))
    search_dirs.extend(
        [
            work_library_dir(pc),
            Path(E_MEDIA_ROOT) / pc,
            Path(E_DATA_ROOT) / pc,
            Path(E_DATA_ROOT) / "media" / pc,
            Path(MEDIA_ROOT) / pc,
        ]
    )
    return search_dirs


def find_all_video_paths_for_product(
    product_code: str,
    folder_path: str | None = None,
) -> list[Path]:
    """연결 폴더·라이브러리·미디어 루트에서 품번이 파일명에 포함된 영상을 모두 탐색."""
    pc = (product_code or "").strip().upper()
    if not pc:
        return []
    all_found: list[Path] = []
    seen: set[Path] = set()
    for base in video_search_dirs(pc, folder_path):
        if not base.is_dir():
            continue
        for v in scan_videos_in_dir(base):
            abs_v = v.resolve()
            if abs_v in seen:
                continue
            if pc in v.name.upper():
                all_found.append(v)
                seen.add(abs_v)
    return all_found


def guess_video_path_for_product(
    product_code: str,
    folder_path: str | None = None,
) -> Path | None:
    """첫 번째 매칭 영상 경로."""
    res = find_all_video_paths_for_product(product_code, folder_path)
    return res[0] if res else None


def guess_video_path_for_product_fast(
    product_code: str,
    folder_path: str | None = None,
) -> Path | None:
    """연결 폴더 직하위만 빠르게 탐색."""
    if not folder_path:
        return None
    pc = (product_code or "").strip().upper()
    base = Path(folder_path)
    if not base.is_dir():
        return None
    for v in scan_videos_in_dir(base):
        if pc in v.name.upper():
            return v
    return None

