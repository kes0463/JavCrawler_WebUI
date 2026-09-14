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
    EmbeddingsGgufOptionsResponse,
    FasterWhisperModelOption,
    HarvestSettingsPatch,
    HarvestSettingsResponse,
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
        # omniroute/gemini는 JAVSTORY_LLM_PLATFORM을 건드리지 않는다 — 그 변수는
        # harvest/correction/데스크톱 GUI가 공유하는 llamacpp|ollama|openai 3-way
        # 스위치라, 값을 넣으면 그쪽의 platform-suffixed override가 깨진다.
        # 번역 provider 판단은 _effective_translation_provider가 JAVSTORY_TRANSLATION_PROVIDER를
        # 직접 보고 처리한다.

    if "openrouter_profile" in data and data["openrouter_profile"]:
        prof = str(data["openrouter_profile"]).strip().lower()
        set_env_runtime_value("JAVSTORY_TRANSLATION_PROFILE", prof)

    if "omniroute_url" in data and data["omniroute_url"]:
        url = str(data["omniroute_url"]).strip().rstrip("/")
        set_env_runtime_value("JAVSTORY_OMNIROUTE_URL", url)

    if "omniroute_model" in data:
        set_env_runtime_value("JAVSTORY_OMNIROUTE_MODEL", str(data["omniroute_model"] or "").strip())

    if "gemini_api_key" in data and data["gemini_api_key"]:
        set_env_runtime_value("JAVSTORY_GEMINI_API_KEY", str(data["gemini_api_key"]).strip())

    if "gemini_chain" in data and data["gemini_chain"]:
        # 체인 1순위가 곧 기본 모델 — 별도 "기본 모델" 필드를 두지 않고 체인 저장 시
        # JAVSTORY_GEMINI_MODEL을 체인[0]으로 동기화한다. 카탈로그 키 그대로 저장하고
        # 별칭(-preview 등) 정규화는 실제 API 호출 직전(gemini_translation_llm_tier)에서만 한다
        # — 여기서 정규화하면 model_options[].id와 어긋나 저장 후 드롭다운이 비어 보인다.
        chain = [str(m).strip() for m in data["gemini_chain"] if str(m).strip()]
        set_env_runtime_value("JAVSTORY_GEMINI_TRANSLATION_CHAIN", ",".join(chain))
        if chain:
            set_env_runtime_value("JAVSTORY_GEMINI_MODEL", chain[0])

    if "gemini_chunk_target_lines" in data and data["gemini_chunk_target_lines"] is not None:
        set_env_runtime_value(
            "JAVSTORY_TRANSLATION_GEMINI_CHUNK_TARGET_LINES", str(data["gemini_chunk_target_lines"])
        )
    if "gemini_chunk_overlap_lines" in data and data["gemini_chunk_overlap_lines"] is not None:
        set_env_runtime_value(
            "JAVSTORY_TRANSLATION_GEMINI_CHUNK_OVERLAP_LINES", str(data["gemini_chunk_overlap_lines"])
        )

    if "llamacpp_chunk_target_lines" in data and data["llamacpp_chunk_target_lines"] is not None:
        set_env_runtime_value(
            "JAVSTORY_TRANSLATION_LLAMACPP_CHUNK_TARGET_LINES", str(data["llamacpp_chunk_target_lines"])
        )
    if "llamacpp_chunk_overlap_lines" in data and data["llamacpp_chunk_overlap_lines"] is not None:
        set_env_runtime_value(
            "JAVSTORY_TRANSLATION_LLAMACPP_CHUNK_OVERLAP_LINES", str(data["llamacpp_chunk_overlap_lines"])
        )
    if "ollama_chunk_target_lines" in data and data["ollama_chunk_target_lines"] is not None:
        set_env_runtime_value(
            "JAVSTORY_TRANSLATION_OLLAMA_CHUNK_TARGET_LINES", str(data["ollama_chunk_target_lines"])
        )
    if "ollama_chunk_overlap_lines" in data and data["ollama_chunk_overlap_lines"] is not None:
        set_env_runtime_value(
            "JAVSTORY_TRANSLATION_OLLAMA_CHUNK_OVERLAP_LINES", str(data["ollama_chunk_overlap_lines"])
        )
    if "ollama_context_length" in data and data["ollama_context_length"] is not None:
        set_env_runtime_value("OLLAMA_NUM_CTX", str(data["ollama_context_length"]))
    if "openrouter_chunk_target_lines" in data and data["openrouter_chunk_target_lines"] is not None:
        set_env_runtime_value(
            "JAVSTORY_TRANSLATION_OPENROUTER_CHUNK_TARGET_LINES", str(data["openrouter_chunk_target_lines"])
        )
    if "openrouter_chunk_overlap_lines" in data and data["openrouter_chunk_overlap_lines"] is not None:
        set_env_runtime_value(
            "JAVSTORY_TRANSLATION_OPENROUTER_CHUNK_OVERLAP_LINES", str(data["openrouter_chunk_overlap_lines"])
        )
    if "omniroute_chunk_target_lines" in data and data["omniroute_chunk_target_lines"] is not None:
        set_env_runtime_value(
            "JAVSTORY_TRANSLATION_OMNIROUTE_CHUNK_TARGET_LINES", str(data["omniroute_chunk_target_lines"])
        )
    if "omniroute_chunk_overlap_lines" in data and data["omniroute_chunk_overlap_lines"] is not None:
        set_env_runtime_value(
            "JAVSTORY_TRANSLATION_OMNIROUTE_CHUNK_OVERLAP_LINES", str(data["omniroute_chunk_overlap_lines"])
        )
    if "omniroute_context_length" in data and data["omniroute_context_length"] is not None:
        set_env_runtime_value(
            "JAVSTORY_TRANSLATION_OMNIROUTE_MAX_CTX", str(data["omniroute_context_length"])
        )

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


