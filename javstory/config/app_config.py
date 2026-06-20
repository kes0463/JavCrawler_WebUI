"""애플리케이션 전역 상수 (진입점·보안·GUI 공통)."""
import os
from pathlib import Path
from typing import Any

APP_NAME = "JAV Story Analyzer"
APP_DISPLAY_TITLE = "JAV 스마트 분석기"

# keyring 서비스명(Windows: 자격 증명 관리자에 표시되는 이름과 유사)
KEYRING_SERVICE_NAME = APP_NAME

# keyring 계정(사용자) 키 — 여러 API를 구분할 때 계정명으로 사용
KEYRING_ACCOUNT_OPENROUTER = "openrouter_api_key"

# python-dotenv / OS 환경변수 이름
ENV_OPENROUTER_API_KEY = "OPENROUTER_API_KEY"

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"

# --- 데이터 레이아웃 (단일 루트 `data/`) ---
# 기존 파일이 있으면 수동 이동: Harvest/jav_database.db → data/db/,
# Transcription/story_context_cache → data/cache/story_context,
# Transcription/reference_cache → data/cache/reference, 루트 master_db.js → data/derived/
# 프로젝트 내부 데이터(DB/캐시 등)
DATA_ROOT = PROJECT_ROOT / "data"
DB_PATH = DATA_ROOT / "db" / "jav_database.db"

# 대용량 데이터 루트 — 환경변수 JAVSTORY_E_DATA_ROOT로 재지정 가능
E_DATA_ROOT = Path(os.environ.get("JAVSTORY_E_DATA_ROOT", "E:/App/JAVSTORY/data"))

# 작품별 산출물 루트
# 요구사항: E:\App\JAVSTORY\data\<작품폴더명>\{product_id}\...
E_WORKS_DIRNAME = "works"
E_MEDIA_ROOT = E_DATA_ROOT / E_WORKS_DIRNAME

# 레거시(프로젝트 내부) 미디어 루트 — 이행 기간 fallback 탐색용
MEDIA_ROOT = DATA_ROOT / "media"
DERIVED_DATA_DIR = DATA_ROOT / "derived"
STORY_CONTEXT_CACHE_DIR = DATA_ROOT / "cache" / "story_context"
REFERENCE_CACHE_DIR = DATA_ROOT / "cache" / "reference"

# 표지 CDN 프록시 (SNI/지역 필터 회피용 — wsrv.nl 계열 공용 프록시)
# 공식 도메인은 images.weserv.nl (wsrv.nl 표기와 동일 계열 서비스)
WESERV_IMAGE_PROXY = "https://images.weserv.nl/"

VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".webm", ".mov", ".wmv", ".ts")

# DB v2 P3: 1/true/on 이면 재생·목록 영상 경로에 L2 video_files 사용 (L4 parts 우선)
ENV_DB_V2_READ = "JAVSTORY_DB_V2_READ"
# DB v2 P2: 1/true/on 이면 앱 부트 시 products backfill 생략 (tools/hydrate_products_v2.py 로 실행)
ENV_SKIP_BOOT_HYDRATE = "JAVSTORY_SKIP_BOOT_HYDRATE"
PRODUCTS_V2_HYDRATE_MARKER = DATA_ROOT / "db" / ".products_v2_hydrate_done"
HYDRATE_PROGRESS_EVERY = int(os.environ.get("JAVSTORY_HYDRATE_PROGRESS_EVERY", "100") or 100)

# [Phase 4] 장면 분석 및 썸네일 추출 설정
SCENE_THRESHOLD = 27.0      # PySceneDetect ContentDetector 임계값 (지나치게 높지 않게 설정)
SCENE_IMG_WIDTH = 640       # 추출 썸네일 가로 해상도
SCENE_IMG_QUALITY = 80      # WebP 압축 품질 (0-100)
SCENE_MIN_COUNT = 3         # 최소 감지 씬 개수 (미달 시 정적 샘플 위주 작동)
SCENE_FALLBACK_INTERVAL = 180 # Fallback 시 추출 간격 (초 단위, 3분)
SCENE_FRAME_SKIP = 4        # 장면 분석 시 스킵할 프레임 수
SCENE_TARGET_COUNT = 24     # 최종적으로 리포트에 포함할 목표 썸네일 수 (균등 분포 보장용)

# ============================================================
# 메타데이터 및 번역 파이프라인 설정
# ============================================================
METADATA_CONFIG = {
    # title + synopsis 모두 동일한 translation 파이프라인 사용
    "title_pipeline"    : "translation",  # DeepSeek V3.2 NT → Hermes:free → ...
    "synopsis_pipeline" : "translation",

    # Gemini는 genre/maker 크롤링 보조용으로만 명시 (현재 크롤링 우선)
    "genre_pipeline"    : "crawling",
    "maker_pipeline"    : "crawling",
}

