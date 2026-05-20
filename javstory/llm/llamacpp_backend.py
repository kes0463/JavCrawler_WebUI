"""
llama.cpp + TurboQuant KV 캐시 — subprocess ``llama-server`` + OpenAI 호환 ``/v1``.

환경 변수(주요):
  JAVSTORY_LLAMACPP_BIN          llama-server 실행 파일 경로
  JAVSTORY_LLAMACPP_URL          OpenAI 호환 base (기본 http://127.0.0.1:8081)
  JAVSTORY_LLAMACPP_HOST / PORT
  JAVSTORY_LLAMACPP_MODEL        프리셋 id (qwen3.5-35b-a3b | gemma-4-e4b)
  JAVSTORY_LLAMACPP_*_GGUF       프리셋별 GGUF 경로
  JAVSTORY_LLAMACPP_CACHE_TYPE_K / _V   TurboQuant (예: turbo3, q8_0)
  JAVSTORY_LLAMACPP_N_GPU_LAYERS (-ngl, 미설정 시 -fit on 으로 VRAM 자동 맞춤)
  JAVSTORY_LLAMACPP_FIT          on|off (기본 on, N_GPU 미설정 시)
  JAVSTORY_LLAMACPP_CTX          (-c, MoE 12GB VRAM 권장 4096)
  JAVSTORY_TRANSLATION_LLAMACPP_MAX_TOKENS / JAVSTORY_CORRECTION_LLAMACPP_MAX_TOKENS (기본 3072)
  JAVSTORY_LLAMACPP_STOP_AFTER_JOB  1|0 (파이프라인 후 llama-server 종료)
  JAVSTORY_LLAMACPP_PROMPT_CACHE_MB  프롬프트 캐시 RAM 상한 MiB (0=비활성, 기본 0)
  JAVSTORY_LLAMACPP_N_CPU_MOE      MoE 프리셋만: --n-cpu-moe (기본 24, 0/off=미전달)
  JAVSTORY_LLAMACPP_AUTO_START   1|0
"""

from __future__ import annotations

import atexit
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

import httpx

_lock = threading.Lock()
_server_proc: subprocess.Popen | None = None
_active_preset_id: Optional[str] = None
_log_path: Optional[Path] = None

LoggerFunc = Callable[[str], Any]

# 12GB VRAM + 32GB RAM 환경 권장 (35B MoE Q4)
LLAMACPP_DEFAULT_MAX_TOKENS = 3072
LLAMACPP_DEFAULT_CTX_MOE = 4096
LLAMACPP_DEFAULT_CTX_DENSE = 8192
# llama-server 기본 prompt cache 상한(약 8GB). JAVSTORY 기본은 0(비활성).
LLAMACPP_DEFAULT_PROMPT_CACHE_MIB = 0
LLAMACPP_SERVER_DEFAULT_PROMPT_CACHE_MIB = 8192
# Qwen3.5-A3B MoE: VRAM 여유 확보용 CPU expert 레이어 수 (preset.moe 일 때만)
LLAMACPP_DEFAULT_N_CPU_MOE = 24


def llamacpp_max_tokens_from_env(
    *,
    correction: bool = False,
    default: int = LLAMACPP_DEFAULT_MAX_TOKENS,
) -> int:
    keys = (
        ("JAVSTORY_CORRECTION_LLAMACPP_MAX_TOKENS", "JAVSTORY_TRANSLATION_LLAMACPP_MAX_TOKENS")
        if correction
        else ("JAVSTORY_TRANSLATION_LLAMACPP_MAX_TOKENS", "JAVSTORY_CORRECTION_LLAMACPP_MAX_TOKENS")
    )
    for key in keys:
        raw = (os.environ.get(key, "") or "").strip()
        if raw:
            try:
                return max(512, int(raw))
            except ValueError:
                break
    return max(512, default)


def llamacpp_stop_after_job_enabled() -> bool:
    return _env_bool("JAVSTORY_LLAMACPP_STOP_AFTER_JOB", False)


