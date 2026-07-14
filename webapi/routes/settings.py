from __future__ import annotations

from fastapi import APIRouter, HTTPException

from javstory.transcription.stt_config import (
    STT_ENGINE_IMPLEMENTED,
    normalize_stt_engine,
    stt_settings_snapshot,
)
from javstory.translation.translation_config import (
    gguf_env_key_for_model,
    llamacpp_model_from_env,
    normalize_translation_provider,
    translation_settings_snapshot,
)
from javstory.translation.translation_prompt_config import (
    normalize_prompt_mode,
    normalize_prompt_variant,
    translation_prompt_settings_snapshot,
)
from webapi.schemas import (
    EmbeddingsSettingsPatch,
    EmbeddingsSettingsResponse,
    FasterWhisperModelOption,
    SttEngineOption,
    SttFwXxlOptions,
    SttSettingsPatch,
    SttSettingsResponse,
    TranslationSettingsPatch,
    TranslationSettingsResponse,
    TranslationPromptSettingsPatch,
    TranslationPromptSettingsResponse,
)

router = APIRouter()


def _to_response(snap: dict) -> SttSettingsResponse:
    return SttSettingsResponse(
        engine=snap["engine"],
        whisper_model=snap["whisper_model"],
        faster_whisper_model=snap["faster_whisper_model"],
        hf_whisper_model=snap["hf_whisper_model"],
        vad_threshold=snap["vad_threshold"],
        dialogue_only=snap["dialogue_only"],
        fw_xxl=SttFwXxlOptions(**snap["fw_xxl"]),
        engine_options=[SttEngineOption(**o) for o in snap["engine_options"]],
        faster_whisper_model_options=[
            FasterWhisperModelOption(**o) for o in snap.get("faster_whisper_model_options") or []
        ],
    )


@router.get("/stt", response_model=SttSettingsResponse)
def get_stt_settings():
    return _to_response(stt_settings_snapshot())


@router.patch("/stt", response_model=SttSettingsResponse)
def patch_stt_settings(body: SttSettingsPatch):
    from javstory.config.secrets_manager import set_env_runtime_value
    from javstory.transcription.stt_config import fw_xxl_env_key

    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(400, "수정할 필드가 없습니다")

    if "engine" in data:
        eng = normalize_stt_engine(data["engine"])
        if not STT_ENGINE_IMPLEMENTED.get(eng, False):
            raise HTTPException(400, f"엔진 '{eng}'은(는) 아직 지원되지 않습니다")
        set_env_runtime_value("JAVSTORY_STT_ENGINE", eng)

    if "whisper_model" in data:
        wm = str(data["whisper_model"] or "").strip()
        if not wm:
            raise HTTPException(400, "whisper_model is required")
        set_env_runtime_value("JAVSTORY_WHISPER_MODEL", wm)

    if "faster_whisper_model" in data:
        fm = str(data["faster_whisper_model"] or "").strip()
        if not fm:
            raise HTTPException(400, "faster_whisper_model is required")
        set_env_runtime_value("JAVSTORY_FASTER_WHISPER_MODEL", fm)

    if "hf_whisper_model" in data:
        hm = str(data["hf_whisper_model"] or "").strip()
        if not hm:
            raise HTTPException(400, "hf_whisper_model is required")
        set_env_runtime_value("JAVSTORY_HF_WHISPER_MODEL", hm)

    if "vad_threshold" in data and data["vad_threshold"] is not None:
        set_env_runtime_value("JAVSTORY_VAD_THRESHOLD", str(data["vad_threshold"]))

    if "dialogue_only" in data and data["dialogue_only"] is not None:
        set_env_runtime_value(
            "JAVSTORY_STT_DIALOGUE_ONLY",
            "1" if data["dialogue_only"] else "0",
        )

    if "fw_xxl" in data and data["fw_xxl"] is not None:
        fw = {k: v for k, v in data["fw_xxl"].items() if v is not None}
        for field, value in fw.items():
            env_key = fw_xxl_env_key(field)
            if not env_key:
                continue
            if isinstance(value, bool):
                set_env_runtime_value(env_key, "1" if value else "0")
            else:
                set_env_runtime_value(env_key, str(value))
        if "vad_threshold" in fw:
            set_env_runtime_value("JAVSTORY_VAD_THRESHOLD", str(fw["vad_threshold"]))

    return _to_response(stt_settings_snapshot())


def _translation_to_response(snap: dict) -> TranslationSettingsResponse:
    return TranslationSettingsResponse(**snap)


@router.get("/translation", response_model=TranslationSettingsResponse)
def get_translation_settings():
    return _translation_to_response(translation_settings_snapshot())


