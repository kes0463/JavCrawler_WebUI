"""STT engine / VAD / dialogue-only settings from environment."""

from __future__ import annotations

import os
from typing import Any

STT_ENGINE_STABLE_TS = "stable_ts"
STT_ENGINE_STABLE_TS_FW = "stable_ts_fw"
STT_ENGINE_ANIME_WHISPER = "anime_whisper"
STT_ENGINE_WHISPERX = "whisperx"

STT_ENGINES: tuple[str, ...] = (
    STT_ENGINE_STABLE_TS,
    STT_ENGINE_STABLE_TS_FW,
    STT_ENGINE_ANIME_WHISPER,
    STT_ENGINE_WHISPERX,
)

STT_ENGINE_IMPLEMENTED: dict[str, bool] = {
    STT_ENGINE_STABLE_TS: True,
    STT_ENGINE_STABLE_TS_FW: True,
    STT_ENGINE_ANIME_WHISPER: True,
    STT_ENGINE_WHISPERX: False,
}

STT_ENGINE_LABELS: dict[str, str] = {
    STT_ENGINE_STABLE_TS: "Stable TS (PyTorch)",
    STT_ENGINE_STABLE_TS_FW: "Faster-Whisper XXL (Native)",
    STT_ENGINE_ANIME_WHISPER: "Anime-Whisper + Stable TS",
    STT_ENGINE_WHISPERX: "WhisperX (예정)",
}

STT_ENGINE_DESCRIPTIONS: dict[str, str] = {
    STT_ENGINE_STABLE_TS: "OpenAI Whisper large-v2/v3 + stable-ts VAD·싱크 보정",
    STT_ENGINE_STABLE_TS_FW: (
        "CTranslate2(faster-whisper) 순정 파이프라인 — ffmpeg 추출 → transcribe() → SRT. "
        "stable-ts VAD/후처리 없음(참조 Faster-Whisper-XXL 툴과 동일 형태)"
    ),
    STT_ENGINE_ANIME_WHISPER: "litagin/anime-whisper 일본어 연기 도메인 + stable-ts 후처리",
    STT_ENGINE_WHISPERX: "아직 미구현 — forced alignment 전용",
}

DEFAULT_WHISPER_MODEL = "large-v2"
DEFAULT_FASTER_WHISPER_MODEL = "kotoba-tech/kotoba-whisper-v2.0-faster"
DEFAULT_HF_WHISPER_MODEL = "litagin/anime-whisper"
DEFAULT_VAD_THRESHOLD = 0.35
DIALOGUE_ONLY_VAD_FLOOR = 0.45

_ALIASES: dict[str, str] = {
    "stable-ts": STT_ENGINE_STABLE_TS,
    "stablets": STT_ENGINE_STABLE_TS,
    "faster_whisper": STT_ENGINE_STABLE_TS_FW,
    "faster-whisper": STT_ENGINE_STABLE_TS_FW,
    "faster_whisper_xxl": STT_ENGINE_STABLE_TS_FW,
    "stable_ts_fw": STT_ENGINE_STABLE_TS_FW,
    "anime-whisper": STT_ENGINE_ANIME_WHISPER,
    "anime_whisper": STT_ENGINE_ANIME_WHISPER,
    "whisperx": STT_ENGINE_WHISPERX,
}


def normalize_stt_engine(raw: str | None) -> str:
    key = (raw or STT_ENGINE_STABLE_TS).strip().lower()
    if key in STT_ENGINES:
        return key
    return _ALIASES.get(key, STT_ENGINE_STABLE_TS)


def stt_engine_from_env() -> str:
    return normalize_stt_engine(os.environ.get("JAVSTORY_STT_ENGINE", STT_ENGINE_STABLE_TS))


def whisper_model_from_env() -> str:
    return (os.environ.get("JAVSTORY_WHISPER_MODEL", DEFAULT_WHISPER_MODEL) or DEFAULT_WHISPER_MODEL).strip()


def faster_whisper_model_from_env() -> str:
    return (
        os.environ.get("JAVSTORY_FASTER_WHISPER_MODEL", DEFAULT_FASTER_WHISPER_MODEL)
        or DEFAULT_FASTER_WHISPER_MODEL
    ).strip()


def hf_whisper_model_from_env() -> str:
    return (
        os.environ.get("JAVSTORY_HF_WHISPER_MODEL", DEFAULT_HF_WHISPER_MODEL)
        or DEFAULT_HF_WHISPER_MODEL
    ).strip()