def llamacpp_n_cpu_moe_for_spawn(*, preset_moe: bool) -> int | None:
    """MoE 프리셋일 때 ``--n-cpu-moe`` 값. None이면 플래그 생략."""
    if not preset_moe:
        return None
    raw = (os.environ.get("JAVSTORY_LLAMACPP_N_CPU_MOE", "") or "").strip().lower()
    if raw in ("0", "off", "false", "no", "none"):
        return None
    if raw:
        try:
            n = int(raw)
            return n if n > 0 else None
        except ValueError:
            return LLAMACPP_DEFAULT_N_CPU_MOE
    return LLAMACPP_DEFAULT_N_CPU_MOE


def maybe_stop_llamacpp_after_job(*, logger_func: LoggerFunc | None = None) -> None:
    """JAVSTORY_LLAMACPP_STOP_AFTER_JOB=1 이면 llama-server 프로세스 종료(RAM 회복)."""
    cleanup_llamacpp_after_job(cancelled=False, logger_func=logger_func)


def cleanup_llamacpp_after_job(
    *,
    cancelled: bool = False,
    logger_func: LoggerFunc | None = None,
) -> None:
    """작업 종료 시 llama-server 정리.

    - ``cancelled=True`` (사용자 중단): 설정과 무관하게 항상 종료
    - 정상 완료: ``JAVSTORY_LLAMACPP_STOP_AFTER_JOB=1`` 일 때만 종료
    """
    if cancelled or llamacpp_stop_after_job_enabled():
        stop_llamacpp_server(logger_func=logger_func)