# ============================================================
# LLM & OpenRouter 설정
# ============================================================
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OLLAMA_BASE_URL     = "http://localhost:11434"
LLAMACPP_BASE_URL   = (
    os.environ.get("JAVSTORY_LLAMACPP_URL", "").strip().rstrip("/")
    or f"http://{(os.environ.get('JAVSTORY_LLAMACPP_HOST', '127.0.0.1') or '127.0.0.1').strip()}:"
    f"{int(os.environ.get('JAVSTORY_LLAMACPP_PORT', '8081') or '8081')}"
)
GEMINI_BASE_URL     = "https://generativelanguage.googleapis.com/v1beta/openai/"

# keyring 계정 및 환경변수 — Gemini API 키
KEYRING_ACCOUNT_GEMINI = "gemini_api_key"
ENV_GEMINI_API_KEY     = "JAVSTORY_GEMINI_API_KEY"

# Gemini 모델 메타 (AI Studio 무료 등급 rate limits 기준)
GEMINI_MODELS: dict[str, dict] = {
    # AI Studio (무료 등급) 스크린샷 기준 (2026-05)
    # - rpm: requests/minute
    # - tpm: tokens/minute (input+output)
    # - rpd: requests/day (None=무제한 표기)
    "gemini-3.0-flash":      {"rpm": 1000, "tpm": 2_000_000, "rpd": 10000,  "is_pro": False},
    "gemini-3.1-flash-lite": {"rpm": 4000, "tpm": 4_000_000, "rpd": 150000, "is_pro": False},
    "gemini-2.5-flash":      {"rpm": 1000, "tpm": 1_000_000, "rpd": 10000,  "is_pro": False},
    "gemini-2.5-pro":        {"rpm": 150,  "tpm": 2_000_000, "rpd": 1000,   "is_pro": True},
    "gemini-2.0-flash":      {"rpm": 2000, "tpm": 4_000_000, "rpd": None,   "is_pro": False},
    "gemini-2.0-flash-lite": {"rpm": 4000, "tpm": 4_000_000, "rpd": None,   "is_pro": False},
}

# Gemini 모델 ID 별칭(실제 ListModels에 있는 name 기준)
# - UI/과거 문서에서 쓰던 슬러그가 API에서 그대로 노출되지 않는 경우가 있어, 런타임에서 정규화한다.
_GEMINI_MODEL_ALIASES: dict[str, str] = {
    "gemini-3.0-flash": "gemini-3-flash-preview",
    "gemini-3.1-flash-lite": "gemini-3.1-flash-lite-preview",
}


def normalize_gemini_model_id(model_id: str | None) -> str:
    """Gemini 모델 ID를 API가 실제로 받는 형태로 정규화(aliases + models/ prefix 제거)."""
    mid = (model_id or "").strip()
    if not mid:
        return "gemini-2.0-flash"
    if mid.startswith("models/"):
        mid = mid.split("/", 1)[1].strip()
    return _GEMINI_MODEL_ALIASES.get(mid, mid)


def gemini_default_chunk_params(model_id: str) -> tuple[float, float, int]:
    """
    Gemini 모델별 기본 청킹 파라미터(초) + 동시성.
    목표: rpm이 낮은 모델은 청크를 길게(요청 수 감소), rpm이 높은 모델은 청크를 짧게(품질/지연 균형).
    """
    mid_raw = (model_id or "").strip() or "gemini-2.0-flash"
    mid = normalize_gemini_model_id(mid_raw)
    meta = GEMINI_MODELS.get(mid, {}) or GEMINI_MODELS.get(mid_raw, {})
    rpm = int(meta.get("rpm") or 0)

    # 매우 보수적인 기본값 (환경변수로 덮어쓰기 가능: *_CHUNK_TARGET_SEC / *_CONCURRENCY)
    if rpm <= 200:
        # Pro 계열(150 rpm 등): 요청 수를 최대한 줄인다.
        return 120.0, 12.0, 1
    if rpm <= 1000:
        return 45.0, 10.0, 4
    if rpm <= 2000:
        return 35.0, 8.0, 6
    # 4000 rpm 등
    return 25.0, 6.0, 8

_GEMINI_PROFILE_MAP: dict[str, str] = {
    "gemini_3_flash":      "gemini-3.0-flash",
    "gemini_3_flash_lite": "gemini-3.1-flash-lite",
    "gemini_25_flash":     "gemini-2.5-flash",
    "gemini_25_pro":       "gemini-2.5-pro",
    "gemini_2_flash":      "gemini-2.0-flash",
    "gemini_2_flash_lite": "gemini-2.0-flash-lite",
}