def _env_bool(key: str, default: bool = False) -> bool:
    raw = (os.environ.get(key, "") or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def dialogue_only_from_env() -> bool:
    return _env_bool("JAVSTORY_STT_DIALOGUE_ONLY", False)


def vad_threshold_from_env() -> float:
    raw = (os.environ.get("JAVSTORY_VAD_THRESHOLD", "") or "").strip()
    try:
        base = float(raw) if raw else DEFAULT_VAD_THRESHOLD
    except ValueError:
        base = DEFAULT_VAD_THRESHOLD
    if dialogue_only_from_env():
        return max(base, DIALOGUE_ONLY_VAD_FLOOR)
    return base


def stt_engine_options() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for eid in STT_ENGINES:
        out.append(
            {
                "id": eid,
                "label": STT_ENGINE_LABELS.get(eid, eid),
                "description": STT_ENGINE_DESCRIPTIONS.get(eid, ""),
                "implemented": STT_ENGINE_IMPLEMENTED.get(eid, False),
            }
        )
    return out


FW_XXL_DEFAULTS: dict[str, Any] = {
    "language": "ja",
    "vad_filter": True,
    "vad_threshold": 0.6,
    "vad_min_speech_duration_ms": 400,
    "vad_max_speech_duration_s": 18,
    "condition_on_previous_text": False,
    "no_speech_threshold": 0.6,
    "beam_size": 7,
    "best_of": 5,
    "temperature": 0.0,
    "temperature_increment_on_fallback": 0.2,
    "hallucination_silence_threshold": 1.5,
    "compute_type": "float16",
    "batch_size": 8,
    "word_timestamps": False,
    "repetition_penalty": 1.2,
    "log_prob_threshold": -1.0,
    "compression_ratio_threshold": 2.4,
}

_FW_XXL_ENV: dict[str, str] = {
    "language": "JAVSTORY_FW_LANGUAGE",
    "vad_filter": "JAVSTORY_FW_VAD_FILTER",
    "vad_threshold": "JAVSTORY_FW_VAD_THRESHOLD",
    "vad_min_speech_duration_ms": "JAVSTORY_FW_VAD_MIN_SPEECH_MS",
    "vad_max_speech_duration_s": "JAVSTORY_FW_VAD_MAX_SPEECH_S",
    "condition_on_previous_text": "JAVSTORY_FW_CONDITION_ON_PREVIOUS_TEXT",
    "no_speech_threshold": "JAVSTORY_FW_NO_SPEECH_THRESHOLD",
    "beam_size": "JAVSTORY_FW_BEAM_SIZE",
    "best_of": "JAVSTORY_FW_BEST_OF",
    "temperature": "JAVSTORY_FW_TEMPERATURE",
    "temperature_increment_on_fallback": "JAVSTORY_FW_TEMPERATURE_INCREMENT",
    "hallucination_silence_threshold": "JAVSTORY_FW_HALLUCINATION_SILENCE",
    "compute_type": "JAVSTORY_FW_COMPUTE_TYPE",
    "batch_size": "JAVSTORY_FW_BATCH_SIZE",
    "word_timestamps": "JAVSTORY_FW_WORD_TIMESTAMPS",
    "repetition_penalty": "JAVSTORY_FW_REPETITION_PENALTY",
    "log_prob_threshold": "JAVSTORY_FW_LOG_PROB_THRESHOLD",
    "compression_ratio_threshold": "JAVSTORY_FW_COMPRESSION_RATIO_THRESHOLD",
}


def fw_xxl_env_key(field: str) -> str | None:
    return _FW_XXL_ENV.get(field)


def fw_xxl_options_from_env() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field, default in FW_XXL_DEFAULTS.items():
        env_key = _FW_XXL_ENV[field]
        raw = (os.environ.get(env_key, "") or "").strip()
        if not raw:
            out[field] = default
            continue
        if isinstance(default, bool):
            out[field] = raw.lower() in ("1", "true", "yes", "on")
        elif isinstance(default, int):
            try:
                out[field] = int(float(raw))
            except ValueError:
                out[field] = default
        elif isinstance(default, float):
            try:
                out[field] = float(raw)
            except ValueError:
                out[field] = default
        else:
            out[field] = raw
    return out


def stt_settings_snapshot() -> dict[str, Any]:
    return {
        "engine": stt_engine_from_env(),
        "whisper_model": whisper_model_from_env(),
        "faster_whisper_model": faster_whisper_model_from_env(),
        "hf_whisper_model": hf_whisper_model_from_env(),
        "vad_threshold": vad_threshold_from_env(),
        "dialogue_only": dialogue_only_from_env(),
        "fw_xxl": fw_xxl_options_from_env(),
        "engine_options": stt_engine_options(),
    }
