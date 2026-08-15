"""Subprocess entry point for FW-XXL native STT.

Runs ``run_fw_native()`` in an isolated process so a native crash in
ctranslate2/CUDA cleanup (observed on this machine: WER fault buckets
0xe06d7363 / 0xc0000409, right after the model is deleted at the end of a
full-length job) kills only this subprocess, not the parent webapi server.
Progress/log lines are streamed to stdout as one JSON object per line;
``run_fw_native_subprocess`` in ``fw_xxl_native.py`` parses them back into the
usual logger/progress callbacks.
"""
from __future__ import annotations

import argparse
import json
import sys


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video_path")
    parser.add_argument("work_dir")
    args = parser.parse_args()

    from javstory.transcription.fw_xxl_native import run_fw_native
    from javstory.transcription.stt_types import STTCancelled, STTProgressEvent

    def logger(msg: str) -> None:
        _emit({"type": "log", "msg": msg})

    def progress(ev: STTProgressEvent) -> None:
        _emit({"type": "progress", "stage": ev.stage, "percent": ev.percent, "message": ev.message})

    try:
        interim_srt, _segments = run_fw_native(
            video_path=args.video_path,
            work_dir=args.work_dir,
            logger=logger,
            progress=progress,
            should_cancel=None,
        )
        _emit({"type": "result", "ok": True, "srt_path": str(interim_srt)})
        return 0
    except STTCancelled:
        _emit({"type": "result", "ok": False, "cancelled": True})
        return 2
    except Exception as e:  # noqa: BLE001 - report to parent, don't swallow
        _emit({"type": "result", "ok": False, "error": str(e)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