# [자동 폴백 티어]
LLM_TIERS = [
    {
        "rank"        : 1,
        "name"        : "deepseek_v3_2",
        "model"       : "deepseek/deepseek-v3.2",
        "provider"    : "openrouter",
        "cost_tier"   : "low",
        "uncensored"  : False,
        "timeout"     : 45,
        "max_ctx"     : 64000,
    },
    {
        "rank"        : 2,
        "name"        : "qwen_235b_openrouter",
        "model"       : "qwen/qwen3-235b-a22b",
        "provider"    : "openrouter",
        "cost_tier"   : "high",
        "uncensored"  : False,
        "timeout"     : 180,
        "max_ctx"     : 65536,
    },
    {
        "rank"        : 3,
        "name"        : "hermes_405b_free",
        "model"       : "nousresearch/hermes-3-llama-3.1-405b:free",
        "provider"    : "openrouter",
        "cost_tier"   : "free",
        "uncensored"  : True,
        "timeout"     : 90,
        "max_ctx"     : 32000,
        "daily_limit" : 18,
    },
    {
        "rank"        : 3,
        "name"        : "hermes_70b",
        "model"       : "nousresearch/hermes-3-llama-3.1-70b",
        "provider"    : "openrouter",
        "cost_tier"   : "medium",
        "uncensored"  : True,
        "timeout"     : 60,
        "max_ctx"     : 32000,
    },
    {
        "rank"        : 4,
        "name"        : "hermes_405b_paid",
        "model"       : "nousresearch/hermes-3-llama-3.1-405b",
        "provider"   : "openrouter",
        "cost_tier"   : "high",
        "uncensored"  : True,
        "timeout"     : 120,
        "max_ctx"     : 32000,
    },
    {
        "rank"        : 5,
        "name"        : "qwen_local",
        "model"       : "qwen3:8b",
        "provider"    : "ollama",
        "cost_tier"   : "free",
        "uncensored"  : False,
        "timeout"     : 180,
        "max_ctx"     : 8192,
    },
]

# ============================================================
# 자막 교정 LLM (플랜: Grok Pass1 → Pass2 기본 GLM 5.1; claude_polish 시 Pass2가 Pass3 모델(Claude)만 사용)
# OpenRouter 모델 ID. 환경변수로 덮어쓰기 가능.
# ============================================================
# 플랜 "Grok 4.2" 계열 — OpenRouter 슬러그는 시기에 따라 조정. 필요 시 JAVSTORY_CORRECTION_PASS1_MODEL 로 변경.
CORRECTION_PASS1_MODEL = os.environ.get("JAVSTORY_CORRECTION_PASS1_MODEL", "x-ai/grok-4.20")
# Pass2 병렬·청크 길이는 Transcription/correction_chunk.py 의 JAVSTORY_CORRECTION_PASS2_CONCURRENCY 등 참고.
CORRECTION_PASS2_MODEL = os.environ.get("JAVSTORY_CORRECTION_PASS2_MODEL", "qwen/qwen3-235b-a22b-2507")
# OpenRouter 라우팅에 anthropic/claude-3.5-sonnet 슬러그가 더 이상 없을 수 있음(404 No endpoints).
# https://openrouter.ai/api/v1/models 기준 후속: claude-3.7-sonnet, claude-sonnet-4 등.
CORRECTION_PASS3_MODEL = os.environ.get("JAVSTORY_CORRECTION_PASS3_MODEL", "anthropic/claude-3.7-sonnet")


def correction_llm_tier(pass_n: int) -> dict:
    """
    pass_n: 1=컨텍스트(Grok 계열), 2=주교정(GLM 5.1 등), 3=별미(Claude, 선택).
    `MultiTierRouter.route(..., tier_override=...)` 형식과 동일.
    """
    if pass_n == 1:
        return {
            "rank": 99,
            "name": "correction_pass1_grok",
            "model": CORRECTION_PASS1_MODEL,
            "provider": "openrouter",
            "cost_tier": "high",
            "uncensored": True,
            "timeout": 240,
            "max_ctx": 200000,
        }
    if pass_n == 2:
        # Pass2 모델은 설정(UI)에서 런타임에 바뀔 수 있으므로, 상수 대신 환경변수 값을 매 호출 시 읽는다.
        raw = (os.environ.get("JAVSTORY_CORRECTION_PASS2_MODEL", CORRECTION_PASS2_MODEL) or "").strip()
        vlow = raw.lower()

        if vlow.startswith("ollama:"):
            omodel = raw.split(":", 1)[1].strip() if ":" in raw else "gemma4:e4b"
            _mt = (os.environ.get("JAVSTORY_CORRECTION_OLLAMA_MAX_TOKENS", "") or "").strip() or "8192"
            try:
                max_tokens = max(512, int(_mt))
            except ValueError:
                max_tokens = 8192
            return {
                "rank": 99,
                "name": "correction_pass2_ollama",
                "model": omodel or "gemma4:e4b",
                "provider": "ollama",
                "cost_tier": "free",
                "uncensored": True,
                "timeout": 600,
                "max_ctx": 32768,
                "max_tokens": max_tokens,
                "ollama_think": False,
            }

        if vlow.startswith("llamacpp:"):
            preset_id = raw.split(":", 1)[1].strip() if ":" in raw else "qwen3-14b-uncensored"
            from javstory.llm.llamacpp_backend import resolve_llamacpp_preset

            preset = resolve_llamacpp_preset(preset_id or "qwen3-14b-uncensored")
            from javstory.llm.llamacpp_backend import llamacpp_max_tokens_from_env

            max_tokens = llamacpp_max_tokens_from_env(correction=True)
            ctx_raw = (os.environ.get("JAVSTORY_LLAMACPP_CTX", "") or "").strip()
            try:
                max_ctx = max(512, int(ctx_raw)) if ctx_raw else preset.default_ctx
            except ValueError:
                max_ctx = preset.default_ctx
            return {
                "rank": 99,
                "name": "correction_pass2_llamacpp",
                "model": preset.serve_alias or preset.id,
                "llamacpp_preset": preset.id,
                "provider": "llamacpp",
                "cost_tier": "free",
                "uncensored": True,
                "timeout": 600,
                "max_ctx": max_ctx,
                "max_tokens": max_tokens,
            }

        if vlow.startswith("gemini:"):
            model_id_raw = raw.split(":", 1)[1].strip() or "gemini-2.0-flash"
            model_id = normalize_gemini_model_id(model_id_raw)
            meta = GEMINI_MODELS.get(model_id, {}) or GEMINI_MODELS.get(model_id_raw, {})
            return {
                "rank": 99,
                "name": "correction_pass2_gemini",
                "model": model_id,
                "provider": "gemini",
                "cost_tier": "high" if meta.get("is_pro") else "low",
                "uncensored": True,
                "timeout": 180,
                "max_ctx": 1_000_000,
            }
        return {
            "rank": 99,
            "name": "correction_pass2_glm51",
            "model": raw,
            "provider": "openrouter",
            "cost_tier": "high",
            "uncensored": True,
            "timeout": 180,
            "max_ctx": 196608,
        }
    if pass_n == 3:
        return {
            "rank": 99,
            "name": "correction_pass3_claude",
            "model": CORRECTION_PASS3_MODEL,
            "provider": "openrouter",
            "cost_tier": "high",
            "uncensored": False,
            "timeout": 180,
            "max_ctx": 160000,
        }
    raise ValueError(f"correction_llm_tier: pass_n must be 1..3, got {pass_n!r}")


