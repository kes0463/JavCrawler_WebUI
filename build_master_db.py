import json
import os
import argparse
from dataclasses import dataclass
from pathlib import Path

from javstory.library.export.master_js import write_master_db_js


ROOT = Path(__file__).resolve().parent

# `data/derived/master_db.js` — 경로는 `core.app_config.DERIVED_DATA_DIR`와 동기
def _derived_dir() -> Path:
    from javstory.config.app_config import DERIVED_DATA_DIR

    return DERIVED_DATA_DIR
DEFAULT_FACTORY_ROOT = (
    Path(os.environ.get("JAVSTORY_FACTORY_ROOT", "")).expanduser()
    if os.environ.get("JAVSTORY_FACTORY_ROOT")
    else None
)
if DEFAULT_FACTORY_ROOT is None:
    local_app_data = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    DEFAULT_FACTORY_ROOT = Path(local_app_data) / "JAVSTORY" / "Factory"


@dataclass
class BuildStats:
    files: int = 0
    videos: int = 0
    scenes: int = 0
    errors: int = 0


def _read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _safe_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _safe_text(v) -> str:
    if v is None:
        return ""
    return str(v)


def _normalize_rel_path(path_str: str) -> str:
    return path_str.replace("\\", "/")


def _resolve_to_root_rel(*, base_dir: Path, rel_or_abs: str) -> str | None:
    """
    web_output_dir(=base_dir) 기준의 src/screenshot 경로를 실제 파일로 해석하고
    ROOT 기준의 상대 경로로 변환한다.
    """
    if not rel_or_abs or not isinstance(rel_or_abs, str):
        return None

    p = Path(rel_or_abs)
    if not p.is_absolute():
        abs_path = (base_dir / rel_or_abs).resolve()
    else:
        abs_path = p.resolve()

    try:
        rel = abs_path.relative_to(ROOT)
    except Exception:
        # 다른 드라이브/외부 경로면 상대 경로를 만들 수 없으므로 basename으로 폴백
        return abs_path.name

    return _normalize_rel_path(str(rel))


def _iter_web_databases(factory_root: Path) -> list[Path]:
    completed = factory_root / "03_COMPLETED"
    if not completed.exists():
        return []
    return sorted(completed.rglob("web_database.json"))


def _extract_scenes(db: dict, *, web_base_dir: Path, source_tag: str) -> list[dict]:
    """
    db(zones/sub_chapters/vlm_snapshots) → 검색용 scene entry array로 변환
    """
    zones = db.get("zones") if isinstance(db, dict) else None
    if not isinstance(zones, list):
        zones = []

    video_meta = db.get("video") if isinstance(db, dict) else {}
    if not isinstance(video_meta, dict):
        video_meta = {}

    raw_video_src = video_meta.get("src")
    video_src = _resolve_to_root_rel(base_dir=web_base_dir, rel_or_abs=_safe_text(raw_video_src))

    duration = _safe_float(video_meta.get("duration"), 0.0)
    fps = video_meta.get("fps")

    out: list[dict] = []

    for z in zones:
        if not isinstance(z, dict):
            continue

        zone_label = _safe_text(z.get("zone") or "UNKNOWN")
        z_start = _safe_float(z.get("start"), 0.0)
        z_end = _safe_float(z.get("end"), 0.0)

        snaps = z.get("vlm_snapshots")
        if not isinstance(snaps, list):
            snaps = []

        sub = z.get("sub_chapters")
        if not isinstance(sub, list):
            sub = []

        for idx, sc in enumerate(sub):
            if not isinstance(sc, dict):
                continue

            t = _safe_float(sc.get("start_t"), z_start)
            position = _safe_text(sc.get("position") or "unclear")
            action = _safe_text(sc.get("action") or "unknown")
            intensity = _safe_text(sc.get("intensity") or "?")
            description = _safe_text(sc.get("description") or "")

            # 대표 스크린샷: t와 가장 가까운 스냅샷의 screenshot
            thumb = None
            best_dist = None
            for s in snaps:
                if not isinstance(s, dict):
                    continue
                if s.get("error"):
                    continue
                st = s.get("t")
                stf = _safe_float(st, float("nan"))
                if not (stf == stf):  # nan
                    continue
                shot = s.get("screenshot")
                if not (isinstance(shot, str) and shot.strip()):
                    # screenshot이 없으면 "거리"를 고려할 의미가 없으므로 스킵
                    continue
                d = abs(stf - t)
                if best_dist is None or d < best_dist:
                    thumb = _resolve_to_root_rel(base_dir=web_base_dir, rel_or_abs=shot.strip())
                    best_dist = d

            text_blob = " ".join([zone_label, position, action, intensity, description]).strip()

            out.append(
                {
                    "id": f"{source_tag}::{zone_label}::{idx}::{t:.3f}",
                    "source": source_tag,  # 어떤 작업 폴더에서 왔는지(디버깅/추적용)
                    "video": {
                        "src": video_src,
                        "duration": duration,
                        "fps": fps,
                    },
                    "scene": {
                        "t": t,
                        "zone": zone_label,  # UI의 Location 필터로 사용
                        "position": position,
                        "action": action,
                        "intensity": intensity,
                        "description": description,
                        "zoneStart": z_start,
                        "zoneEnd": z_end,
                    },
                    "thumb": thumb,
                    "text": text_blob,
                }
            )

    # 시간순 정렬(같은 비디오 내 의미가 살아있도록)
    out.sort(key=lambda e: (_safe_text(e.get("video", {}).get("src")), _safe_float(e.get("scene", {}).get("t"), 0.0)))
    return out


def build_master_db(factory_root: Path) -> tuple[list[dict], BuildStats]:
    stats = BuildStats()
    all_scenes: list[dict] = []

    completed = factory_root / "03_COMPLETED"
    for json_path in _iter_web_databases(factory_root):
        stats.files += 1
        try:
            db = _read_json(json_path)
            web_base_dir = json_path.parent  # .../<job>/web
            # source_tag: 03_COMPLETED 기준 상대 경로(유니크/추적용)
            try:
                source_tag = _normalize_rel_path(str(json_path.parent.parent.relative_to(completed)))
            except Exception:
                source_tag = _normalize_rel_path(str(json_path.parent.parent.name))

            scenes = _extract_scenes(db, web_base_dir=web_base_dir, source_tag=source_tag)
            if scenes:
                stats.videos += 1
                stats.scenes += len(scenes)
                all_scenes.extend(scenes)
        except Exception:
            stats.errors += 1

    return all_scenes, stats


def write_master_js(entries: list[dict]) -> Path:
    d = _derived_dir()
    d.mkdir(parents=True, exist_ok=True)
    out_path = d / "master_db.js"
    write_master_db_js(out_path, entries)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build master_db.js from all 03_COMPLETED/*/web/web_database.json")
    parser.add_argument(
        "--factory-root",
        default=str(DEFAULT_FACTORY_ROOT),
        help="워치독 공장 루트(03_COMPLETED를 포함). 기본값: LOCALAPPDATA\\JAVSTORY\\Factory",
    )
    args = parser.parse_args()

    factory_root = Path(args.factory_root).expanduser().resolve()
    entries, stats = build_master_db(factory_root)
    out_path = write_master_js(entries)
    print(f"[MasterDB] 완료: {out_path}")
    print(f"[MasterDB] web_database.json 파일: {stats.files} | 비디오(세트): {stats.videos} | 씬 엔트리: {stats.scenes} | 에러: {stats.errors}")


if __name__ == "__main__":
    main()

