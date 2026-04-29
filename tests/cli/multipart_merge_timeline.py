#!/usr/bin/env python3
"""CLI: 멀티파트 영상 경로들 → 논리 타임라인 합본 SRT (파트별 동명 .ja.srt/.srt 필요)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from javstory.library.multipart import build_logical_merged_srt


def main() -> int:
    p = argparse.ArgumentParser(description="멀티파트 논리 타임라인 SRT 합성")
    p.add_argument("videos", nargs="+", help="영상 파일 경로 (순서는 파일명 파트 규칙으로 재정렬됨)")
    p.add_argument("-o", "--output", required=True, help="출력 .srt 경로")
    args = p.parse_args()
    paths = [Path(x).resolve() for x in args.videos]
    out = Path(args.output).resolve()
    ok, msg = build_logical_merged_srt(paths, out)
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