def correction_skip_enabled() -> bool:
    v = os.environ.get("JAVSTORY_CORRECTION_SKIP", "0").strip().lower()
    return v in ("1", "true", "yes", "on")


# ============================================================
# 한국어 자막 번역 (청크 JSON) — 프로필로 모델 선택
#
# JAVSTORY_TRANSLATION_PROFILE (미설정 시 default)
#   default       — OpenRouter deepseek/deepseek-v3.2 (Non-Thinking)
#   keeper        — OpenRouter z-ai/glm-5.1 (번역 전용 · Non-Thinking / 추론 전용 R1 아님)
#   deepseek_chat — OpenRouter deepseek/deepseek-chat (V3 대화형 · Non-Thinking)
#   budget        — Ollama + JAVSTORY_TRANSLATION_OLLAMA_MODEL (기본 gemma4:e4b)
#   qwen35        — Ollama qwen3.5:9b + think=false (번역 전용 Non-Thinking; 로컬은 느리기 쉬움 —
#                   `ko_translation_chunk`에서 Qwen 전용 짧은 청크·num_predict 상한 적용, 실사용은 OpenRouter 권장)
#   qwen3_14      — Ollama qwen3:14b + think=false (번역 전용 Non-Thinking; 9B보다 무겁고 느릴 수 있음)
#   gemma3_12     — Ollama gemma3:12b + think=false (번역 전용 Non-Thinking)
#   gemma2_9      — Ollama gemma2:9b + think=false (번역 전용 Non-Thinking)
#   qwen25_7      — Ollama qwen2.5:7b + think=false (번역 전용 Non-Thinking)
# JAVSTORY_TRANSLATION_OPENROUTER_MODEL — 설정 시 OpenRouter 모델을 프로필보다 우선
# JAVSTORY_TRANSLATION_PROVIDER — openrouter|ollama, 설정 시 프로필의 provider보다 우선
# ============================================================
TRANSLATION_PROVIDER_DEFAULT = (
    os.environ.get("JAVSTORY_TRANSLATION_PROVIDER", "openrouter").strip().lower() or "openrouter"
)
if TRANSLATION_PROVIDER_DEFAULT not in ("openrouter", "ollama", "gemini", "llamacpp"):
    TRANSLATION_PROVIDER_DEFAULT = "openrouter"


def llm_platform_from_env() -> str:
    """Settings ``llmPlatform``: openai | ollama | llamacpp (openai → OpenRouter API)."""
    raw = (os.environ.get("JAVSTORY_LLM_PLATFORM", "openai") or "openai").strip().lower()
    if raw in ("openai", "openrouter"):
        return "openai"
    if raw in ("ollama", "llamacpp"):
        return raw
    return "openai"

# OpenRouter 번역 전용 슬러그(Non-Thinking 계열; R1·reasoning 전용 아님)
TRANSLATION_OPENROUTER_MODEL_DEFAULT = "deepseek/deepseek-v3.2"
TRANSLATION_OPENROUTER_MODEL_KEEPER = "z-ai/glm-5.1"
TRANSLATION_OPENROUTER_MODEL_DEEPSEEK_CHAT = "deepseek/deepseek-chat"
TRANSLATION_OLLAMA_MODEL_BUDGET_DEFAULT = "gemma4:e4b"
TRANSLATION_OLLAMA_MODEL_QWEN35_DEFAULT = "qwen3.5:9b"
TRANSLATION_OLLAMA_MODEL_QWEN3_14_DEFAULT = "qwen3:14b"
TRANSLATION_OLLAMA_MODEL_GEMMA3_12_DEFAULT = "gemma3:12b"
TRANSLATION_OLLAMA_MODEL_GEMMA2_9_DEFAULT = "gemma2:9b"
TRANSLATION_OLLAMA_MODEL_QWEN25_7_DEFAULT = "qwen2.5:7b"
TRANSLATION_OLLAMA_MODEL_JKV_12B_DEFAULT = "ja-ko-vn-jav:latest"


