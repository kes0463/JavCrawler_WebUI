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
        self._ollama_url = os.environ.get("JAVSTORY_OLLAMA_URL", OLLAMA_BASE_URL)
        self._media_root = os.environ.get("JAVSTORY_MEDIA_ROOT", str(E_MEDIA_ROOT))
        
        # 2. 모델 및 번역
        self._whisper_model = os.environ.get("JAVSTORY_WHISPER_MODEL", "large-v2")
        self._translation_profile = os.environ.get("JAVSTORY_TRANSLATION_PROFILE", "default").lower()
        self._harvest_translation_model = (os.environ.get("JAVSTORY_HARVEST_TRANSLATION_MODEL", "openrouter:deepseek/deepseek-v3.2") or "").strip() or "openrouter:deepseek/deepseek-v3.2"
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
        self._correction_profile = os.environ.get("JAVSTORY_CORRECTION_PASS2_MODEL", "qwen/qwen3-235b-a22b-2507")
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
        set_env_runtime_value("JAVSTORY_WHISPER_MODEL", self._whisper_model)
        set_env_runtime_value("JAVSTORY_TRANSLATION_PROFILE", self._translation_profile)
        set_env_runtime_value("JAVSTORY_HARVEST_TRANSLATION_MODEL", str(getattr(self, "_harvest_translation_model", "openrouter:deepseek/deepseek-v3.2")))
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

        self.toastMessage.emit(
            f"임베딩 {'강제 재생성' if force else '생성'} 시작: {pc} (model={model})",
            "info",
        )

        def _job():
            try:
                import asyncio
                from javstory.library.embeddings.pipeline import build_and_store_embeddings_for_product

                path = asyncio.run(
                    build_and_store_embeddings_for_product(
                        pc,
                        model=model,
                        include_subtitles=True,
                        force=bool(force),
                        logger_func=None,
                    )
                )
                if path:
                    self.toastMessage.emit(f"임베딩 완료: {pc}", "success")
                else:
                    self.toastMessage.emit(f"임베딩 스킵/실패: {pc}", "warning")
            except Exception as e:
                self.toastMessage.emit(f"임베딩 실패: {pc} ({e})", "error")

        threading.Thread(target=_job, daemon=True).start()

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