def _env_bool(key: str, default: bool = True) -> bool:
    raw = (os.environ.get(key, "") or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _env_int(key: str, default: int) -> int:
    try:
        return int((os.environ.get(key, str(default)) or "").strip())
    except ValueError:
        return default


def llamacpp_base_url() -> str:
    explicit = (os.environ.get("JAVSTORY_LLAMACPP_URL", "") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    host = (os.environ.get("JAVSTORY_LLAMACPP_HOST", "127.0.0.1") or "127.0.0.1").strip()
    port = _env_int("JAVSTORY_LLAMACPP_PORT", 8081)
    return f"http://{host}:{port}"


def llamacpp_openai_base_url() -> str:
    return f"{llamacpp_base_url().rstrip('/')}/v1"


def llamacpp_bin_path() -> Path:
    raw = (os.environ.get("JAVSTORY_LLAMACPP_BIN", "") or "").strip()
    if raw:
        return Path(raw).expanduser()
    # Windows: llama-server.exe, Unix: llama-server
    name = "llama-server.exe" if sys.platform == "win32" else "llama-server"
    return Path(name)


@dataclass(frozen=True)
class LlamaCppModelPreset:
    """지원 모델 프리셋 (GGUF 경로는 env로 지정)."""

    id: str
    label: str
    gguf_env: str
    moe: bool = False
    default_ctx: int = 8192
    # -1 = -ngl 생략·llama-server -fit on (VRAM에 맞게 자동). 명시 시에만 -ngl 전달.
    default_ngl: int = -1
    extra_args: tuple[str, ...] = ()
    serve_alias: str = ""


LLAMACPP_MODEL_PRESETS: Dict[str, LlamaCppModelPreset] = {
    "qwen3.5-35b-a3b": LlamaCppModelPreset(
        id="qwen3.5-35b-a3b",
        label="Qwen3.5-35B-A3B (MoE)",
        gguf_env="JAVSTORY_LLAMACPP_QWEN35_GGUF",
        moe=True,
        default_ctx=LLAMACPP_DEFAULT_CTX_MOE,
        default_ngl=-1,
        extra_args=("--flash-attn", "on"),
        serve_alias="qwen3.5-35b-a3b",
    ),
    "gemma-4-e4b": LlamaCppModelPreset(
        id="gemma-4-e4b",
        label="Gemma-4-E4B",
        gguf_env="JAVSTORY_LLAMACPP_GEMMA4_GGUF",
        moe=False,
        default_ctx=LLAMACPP_DEFAULT_CTX_DENSE,
        default_ngl=-1,
        extra_args=("--flash-attn", "on"),
        serve_alias="gemma-4-e4b",
    ),
    # 자막 교정 전용 (HauhauCS Uncensored Aggressive)
    "qwen3.5-35b-a3b-uncensored": LlamaCppModelPreset(
        id="qwen3.5-35b-a3b-uncensored",
        label="HauhauCS/Qwen3.5-35B-A3B-Uncensored-HauhauCS-Aggressive",
        gguf_env="JAVSTORY_LLAMACPP_QWEN35_UNC_GGUF",
        moe=True,
        default_ctx=LLAMACPP_DEFAULT_CTX_MOE,
        default_ngl=-1,
        extra_args=("--flash-attn", "on"),
        serve_alias="qwen3.5-35b-a3b-uncensored",
    ),
    "gemma-4-e4b-uncensored": LlamaCppModelPreset(
        id="gemma-4-e4b-uncensored",
        label="HauhauCS/Gemma-4-E4B-Uncensored-HauhauCS-Aggressive",
        gguf_env="JAVSTORY_LLAMACPP_GEMMA4_UNC_GGUF",
        moe=False,
        default_ctx=LLAMACPP_DEFAULT_CTX_DENSE,
        default_ngl=-1,
        extra_args=("--flash-attn", "on"),
        serve_alias="gemma-4-e4b-uncensored",
    ),
}


def list_llamacpp_preset_ids() -> List[str]:
    return list(LLAMACPP_MODEL_PRESETS.keys())


def _llamacpp_preset_id_from_colon_value(raw: str) -> str | None:
    """``llamacpp:gemma-4-e4b`` → ``gemma-4-e4b``."""
    s = (raw or "").strip()
    if not s.lower().startswith("llamacpp:"):
        return None
    tail = s.split(":", 1)[1].strip().lower()
    return tail or None


def _llamacpp_preset_id_from_translation_profile(profile: str) -> str | None:
    prof = (profile or "").strip().lower()
    if prof in ("qwen35", "qwen3.5", "qwen_35", "ollama_qwen"):
        return "qwen3.5-35b-a3b"
    if prof in ("budget", "gemma", "gemma4", "gemma_4"):
        return "gemma-4-e4b"
    if prof.startswith("llamacpp:"):
        return _llamacpp_preset_id_from_colon_value(prof)
    return None


def resolve_active_llamacpp_preset_id(
    *,
    llamacpp_model: str | None = None,
    correction_pass2: str | None = None,
    harvest_translation: str | None = None,
    translation_profile: str | None = None,
) -> str:
    """자막·번역·교정이 동일 GGUF를 쓰도록 프리셋 id 통합.

    우선순위: 정밀 교정(Pass2) → API llama 모델 → 크롤링 번역 → 번역 프로필.
    """
    candidates: list[str | None] = []

    def _read(key: str, override: str | None) -> str | None:
        if override is not None and str(override).strip():
            return str(override).strip()
        return (os.environ.get(key, "") or "").strip() or None

    for raw in (
        _read("JAVSTORY_CORRECTION_PASS2_MODEL", correction_pass2),
        _read("JAVSTORY_LLAMACPP_MODEL", llamacpp_model),
        _read("JAVSTORY_HARVEST_TRANSLATION_MODEL", harvest_translation),
    ):
        if not raw:
            continue
        pid = _llamacpp_preset_id_from_colon_value(raw)
        if pid:
            candidates.append(pid)
            continue
        candidates.append(raw.lower())

    prof_raw = _read("JAVSTORY_TRANSLATION_PROFILE", translation_profile)
    if prof_raw:
        pid = _llamacpp_preset_id_from_translation_profile(prof_raw)
        if pid:
            candidates.append(pid)

    for pid in candidates:
        if pid and pid in LLAMACPP_MODEL_PRESETS:
            return pid
        try:
            resolved = resolve_llamacpp_preset(pid).id
            if resolved:
                return resolved
        except Exception:
            continue

    return resolve_llamacpp_preset(None).id


def resolve_llamacpp_preset(preset_id: str | None = None) -> LlamaCppModelPreset:
    pid = (preset_id or os.environ.get("JAVSTORY_LLAMACPP_MODEL", "") or "").strip().lower()
    if not pid:
        pid = "qwen3.5-35b-a3b"
    if pid not in LLAMACPP_MODEL_PRESETS:
        # 별칭: qwen, gemma, uncensored 교정
        if "uncensored" in pid or "hauhau" in pid:
            if "gemma" in pid:
                pid = "gemma-4-e4b-uncensored"
            else:
                pid = "qwen3.5-35b-a3b-uncensored"
        elif "gemma" in pid:
            pid = "gemma-4-e4b"
        elif "qwen" in pid:
            pid = "qwen3.5-35b-a3b"
        else:
            pid = "qwen3.5-35b-a3b"
    return LLAMACPP_MODEL_PRESETS[pid]


def resolve_gguf_path(preset: LlamaCppModelPreset) -> Path:
    raw = (os.environ.get(preset.gguf_env, "") or "").strip()
    if not raw and preset.id.endswith("-uncensored"):
        base_id = preset.id[: -len("-uncensored")]
        base = LLAMACPP_MODEL_PRESETS.get(base_id)
        if base:
            raw = (os.environ.get(base.gguf_env, "") or "").strip()
    if not raw:
        raise FileNotFoundError(
            f"{preset.gguf_env} 가 비어 있습니다. Settings에서 {preset.label} GGUF 경로를 지정하세요."
        )
    p = Path(raw).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"GGUF 없음: {p}")
    return p.resolve()


@dataclass
class LlamaCppServerConfig:
    host: str = "127.0.0.1"
    port: int = 8081
    cache_type_k: str = "turbo3"
    cache_type_v: str = "q8_0"
    n_gpu_layers: int | None = None  # None → -ngl 생략, -fit on
    ctx_size: int = 8192
    parallel: int = 1
    fit_vram: bool = True
    prompt_cache_mib: int = LLAMACPP_DEFAULT_PROMPT_CACHE_MIB
    extra_cli: List[str] = field(default_factory=list)

    @classmethod
    def from_env(cls, preset: LlamaCppModelPreset) -> "LlamaCppServerConfig":
        base = urlparse(llamacpp_base_url())
        host = base.hostname or "127.0.0.1"
        port = base.port or _env_int("JAVSTORY_LLAMACPP_PORT", 8081)
        ctk = (os.environ.get("JAVSTORY_LLAMACPP_CACHE_TYPE_K", "turbo3") or "turbo3").strip()
        ctv = (os.environ.get("JAVSTORY_LLAMACPP_CACHE_TYPE_V", "q8_0") or "q8_0").strip()
        ngl_raw = (os.environ.get("JAVSTORY_LLAMACPP_N_GPU_LAYERS", "") or "").strip()
        if ngl_raw:
            ngl: int | None = max(0, int(ngl_raw))
        elif preset.default_ngl >= 0:
            ngl = preset.default_ngl
        else:
            ngl = None
        ctx = _env_int("JAVSTORY_LLAMACPP_CTX", preset.default_ctx)
        par = _env_int("JAVSTORY_LLAMACPP_PARALLEL", 1)
        fit_raw = (os.environ.get("JAVSTORY_LLAMACPP_FIT", "on") or "on").strip().lower()
        fit_vram = fit_raw not in ("0", "false", "off", "no")
        pcm_raw = (os.environ.get("JAVSTORY_LLAMACPP_PROMPT_CACHE_MB", "") or "").strip()
        if pcm_raw:
            try:
                prompt_cache_mib = max(0, int(pcm_raw))
            except ValueError:
                prompt_cache_mib = LLAMACPP_DEFAULT_PROMPT_CACHE_MIB
        else:
            prompt_cache_mib = LLAMACPP_DEFAULT_PROMPT_CACHE_MIB
        extra_raw = (os.environ.get("JAVSTORY_LLAMACPP_EXTRA_ARGS", "") or "").strip()
        extra = [x for x in extra_raw.split() if x] if extra_raw else []
        return cls(
            host=host,
            port=int(port),
            cache_type_k=ctk,
            cache_type_v=ctv,
            n_gpu_layers=ngl,
            ctx_size=max(512, ctx),
            parallel=max(1, par),
            fit_vram=fit_vram,
            prompt_cache_mib=prompt_cache_mib,
            extra_cli=extra,
        )


def build_server_argv(
    gguf: Path,
    cfg: LlamaCppServerConfig,
    preset: LlamaCppModelPreset,
) -> List[str]:
    """llama-server CLI 인자 (TurboQuant: -ctk / -ctv)."""
    bin_p = llamacpp_bin_path()
    argv: List[str] = [
        str(bin_p),
        "-m",
        str(gguf),
        "--host",
        cfg.host,
        "--port",
        str(cfg.port),
        "-c",
        str(cfg.ctx_size),
        "-ctk",
        cfg.cache_type_k,
        "-ctv",
        cfg.cache_type_v,
        "--parallel",
        str(cfg.parallel),
        "--cache-ram",
        str(max(0, cfg.prompt_cache_mib)),
    ]
    if cfg.n_gpu_layers is not None:
        argv.extend(["-ngl", str(cfg.n_gpu_layers)])
    elif cfg.fit_vram:
        argv.extend(["-fit", "on"])
    if preset.moe:
        # MoE (Qwen3.5-A3B 등): preset.moe 기준 — GGUF 파일명 매칭은 사용하지 않음
        n_cpu_moe = llamacpp_n_cpu_moe_for_spawn(preset_moe=True)
        if n_cpu_moe is not None:
            argv.extend(["--n-cpu-moe", str(n_cpu_moe)])
        moe_mode = (os.environ.get("JAVSTORY_LLAMACPP_MOE_MODE", "") or "").strip()
        if moe_mode:
            argv.extend(["--moe", moe_mode])
    argv.extend(list(preset.extra_args))
    argv.extend(cfg.extra_cli)
    return argv


def _server_health_ok(base_url: str, timeout: float = 2.0) -> bool:
    root = base_url.rstrip("/")
    for path in ("/health", "/v1/models", "/"):
        try:
            r = httpx.get(f"{root}{path}", timeout=timeout)
            if r.status_code < 500:
                return True
        except Exception:
            continue
    return False


def stop_llamacpp_server(*, logger_func: LoggerFunc | None = None) -> None:
    global _server_proc, _active_preset_id
    log = logger_func or print
    with _lock:
        proc = _server_proc
        _server_proc = None
        _active_preset_id = None
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=15)
        log("[llama.cpp] llama-server 종료")
    except subprocess.TimeoutExpired:
        proc.kill()
        log("[llama.cpp] llama-server 강제 종료")
    except Exception as e:
        log(f"[llama.cpp] 종료 중 오류(무시): {e}")