def _translation_profile() -> str:
    v = os.environ.get("JAVSTORY_TRANSLATION_PROFILE", "default").strip().lower()
    if v in ("keeper", "archive", "premium", "glm", "소장"):
        return "keeper"
    if v in ("budget", "cheap", "local"):
        return "budget"
    if v in ("deepseek_chat", "deepseek-chat", "ds_chat", "deepseekchat"):
        return "deepseek_chat"
    if v in ("qwen35", "qwen3.5", "qwen_35", "ollama_qwen"):
        return "qwen35"
    if v in (
        "qwen3_14",
        "qwen3-14",
        "qwen3_14b",
        "qwen3-14b",
        "qwen314",
        "qwen_14b",
        "ollama_qwen3_14",
    ):
        return "qwen3_14"
    if v in ("gemma3_12", "gemma312", "gemma3-12b", "gemma3_12b"):
        return "gemma3_12"
    if v in ("gemma2_9", "gemma29", "gemma2-9b", "gemma2_9b"):
        return "gemma2_9"
    if v in ("qwen25_7", "qwen25-7b", "qwen2.5-7b", "qwen2.5:7b"):
        return "qwen25_7"
    if v in ("jkv_12b", "ja-ko-vn", "jkv12b"):
        return "jkv_12b"
    if v in ("gemini_3_flash", "gemini3flash"):
        return "gemini_3_flash"
    if v in ("gemini_3_flash_lite", "gemini31flashlite", "gemini3flashlite"):
        return "gemini_3_flash_lite"
    if v in ("gemini_25_flash", "gemini25flash"):
        return "gemini_25_flash"
    if v in ("gemini_25_pro", "gemini25pro"):
        return "gemini_25_pro"
    if v in ("gemini_2_flash", "gemini2flash"):
        return "gemini_2_flash"
    if v in ("gemini_2_flash_lite", "gemini2flashlite"):
        return "gemini_2_flash_lite"
    return "default"


def _openrouter_translation_model() -> str:
    explicit = os.environ.get("JAVSTORY_TRANSLATION_OPENROUTER_MODEL", "").strip()
    if explicit:
        return explicit
    prof = _translation_profile()
    if prof == "keeper":
        return TRANSLATION_OPENROUTER_MODEL_KEEPER
    if prof == "deepseek_chat":
        return TRANSLATION_OPENROUTER_MODEL_DEEPSEEK_CHAT
    return TRANSLATION_OPENROUTER_MODEL_DEFAULT


def _ollama_translation_model() -> str:
    explicit = os.environ.get("JAVSTORY_TRANSLATION_OLLAMA_MODEL", "").strip()
    if explicit:
        return explicit
    prof = _translation_profile()
    if prof == "qwen35":
        return TRANSLATION_OLLAMA_MODEL_QWEN35_DEFAULT
    if prof == "qwen3_14":
        return TRANSLATION_OLLAMA_MODEL_QWEN3_14_DEFAULT
    if prof == "gemma3_12":
        return TRANSLATION_OLLAMA_MODEL_GEMMA3_12_DEFAULT
    if prof == "gemma2_9":
        return TRANSLATION_OLLAMA_MODEL_GEMMA2_9_DEFAULT
    if prof == "qwen25_7":
        return TRANSLATION_OLLAMA_MODEL_QWEN25_7_DEFAULT
    if prof == "jkv_12b":
        return TRANSLATION_OLLAMA_MODEL_JKV_12B_DEFAULT
    return TRANSLATION_OLLAMA_MODEL_BUDGET_DEFAULT


def _effective_translation_provider(translation_provider: str | None) -> str:
    if translation_provider and str(translation_provider).strip():
        p = str(translation_provider).strip().lower()
        if p in ("openrouter", "ollama", "gemini", "llamacpp"):
            return p
    platform = llm_platform_from_env()
    if platform == "llamacpp":
        return "llamacpp"
    if platform == "ollama":
        return "ollama"
    prof = _translation_profile()
    if prof in _GEMINI_PROFILE_MAP:
        return "gemini"
    if prof in (
        "budget",
        "qwen35",
        "qwen3_14",
        "gemma3_12",
        "gemma2_9",
        "qwen25_7",
        "jkv_12b",
    ):
        return "ollama"
    env_p = os.environ.get("JAVSTORY_TRANSLATION_PROVIDER", "").strip().lower()
    if env_p in ("openrouter", "ollama", "gemini", "llamacpp"):
        return env_p
    return "openrouter"


