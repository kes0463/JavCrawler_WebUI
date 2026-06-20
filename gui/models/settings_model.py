"""설정 모델: API 키, 경로, 테마, 모델, 옵션 관리."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot, QMetaObject, Qt, QTimer

_ROOT = Path(__file__).resolve().parent.parent.parent


class SettingsModel(QObject):
    apiKeyChanged = Signal()
    geminiApiKeyChanged = Signal()
    ollamaUrlChanged = Signal()
    llmPlatformChanged = Signal()
    llamacppUrlChanged = Signal()
    llamacppBinChanged = Signal()
    llamacppModelsDirChanged = Signal()
    llamacppModelChanged = Signal()
    llamacppGemmaGgufChanged = Signal()
    llamacppQwen14bGgufChanged = Signal()
    llamacppQwen14bUncGgufChanged = Signal()
    llamacppCacheTypeKChanged = Signal()
    llamacppCacheTypeVChanged = Signal()
    llamacppCtxChanged = Signal()
    llamacppMaxTokensChanged = Signal()
    llamacppStopAfterJobChanged = Signal()
    llamacppPromptCacheChanged = Signal()
    llamacppAutoStartChanged = Signal()
    personaCardPresetChanged = Signal()
    personaChatModelChanged = Signal()
    mediaRootChanged = Signal()
    whisperModelChanged = Signal()
    translationProfileChanged = Signal()
    translationNoteGlobalChanged = Signal()
    harvestTranslationModelChanged = Signal()
    grokEnabledChanged = Signal()
    dpiBypassChanged = Signal()
    themeModeChanged = Signal()
    isSystemDarkChanged = Signal()
    correctionProfileChanged = Signal()
    harvestConcurrencyChanged = Signal()
    ladaOptionsChanged = Signal()
    cudaDevicesChanged = Signal()
    embeddingsEnabledChanged = Signal()
    embeddingsModelChanged = Signal()
    excludedGenresChanged = Signal()
    insightHarvestAlertEnabledChanged = Signal()
    insightHarvestAlertThresholdChanged = Signal()
    personaDeepAnalysisEnabledChanged = Signal()
    personaSampleSizeChanged = Signal()
    toastMessage = Signal(str, str)
    similarEmbeddingsReady = Signal(str, str, str)  # productCode, model, formattedText


    def __init__(self, parent=None):
        super().__init__(parent)
        print("[SettingsModel] Loading values...")
        self._load_values()
        print("[SettingsModel] Initialization complete.")
        # 테마 리스너는 안정화될 때까지 비활성화 유지 (필요 시 주석 제거)
        # self._start_theme_listener()

    @staticmethod
    def _platform_env_suffix(platform: str) -> str:
        p = (platform or "openai").strip().lower()
        if p == "llamacpp":
            return "LLAMACPP"
        if p == "ollama":
            return "OLLAMA"
        return "OPENAI"

    @classmethod
    def _platform_env_value(cls, base_key: str, platform: str, default: str) -> str:
        suffix_key = f"{base_key}_{cls._platform_env_suffix(platform)}"
        raw = (os.environ.get(suffix_key, "") or "").strip()
        if raw:
            return raw
        return (os.environ.get(base_key, default) or default).strip()

    @staticmethod
    def _platform_translation_defaults(platform: str) -> tuple[str, str, str]:
        p = (platform or "openai").strip().lower()
        if p == "llamacpp":
            return (
                "budget",
                "llamacpp:gemma-4-e4b",
                "llamacpp:gemma-4-e4b-uncensored",
            )
        if p == "ollama":
            return ("budget", "ollama:gemma4:e4b", "ollama:gemma4:e4b")
        return (
            "default",
            "openrouter:deepseek/deepseek-v3.2",
            "qwen/qwen3-235b-a22b-2507",
        )

    @staticmethod
    def _llamacpp_base_model_id(value: str | None) -> str:
        raw = (value or "").strip().lower()
        if raw.startswith("llamacpp:"):
            raw = raw.split(":", 1)[1].strip()
        if "qwen3-14" in raw or "qwen3_14" in raw or ("qwen" in raw and "14" in raw):
            return "qwen3-14b"
        if "qwen3.5" in raw or "35b" in raw or "a3b" in raw:
            return "qwen3-14b"
        if "gemma" in raw:
            return "gemma-4-e4b"
        return "gemma-4-e4b"

    @staticmethod
    def _persona_card_preset_id(value: str | None) -> str:
        return SettingsModel._llamacpp_base_model_id(value)

    @staticmethod
    def _persona_chat_model_id(value: str | None) -> str:
        raw = (value or "").strip().lower()
        if raw.startswith("llamacpp:"):
            raw = raw.split(":", 1)[1].strip()
        if "qwen3-14" in raw or "qwen3_14" in raw or ("qwen" in raw and "14" in raw):
            return "qwen3-14b-uncensored"
        if "qwen3.5" in raw or "35b" in raw or "a3b" in raw:
            return "qwen3-14b-uncensored"
        if "gemma" in raw:
            return "gemma-4-e4b-uncensored"
        return "gemma-4-e4b-uncensored"

    def _sync_llamacpp_translation_models_to_active(self, *, emit: bool = True) -> None:
        """Keep llama.cpp translation/correction choices on the selected base model."""
        base = self._llamacpp_base_model_id(str(getattr(self, "_llamacpp_model", "") or ""))
        profile = "qwen3_14" if base == "qwen3-14b" else "budget"
        harvest = f"llamacpp:{base}"
        correction = f"llamacpp:{base}-uncensored"

        if profile != getattr(self, "_translation_profile", ""):
            self._translation_profile = profile
            if emit:
                self.translationProfileChanged.emit()
        if harvest != getattr(self, "_harvest_translation_model", ""):
            self._harvest_translation_model = harvest
            if emit:
                self.harvestTranslationModelChanged.emit()
        if correction != getattr(self, "_correction_profile", ""):
            self._correction_profile = correction
            if emit:
                self.correctionProfileChanged.emit()

    def _apply_llamacpp_model_runtime_defaults(self, *, emit: bool = True) -> None:
        """Dense Gemma/Qwen3-14B presets share the generic runtime fields."""
        return

    def _cache_platform_translation_values(self, platform: str) -> None:
        suffix = self._platform_env_suffix(platform)
        os.environ[f"JAVSTORY_TRANSLATION_PROFILE_{suffix}"] = str(
            getattr(self, "_translation_profile", "") or ""
        )
        os.environ[f"JAVSTORY_HARVEST_TRANSLATION_MODEL_{suffix}"] = str(
            getattr(self, "_harvest_translation_model", "") or ""
        )
        os.environ[f"JAVSTORY_CORRECTION_PASS2_MODEL_{suffix}"] = str(
            getattr(self, "_correction_profile", "") or ""
        )

    def _restore_platform_translation_values(self, platform: str) -> None:
        profile_default, harvest_default, correction_default = self._platform_translation_defaults(platform)
        suffix = self._platform_env_suffix(platform)
        profile = (
            os.environ.get(f"JAVSTORY_TRANSLATION_PROFILE_{suffix}", "")
            or profile_default
        ).strip().lower()
        harvest = (
            os.environ.get(f"JAVSTORY_HARVEST_TRANSLATION_MODEL_{suffix}", "")
            or harvest_default
        ).strip() or harvest_default
        correction = (
            os.environ.get(f"JAVSTORY_CORRECTION_PASS2_MODEL_{suffix}", "")
            or correction_default
        ).strip() or correction_default

        if profile != getattr(self, "_translation_profile", ""):
            self._translation_profile = profile
            self.translationProfileChanged.emit()
        if harvest != getattr(self, "_harvest_translation_model", ""):
            self._harvest_translation_model = harvest
            self.harvestTranslationModelChanged.emit()
        if correction != getattr(self, "_correction_profile", ""):
            self._correction_profile = correction
            self.correctionProfileChanged.emit()

    def _translation_provider_for_profile(self, platform: str | None = None) -> str:
        p = (platform or getattr(self, "_llm_platform", "openai") or "openai").strip().lower()
        if p == "llamacpp":
            return "llamacpp"
        if p == "ollama":
            return "ollama"
        prof = str(getattr(self, "_translation_profile", "") or "").strip().lower()
        if prof.startswith("gemini_") or prof.startswith("gemini"):
            return "gemini"
        return "openrouter"

    def _normalize_loaded_translation_values(self) -> None:
        """기존 공통 env가 현재 플랫폼 옵션과 안 맞을 때 시작값 보정."""
        platform = str(getattr(self, "_llm_platform", "openai") or "openai")
        if platform != "llamacpp":
            return

        self._llamacpp_model = self._llamacpp_base_model_id(
            str(getattr(self, "_llamacpp_model", "") or "")
        )
        self._sync_llamacpp_translation_models_to_active(emit=False)
        self._apply_llamacpp_model_runtime_defaults(emit=False)

    def _start_theme_listener(self):
        """시스템 테마 변화 감지 시작."""
        print("[SettingsModel] Starting theme listener...")
        try:
            import darkdetect
            darkdetect.listener(lambda _: self.isSystemDarkChanged.emit())
        except Exception:
            pass

    def _load_values(self):
        from javstory.config.app_config import OLLAMA_BASE_URL, E_MEDIA_ROOT
        try:
            from javstory.config import secrets_manager
            self._api_key = secrets_manager.get_openrouter_api_key() or ""
            self._gemini_api_key = secrets_manager.get_gemini_api_key() or ""
        except Exception:
            self._api_key = ""
            self._gemini_api_key = ""

        def _env_bool(key: str, default: bool) -> bool:
            try:
                raw = os.environ.get(key, "1" if default else "0")
                v = (raw or "").strip().lower()
                return v in ("1", "true", "yes", "on")
            except Exception:
                return bool(default)

        def _env_int(key: str, default: int) -> int:
            try:
                return int((os.environ.get(key, str(int(default))) or "").strip())
            except Exception:
                return int(default)
        
        # 1. API 및 미디어
        from javstory.config.app_config import LLAMACPP_BASE_URL, llm_platform_from_env
        from javstory.llm.llamacpp_backend import (
            LLAMACPP_DEFAULT_CTX_DENSE,
            LLAMACPP_DEFAULT_MAX_TOKENS,
            LLAMACPP_DEFAULT_PROMPT_CACHE_MIB,
            LLAMACPP_SERVER_DEFAULT_PROMPT_CACHE_MIB,
        )

        self._llm_platform = llm_platform_from_env()
        self._ollama_url = os.environ.get("JAVSTORY_OLLAMA_URL", OLLAMA_BASE_URL)
        self._llamacpp_url = os.environ.get("JAVSTORY_LLAMACPP_URL", LLAMACPP_BASE_URL)
        self._llamacpp_bin = os.environ.get("JAVSTORY_LLAMACPP_BIN", "")
        self._llamacpp_models_dir = os.environ.get("JAVSTORY_LLAMACPP_MODELS_DIR", "")
        self._llamacpp_model = self._llamacpp_base_model_id(
            os.environ.get("JAVSTORY_LLAMACPP_MODEL", "gemma-4-e4b")
        )
        self._persona_card_preset = self._persona_card_preset_id(
            os.environ.get(
                "JAVSTORY_PERSONA_CARD_PRESET",
                os.environ.get("JAVSTORY_LLAMACPP_PRESET", self._llamacpp_model),
            )
        )
        self._persona_chat_model = self._persona_chat_model_id(
            os.environ.get("JAVSTORY_PERSONA_CHAT_MODEL", "gemma-4-e4b-uncensored")
        )
        self._llamacpp_gemma_gguf = os.environ.get("JAVSTORY_LLAMACPP_GEMMA4_GGUF", "")
        self._llamacpp_qwen14b_gguf = os.environ.get("JAVSTORY_LLAMACPP_QWEN3_14B_GGUF", "")
        self._llamacpp_qwen14b_unc_gguf = os.environ.get("JAVSTORY_LLAMACPP_QWEN3_14B_UNC_GGUF", "")
        self._llamacpp_cache_type_k = os.environ.get("JAVSTORY_LLAMACPP_CACHE_TYPE_K", "turbo3")
        self._llamacpp_cache_type_v = os.environ.get("JAVSTORY_LLAMACPP_CACHE_TYPE_V", "q8_0")
        self._llamacpp_auto_start = _env_bool("JAVSTORY_LLAMACPP_AUTO_START", True)
        _ctx_raw = (os.environ.get("JAVSTORY_LLAMACPP_CTX", "") or "").strip()
        self._llamacpp_ctx = _ctx_raw or str(LLAMACPP_DEFAULT_CTX_DENSE)
        _mt_raw = (
            (os.environ.get("JAVSTORY_TRANSLATION_LLAMACPP_MAX_TOKENS", "") or "").strip()
            or (os.environ.get("JAVSTORY_CORRECTION_LLAMACPP_MAX_TOKENS", "") or "").strip()
        )
        self._llamacpp_max_tokens = _mt_raw or str(LLAMACPP_DEFAULT_MAX_TOKENS)
        self._llamacpp_stop_after_job = _env_bool("JAVSTORY_LLAMACPP_STOP_AFTER_JOB", False)
        _pcm_raw = (os.environ.get("JAVSTORY_LLAMACPP_PROMPT_CACHE_MB", "") or "").strip()
        if _pcm_raw:
            try:
                _pcm = int(_pcm_raw)
            except ValueError:
                _pcm = LLAMACPP_DEFAULT_PROMPT_CACHE_MIB
        else:
            _pcm = LLAMACPP_DEFAULT_PROMPT_CACHE_MIB
        self._llamacpp_prompt_cache = _pcm > 0
        self._llamacpp_prompt_cache_mib = (
            LLAMACPP_SERVER_DEFAULT_PROMPT_CACHE_MIB if self._llamacpp_prompt_cache else 0
        )
        self._media_root = os.environ.get("JAVSTORY_MEDIA_ROOT", str(E_MEDIA_ROOT))
        
        # 2. 모델 및 번역
        self._whisper_model = os.environ.get("JAVSTORY_WHISPER_MODEL", "large-v2")
        profile_default, harvest_default, correction_default = self._platform_translation_defaults(
            self._llm_platform
        )
        self._translation_profile = self._platform_env_value(
            "JAVSTORY_TRANSLATION_PROFILE",
            self._llm_platform,
            profile_default,
        ).lower()
        self._harvest_translation_model = (
            self._platform_env_value(
                "JAVSTORY_HARVEST_TRANSLATION_MODEL",
                self._llm_platform,
                harvest_default,
            )
            or harvest_default
        )
        # 전역 번역 노트(공통 규칙·표기 정책 등) — Gemini 프롬프트의 {{note}}에 합쳐 주입됨
        # 파일 저장(`data/notes/translation_note_global.txt`); .env 폴백 호환.
        try:
            from javstory.translation.translation_notes import load_global_note
            self._translation_note_global = load_global_note() or ""
        except Exception:
            self._translation_note_global = os.environ.get("JAVSTORY_TRANSLATION_NOTE_GLOBAL", "") or ""
        
        # 3. 기능 토글
        self._grok_enabled = _env_bool("JAVSTORY_STORY_ANALYSIS_ENABLED", True)
        self._dpi_bypass = _env_bool("JAVSTORY_DPI_BYPASS_ENABLED", False)
        self._embeddings_enabled = _env_bool("JAVSTORY_EMBEDDINGS_ENABLED", False)
        self._embeddings_ollama_model = (os.environ.get("JAVSTORY_EMBEDDINGS_OLLAMA_MODEL", "") or "").strip() or "nomic-embed-text"
        self._insight_harvest_alert_enabled = _env_bool("JAVSTORY_INSIGHT_HARVEST_ALERT_ENABLED", True)
        try:
            self._insight_harvest_alert_threshold = float(
                os.environ.get("JAVSTORY_INSIGHT_HARVEST_ALERT_THRESHOLD", "0.85") or "0.85"
            )
        except ValueError:
            self._insight_harvest_alert_threshold = 0.85
        self._insight_harvest_alert_threshold = max(0.5, min(1.0, self._insight_harvest_alert_threshold))
        self._persona_deep_enabled = _env_bool("JAVSTORY_PERSONA_DEEP_ENABLED", True)
        try:
            self._persona_sample_size = int(os.environ.get("JAVSTORY_PERSONA_SAMPLE_SIZE", "8") or "8")
        except ValueError:
            self._persona_sample_size = 8
        self._persona_sample_size = max(4, min(12, int(self._persona_sample_size or 8)))

        # 3-c. 유사도 제외 장르 (Similarity Excluded Genres)
        from javstory.config.app_config import SIMILARITY_EXCLUDED_GENRES
        default_excluded = ",".join(sorted(list(SIMILARITY_EXCLUDED_GENRES)))
        self._excluded_genres = os.environ.get("JAVSTORY_SIMILARITY_EXCLUDED_GENRES", default_excluded)

        # Harvest 동시 실행 수(1~5)
        try:
            self._harvest_concurrency = int(os.environ.get("JAVSTORY_HARVEST_CONCURRENCY", "2"))
        except ValueError:
            self._harvest_concurrency = 2
        self._harvest_concurrency = max(1, min(5, int(self._harvest_concurrency or 2)))

        # 3-b. LADA 모자이크 제거 옵션 (1~3)
        self._lada_parallel = max(1, min(3, _env_int("JAVSTORY_LADA_PARALLEL", 2)))
        self._lada_passes = max(1, min(3, _env_int("JAVSTORY_LADA_PASSES", 2)))
        self._lada_encoder = (os.environ.get("JAVSTORY_LADA_ENCODER", "hevc_nvenc") or "hevc_nvenc").strip()
        self._lada_encoding_preset = (os.environ.get("JAVSTORY_LADA_ENCODING_PRESET", "hevc-nvidia-gpu-balanced") or "hevc-nvidia-gpu-balanced").strip()
        self._lada_fp16 = _env_bool("JAVSTORY_LADA_FP16", True)

        def _pass_det(i: int) -> str:
            return (os.environ.get(f"JAVSTORY_LADA_PASS{i}_DET_MODEL", "v4-fast") or "v4-fast").strip()

        def _pass_rest(i: int) -> str:
            return (os.environ.get(f"JAVSTORY_LADA_PASS{i}_REST_MODEL", "basicvsrpp-v1.2") or "basicvsrpp-v1.2").strip()

        def _pass_clip(i: int) -> int:
            return max(20, min(400, _env_int(f"JAVSTORY_LADA_PASS{i}_MAX_CLIP_LENGTH", 180)))

        def _pass_face(i: int) -> bool:
            return _env_bool(f"JAVSTORY_LADA_PASS{i}_DETECT_FACE", False)

        self._lada_pass1_det_model = _pass_det(1)
        self._lada_pass1_rest_model = _pass_rest(1)
        self._lada_pass1_max_clip_length = _pass_clip(1)
        self._lada_pass1_detect_face = _pass_face(1)

        self._lada_pass2_det_model = _pass_det(2)
        self._lada_pass2_rest_model = _pass_rest(2)
        self._lada_pass2_max_clip_length = _pass_clip(2)
        self._lada_pass2_detect_face = _pass_face(2)

        self._lada_pass3_det_model = _pass_det(3)
        self._lada_pass3_rest_model = _pass_rest(3)
        self._lada_pass3_max_clip_length = _pass_clip(3)
        self._lada_pass3_detect_face = _pass_face(3)

        # CUDA 디바이스 목록(표시용) — nvidia-smi 호출은 백그라운드 스레드에서 수행
        self._cuda_devices: list[str] = []
        QTimer.singleShot(0, self._start_cuda_detection)

        # 4. 교정 (Correction) 모델
        self._correction_profile = self._platform_env_value(
            "JAVSTORY_CORRECTION_PASS2_MODEL",
            self._llm_platform,
            correction_default,
        )
        self._normalize_loaded_translation_values()
        self._correction_skip = _env_bool("JAVSTORY_CORRECTION_SKIP", False)
        
        # 5. 외관 (테마)
        try:
            self._theme_mode = int(os.environ.get("JAVSTORY_THEME_MODE", "0"))
        except ValueError:
            self._theme_mode = 0

    # ── Properties ────────────────────────────────────

    @Property(str, notify=apiKeyChanged)
    def apiKey(self): return self._api_key
    @apiKey.setter  # type: ignore[attr-defined]
    def apiKey(self, v):
        if v != self._api_key:
            self._api_key = v; self.apiKeyChanged.emit()

    @Property(str, notify=geminiApiKeyChanged)
    def geminiApiKey(self) -> str:
        return str(getattr(self, "_gemini_api_key", "") or "")

    @geminiApiKey.setter  # type: ignore[attr-defined]
    def geminiApiKey(self, v: str):
        s = str(v or "")
        if s != str(getattr(self, "_gemini_api_key", "") or ""):
            self._gemini_api_key = s
            self.geminiApiKeyChanged.emit()

    @Property(str, notify=ollamaUrlChanged)
    def ollamaUrl(self): return self._ollama_url
    @ollamaUrl.setter  # type: ignore[attr-defined]
    def ollamaUrl(self, v):
        if v != self._ollama_url:
            self._ollama_url = v; self.ollamaUrlChanged.emit()

    @Property(str, notify=llmPlatformChanged)
    def llmPlatform(self) -> str:
        return str(getattr(self, "_llm_platform", "openai") or "openai")

    @llmPlatform.setter  # type: ignore[attr-defined]
    def llmPlatform(self, v: str):
        s = (v or "openai").strip().lower()
        if s not in ("openai", "ollama", "llamacpp"):
            s = "openai"
        old = getattr(self, "_llm_platform", "openai")
        if s != old:
            self._cache_platform_translation_values(old)
            self._llm_platform = s
            self._restore_platform_translation_values(s)
            self.llmPlatformChanged.emit()

    @Property(str, notify=llamacppUrlChanged)
    def llamacppUrl(self) -> str:
        return str(getattr(self, "_llamacpp_url", "") or "")

    @llamacppUrl.setter  # type: ignore[attr-defined]
    def llamacppUrl(self, v: str):
        s = str(v or "")
        if s != getattr(self, "_llamacpp_url", ""):
            self._llamacpp_url = s
            self.llamacppUrlChanged.emit()

    @Property(str, notify=llamacppBinChanged)
    def llamacppBin(self) -> str:
        return str(getattr(self, "_llamacpp_bin", "") or "")

    @llamacppBin.setter  # type: ignore[attr-defined]
    def llamacppBin(self, v: str):
        s = str(v or "")
        if s != getattr(self, "_llamacpp_bin", ""):
            self._llamacpp_bin = s
            self.llamacppBinChanged.emit()

    @Property(str, notify=llamacppModelsDirChanged)
    def llamacppModelsDir(self) -> str:
        return str(getattr(self, "_llamacpp_models_dir", "") or "")

    @llamacppModelsDir.setter  # type: ignore[attr-defined]
    def llamacppModelsDir(self, v: str):
        s = str(v or "")
        if s != getattr(self, "_llamacpp_models_dir", ""):
            self._llamacpp_models_dir = s
            self.llamacppModelsDirChanged.emit()

    @Property(str, notify=llamacppModelChanged)
    def llamacppModel(self) -> str:
        return str(getattr(self, "_llamacpp_model", "gemma-4-e4b") or "gemma-4-e4b")

    @llamacppModel.setter  # type: ignore[attr-defined]
    def llamacppModel(self, v: str):
        s = self._llamacpp_base_model_id(v)
        if s != getattr(self, "_llamacpp_model", ""):
            self._llamacpp_model = s
            if str(getattr(self, "_llm_platform", "") or "").lower() == "llamacpp":
                self._sync_llamacpp_translation_models_to_active()
                self._apply_llamacpp_model_runtime_defaults()
            self.llamacppModelChanged.emit()

    @Property(str, notify=llamacppGemmaGgufChanged)
    def llamacppGemmaGguf(self) -> str:
        return str(getattr(self, "_llamacpp_gemma_gguf", "") or "")

    @llamacppGemmaGguf.setter  # type: ignore[attr-defined]
    def llamacppGemmaGguf(self, v: str):
        s = str(v or "")
        if s != getattr(self, "_llamacpp_gemma_gguf", ""):
            self._llamacpp_gemma_gguf = s
            self.llamacppGemmaGgufChanged.emit()

    @Property(str, notify=llamacppQwen14bGgufChanged)
    def llamacppQwen14bGguf(self) -> str:
        return str(getattr(self, "_llamacpp_qwen14b_gguf", "") or "")

    @llamacppQwen14bGguf.setter  # type: ignore[attr-defined]
    def llamacppQwen14bGguf(self, v: str):
        s = str(v or "")
        if s != getattr(self, "_llamacpp_qwen14b_gguf", ""):
            self._llamacpp_qwen14b_gguf = s
            self.llamacppQwen14bGgufChanged.emit()

    @Property(str, notify=llamacppQwen14bUncGgufChanged)
    def llamacppQwen14bUncGguf(self) -> str:
        return str(getattr(self, "_llamacpp_qwen14b_unc_gguf", "") or "")

    @llamacppQwen14bUncGguf.setter  # type: ignore[attr-defined]
    def llamacppQwen14bUncGguf(self, v: str):
        s = str(v or "")
        if s != getattr(self, "_llamacpp_qwen14b_unc_gguf", ""):
            self._llamacpp_qwen14b_unc_gguf = s
            self.llamacppQwen14bUncGgufChanged.emit()

    @Property(str, notify=personaCardPresetChanged)
    def personaCardPreset(self) -> str:
        return str(getattr(self, "_persona_card_preset", "gemma-4-e4b") or "gemma-4-e4b")

    @personaCardPreset.setter  # type: ignore[attr-defined]
    def personaCardPreset(self, v: str):
        s = self._persona_card_preset_id(v)
        if s != getattr(self, "_persona_card_preset", ""):
            self._persona_card_preset = s
            self.personaCardPresetChanged.emit()

    @Property(str, notify=personaChatModelChanged)
    def personaChatModel(self) -> str:
        return str(getattr(self, "_persona_chat_model", "gemma-4-e4b-uncensored") or "gemma-4-e4b-uncensored")

    @personaChatModel.setter  # type: ignore[attr-defined]
    def personaChatModel(self, v: str):
        s = self._persona_chat_model_id(v)
        if s != getattr(self, "_persona_chat_model", ""):
            self._persona_chat_model = s
            self.personaChatModelChanged.emit()

    @Property("QVariantList", notify=personaCardPresetChanged)
    def availablePersonaCardPresets(self):
        return [
            {"id": "gemma-4-e4b", "label": "Gemma-4-E4B"},
            {"id": "qwen3-14b", "label": "Qwen3-14B"},
        ]

    @Property("QVariantList", notify=personaChatModelChanged)
    def availablePersonaChatModels(self):
        return [
            {"id": "gemma-4-e4b-uncensored", "label": "Gemma-4-E4B Uncensored"},
            {"id": "qwen3-14b-uncensored", "label": "Qwen3-14B Uncensored"},
        ]

    @Property(str, notify=llamacppCacheTypeKChanged)
    def llamacppCacheTypeK(self) -> str:
        return str(getattr(self, "_llamacpp_cache_type_k", "turbo3") or "turbo3")

    @llamacppCacheTypeK.setter  # type: ignore[attr-defined]
    def llamacppCacheTypeK(self, v: str):
        s = (v or "turbo3").strip() or "turbo3"
        if s != getattr(self, "_llamacpp_cache_type_k", ""):
            self._llamacpp_cache_type_k = s
            self.llamacppCacheTypeKChanged.emit()

    @Property(str, notify=llamacppCacheTypeVChanged)
    def llamacppCacheTypeV(self) -> str:
        return str(getattr(self, "_llamacpp_cache_type_v", "q8_0") or "q8_0")

    @llamacppCacheTypeV.setter  # type: ignore[attr-defined]
    def llamacppCacheTypeV(self, v: str):
        s = (v or "q8_0").strip() or "q8_0"
        if s != getattr(self, "_llamacpp_cache_type_v", ""):
            self._llamacpp_cache_type_v = s
            self.llamacppCacheTypeVChanged.emit()

    @Property(bool, notify=llamacppAutoStartChanged)
    def llamacppAutoStart(self) -> bool:
        return bool(getattr(self, "_llamacpp_auto_start", True))

    @llamacppAutoStart.setter  # type: ignore[attr-defined]
    def llamacppAutoStart(self, v: bool):
        b = bool(v)
        if b != bool(getattr(self, "_llamacpp_auto_start", True)):
            self._llamacpp_auto_start = b
            self.llamacppAutoStartChanged.emit()

    @Property(str, notify=llamacppCtxChanged)
    def llamacppCtx(self) -> str:
        return str(getattr(self, "_llamacpp_ctx", "4096") or "4096")

    @llamacppCtx.setter  # type: ignore[attr-defined]
    def llamacppCtx(self, v: str):
        s = (v or "").strip() or "4096"
        if s != getattr(self, "_llamacpp_ctx", ""):
            self._llamacpp_ctx = s
            self.llamacppCtxChanged.emit()

    @Property(str, notify=llamacppMaxTokensChanged)
    def llamacppMaxTokens(self) -> str:
        return str(getattr(self, "_llamacpp_max_tokens", "3072") or "3072")

    @llamacppMaxTokens.setter  # type: ignore[attr-defined]
    def llamacppMaxTokens(self, v: str):
        s = (v or "").strip() or "3072"
        if s != getattr(self, "_llamacpp_max_tokens", ""):
            self._llamacpp_max_tokens = s
            self.llamacppMaxTokensChanged.emit()

    @Property(bool, notify=llamacppStopAfterJobChanged)
    def llamacppStopAfterJob(self) -> bool:
        return bool(getattr(self, "_llamacpp_stop_after_job", False))

    @llamacppStopAfterJob.setter  # type: ignore[attr-defined]
    def llamacppStopAfterJob(self, v: bool):
        b = bool(v)
        if b != bool(getattr(self, "_llamacpp_stop_after_job", False)):
            self._llamacpp_stop_after_job = b
            self.llamacppStopAfterJobChanged.emit()

    @Property(bool, notify=llamacppPromptCacheChanged)
    def llamacppPromptCache(self) -> bool:
        return bool(getattr(self, "_llamacpp_prompt_cache", False))

    @llamacppPromptCache.setter  # type: ignore[attr-defined]
    def llamacppPromptCache(self, v: bool):
        b = bool(v)
        if b != bool(getattr(self, "_llamacpp_prompt_cache", False)):
            from javstory.llm.llamacpp_backend import LLAMACPP_SERVER_DEFAULT_PROMPT_CACHE_MIB

            self._llamacpp_prompt_cache = b
            self._llamacpp_prompt_cache_mib = (
                LLAMACPP_SERVER_DEFAULT_PROMPT_CACHE_MIB if b else 0
            )
            self.llamacppPromptCacheChanged.emit()

    @Property(str, notify=mediaRootChanged)
    def mediaRoot(self): return self._media_root
    @mediaRoot.setter  # type: ignore[attr-defined]
    def mediaRoot(self, v):
        if v != self._media_root:
            self._media_root = v; self.mediaRootChanged.emit()

    @Property(str, notify=whisperModelChanged)
    def whisperModel(self): return self._whisper_model
    @whisperModel.setter  # type: ignore[attr-defined]
    def whisperModel(self, v):
        if v != self._whisper_model:
            self._whisper_model = v; self.whisperModelChanged.emit()

    @Property(str, notify=translationProfileChanged)
    def translationProfile(self): return self._translation_profile
    @translationProfile.setter  # type: ignore[attr-defined]
    def translationProfile(self, v):
        if v != self._translation_profile:
            self._translation_profile = v; self.translationProfileChanged.emit()

    @Property(str, notify=translationNoteGlobalChanged)
    def translationNoteGlobal(self) -> str:
        return str(getattr(self, "_translation_note_global", "") or "")

    @translationNoteGlobal.setter  # type: ignore[attr-defined]
    def translationNoteGlobal(self, v: str):
        s = str(v or "")
        if s != str(getattr(self, "_translation_note_global", "") or ""):
            self._translation_note_global = s
            self.translationNoteGlobalChanged.emit()

    @Property(str, notify=harvestTranslationModelChanged)
    def harvestTranslationModel(self) -> str:
        return str(getattr(self, "_harvest_translation_model", "openrouter:deepseek/deepseek-v3.2") or "openrouter:deepseek/deepseek-v3.2")

    @harvestTranslationModel.setter  # type: ignore[attr-defined]
    def harvestTranslationModel(self, v: str):
        s = (v or "").strip() or "openrouter:deepseek/deepseek-v3.2"
        if s != getattr(self, "_harvest_translation_model", ""):
            self._harvest_translation_model = s
            self.harvestTranslationModelChanged.emit()

    @Property(bool, notify=grokEnabledChanged)
    def grokEnabled(self): return self._grok_enabled
    @grokEnabled.setter  # type: ignore[attr-defined]
    def grokEnabled(self, v):
        if v != self._grok_enabled:
            self._grok_enabled = v; self.grokEnabledChanged.emit()

    @Property(str, notify=correctionProfileChanged)
    def correctionProfile(self): return self._correction_profile
    @correctionProfile.setter  # type: ignore[attr-defined]
    def correctionProfile(self, v):
        if v != self._correction_profile:
            self._correction_profile = v; self.correctionProfileChanged.emit()

    @Property(bool, notify=correctionProfileChanged)
    def correctionSkip(self): return self._correction_skip
    @correctionSkip.setter  # type: ignore[attr-defined]
    def correctionSkip(self, v):
        if v != self._correction_skip:
            self._correction_skip = v
            from javstory.config.secrets_manager import set_env_runtime_value
            set_env_runtime_value("JAVSTORY_CORRECTION_SKIP", "1" if v else "0")
            self.correctionProfileChanged.emit()

    @Property(bool, notify=dpiBypassChanged)
    def dpiBypass(self): return self._dpi_bypass
    @dpiBypass.setter  # type: ignore[attr-defined]
    def dpiBypass(self, v):
        if v != self._dpi_bypass:
            self._dpi_bypass = v; self.dpiBypassChanged.emit()

    @Property(bool, notify=embeddingsEnabledChanged)
    def embeddingsEnabled(self) -> bool:
        return bool(getattr(self, "_embeddings_enabled", False))

    @embeddingsEnabled.setter  # type: ignore[attr-defined]
    def embeddingsEnabled(self, v: bool):
        b = bool(v)
        if b != bool(getattr(self, "_embeddings_enabled", False)):
            self._embeddings_enabled = b
            self.embeddingsEnabledChanged.emit()

    @Property(str, notify=embeddingsModelChanged)
    def embeddingsOllamaModel(self) -> str:
        return str(getattr(self, "_embeddings_ollama_model", "nomic-embed-text") or "nomic-embed-text")

    @embeddingsOllamaModel.setter  # type: ignore[attr-defined]
    def embeddingsOllamaModel(self, v: str):
        s = (v or "").strip() or "nomic-embed-text"
        if s != str(getattr(self, "_embeddings_ollama_model", "nomic-embed-text") or "nomic-embed-text"):
            self._embeddings_ollama_model = s
            self.embeddingsModelChanged.emit()

    @Property(str, notify=excludedGenresChanged)
    def excludedGenres(self) -> str:
        return str(getattr(self, "_excluded_genres", ""))

    @excludedGenres.setter  # type: ignore[attr-defined]
    def excludedGenres(self, v: str):
        if v != getattr(self, "_excluded_genres", ""):
            self._excluded_genres = v
            self.excludedGenresChanged.emit()

    @Property(bool, notify=insightHarvestAlertEnabledChanged)
    def insightHarvestAlertEnabled(self) -> bool:
        return bool(getattr(self, "_insight_harvest_alert_enabled", True))

    @insightHarvestAlertEnabled.setter  # type: ignore[attr-defined]
    def insightHarvestAlertEnabled(self, v: bool):
        b = bool(v)
        if b != bool(getattr(self, "_insight_harvest_alert_enabled", True)):
            self._insight_harvest_alert_enabled = b
            from javstory.config.secrets_manager import set_env_runtime_value
            set_env_runtime_value("JAVSTORY_INSIGHT_HARVEST_ALERT_ENABLED", "1" if b else "0")
            self.insightHarvestAlertEnabledChanged.emit()

    @Property(float, notify=insightHarvestAlertThresholdChanged)
    def insightHarvestAlertThreshold(self) -> float:
        return float(getattr(self, "_insight_harvest_alert_threshold", 0.85))

    @insightHarvestAlertThreshold.setter  # type: ignore[attr-defined]
    def insightHarvestAlertThreshold(self, v: float):
        try:
            f = float(v)
        except (TypeError, ValueError):
            f = 0.85
        f = max(0.5, min(1.0, f))
        if abs(f - float(getattr(self, "_insight_harvest_alert_threshold", 0.85))) > 1e-6:
            self._insight_harvest_alert_threshold = f
            from javstory.config.secrets_manager import set_env_runtime_value
            set_env_runtime_value("JAVSTORY_INSIGHT_HARVEST_ALERT_THRESHOLD", str(f))
            self.insightHarvestAlertThresholdChanged.emit()

    @Property(bool, notify=personaDeepAnalysisEnabledChanged)
    def personaDeepAnalysisEnabled(self) -> bool:
        return bool(getattr(self, "_persona_deep_enabled", True))

    @personaDeepAnalysisEnabled.setter  # type: ignore[attr-defined]
    def personaDeepAnalysisEnabled(self, v: bool):
        b = bool(v)
        if b != bool(getattr(self, "_persona_deep_enabled", True)):
            self._persona_deep_enabled = b
            from javstory.config.secrets_manager import set_env_runtime_value
            set_env_runtime_value("JAVSTORY_PERSONA_DEEP_ENABLED", "1" if b else "0")
            self.personaDeepAnalysisEnabledChanged.emit()

    @Property(int, notify=personaSampleSizeChanged)
    def personaSampleSize(self) -> int:
        return int(getattr(self, "_persona_sample_size", 8))

    @personaSampleSize.setter  # type: ignore[attr-defined]
    def personaSampleSize(self, v: int):
        try:
            n = int(v)
        except (TypeError, ValueError):
            n = 8
        n = max(4, min(12, n))
        if n != int(getattr(self, "_persona_sample_size", 8)):
            self._persona_sample_size = n
            from javstory.config.secrets_manager import set_env_runtime_value
            set_env_runtime_value("JAVSTORY_PERSONA_SAMPLE_SIZE", str(n))
            self.personaSampleSizeChanged.emit()

    @Property('QVariantList', notify=apiKeyChanged) # allGenres는 변하지 않는 리스트는 아니지만 일단 apiKeyChanged 등에 편승하거나 필요시 전용 시그널
    def allGenres(self):
        from javstory.harvest.database import get_db_session, Genre
        session = get_db_session()
        try:
            # korean 필드가 있는 것들을 가나다 순으로 반환
            rows = session.query(Genre).filter(Genre.korean != None).order_by(Genre.korean).all()
            return [r.korean for r in rows if r.korean]
        except Exception:
            return []
        finally:
            session.close()


    @Property(int, notify=themeModeChanged)
    def themeMode(self): return self._theme_mode
    @themeMode.setter  # type: ignore[attr-defined]
    def themeMode(self, v):
        if v != self._theme_mode:
            self._theme_mode = v
            from javstory.config.secrets_manager import set_env_runtime_value
            set_env_runtime_value("JAVSTORY_THEME_MODE", str(v))
            self.themeModeChanged.emit()
            self._apply_mica_global()

    @Property(bool, notify=isSystemDarkChanged)
    def isSystemDark(self):
        try:
            import darkdetect
            return darkdetect.isDark()
        except Exception:
            return True

    @Property(int, notify=harvestConcurrencyChanged)
    def harvestConcurrency(self) -> int:
        return int(self._harvest_concurrency)

    @harvestConcurrency.setter  # type: ignore[attr-defined]
    def harvestConcurrency(self, v: int):
        try:
            n = int(v)
        except Exception:
            n = 2
        n = max(1, min(5, n))
        if n != getattr(self, "_harvest_concurrency", 2):
            self._harvest_concurrency = n
            self.harvestConcurrencyChanged.emit()

    # ── LADA (모자이크 제거) ───────────────────────────

    @Property('QVariantList', notify=cudaDevicesChanged)
    def cudaDevices(self):
        return list(getattr(self, "_cuda_devices", []) or [])

    def _start_cuda_detection(self) -> None:
        threading.Thread(target=self._run_cuda_detection, daemon=True, name="cuda-detect").start()

    def _run_cuda_detection(self) -> None:
        self._cuda_devices = self._detect_cuda_devices()
        # 메인 스레드에서 시그널 발생 (Qt 스레드 안전 규칙)
        QMetaObject.invokeMethod(self, "_on_cuda_detected", Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _on_cuda_detected(self) -> None:
        self.cudaDevicesChanged.emit()

    def _detect_cuda_devices(self) -> list[str]:
        try:
            out = subprocess.check_output(
                "nvidia-smi --list-gpus",
                shell=True,
                stderr=subprocess.STDOUT,
            ).decode(errors="replace")
            lines = [ln.strip() for ln in (out or "").splitlines() if ln.strip()]
            # Example: "GPU 0: NVIDIA GeForce RTX 4090 (UUID: GPU-...)"
            devs = []
            for ln in lines:
                if ln.lower().startswith("gpu "):
                    devs.append(ln)
            return devs
        except Exception:
            return []

    @Property(int, notify=ladaOptionsChanged)
    def ladaParallel(self) -> int:
        return int(getattr(self, "_lada_parallel", 2) or 2)

    @ladaParallel.setter  # type: ignore[attr-defined]
    def ladaParallel(self, v: int):
        try:
            n = int(v)
        except Exception:
            n = 2
        n = max(1, min(3, n))
        if n != getattr(self, "_lada_parallel", 2):
            self._lada_parallel = n
            self.ladaOptionsChanged.emit()

    @Property(int, notify=ladaOptionsChanged)
    def ladaPasses(self) -> int:
        return int(getattr(self, "_lada_passes", 2) or 2)

    @ladaPasses.setter  # type: ignore[attr-defined]
    def ladaPasses(self, v: int):
        try:
            n = int(v)
        except Exception:
            n = 2
        n = max(1, min(3, n))
        if n != getattr(self, "_lada_passes", 2):
            self._lada_passes = n
            self.ladaOptionsChanged.emit()

    @Property(str, notify=ladaOptionsChanged)
    def ladaPass1DetModel(self) -> str: return getattr(self, "_lada_pass1_det_model", "v4-fast")
    @ladaPass1DetModel.setter  # type: ignore[attr-defined]
    def ladaPass1DetModel(self, v: str):
        v = (v or "").strip() or "v4-fast"
        if v != getattr(self, "_lada_pass1_det_model", "v4-fast"):
            self._lada_pass1_det_model = v
            self.ladaOptionsChanged.emit()

    @Property(str, notify=ladaOptionsChanged)
    def ladaPass1RestModel(self) -> str: return getattr(self, "_lada_pass1_rest_model", "basicvsrpp-v1.2")
    @ladaPass1RestModel.setter  # type: ignore[attr-defined]
    def ladaPass1RestModel(self, v: str):
        v = (v or "").strip() or "basicvsrpp-v1.2"
        if v != getattr(self, "_lada_pass1_rest_model", "basicvsrpp-v1.2"):
            self._lada_pass1_rest_model = v
            self.ladaOptionsChanged.emit()

    @Property(int, notify=ladaOptionsChanged)
    def ladaPass1MaxClipLength(self) -> int: return int(getattr(self, "_lada_pass1_max_clip_length", 180) or 180)
    @ladaPass1MaxClipLength.setter  # type: ignore[attr-defined]
    def ladaPass1MaxClipLength(self, v: int):
        try:
            n = int(v)
        except Exception:
            n = 180
        n = max(20, min(400, n))
        if n != getattr(self, "_lada_pass1_max_clip_length", 180):
            self._lada_pass1_max_clip_length = n
            self.ladaOptionsChanged.emit()

    @Property(bool, notify=ladaOptionsChanged)
    def ladaPass1DetectFace(self) -> bool: return bool(getattr(self, "_lada_pass1_detect_face", False))
    @ladaPass1DetectFace.setter  # type: ignore[attr-defined]
    def ladaPass1DetectFace(self, v: bool):
        b = bool(v)
        if b != bool(getattr(self, "_lada_pass1_detect_face", False)):
            self._lada_pass1_detect_face = b
            self.ladaOptionsChanged.emit()

    @Property(str, notify=ladaOptionsChanged)
    def ladaPass2DetModel(self) -> str: return getattr(self, "_lada_pass2_det_model", "v4-fast")
    @ladaPass2DetModel.setter  # type: ignore[attr-defined]
    def ladaPass2DetModel(self, v: str):
        v = (v or "").strip() or "v4-fast"
        if v != getattr(self, "_lada_pass2_det_model", "v4-fast"):
            self._lada_pass2_det_model = v
            self.ladaOptionsChanged.emit()

    @Property(str, notify=ladaOptionsChanged)
    def ladaPass2RestModel(self) -> str: return getattr(self, "_lada_pass2_rest_model", "basicvsrpp-v1.2")
    @ladaPass2RestModel.setter  # type: ignore[attr-defined]
    def ladaPass2RestModel(self, v: str):
        v = (v or "").strip() or "basicvsrpp-v1.2"
        if v != getattr(self, "_lada_pass2_rest_model", "basicvsrpp-v1.2"):
            self._lada_pass2_rest_model = v
            self.ladaOptionsChanged.emit()

    @Property(int, notify=ladaOptionsChanged)
    def ladaPass2MaxClipLength(self) -> int: return int(getattr(self, "_lada_pass2_max_clip_length", 180) or 180)
    @ladaPass2MaxClipLength.setter  # type: ignore[attr-defined]
    def ladaPass2MaxClipLength(self, v: int):
        try:
            n = int(v)
        except Exception:
            n = 180
        n = max(20, min(400, n))
        if n != getattr(self, "_lada_pass2_max_clip_length", 180):
            self._lada_pass2_max_clip_length = n
            self.ladaOptionsChanged.emit()

    @Property(bool, notify=ladaOptionsChanged)
    def ladaPass2DetectFace(self) -> bool: return bool(getattr(self, "_lada_pass2_detect_face", False))
    @ladaPass2DetectFace.setter  # type: ignore[attr-defined]
    def ladaPass2DetectFace(self, v: bool):
        b = bool(v)
        if b != bool(getattr(self, "_lada_pass2_detect_face", False)):
            self._lada_pass2_detect_face = b
            self.ladaOptionsChanged.emit()

    @Property(str, notify=ladaOptionsChanged)
    def ladaPass3DetModel(self) -> str: return getattr(self, "_lada_pass3_det_model", "v4-fast")
    @ladaPass3DetModel.setter  # type: ignore[attr-defined]
    def ladaPass3DetModel(self, v: str):
        v = (v or "").strip() or "v4-fast"
        if v != getattr(self, "_lada_pass3_det_model", "v4-fast"):
            self._lada_pass3_det_model = v
            self.ladaOptionsChanged.emit()

    @Property(str, notify=ladaOptionsChanged)
    def ladaPass3RestModel(self) -> str: return getattr(self, "_lada_pass3_rest_model", "basicvsrpp-v1.2")
    @ladaPass3RestModel.setter  # type: ignore[attr-defined]
    def ladaPass3RestModel(self, v: str):
        v = (v or "").strip() or "basicvsrpp-v1.2"
        if v != getattr(self, "_lada_pass3_rest_model", "basicvsrpp-v1.2"):
            self._lada_pass3_rest_model = v
            self.ladaOptionsChanged.emit()

    @Property(int, notify=ladaOptionsChanged)
    def ladaPass3MaxClipLength(self) -> int: return int(getattr(self, "_lada_pass3_max_clip_length", 180) or 180)
    @ladaPass3MaxClipLength.setter  # type: ignore[attr-defined]
    def ladaPass3MaxClipLength(self, v: int):
        try:
            n = int(v)
        except Exception:
            n = 180
        n = max(20, min(400, n))
        if n != getattr(self, "_lada_pass3_max_clip_length", 180):
            self._lada_pass3_max_clip_length = n
            self.ladaOptionsChanged.emit()

    @Property(bool, notify=ladaOptionsChanged)
    def ladaPass3DetectFace(self) -> bool: return bool(getattr(self, "_lada_pass3_detect_face", False))
    @ladaPass3DetectFace.setter  # type: ignore[attr-defined]
    def ladaPass3DetectFace(self, v: bool):
        b = bool(v)
        if b != bool(getattr(self, "_lada_pass3_detect_face", False)):
            self._lada_pass3_detect_face = b
            self.ladaOptionsChanged.emit()

    @Property(str, notify=ladaOptionsChanged)
    def ladaEncoder(self) -> str: return getattr(self, "_lada_encoder", "hevc_nvenc")
    @ladaEncoder.setter  # type: ignore[attr-defined]
    def ladaEncoder(self, v: str):
        v = (v or "").strip() or "hevc_nvenc"
        if v != getattr(self, "_lada_encoder", "hevc_nvenc"):
            self._lada_encoder = v
            self.ladaOptionsChanged.emit()

    @Property(str, notify=ladaOptionsChanged)
    def ladaEncodingPreset(self) -> str: return getattr(self, "_lada_encoding_preset", "hevc-nvidia-gpu-balanced")
    @ladaEncodingPreset.setter  # type: ignore[attr-defined]
    def ladaEncodingPreset(self, v: str):
        v = (v or "").strip() or "hevc-nvidia-gpu-balanced"
        if v != getattr(self, "_lada_encoding_preset", "hevc-nvidia-gpu-balanced"):
            self._lada_encoding_preset = v
            self.ladaOptionsChanged.emit()

    @Property(bool, notify=ladaOptionsChanged)
    def ladaFp16(self) -> bool: return bool(getattr(self, "_lada_fp16", True))
    @ladaFp16.setter  # type: ignore[attr-defined]
    def ladaFp16(self, v: bool):
        b = bool(v)
        if b != bool(getattr(self, "_lada_fp16", True)):
            self._lada_fp16 = b
            self.ladaOptionsChanged.emit()

    def _apply_mica_global(self):
        """변경된 테마에 맞춰 Mica 효과 재적용."""
        if sys.platform != "win32": return
        try:
            import win32mica
            # 현재 활성화된 메인 윈도우 찾기
            from PySide6.QtWidgets import QApplication
            for top_level_widget in QApplication.topLevelWidgets():
                if top_level_widget.inherits("QQuickWindow"):
                    hwnd = int(top_level_widget.winId())
                    is_dark = self.isSystemDark if self._theme_mode == 0 else (self._theme_mode == 2)
                    mode = win32mica.MicaTheme.DARK if is_dark else win32mica.MicaTheme.LIGHT
                    win32mica.ApplyMica(hwnd, mode)
        except Exception:
            pass

    # ── Slots ─────────────────────────────────────────

    @Slot()
    def saveApiKey(self):
        key = self._api_key.strip()
        try:
            from javstory.config.secrets_manager import (
                set_openrouter_api_key,
                set_gemini_api_key,
                set_env_runtime_value,
            )

            if key:
                set_openrouter_api_key(key)
            else:
                self.toastMessage.emit("OpenRouter API 키가 비어 있습니다. (Gemini만 저장 가능)", "info")

            gk = str(getattr(self, "_gemini_api_key", "") or "").strip()
            if gk:
                set_gemini_api_key(gk)

            if self._ollama_url.strip():
                set_env_runtime_value("JAVSTORY_OLLAMA_URL", self._ollama_url.strip())

            platform = str(getattr(self, "_llm_platform", "openai") or "openai")
            platform_suffix = self._platform_env_suffix(platform)
            set_env_runtime_value("JAVSTORY_LLM_PLATFORM", platform)
            set_env_runtime_value(
                "JAVSTORY_TRANSLATION_PROVIDER",
                self._translation_provider_for_profile(platform),
            )

            if getattr(self, "_llamacpp_url", "").strip():
                set_env_runtime_value("JAVSTORY_LLAMACPP_URL", self._llamacpp_url.strip())
            if getattr(self, "_llamacpp_bin", "").strip():
                set_env_runtime_value("JAVSTORY_LLAMACPP_BIN", self._llamacpp_bin.strip())
            if getattr(self, "_llamacpp_models_dir", "").strip():
                set_env_runtime_value("JAVSTORY_LLAMACPP_MODELS_DIR", self._llamacpp_models_dir.strip())
            set_env_runtime_value(
                f"JAVSTORY_TRANSLATION_PROFILE_{platform_suffix}",
                self._translation_profile,
            )
            set_env_runtime_value(
                f"JAVSTORY_HARVEST_TRANSLATION_MODEL_{platform_suffix}",
                str(getattr(self, "_harvest_translation_model", "")),
            )
            set_env_runtime_value(
                f"JAVSTORY_CORRECTION_PASS2_MODEL_{platform_suffix}",
                self._correction_profile,
            )
            if platform == "llamacpp":
                set_env_runtime_value("JAVSTORY_TRANSLATION_PROFILE", self._translation_profile)
                set_env_runtime_value(
                    "JAVSTORY_HARVEST_TRANSLATION_MODEL",
                    str(getattr(self, "_harvest_translation_model", "llamacpp:gemma-4-e4b")),
                )
                set_env_runtime_value("JAVSTORY_CORRECTION_PASS2_MODEL", self._correction_profile)
                self._llamacpp_model = self._llamacpp_base_model_id(
                    str(getattr(self, "_llamacpp_model", "") or "")
                )
                self._sync_llamacpp_translation_models_to_active()
                self._apply_llamacpp_model_runtime_defaults()
                set_env_runtime_value("JAVSTORY_TRANSLATION_PROFILE", self._translation_profile)
                set_env_runtime_value("JAVSTORY_HARVEST_TRANSLATION_MODEL", self._harvest_translation_model)
                set_env_runtime_value("JAVSTORY_CORRECTION_PASS2_MODEL", self._correction_profile)
                set_env_runtime_value(f"JAVSTORY_TRANSLATION_PROFILE_{platform_suffix}", self._translation_profile)
                set_env_runtime_value(
                    f"JAVSTORY_HARVEST_TRANSLATION_MODEL_{platform_suffix}",
                    self._harvest_translation_model,
                )
                set_env_runtime_value(
                    f"JAVSTORY_CORRECTION_PASS2_MODEL_{platform_suffix}",
                    self._correction_profile,
                )
                set_env_runtime_value("JAVSTORY_LLAMACPP_MODEL", self._llamacpp_model)
            else:
                set_env_runtime_value("JAVSTORY_LLAMACPP_MODEL", str(getattr(self, "_llamacpp_model", "gemma-4-e4b")))
            set_env_runtime_value("JAVSTORY_PERSONA_CARD_PRESET", self._persona_card_preset)
            set_env_runtime_value("JAVSTORY_PERSONA_CHAT_MODEL", self._persona_chat_model)
            if getattr(self, "_llamacpp_gemma_gguf", "").strip():
                set_env_runtime_value("JAVSTORY_LLAMACPP_GEMMA4_GGUF", self._llamacpp_gemma_gguf.strip())
            if getattr(self, "_llamacpp_qwen14b_gguf", "").strip():
                set_env_runtime_value("JAVSTORY_LLAMACPP_QWEN3_14B_GGUF", self._llamacpp_qwen14b_gguf.strip())
            if getattr(self, "_llamacpp_qwen14b_unc_gguf", "").strip():
                set_env_runtime_value("JAVSTORY_LLAMACPP_QWEN3_14B_UNC_GGUF", self._llamacpp_qwen14b_unc_gguf.strip())
            set_env_runtime_value("JAVSTORY_LLAMACPP_CACHE_TYPE_K", str(getattr(self, "_llamacpp_cache_type_k", "turbo3")))
            set_env_runtime_value("JAVSTORY_LLAMACPP_CACHE_TYPE_V", str(getattr(self, "_llamacpp_cache_type_v", "q8_0")))
            set_env_runtime_value(
                "JAVSTORY_LLAMACPP_AUTO_START",
                "1" if bool(getattr(self, "_llamacpp_auto_start", True)) else "0",
            )
            ctx_s = str(getattr(self, "_llamacpp_ctx", "4096") or "4096").strip()
            if ctx_s:
                set_env_runtime_value("JAVSTORY_LLAMACPP_CTX", ctx_s)
            mt_s = str(getattr(self, "_llamacpp_max_tokens", "3072") or "3072").strip()
            if mt_s:
                set_env_runtime_value("JAVSTORY_TRANSLATION_LLAMACPP_MAX_TOKENS", mt_s)
                set_env_runtime_value("JAVSTORY_CORRECTION_LLAMACPP_MAX_TOKENS", mt_s)
            set_env_runtime_value(
                "JAVSTORY_LLAMACPP_STOP_AFTER_JOB",
                "1" if bool(getattr(self, "_llamacpp_stop_after_job", False)) else "0",
            )
            pcm = int(getattr(self, "_llamacpp_prompt_cache_mib", 0) or 0)
            if bool(getattr(self, "_llamacpp_prompt_cache", False)) and pcm <= 0:
                from javstory.llm.llamacpp_backend import LLAMACPP_SERVER_DEFAULT_PROMPT_CACHE_MIB

                pcm = LLAMACPP_SERVER_DEFAULT_PROMPT_CACHE_MIB
            set_env_runtime_value("JAVSTORY_LLAMACPP_PROMPT_CACHE_MB", str(pcm))

            self.toastMessage.emit("API 키 저장 완료", "success")
        except Exception as e:
            self.toastMessage.emit(f"API 키 저장 실패: {e}", "error")

    @Slot()
    def savePaths(self):
        from javstory.config.secrets_manager import set_env_runtime_value
        if self._media_root.strip():
            set_env_runtime_value("JAVSTORY_MEDIA_ROOT", self._media_root.strip())
        self.toastMessage.emit("경로 설정 적용 완료", "success")

    @Slot()
    def saveOptions(self):
        from javstory.config.secrets_manager import set_env_runtime_value
        platform = str(getattr(self, "_llm_platform", "openai") or "openai")
        platform_suffix = self._platform_env_suffix(platform)
        set_env_runtime_value("JAVSTORY_WHISPER_MODEL", self._whisper_model)
        set_env_runtime_value("JAVSTORY_TRANSLATION_PROFILE", self._translation_profile)
        set_env_runtime_value(
            "JAVSTORY_TRANSLATION_PROVIDER",
            self._translation_provider_for_profile(platform),
        )
        set_env_runtime_value("JAVSTORY_HARVEST_TRANSLATION_MODEL", str(getattr(self, "_harvest_translation_model", "openrouter:deepseek/deepseek-v3.2")))
        set_env_runtime_value(
            f"JAVSTORY_TRANSLATION_PROFILE_{platform_suffix}",
            self._translation_profile,
        )
        set_env_runtime_value(
            f"JAVSTORY_HARVEST_TRANSLATION_MODEL_{platform_suffix}",
            str(getattr(self, "_harvest_translation_model", "openrouter:deepseek/deepseek-v3.2")),
        )
        set_env_runtime_value(
            f"JAVSTORY_CORRECTION_PASS2_MODEL_{platform_suffix}",
            self._correction_profile,
        )
        if platform == "llamacpp":
            self._llamacpp_model = self._llamacpp_base_model_id(
                str(getattr(self, "_llamacpp_model", "") or "")
            )
            self._sync_llamacpp_translation_models_to_active()
            self._apply_llamacpp_model_runtime_defaults()
            set_env_runtime_value("JAVSTORY_TRANSLATION_PROFILE", self._translation_profile)
            set_env_runtime_value("JAVSTORY_HARVEST_TRANSLATION_MODEL", self._harvest_translation_model)
            set_env_runtime_value("JAVSTORY_CORRECTION_PASS2_MODEL", self._correction_profile)
            set_env_runtime_value(f"JAVSTORY_TRANSLATION_PROFILE_{platform_suffix}", self._translation_profile)
            set_env_runtime_value(
                f"JAVSTORY_HARVEST_TRANSLATION_MODEL_{platform_suffix}",
                self._harvest_translation_model,
            )
            set_env_runtime_value(
                f"JAVSTORY_CORRECTION_PASS2_MODEL_{platform_suffix}",
                self._correction_profile,
            )
            set_env_runtime_value("JAVSTORY_LLAMACPP_MODEL", self._llamacpp_model)
        set_env_runtime_value("JAVSTORY_PERSONA_CARD_PRESET", self._persona_card_preset)
        set_env_runtime_value("JAVSTORY_PERSONA_CHAT_MODEL", self._persona_chat_model)
        try:
            from javstory.translation.translation_notes import save_global_note
            save_global_note(str(getattr(self, "_translation_note_global", "") or ""))
        except Exception as _e:
            self.toastMessage.emit(f"전역 번역 노트 저장 실패: {_e}", "error")
        set_env_runtime_value("JAVSTORY_STORY_ANALYSIS_ENABLED", "1" if self._grok_enabled else "0")
        set_env_runtime_value("JAVSTORY_CORRECTION_PASS2_MODEL", self._correction_profile)
        set_env_runtime_value("JAVSTORY_CORRECTION_SKIP", "1" if self._correction_skip else "0")
        set_env_runtime_value("JAVSTORY_DPI_BYPASS_ENABLED", "1" if self._dpi_bypass else "0")
        set_env_runtime_value("JAVSTORY_EMBEDDINGS_ENABLED", "1" if bool(getattr(self, "_embeddings_enabled", False)) else "0")
        set_env_runtime_value("JAVSTORY_EMBEDDINGS_OLLAMA_MODEL", str(getattr(self, "_embeddings_ollama_model", "nomic-embed-text") or "nomic-embed-text"))
        set_env_runtime_value("JAVSTORY_INSIGHT_HARVEST_ALERT_ENABLED", "1" if bool(getattr(self, "_insight_harvest_alert_enabled", True)) else "0")
        set_env_runtime_value("JAVSTORY_INSIGHT_HARVEST_ALERT_THRESHOLD", str(float(getattr(self, "_insight_harvest_alert_threshold", 0.85))))
        set_env_runtime_value("JAVSTORY_PERSONA_DEEP_ENABLED", "1" if bool(getattr(self, "_persona_deep_enabled", True)) else "0")
        set_env_runtime_value("JAVSTORY_PERSONA_SAMPLE_SIZE", str(int(getattr(self, "_persona_sample_size", 8))))
        set_env_runtime_value("JAVSTORY_SIMILARITY_EXCLUDED_GENRES", str(getattr(self, "_excluded_genres", "")))
        set_env_runtime_value("JAVSTORY_HARVEST_CONCURRENCY", str(int(self._harvest_concurrency or 2)))


        # LADA 모자이크 제거 옵션
        set_env_runtime_value("JAVSTORY_LADA_PARALLEL", str(int(self._lada_parallel or 2)))
        set_env_runtime_value("JAVSTORY_LADA_PASSES", str(int(self._lada_passes or 2)))
        set_env_runtime_value("JAVSTORY_LADA_ENCODER", str(self._lada_encoder or "hevc_nvenc"))
        set_env_runtime_value("JAVSTORY_LADA_ENCODING_PRESET", str(self._lada_encoding_preset or "hevc-nvidia-gpu-balanced"))
        set_env_runtime_value("JAVSTORY_LADA_FP16", "1" if bool(self._lada_fp16) else "0")

        set_env_runtime_value("JAVSTORY_LADA_PASS1_DET_MODEL", str(self._lada_pass1_det_model or "v4-fast"))
        set_env_runtime_value("JAVSTORY_LADA_PASS1_REST_MODEL", str(self._lada_pass1_rest_model or "basicvsrpp-v1.2"))
        set_env_runtime_value("JAVSTORY_LADA_PASS1_MAX_CLIP_LENGTH", str(int(self._lada_pass1_max_clip_length or 180)))
        set_env_runtime_value("JAVSTORY_LADA_PASS1_DETECT_FACE", "1" if bool(self._lada_pass1_detect_face) else "0")

        set_env_runtime_value("JAVSTORY_LADA_PASS2_DET_MODEL", str(self._lada_pass2_det_model or "v4-fast"))
        set_env_runtime_value("JAVSTORY_LADA_PASS2_REST_MODEL", str(self._lada_pass2_rest_model or "basicvsrpp-v1.2"))
        set_env_runtime_value("JAVSTORY_LADA_PASS2_MAX_CLIP_LENGTH", str(int(self._lada_pass2_max_clip_length or 180)))
        set_env_runtime_value("JAVSTORY_LADA_PASS2_DETECT_FACE", "1" if bool(self._lada_pass2_detect_face) else "0")

        set_env_runtime_value("JAVSTORY_LADA_PASS3_DET_MODEL", str(self._lada_pass3_det_model or "v4-fast"))
        set_env_runtime_value("JAVSTORY_LADA_PASS3_REST_MODEL", str(self._lada_pass3_rest_model or "basicvsrpp-v1.2"))
        set_env_runtime_value("JAVSTORY_LADA_PASS3_MAX_CLIP_LENGTH", str(int(self._lada_pass3_max_clip_length or 180)))
        set_env_runtime_value("JAVSTORY_LADA_PASS3_DETECT_FACE", "1" if bool(self._lada_pass3_detect_face) else "0")

        # DPI 우회 연결
        try:
            from javstory.utils.bypass_manager import BypassManager
            bm = BypassManager()
            if self._dpi_bypass:
                bm.start()
            else:
                bm.stop()
        except Exception:
            pass

        self.toastMessage.emit("옵션 저장 완료", "success")

    @Slot(str, bool)
    def runEmbeddings(self, productCode: str, force: bool = False):
        """
        QML에서 호출: 특정 품번의 임베딩을 백그라운드에서 생성/재생성.
        UI 멈춤 방지를 위해 별도 스레드에서 asyncio.run 수행.
        """
        pc = (productCode or "").strip().upper()
        if not pc:
            self.toastMessage.emit("품번을 입력하세요. (예: ABC-123)", "warning")
            return

        model = str(getattr(self, "_embeddings_ollama_model", "nomic-embed-text") or "nomic-embed-text").strip()
        if not model:
            model = "nomic-embed-text"

        try:
            from gui.models.embedding_queue_model import EmbeddingQueueController

            q = EmbeddingQueueController.instance()
            if not q:
                self.toastMessage.emit("임베딩 큐 모델을 찾을 수 없습니다.", "error")
                return
            q.enqueue(pc, model, bool(force))
        except Exception as e:
            self.toastMessage.emit(f"임베딩 큐 등록 실패: {pc} ({e})", "error")

    @Slot(str)
    def findSimilarEmbeddings(self, productCode: str):
        """
        QML에서 호출: 품번 기준 유사 작품 Top N 조회(임베딩 캐시 기반).
        결과는 토스트로 요약 출력(상세 UI는 추후).
        """
        pc = (productCode or "").strip().upper()
        if not pc:
            self.toastMessage.emit("품번을 입력하세요. (예: ABC-123)", "warning")
            return

        model = str(getattr(self, "_embeddings_ollama_model", "nomic-embed-text") or "nomic-embed-text").strip() or "nomic-embed-text"
        self.toastMessage.emit(f"유사작 검색 시작: {pc} (model={model})", "info")

        def _job():
            try:
                from javstory.library.embeddings.similarity import find_similar_products

                results = find_similar_products(pc, model=model, top_k=10)
                if not results:
                    self.toastMessage.emit(
                        f"유사작 결과 없음: {pc} (캐시가 없거나 비교 대상이 부족합니다)",
                        "warning",
                    )
                    return

                lines = [f"{i+1}. {r.product_code} ({r.score:.3f})" for i, r in enumerate(results)]
                msg = "\n".join(lines)
                # 토스트는 짧게, 상세는 팝업으로
                self.toastMessage.emit(f"유사작 Top10 준비됨: {pc}", "success")
                self.similarEmbeddingsReady.emit(pc, model, msg)
            except Exception as e:
                self.toastMessage.emit(f"유사작 검색 실패: {pc} ({e})", "error")

        threading.Thread(target=_job, daemon=True).start()

    @Slot()
    def openPipelineErrorFolder(self):
        """파이프라인 실패 작업 폴더(`data/error/04_ERROR/`)를 탐색기에서 연다."""
        from javstory.config.app_config import DATA_ROOT

        err_dir = DATA_ROOT / "error" / "04_ERROR"
        err_dir.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(err_dir)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", str(err_dir)], check=False)
            else:
                subprocess.run(["xdg-open", str(err_dir)], check=False)
            self.toastMessage.emit(f"폴더를 열었습니다: {err_dir}", "info")
        except Exception as e:
            self.toastMessage.emit(f"폴더 열기 실패: {e}", "error")

    @Slot(result=str)
    def browseFolder(self):
        """QML에서 호출: 네이티브 폴더 선택 대화상자 (단일)."""
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(None, "폴더 선택")
        return d or ""

    @Slot(result=str)
    def browseFile(self):
        """QML에서 호출: 네이티브 파일 선택 대화상자."""
        from PySide6.QtWidgets import QFileDialog
        f, _ = QFileDialog.getOpenFileName(None, "파일 선택", "", "Videos (*.mp4 *.mkv *.avi *.wmv)")
        return f or ""

    @Slot(result=str)
    def browseGgufFile(self) -> str:
        """GGUF / llama-server 실행 파일 선택."""
        from PySide6.QtWidgets import QFileDialog

        f, _ = QFileDialog.getOpenFileName(
            None,
            "GGUF 또는 실행 파일 선택",
            "",
            "GGUF (*.gguf);;Executables (*.exe);;All (*.*)",
        )
        return f or ""

    @Slot(result=str)
    def browseExecutableFile(self) -> str:
        from PySide6.QtWidgets import QFileDialog

        f, _ = QFileDialog.getOpenFileName(
            None,
            "실행 파일 선택",
            "",
            "Executables (*.exe);;All (*.*)",
        )
        return f or ""
