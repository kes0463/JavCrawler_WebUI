"""
CLI: 품번 단위 파이프라인 (Harvest / STT / 자막).

예:
  python scripts/run_product_pipeline.py ABC-123 --video "D:/media/ABC-123/foo.mp4"
  python scripts/run_product_pipeline.py ABC-123 --video path/to.mp4 --stages harvest,stt
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from javstory.pipeline.orchestrator import PipelineStage, run_product_pipeline_async


def _parse_stages(s: str) -> set[PipelineStage] | str:
    t = (s or "all").strip().lower()
    if t == "all":
        return "all"
    out: set[PipelineStage] = set()
    for part in t.replace(" ", "").split(","):
        if not part:
            continue
        out.add(PipelineStage(part))
    return out


async def _amain() -> int:
    p = argparse.ArgumentParser(description="Harvest → STT → 자막 파이프라인")
    p.add_argument("product_code", help="품번")
    p.add_argument("--video", type=Path, help="로컬 영상 파일 (STT/자막 단계에 필요)")
    p.add_argument("--product-code-override", type=str, default=None, help="크롤 시 명시 품번")
    p.add_argument("--work-dir", type=Path, default=None, help="STT 작업 디렉터리(기본: 영상과 동일 폴더)")
    p.add_argument(
        "--stages",
        default="all",
        help="all | harvest,stt,subtitle (쉼표)",
    )
    p.add_argument("--force", action="store_true", help="기존 산출물이 있어도 단계 재실행")
    args = p.parse_args()

    stages = _parse_stages(args.stages)

    r = await run_product_pipeline_async(
        product_code=args.product_code,
        video_path=args.video,
        product_code_override=args.product_code_override,
        stages=stages,
        work_dir=args.work_dir,
        skip_if_outputs_exist=not args.force,
        force=args.force,
    )
    print(r)
    err = any(
        isinstance(v, dict) and v.get("error")
        for k, v in r.items()
        if k == "harvest" and isinstance(v, dict)
    )
    return 1 if err else 0


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
