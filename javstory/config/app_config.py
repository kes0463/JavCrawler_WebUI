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

# 대용량 데이터(E:) 루트
E_DATA_ROOT = Path("E:/App/JAVSTORY/data")

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
        return {
            "rank": 99,
            "name": "correction_pass2_glm51",
            "model": CORRECTION_PASS2_MODEL,
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
if TRANSLATION_PROVIDER_DEFAULT not in ("openrouter", "ollama"):
    TRANSLATION_PROVIDER_DEFAULT = "openrouter"

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
        if p in ("openrouter", "ollama"):
            return p
    env_p = os.environ.get("JAVSTORY_TRANSLATION_PROVIDER", "").strip().lower()
    if env_p in ("openrouter", "ollama"):
        return env_p
    prof = _translation_profile()
    if prof in ("budget", "qwen35", "qwen3_14", "gemma3_12", "jkv_12b"):
        return "ollama"
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
        base = (
            translation_llm_tier_ollama()
            if str(translation_tier.get("provider")).lower() == "ollama"
            else translation_llm_tier_openrouter()
        )
        return {**base, **translation_tier}
    prov = _effective_translation_provider(translation_provider)
    if prov == "ollama":
        return translation_llm_tier_ollama()
    return translation_llm_tier_openrouter()


# ============================================================
# Harvest(크롤링) 메타 다국어 번역 모델 선택 (SettingsModel 연동)
# - 환경변수: JAVSTORY_HARVEST_TRANSLATION_MODEL
#   - openrouter:deepseek/deepseek-v3.2
#   - ollama:gemma4:e4b
#   - ollama:qwen2.4:14b
# ============================================================
def harvest_translation_llm_tier() -> dict:
    raw = (os.environ.get("JAVSTORY_HARVEST_TRANSLATION_MODEL", "") or "").strip()
    v = raw.lower()
    if not v:
        v = "openrouter:deepseek/deepseek-v3.2"

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
    os.environ.get("JAVSTORY_STORY_CONTEXT_MODEL", "x-ai/grok-4.1-fast:online").strip()
    or "x-ai/grok-4.1-fast:online"
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
    "독점 전송", "단독 배포", "블루레이"
}

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


