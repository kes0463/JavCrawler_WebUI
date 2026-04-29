"""STT 워커·엔진 공용 타입(stable-ts 단일 경로). Obsolete 미참조."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

STTStage = str

STT_PRESET_DEFAULT = "stable_ts"


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