def _tail_server_log(max_lines: int = 24) -> str:
    if not _log_path or not _log_path.is_file():
        return ""
    try:
        lines = _log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception:
        return ""


def _server_exit_hint(tail: str) -> str:
    t = (tail or "").lower()
    if "cuda" in t and ("out of memory" in t or "cudamalloc failed" in t):
        return (
            "GPU VRAM 부족입니다. JAVSTORY_LLAMACPP_N_GPU_LAYERS 를 비우고 재시도(-fit 자동), "
            "또는 JAVSTORY_LLAMACPP_CTX=4096·더 작은 양자화(Q4) GGUF를 사용하세요."
        )
    if "n_gpu_layers already set" in t:
        return (
            "JAVSTORY_LLAMACPP_N_GPU_LAYERS=99 등 고정값이 VRAM에 맞지 않습니다. "
            "환경변수를 제거하거나 낮춘 뒤 다시 시도하세요."
        )
    if "failed to load model" in t or "model loading error" in t:
        return "GGUF 로드 실패 — 경로·VRAM·-c(컨텍스트) 설정을 확인하세요."
    return ""


def _spawn_server(
    argv: List[str],
    *,
    logger_func: LoggerFunc | None = None,
) -> subprocess.Popen:
    global _log_path
    log = logger_func or print
    log_dir = Path(__file__).resolve().parents[2] / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    _log_path = log_dir / "llama-server.log"
    log_f = open(_log_path, "a", encoding="utf-8")
    log_f.write(f"\n--- spawn {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    log_f.write(" ".join(argv) + "\n")
    log_f.flush()
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    proc = subprocess.Popen(
        argv,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    log(f"[llama.cpp] llama-server 시작 (pid={proc.pid}, log={_log_path})")
    return proc


def ensure_llamacpp_server_ready(
    model_cfg: Dict[str, Any] | None = None,
    *,
    logger_func: LoggerFunc | None = None,
    wait_sec: float = 120.0,
) -> str:
    """
    요청된 프리셋/모델에 맞게 llama-server가 떠 있는지 확인하고 없으면 기동.
    Returns: OpenAI API ``model`` 필드에 넣을 이름(serve_alias).
    """
    if not _env_bool("JAVSTORY_LLAMACPP_AUTO_START", True):
        base = llamacpp_base_url()
        if not _server_health_ok(base):
            raise RuntimeError(
                f"llama-server가 응답하지 않습니다 ({base}). "
                "JAVSTORY_LLAMACPP_AUTO_START=1 이거나 수동으로 서버를 띄우세요."
            )
        preset = resolve_llamacpp_preset(
            (model_cfg or {}).get("llamacpp_preset") or (model_cfg or {}).get("model")
        )
        return preset.serve_alias or preset.id

    preset_id = None
    if isinstance(model_cfg, dict):
        preset_id = model_cfg.get("llamacpp_preset") or model_cfg.get("model")
    preset = resolve_llamacpp_preset(str(preset_id) if preset_id else None)
    gguf = resolve_gguf_path(preset)
    cfg = LlamaCppServerConfig.from_env(preset)
    base = llamacpp_base_url()

    global _server_proc, _active_preset_id
    log = logger_func or print

    with _lock:
        if _server_proc is not None and _server_proc.poll() is not None:
            _server_proc = None
            _active_preset_id = None

        if (
            _server_proc is not None
            and _active_preset_id == preset.id
            and _server_health_ok(base)
        ):
            return preset.serve_alias or preset.id

        if _server_proc is not None:
            stop_llamacpp_server(logger_func=log)

    argv = build_server_argv(gguf, cfg, preset)
    proc = _spawn_server(argv, logger_func=log)
    deadline = time.time() + max(5.0, wait_sec)
    while time.time() < deadline:
        if proc.poll() is not None:
            tail = _tail_server_log()
            hint = _server_exit_hint(tail)
            msg = f"llama-server가 조기 종료되었습니다 (code={proc.returncode}). 로그: {_log_path}"
            if hint:
                msg += f"\n{hint}"
            if tail:
                msg += f"\n--- log tail ---\n{tail}"
            raise RuntimeError(msg)
        if _server_health_ok(base, timeout=2.0):
            with _lock:
                _server_proc = proc
                _active_preset_id = preset.id
            log(f"[llama.cpp] 준비 완료 — {preset.label} @ {base}/v1")
            return preset.serve_alias or preset.id
        time.sleep(0.5)

    stop_llamacpp_server(logger_func=log)
    raise TimeoutError(
        f"llama-server 헬스체크 시간 초과 ({wait_sec}s). 로그: {_log_path}"
    )


async def llamacpp_ensure_model(
    model_cfg: Dict[str, Any],
    *,
    logger_func: LoggerFunc | None = None,
) -> bool:
    """번역 시작 전 서버·모델 준비 (Ollama ``ollama_ensure_model`` 대응)."""
    try:
        ensure_llamacpp_server_ready(model_cfg, logger_func=logger_func)
        return True
    except Exception as e:
        log = logger_func or print
        log(f"[llama.cpp] 모델 준비 실패: {e}")
        return False


def tier_from_llamacpp_env() -> Dict[str, Any]:
    """``translation_llm_tier`` / harvest용 tier dict."""
    preset = resolve_llamacpp_preset(resolve_active_llamacpp_preset_id())
    max_tokens = llamacpp_max_tokens_from_env(correction=False)
    return {
        "rank": 99,
        "name": "translation_llamacpp_local",
        "model": preset.serve_alias or preset.id,
        "llamacpp_preset": preset.id,
        "provider": "llamacpp",
        "cost_tier": "free",
        "uncensored": True,
        "timeout": 600,
        "max_ctx": preset.default_ctx,
        "max_tokens": max_tokens,
    }


atexit.register(lambda: stop_llamacpp_server())
