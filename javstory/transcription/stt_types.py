"""STT 워커·엔진 공용 타입(stable-ts 단일 경로). Obsolete 미참조."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Optional

STTStage = str

STT_PRESET_DEFAULT = "stable_ts"

# JAVSTORY_STT_ENGINE values — see javstory.transcription.stt_config


def safe_console_print(text: str) -> None:
    """print()가 콘솔 코드페이지(예: Windows cp949)에서 인코딩 못 하는 문자를 만나도
    죽지 않게 함 — 진단 로그 하나 때문에 전사 작업 전체가 실패하면 안 됨."""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(text.encode(enc, errors="replace").decode(enc, errors="replace"), flush=True)


@dataclass
class STTProgressEvent:
    stage: STTStage
    percent: int
    message: str
    detail: Optional[dict[str, Any]] = None


class STTCancelled(Exception):
    pass


class SimpleSegment:
    def __init__(
        self,
        start: float,
        end: float,
        text: str,
        avg_logprob: float = 0.0,
        no_speech_prob: float = 0.0,
        compression_ratio: float = 0.0,
    ):
        self.start = start
        self.end = end
        self.text = text.strip()
        self.avg_logprob = avg_logprob
        self.no_speech_prob = no_speech_prob
        self.compression_ratio = compression_ratio
        self.needs_review = False
        self.review_reason: list[str] = []