@router.patch("/translation", response_model=TranslationSettingsResponse)
def patch_translation_settings(body: TranslationSettingsPatch):
    from pathlib import Path

    from javstory.config.secrets_manager import set_env_runtime_value
    from javstory.llm.llamacpp_backend import (
        LLAMACPP_GGUF_PATH_ENV,
        LLAMACPP_MODEL_PRESETS,
        _infer_preset_from_gguf_path,
        gguf_option_id,
        is_gguf_option_id,
        parse_gguf_option_id,
        resolve_llamacpp_preset,
    )

    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(400, "수정할 필드가 없습니다")

    if "provider" in data:
        prov = normalize_translation_provider(data["provider"])
        set_env_runtime_value("JAVSTORY_TRANSLATION_PROVIDER", prov)
        if prov == "llamacpp":
            set_env_runtime_value("JAVSTORY_LLM_PLATFORM", "llamacpp")
        elif prov == "ollama":
            set_env_runtime_value("JAVSTORY_LLM_PLATFORM", "ollama")
        elif prov == "openrouter":
            set_env_runtime_value("JAVSTORY_LLM_PLATFORM", "openai")

    if "openrouter_profile" in data and data["openrouter_profile"]:
        prof = str(data["openrouter_profile"]).strip().lower()
        set_env_runtime_value("JAVSTORY_TRANSLATION_PROFILE", prof)

    model_id = data.get("llamacpp_model") or llamacpp_model_from_env()

    if "llamacpp_model" in data and data["llamacpp_model"]:
        mid = str(data["llamacpp_model"]).strip()
        if is_gguf_option_id(mid):
            parsed = parse_gguf_option_id(mid)
            if parsed is None:
                raise HTTPException(400, f"GGUF 파일 없음: {mid[len('gguf:'):]}")
            preset = _infer_preset_from_gguf_path(parsed)
            set_env_runtime_value("JAVSTORY_LLAMACPP_MODEL", mid)
            set_env_runtime_value(LLAMACPP_GGUF_PATH_ENV, str(parsed))
            set_env_runtime_value("JAVSTORY_TRANSLATION_PROFILE", f"llamacpp:{preset.id}")
            model_id = mid
        else:
            mid_lower = mid.lower()
            if mid_lower not in LLAMACPP_MODEL_PRESETS:
                try:
                    preset = resolve_llamacpp_preset(mid_lower)
                except Exception as exc:
                    raise HTTPException(400, f"알 수 없는 모델: {mid}") from exc
            else:
                preset = resolve_llamacpp_preset(mid_lower)
            set_env_runtime_value("JAVSTORY_LLAMACPP_MODEL", preset.id)
            set_env_runtime_value(LLAMACPP_GGUF_PATH_ENV, "")
            set_env_runtime_value("JAVSTORY_TRANSLATION_PROFILE", f"llamacpp:{preset.id}")
            model_id = preset.id

    if "llamacpp_bin" in data:
        set_env_runtime_value("JAVSTORY_LLAMACPP_BIN", str(data["llamacpp_bin"] or "").strip())

    if "llamacpp_url" in data and data["llamacpp_url"]:
        url = str(data["llamacpp_url"]).strip().rstrip("/")
        set_env_runtime_value("JAVSTORY_LLAMACPP_URL", url)

    if "llamacpp_port" in data and data["llamacpp_port"] is not None:
        port = int(data["llamacpp_port"])
        set_env_runtime_value("JAVSTORY_LLAMACPP_PORT", str(port))
        set_env_runtime_value("JAVSTORY_LLAMACPP_URL", f"http://127.0.0.1:{port}")

    if "llamacpp_gguf_path" in data:
        gguf = str(data["llamacpp_gguf_path"] or "").strip()
        if gguf:
            p = Path(gguf).expanduser()
            if not p.is_file():
                raise HTTPException(400, f"GGUF 파일 없음: {gguf}")
            resolved = p.resolve()
            gid = gguf_option_id(resolved)
            preset = _infer_preset_from_gguf_path(resolved)
            set_env_runtime_value(LLAMACPP_GGUF_PATH_ENV, str(resolved))
            set_env_runtime_value("JAVSTORY_LLAMACPP_MODEL", gid)
            set_env_runtime_value("JAVSTORY_TRANSLATION_PROFILE", f"llamacpp:{preset.id}")
            model_id = gid
        elif not is_gguf_option_id(str(model_id)):
            env_key = gguf_env_key_for_model(model_id)
            set_env_runtime_value(env_key, "")
            set_env_runtime_value(LLAMACPP_GGUF_PATH_ENV, "")

    if "llamacpp_ctx" in data and data["llamacpp_ctx"] is not None:
        set_env_runtime_value("JAVSTORY_LLAMACPP_CTX", str(data["llamacpp_ctx"]))

    if "llamacpp_n_gpu_layers" in data:
        ngl = data["llamacpp_n_gpu_layers"]
        if ngl is None:
            set_env_runtime_value("JAVSTORY_LLAMACPP_N_GPU_LAYERS", "")
        else:
            set_env_runtime_value("JAVSTORY_LLAMACPP_N_GPU_LAYERS", str(max(0, int(ngl))))

    if "llamacpp_cache_type_k" in data and data["llamacpp_cache_type_k"]:
        set_env_runtime_value(
            "JAVSTORY_LLAMACPP_CACHE_TYPE_K",
            str(data["llamacpp_cache_type_k"]).strip(),
        )

    if "llamacpp_cache_type_v" in data and data["llamacpp_cache_type_v"]:
        set_env_runtime_value(
            "JAVSTORY_LLAMACPP_CACHE_TYPE_V",
            str(data["llamacpp_cache_type_v"]).strip(),
        )

    if "llamacpp_threads" in data:
        th = data["llamacpp_threads"]
        if th is None:
            set_env_runtime_value("JAVSTORY_LLAMACPP_THREADS", "")
        else:
            set_env_runtime_value("JAVSTORY_LLAMACPP_THREADS", str(int(th)))

    if "llamacpp_tensorcores" in data and data["llamacpp_tensorcores"] is not None:
        set_env_runtime_value(
            "JAVSTORY_LLAMACPP_TENSORCORES",
            "1" if data["llamacpp_tensorcores"] else "0",
        )

    if "llamacpp_flash_attn" in data and data["llamacpp_flash_attn"] is not None:
        set_env_runtime_value(
            "JAVSTORY_LLAMACPP_FLASH_ATTN",
            "1" if data["llamacpp_flash_attn"] else "0",
        )

    if "llamacpp_auto_start" in data and data["llamacpp_auto_start"] is not None:
        set_env_runtime_value(
            "JAVSTORY_LLAMACPP_AUTO_START",
            "1" if data["llamacpp_auto_start"] else "0",
        )

    if "llamacpp_fit_vram" in data and data["llamacpp_fit_vram"] is not None:
        set_env_runtime_value(
            "JAVSTORY_LLAMACPP_FIT",
            "on" if data["llamacpp_fit_vram"] else "off",
        )

    active = llamacpp_model_from_env()
    if is_gguf_option_id(active):
        if parse_gguf_option_id(active) is None:
            raise HTTPException(400, f"GGUF 파일 없음: {active[len('gguf:'):]}")
    elif active not in LLAMACPP_MODEL_PRESETS:
        try:
            resolve_llamacpp_preset(active)
        except Exception as exc:
            raise HTTPException(400, f"알 수 없는 llama.cpp 모델: {active}") from exc

    return _translation_to_response(translation_settings_snapshot())