def translation_llm_tier_openrouter() -> dict:
    """JA→KO 번역 — OpenRouter (프로필·JAVSTORY_TRANSLATION_OPENROUTER_MODEL로 모델 결정)."""
    model = _openrouter_translation_model()
    is_glm = model.lower().startswith("z-ai/glm") or "glm-5" in model.lower()
    return {
        "rank": 99,
        "name": "translation_openrouter",
        "model": model,
        "provider": "openrouter",
        "cost_tier": "high" if is_glm else "low",
        "uncensored": True,
        "timeout": 240 if is_glm else 120,
        "max_ctx": 196608 if is_glm else 65536,
    }


def translation_llm_tier_llamacpp() -> dict:
    from javstory.llm.llamacpp_backend import tier_from_llamacpp_env

    return tier_from_llamacpp_env()


def translation_llm_tier_ollama() -> dict:
    # Ollama: max_tokens → num_predict. 과대(예: 12k)는 호출당 지연·VRAM 부담을 키울 수 있어 기본 8192.
    # 긴 구간 JSON이 잘리면 JAVSTORY_TRANSLATION_OLLAMA_MAX_TOKENS로 상향.
    _mt = (os.environ.get("JAVSTORY_TRANSLATION_OLLAMA_MAX_TOKENS", "") or "").strip() or "8192"
    try:
        max_tokens = max(512, int(_mt))
    except ValueError:
        max_tokens = 8192
    return {
        "rank": 99,
        "name": "translation_ollama_local",
        "model": _ollama_translation_model(),
        "provider": "ollama",
        "cost_tier": "free",
        "uncensored": True,
        "timeout": 600,
        "max_ctx": 32768,
        "max_tokens": max_tokens,
        # 번역은 JSON 출력만 필요 — Qwen3/Gemma 등에서 내부 thinking 경로 억제(Ollama가 지원할 때만 적용)
        "ollama_think": False,
    }


def gemini_translation_llm_tier(model_id: str | None = None) -> dict:
    """Gemini 번역 tier 딕셔너리. 환경변수 JAVSTORY_GEMINI_MODEL로 모델 덮어쓰기 가능."""
    prof = _translation_profile()
    resolved = (
        (model_id or "").strip()
        or os.environ.get("JAVSTORY_GEMINI_MODEL", "").strip()
        or _GEMINI_PROFILE_MAP.get(prof, "gemini-2.0-flash")
    )
    resolved_raw = resolved
    resolved = normalize_gemini_model_id(resolved)
    meta = GEMINI_MODELS.get(resolved, {}) or GEMINI_MODELS.get(resolved_raw, {})
    is_pro = bool(meta.get("is_pro"))
    return {
        "rank": 99,
        "name": "translation_gemini",
        "model": resolved,
        "provider": "gemini",
        "cost_tier": "high" if is_pro else "low",
        "uncensored": True,
        "timeout": 240 if is_pro else 120,
        "max_ctx": 1_000_000,
    }


def resolve_translation_llm_tier(
    *,
    translation_provider: str | None = None,
    translation_tier: dict | None = None,
) -> dict:
    """
    `translation_tier`에 provider·model이 있으면 베이스 티어와 병합해 반환.
    없으면 `translation_provider` → `JAVSTORY_TRANSLATION_PROVIDER` → `JAVSTORY_TRANSLATION_PROFILE`(budget→ollama) 순.
    """
    if isinstance(translation_tier, dict) and translation_tier.get("provider") and translation_tier.get("model"):
        prov = str(translation_tier.get("provider")).lower()
        if prov == "gemini":
            base = gemini_translation_llm_tier(str(translation_tier.get("model", "")))
        elif prov == "ollama":
            base = translation_llm_tier_ollama()
        elif prov == "llamacpp":
            base = translation_llm_tier_llamacpp()
        else:
            base = translation_llm_tier_openrouter()
        return {**base, **translation_tier}
    prov = _effective_translation_provider(translation_provider)
    if prov == "gemini":
        return gemini_translation_llm_tier()
    if prov == "ollama":
        return translation_llm_tier_ollama()
    if prov == "llamacpp":
        return translation_llm_tier_llamacpp()
    return translation_llm_tier_openrouter()