@router.get("/embeddings/gguf-options", response_model=EmbeddingsGgufOptionsResponse)
def get_embeddings_gguf_options():
    from javstory.library.embeddings.web_status import embeddings_gguf_options_snapshot

    return EmbeddingsGgufOptionsResponse(**embeddings_gguf_options_snapshot())


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
    if "backend" in data and data["backend"] is not None:
        backend = str(data["backend"] or "").strip().lower() or "llamacpp"
        if backend not in ("llamacpp", "ollama"):
            raise HTTPException(400, "backend must be llamacpp or ollama")
        set_env_runtime_value("JAVSTORY_EMBEDDINGS_BACKEND", backend)
    if "model" in data:
        model = str(data["model"] or "").strip()
        if not model:
            raise HTTPException(400, "model is required")
        set_env_runtime_value("JAVSTORY_EMBEDDINGS_MODEL", model)
        # 하위 호환
        set_env_runtime_value("JAVSTORY_EMBEDDINGS_OLLAMA_MODEL", model)
    if "gguf_path" in data:
        from pathlib import Path

        gguf = str(data["gguf_path"] or "").strip()
        if gguf:
            p = Path(gguf).expanduser()
            if not p.is_file():
                raise HTTPException(400, f"GGUF 파일 없음: {gguf}")
            gguf = str(p.resolve())
        set_env_runtime_value("JAVSTORY_EMBEDDINGS_LLAMACPP_GGUF", gguf)
        from javstory.llm.llamacpp_embeddings import invalidate_embeddings_gguf_cache

        invalidate_embeddings_gguf_cache()

    if "batch_size" in data and data["batch_size"] is not None:
        set_env_runtime_value(
            "JAVSTORY_EMBEDDINGS_LLAMACPP_BATCH_SIZE",
            str(int(data["batch_size"])),
        )

    search_env_changed = False
    if "search_min_score" in data and data["search_min_score"] is not None:
        set_env_runtime_value(
            "JAVSTORY_EMBEDDING_SEARCH_MIN_SCORE",
            f"{float(data['search_min_score']):.4f}",
        )
        search_env_changed = True
    if "search_relative_ratio" in data and data["search_relative_ratio"] is not None:
        set_env_runtime_value(
            "JAVSTORY_EMBEDDING_SEARCH_RELATIVE_RATIO",
            f"{float(data['search_relative_ratio']):.4f}",
        )
        search_env_changed = True
    if "search_max_gap" in data and data["search_max_gap"] is not None:
        set_env_runtime_value(
            "JAVSTORY_EMBEDDING_SEARCH_MAX_GAP",
            f"{float(data['search_max_gap']):.4f}",
        )
        search_env_changed = True
    if search_env_changed:
        from javstory.search.library_search import clear_embed_search_cache

        clear_embed_search_cache()

    # 모델/GGUF 변경 시 ANN 인덱스 재빌드 유도
    if any(k in data for k in ("model", "gguf_path", "enabled", "backend")):
        try:
            from javstory.library.embeddings.ann_index import invalidate_embedding_ann_index

            invalidate_embedding_ann_index(None)
        except Exception:
            pass

    from javstory.library.embeddings.web_status import invalidate_embeddings_coverage_cache

    invalidate_embeddings_coverage_cache()
    return EmbeddingsSettingsResponse(**embeddings_settings_snapshot())


@router.get("/harvest", response_model=HarvestSettingsResponse)
def get_harvest_settings():
    from javstory.library.embeddings.harvest_coordination import harvest_settings_snapshot

    return HarvestSettingsResponse(**harvest_settings_snapshot())


@router.patch("/harvest", response_model=HarvestSettingsResponse)
def patch_harvest_settings(body: HarvestSettingsPatch):
    from javstory.config.secrets_manager import set_env_runtime_value
    from javstory.library.embeddings.harvest_coordination import harvest_settings_snapshot

    data = body.model_dump(exclude_unset=True)
    if "harvest_concurrency" in data and data["harvest_concurrency"] is not None:
        set_env_runtime_value(
            "JAVSTORY_HARVEST_CONCURRENCY",
            str(int(data["harvest_concurrency"])),
        )
    if "embeddings_pause_during_harvest" in data and data["embeddings_pause_during_harvest"] is not None:
        set_env_runtime_value(
            "JAVSTORY_EMBEDDINGS_PAUSE_DURING_HARVEST",
            "1" if data["embeddings_pause_during_harvest"] else "0",
        )
    if "harvest_llamacpp_slot_ctx" in data:
        slot = data["harvest_llamacpp_slot_ctx"]
        if slot is None:
            set_env_runtime_value("JAVSTORY_HARVEST_LLAMACPP_SLOT_CTX", "")
        else:
            set_env_runtime_value("JAVSTORY_HARVEST_LLAMACPP_SLOT_CTX", str(int(slot)))

    return HarvestSettingsResponse(**harvest_settings_snapshot())