def _prompt_to_response(snap: dict) -> TranslationPromptSettingsResponse:
    return TranslationPromptSettingsResponse(**snap)


@router.get("/translation-prompt", response_model=TranslationPromptSettingsResponse)
def get_translation_prompt_settings():
    return _prompt_to_response(translation_prompt_settings_snapshot())


@router.patch("/translation-prompt", response_model=TranslationPromptSettingsResponse)
def patch_translation_prompt_settings(body: TranslationPromptSettingsPatch):
    from javstory.config.secrets_manager import set_env_runtime_value
    from javstory.translation.translation_notes import save_global_note
    from javstory.translation.translation_prompt_config import save_system_prompt_template

    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(400, "수정할 필드가 없습니다")

    if data.get("reset_system_prompt"):
        save_system_prompt_template("")

    if "prompt_mode" in data and data["prompt_mode"]:
        set_env_runtime_value(
            "JAVSTORY_TRANSLATION_PROMPT_MODE",
            normalize_prompt_mode(data["prompt_mode"]),
        )

    if "prompt_variant" in data and data["prompt_variant"]:
        variant = normalize_prompt_variant(data["prompt_variant"])
        set_env_runtime_value("JAVSTORY_TRANSLATION_PROMPT_VARIANT", variant)
        if not data.get("reset_system_prompt") and "system_prompt_template" not in data:
            save_system_prompt_template("")

    if "system_prompt_template" in data and not data.get("reset_system_prompt"):
        save_system_prompt_template(str(data["system_prompt_template"] or ""))

    if "global_note" in data:
        save_global_note(str(data["global_note"] or ""))
        set_env_runtime_value("JAVSTORY_TRANSLATION_NOTE_GLOBAL", str(data["global_note"] or ""))

    return _prompt_to_response(translation_prompt_settings_snapshot())


@router.get("/embeddings", response_model=EmbeddingsSettingsResponse)
def get_embeddings_settings():
    from javstory.library.embeddings.web_status import embeddings_settings_snapshot

    return EmbeddingsSettingsResponse(**embeddings_settings_snapshot())


@router.patch("/embeddings", response_model=EmbeddingsSettingsResponse)
def patch_embeddings_settings(body: EmbeddingsSettingsPatch):
    from javstory.config.secrets_manager import set_env_runtime_value
    from javstory.library.embeddings.web_status import embeddings_settings_snapshot

    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(400, "수정할 필드가 없습니다")

    if "enabled" in data and data["enabled"] is not None:
        set_env_runtime_value(
            "JAVSTORY_EMBEDDINGS_ENABLED",
            "1" if data["enabled"] else "0",
        )
    if "model" in data:
        model = str(data["model"] or "").strip()
        if not model:
            raise HTTPException(400, "model is required")
        set_env_runtime_value("JAVSTORY_EMBEDDINGS_OLLAMA_MODEL", model)

    return EmbeddingsSettingsResponse(**embeddings_settings_snapshot())