# ============================================================
# Harvest(크롤링) 메타 다국어 번역 모델 선택 (SettingsModel 연동)
# - 환경변수: JAVSTORY_HARVEST_TRANSLATION_MODEL
#   - openrouter:deepseek/deepseek-v3.2
#   - ollama:gemma4:e4b
#   - gemini:gemini-2.0-flash
# ============================================================
def harvest_translation_llm_tier() -> dict:
    raw = (os.environ.get("JAVSTORY_HARVEST_TRANSLATION_MODEL", "") or "").strip()
    v = raw.lower()
    if not v:
        v = "openrouter:deepseek/deepseek-v3.2"

    if v.startswith("gemini:"):
        model = raw.split(":", 1)[1].strip() if ":" in raw else "gemini-2.0-flash"
        model = model or "gemini-2.0-flash"
        meta = GEMINI_MODELS.get(model, {})
        return {
            "rank": 99,
            "name": "harvest_translation_gemini",
            "model": model,
            "provider": "gemini",
            "cost_tier": "high" if meta.get("is_pro") else "low",
            "uncensored": False,
            "timeout": 120,
            "max_ctx": 1_000_000,
        }

    if v.startswith("ollama:"):
        model = raw.split(":", 1)[1].strip() if ":" in raw else "gemma4:e4b"
        return {
            "rank": 99,
            "name": "harvest_translation_ollama",
            "model": model or "gemma4:e4b",
            "provider": "ollama",
            "cost_tier": "free",
            "uncensored": False,
            "timeout": 300,
            "max_ctx": 8192,
        }

    if v.startswith("llamacpp:"):
        model = raw.split(":", 1)[1].strip() if ":" in raw else "gemma-4-e4b"
        from javstory.llm.llamacpp_backend import resolve_llamacpp_preset

        preset = resolve_llamacpp_preset(model or "gemma-4-e4b")
        tier = translation_llm_tier_llamacpp()
        tier["model"] = preset.serve_alias or preset.id
        tier["llamacpp_preset"] = preset.id
        tier["name"] = "harvest_translation_llamacpp"
        return tier

    if v.startswith("openrouter:"):
        model = raw.split(":", 1)[1].strip() if ":" in raw else "deepseek/deepseek-v3.2"
        return {
            "rank": 99,
            "name": "harvest_translation_openrouter",
            "model": model or "deepseek/deepseek-v3.2",
            "provider": "openrouter",
            "cost_tier": "low",
            "uncensored": False,
            "timeout": 180,
            "max_ctx": 64000,
        }

    # fallback: allow passing plain model id, default to openrouter
    return {
        "rank": 99,
        "name": "harvest_translation_openrouter",
        "model": raw or "deepseek/deepseek-v3.2",
        "provider": "openrouter",
        "cost_tier": "low",
        "uncensored": False,
        "timeout": 180,
        "max_ctx": 64000,
    }


# ============================================================
# 스토리 맥락 리포트 (웹검색만·품번 검증, OpenRouter Grok 기본; 자막 미전달)
# `:online` = OpenRouter 웹 검색. 캐시: `STORY_CONTEXT_CACHE_DIR` (`data/cache/story_context/`)
# JAVSTORY_STORY_CONTEXT_USE_CACHE / JAVSTORY_STORY_CONTEXT_FORCE
# ============================================================
STORY_CONTEXT_MODEL = (
    os.environ.get("JAVSTORY_STORY_CONTEXT_MODEL", "x-ai/grok-4.3:online").strip()
    or "x-ai/grok-4.3:online"
)

STORY_CONTEXT_TEMPERATURE = float(os.environ.get("JAVSTORY_STORY_CONTEXT_TEMPERATURE", "0.3") or 0.3)
STORY_CONTEXT_MAX_TOKENS = int(os.environ.get("JAVSTORY_STORY_CONTEXT_MAX_TOKENS", "8192") or 8192)


def story_context_llm_tier(**overrides: Any) -> dict:
    """OpenRouter Grok — 품번 웹검색 전용(자막 없음). `model`·`temperature` 등은 env·overrides로 덮어쓴다."""
    base: dict[str, Any] = {
        "rank": 97,
        "name": "story_context_grok_openrouter",
        "model": STORY_CONTEXT_MODEL,
        "provider": "openrouter",
        "cost_tier": "high",
        "uncensored": True,
        "timeout": 300,
        "max_ctx": 200000,
        "temperature": STORY_CONTEXT_TEMPERATURE,
        "max_tokens": STORY_CONTEXT_MAX_TOKENS,
    }
    if overrides:
        return {**base, **overrides}
    return base


def library_story_context_batch_tier() -> dict[str, Any]:
    """라이브러리 '스토리 컨텍스트' 배치·자막 교정 스토리 캐시 경로와 동일한 OpenRouter Grok 티어 (드리프트 방지)."""
    return story_context_llm_tier(model="x-ai/grok-4.3:online")


def story_analysis_llm_tier(**overrides: Any) -> dict:
    """호환 별칭 — `story_context_llm_tier` 사용 권장."""
    return story_context_llm_tier(**overrides)


def story_analysis_enabled_from_env() -> bool:
    v = os.environ.get("JAVSTORY_STORY_ANALYSIS_ENABLED", "1").strip().lower()
    return v in ("1", "true", "yes", "on")


# [수동 선택 프리셋]
MANUAL_MODEL_PRESETS = [
    {
        "id"         : "claude_sonnet",
        "label"      : "🌟 Claude 3.7 Sonnet (OpenRouter 노출 슬러그 / 고가 / 일부 검열)",
        "model"      : "anthropic/claude-3.7-sonnet",
        "provider"   : "openrouter",
        "note"       : "3.5 슬러그는 OpenRouter에서 미노출될 수 있음. JAVSTORY_CORRECTION_PASS3_MODEL로 교체 가능.",
        "max_ctx"    : 160000,
    },
    {
        "id"         : "deepseek",
        "label"      : "💰 DeepSeek V3.2 NT (가성비 / Non Thinking)",
        "model"      : "deepseek/deepseek-v3.2",
        "provider"   : "openrouter",
        "max_ctx"    : 64000,
    },
    {
        "id"         : "hermes_free",
        "label"      : "🆓 Hermes 405B:free (무료 / 무검열 / 느림)",
        "model"      : "nousresearch/hermes-3-llama-3.1-405b:free",
        "provider"   : "openrouter",
        "max_ctx"    : 32000,
    },
    {
        "id"         : "qwen_72b",
        "label"      : "🚀 Qwen 2.5 72B (고성능 클라우드 / 유료 / 최고품질)",
        "model"      : "qwen/qwen-2.5-72b-instruct",
        "provider"   : "openrouter",
        "max_ctx"    : 32000,
    },
    {
        "id"         : "hermes_70b",
        "label"      : "⚡ Hermes 70B      (유료 중간 / 무검열 / 빠름)",
        "model"      : "nousresearch/hermes-3-llama-3.1-70b",
        "provider"   : "openrouter",
        "max_ctx"    : 32000,
    },
    {
        "id"         : "hermes_405b",
        "label"      : "👑 Hermes 405B     (유료 고가 / 무검열 / 최고품질)",
        "model"      : "nousresearch/hermes-3-llama-3.1-405b",
        "provider"   : "openrouter",
        "max_ctx"    : 32000,
    },
    {
        "id"         : "gemma2_9",
        "label"      : "🖥️  Gemma 2 (9B) Local  (가벼움 / 무검열 / 추천)",
        "model"      : "gemma2:9b",
        "provider"   : "ollama",
        "max_ctx"    : 8192,
    },
    {
        "id"         : "gemma3_12",
        "label"      : "🖥️  Gemma 3 (12B) Local (고성능 / 무검열 / 균형)",
        "model"      : "gemma3:12b",
        "provider"   : "ollama",
        "max_ctx"    : 16384,
    },
    {
        "id"         : "qwen25_7",
        "label"      : "🖥️  Qwen 2.5 (7B) Local (균형 / 범용 / 빠름)",
        "model"      : "qwen2.5:7b",
        "provider"   : "ollama",
        "max_ctx"    : 32768,
    },
    {
        "id"         : "jkv_12b",
        "label"      : "🖥️  JKV-12B Local (번역 전용 / ja-ko-vn / 추천)",
        "model"      : "ja-ko-vn-jav:latest",
        "provider"   : "ollama",
        "max_ctx"    : 32768,
    },
    {
        "id"         : "local",
        "label"      : "🖥️  Qwen 3 (8B) Local  (초고속 / 3080Ti 최적화)",
        "model"      : "qwen3:8b",
        "provider"   : "ollama",
        "max_ctx"    : 8192,
    },
    {
        "id"         : "custom",
        "label"      : "✏️  직접 입력       (OpenRouter 모델 ID)",
        "model"      : None,
        "provider"   : "openrouter",
    },
]

# [지수 백오프 및 검열 감지 설정]
LLM_RETRY_LIMIT = 4
LLM_BACKOFF_STAGES = [2, 4, 8, 16]

LLM_REFUSAL_PATTERNS = [
    r"^i (cannot|can't|am unable to)",
    r"^(sorry|i apologize).{0,30}(cannot|unable|won't)",
    r"this (request|content) (violates|goes against)",
    r"i'm (sorry|not able).{0,20}(cannot|unable)",
]

# ============================================================
# 유사도 분석(Similarity Reasoning) 관련 설정
# ============================================================
# 유사작 추천 시 '공통 장르' 분석에서 제외할 장르 목록
SIMILARITY_EXCLUDED_GENRES = {
    "단독작품", "독점", "모자이크", "고화질",
    "VR 전용", "VR 전용 기기 불필요", "스마트폰 전용",
    "독점 전송", "단독 배포", "블루레이",
    "단독 작품", "스태프 강력 추천", "직원 강력 추천",
    "스태프 추천", "하이비전", "HD", "4K"
}


def similarity_excluded_genres_from_env() -> set[str]:
    """작품 속성 태그를 취향 장르 계산에서 제외하기 위한 공통 설정."""
    raw = (os.environ.get("JAVSTORY_SIMILARITY_EXCLUDED_GENRES", "") or "").strip()
    if raw:
        return {v.strip() for v in raw.split(",") if v.strip()}
    return set(SIMILARITY_EXCLUDED_GENRES)

# 유사도 분석 시 '문맥적 유사성'의 구체적 근거로 활용할 테마 키워드 목록
SIMILARITY_THEME_KEYWORDS = [
    "신인", "데뷔", "유부녀", "여교사", "간호사", "학생", "교복", "수영복", "거유",
    "슬렌더", "사내 연애", "비밀 연애", "동급생", "선배", "후배", "가족", "모녀",
    "자매", "남매", "부녀", "근친", "강제", "최면", "시간 정지", "코스프레",
    "야외", "노출", "치한", "집단", "난교", "임신", "출산", "모유", "오줌",
    "여비서", "메이드", "OL", "승무원", "선생님", "제자", "감금", "조교",
    "SM", "속박", "방치", "수치", "정조대", "전라", "도촬", "목욕탕", "온천",
    "여행", "캠프", "첫 경험", "순애", "하드코어", "아날", "입사", "질내 사정"
]


