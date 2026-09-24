"""
llama.cpp + TurboQuant KV 캐시 — subprocess ``llama-server`` + OpenAI 호환 ``/v1``.

환경 변수(주요):
  JAVSTORY_LLAMACPP_BIN          llama-server 실행 파일 경로
  JAVSTORY_LLAMACPP_URL          OpenAI 호환 base (기본 http://127.0.0.1:8081)
  JAVSTORY_LLAMACPP_HOST / PORT
  JAVSTORY_LLAMACPP_MODEL        프리셋 id (gemma-4-e4b | qwen3-14b)
  JAVSTORY_LLAMACPP_*_GGUF       프리셋별 GGUF 경로
  JAVSTORY_LLAMACPP_CACHE_TYPE_K / _V   TurboQuant (예: turbo3, q8_0)
  JAVSTORY_LLAMACPP_N_GPU_LAYERS (-ngl, 미설정 시 -fit on 으로 VRAM 자동 맞춤)
  JAVSTORY_LLAMACPP_FIT          on|off (기본 on, N_GPU 미설정 시)
  JAVSTORY_LLAMACPP_CTX          (-c, 기본 8192 × parallel 슬롯 수)
  JAVSTORY_LLAMACPP_PARALLEL     (--parallel, 미지정 시 JAVSTORY_HARVEST_CONCURRENCY 값 사용, 기본 1)
  JAVSTORY_LLAMACPP_REASONING_FORMAT  --reasoning-format (기본 deepseek, "none"이면 비활성).
    Qwen3 계열 등 <think>...</think> reasoning 모델에서 생각 과정을 delta.reasoning_content로
    분리 — 없으면 사고 과정이 그대로 content에 섞여 나와 max_tokens를 낭비하고 답변에도 노출됨.
  JAVSTORY_LLAMACPP_BATCH_SIZE   -b (프롬프트 처리/prefill 배치 크기, 미지정 시 llama.cpp 기본).
    크게 잡을수록 prefill(첫 토큰 전 프롬프트 처리)이 빨라지지만 VRAM을 더 씀 — 예: 1024, 2048.
  JAVSTORY_LLAMACPP_UBATCH_SIZE  -ub (micro-batch, 미지정 시 llama.cpp 기본). 위와 같은 취지.
    둘 다 안 지정하면 기존과 동일하게 동작(회귀 없음) — VRAM 여유를 보며 조금씩 올려서 테스트 권장.
  JAVSTORY_HARVEST_LLAMACPP_SLOT_CTX  Harvest 번역 슬롯당 ctx (미설정 시 preset.default_ctx × parallel)
  JAVSTORY_HARVEST_CONCURRENCY   Harvest 동시 실행 수 (1~5, parallel 기본 연동)
  JAVSTORY_EMBEDDINGS_PAUSE_DURING_HARVEST  Harvest 중 임베딩 일시정지 (기본 1)

Harvest 성능 튜닝 (12GB VRAM, 5병렬 예시):
  JAVSTORY_HARVEST_CONCURRENCY=5
  JAVSTORY_LLAMACPP_PARALLEL=5
  JAVSTORY_HARVEST_LLAMACPP_SLOT_CTX=4096   # total ctx = 20480 (5×4096)
  JAVSTORY_LLAMACPP_N_GPU_LAYERS=99         # Gemma-4-E4B Q4; Qwen3-14B는 parallel 3 권장
  JAVSTORY_LLAMACPP_FIT=off
  JAVSTORY_EMBEDDINGS_PAUSE_DURING_HARVEST=1
  env 변경 후 llama-server.exe 종료 후 재시작 필요
  JAVSTORY_TRANSLATION_LLAMACPP_MAX_TOKENS / JAVSTORY_CORRECTION_LLAMACPP_MAX_TOKENS (기본 3072)
  JAVSTORY_LLAMACPP_STOP_AFTER_JOB  1|0 (작업 완료 후 llama-server 종료, 기본 0 — 유휴 타임아웃으로 자동 종료)
  JAVSTORY_LLAMACPP_IDLE_SHUTDOWN   1|0 (미사용 시 자동 종료, 기본 1)
  JAVSTORY_LLAMACPP_IDLE_TIMEOUT_SEC  유휴 종료 대기(초, 기본 300=5분)
  JAVSTORY_LLAMACPP_PROMPT_CACHE_MB  프롬프트 캐시 RAM 상한 MiB (0=비활성, 기본 0)
  JAVSTORY_LLAMACPP_AUTO_START   1|0 (LLM 작업 시 자동 기동, 기본 1)
  JAVSTORY_LLAMACPP_PREWARM       1|0 (앱 시작 시 선기동, 기본 0)

듀얼 GPU (예: GPU0=3080Ti 12GB 기본, GPU1=5060Ti 16GB 보조):
  JAVSTORY_LLAMACPP_GPU0_INDEX   기본 GPU의 CUDA 인덱스 (기본 0, 3080Ti)
  JAVSTORY_LLAMACPP_GPU1_INDEX   보조 GPU의 CUDA 인덱스 (기본 1, 5060Ti)
  JAVSTORY_LLAMACPP_MULTI_GPU    auto|on|off (기본 auto)
    - auto: GPU가 실제로 2장 이상 감지되고, GGUF 파일 크기가 임계값을 넘을 때만
      GPU1도 노출해 분할 로딩. GPU가 1장뿐이면(예: 아직 3080Ti 미장착) 항상 단일 GPU.
    - on/off: 감지 결과와 무관하게 강제
  JAVSTORY_LLAMACPP_GPU_SPLIT_THRESHOLD_GB  분할 임계값 GiB (기본 12 = 3080Ti VRAM)
  JAVSTORY_LLAMACPP_MAIN_GPU     분할 시 llama-server --main-gpu (기본 0 = GPU0/3080Ti)
  JAVSTORY_LLAMACPP_SPLIT_MODE   layer|row|none (기본 layer, --split-mode)
  JAVSTORY_LLAMACPP_TENSOR_SPLIT 수동 비율 오버라이드 (예: "1,0.5"). 미지정 시 --tensor-split을
    아예 안 넘겨 llama.cpp -fit이 ngl과 분배 비율을 함께 계산하게 둔다 — 직접 넘기면
    ("model_params::tensor_split already set by user") -fit의 자체 적합성 검사가
    건너뛰어져 VRAM이 실제로 부족할 때 Windows 드라이버가 시스템 RAM으로 조용히
    넘쳐서(spillover) 10~50배 느려질 수 있다. 지정할 거면 JAVSTORY_LLAMACPP_N_GPU_LAYERS도
    함께 명시해 -fit을 완전히 끄고 수동으로 다 책임지는 걸 권장.
  JAVSTORY_LLAMACPP_GPU_COUNT_OVERRIDE  감지된 GPU 수 강제 지정(테스트/디버그용)
"""

from __future__ import annotations

import atexit
import os
import re
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

import httpx

_lock = threading.Lock()
# ensure_llamacpp_server_ready() 전체(존재 확인 → 헬스체크 → spawn 결정)를 직렬화한다.
# harvest 동시 번역 워커 여러 개가 거의 동시에 "서버 없음"으로 판단해 llama-server를
# 중복 기동하는 레이스를 막기 위함 — _lock 은 짧은 상태 갱신에만 쓰고, 이 락은
# 함수 전체(spawn 대기 포함)를 감싼다.
_ensure_lock = threading.Lock()
_server_proc: subprocess.Popen | None = None
_active_preset_id: Optional[str] = None
_active_base_url: Optional[str] = None
_log_path: Optional[Path] = None
_last_activity_at: float = time.time()
_active_requests: int = 0
_idle_thread: threading.Thread | None = None
_idle_stop_event = threading.Event()
_idle_shutdown_logged = False
_idle_managed_port: int | None = None
_reuse_log_base: str | None = None
_active_server_config_key: str | None = None
_spawning: bool = False

LoggerFunc = Callable[[str], Any]

# 12GB VRAM + 32GB RAM 환경 권장
LLAMACPP_DEFAULT_MAX_TOKENS = 3072
LLAMACPP_DEFAULT_CTX_DENSE = 8192
# llama-server 기본 prompt cache 상한(약 8GB). JAVSTORY 기본은 0(비활성).
LLAMACPP_DEFAULT_PROMPT_CACHE_MIB = 0
LLAMACPP_SERVER_DEFAULT_PROMPT_CACHE_MIB = 8192


def _port_bind_probe(host: str, port: int) -> Dict[str, Any]:
    """Probe whether this process can bind host:port without keeping it open."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return {"bind_ok": True, "host": host, "port": port}
        except OSError as exc:
            return {
                "bind_ok": False,
                "host": host,
                "port": port,
                "errno": exc.errno,
                "winerror": getattr(exc, "winerror", None),
                "strerror": str(exc),
            }


def _llamacpp_port_is_user_pinned(host: str, port: int) -> bool:
    """Return True when env points to a non-default endpoint we should not rewrite."""
    raw_url = (os.environ.get("JAVSTORY_LLAMACPP_URL", "") or "").strip()
    raw_port = (os.environ.get("JAVSTORY_LLAMACPP_PORT", "") or "").strip()
    default_hosts = {"127.0.0.1", "localhost", "::1"}
    if raw_url:
        parsed = urlparse(raw_url)
        url_host = (parsed.hostname or host or "").strip().lower()
        url_port = int(parsed.port or port)
        # SettingsModel persists the default local URL into the environment, so
        # localhost:8081 still needs automatic recovery when Windows reserves it.
        return not (url_host in default_hosts and url_port == 8081)
    if raw_port:
        try:
            return int(raw_port) != 8081
        except ValueError:
            return True
    return False


def _find_bindable_llamacpp_port(host: str, preferred_port: int) -> tuple[int, Dict[str, Any]] | None:
    candidates = [preferred_port] + list(range(preferred_port + 1, preferred_port + 41)) + [18081, 18082, 28081]
    seen: set[int] = set()
    for port in candidates:
        if port in seen or port <= 0 or port > 65535:
            continue
        seen.add(port)
        if sys.platform == "win32" and _port_is_listening_netstat(port):
            continue
        probe = _port_bind_probe(host, port)
        if probe.get("bind_ok"):
            return port, probe
    return None


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


def llamacpp_idle_shutdown_enabled() -> bool:
    return _env_bool("JAVSTORY_LLAMACPP_IDLE_SHUTDOWN", True)


def llamacpp_idle_timeout_sec_from_env() -> int:
    return max(30, _env_int("JAVSTORY_LLAMACPP_IDLE_TIMEOUT_SEC", 300))


def harvest_slot_ctx_from_env() -> int | None:
    """Per-slot ctx for Harvest translation when JAVSTORY_LLAMACPP_CTX is unset."""
    raw = (os.environ.get("JAVSTORY_HARVEST_LLAMACPP_SLOT_CTX", "") or "").strip()
    if not raw:
        return None
    try:
        return max(512, int(raw))
    except ValueError:
        return None


def harvest_concurrency_for_llamacpp() -> int:
    raw = (os.environ.get("JAVSTORY_HARVEST_CONCURRENCY", "") or "").strip()
    try:
        n = int(raw) if raw else 1
    except ValueError:
        n = 1
    return max(1, min(5, n))


def server_config_fingerprint(cfg: "LlamaCppServerConfig", gguf: Path) -> str:
    ngl = cfg.n_gpu_layers if cfg.n_gpu_layers is not None else "fit"
    # tensor_split은 사용자가 JAVSTORY_LLAMACPP_TENSOR_SPLIT을 명시한 경우에만 지문에
    # 반영한다 — 매 호출 값이 흔들릴 수 있는 값을 그대로 넣으면 실제로는 설정이 안
    # 바뀌었는데도 "불일치"로 오인해 llama-server를 매번 재시작하게 될 수 있다.
    ts_explicit = (os.environ.get("JAVSTORY_LLAMACPP_TENSOR_SPLIT", "") or "").strip()
    ts_key = ts_explicit if ts_explicit else "auto"
    return (
        f"{gguf.resolve()}|c={cfg.ctx_size}|p={cfg.parallel}|ngl={ngl}|"
        f"fit={int(cfg.fit_vram)}|k={cfg.cache_type_k}|v={cfg.cache_type_v}|"
        f"pcm={cfg.prompt_cache_mib}|cvd={cfg.cuda_visible_devices}|mg={cfg.main_gpu}|"
        f"ts={ts_key}|sm={cfg.split_mode}|rf={cfg.reasoning_format}|"
        f"b={cfg.batch_size or '-'}|ub={cfg.ubatch_size or '-'}"
    )


def describe_llamacpp_spawn_diagnostics(
    model_cfg: Dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return would-be llama-server argv and env snapshot for troubleshooting."""
    try:
        runtime = resolve_translation_llamacpp_runtime(model_cfg)
        cfg = LlamaCppServerConfig.from_env(runtime.preset, runtime.gguf)
        argv = build_server_argv(runtime.gguf, cfg, runtime.preset)
        log_path = Path(__file__).resolve().parents[2] / "data" / "logs" / "llama-server.log"
        return {
            "argv": argv,
            "command": " ".join(argv),
            "parallel": cfg.parallel,
            "ctx_size": cfg.ctx_size,
            "slot_ctx": cfg.ctx_size // max(1, cfg.parallel),
            "n_gpu_layers": cfg.n_gpu_layers,
            "fit_vram": cfg.fit_vram,
            "gguf": str(runtime.gguf),
            "model": runtime.serve_alias,
            "log_path": str(log_path),
            "log_exists": log_path.is_file(),
            "harvest_concurrency": harvest_concurrency_for_llamacpp(),
            "harvest_slot_ctx_env": os.environ.get("JAVSTORY_HARVEST_LLAMACPP_SLOT_CTX", ""),
            "gpu_plan": resolve_llamacpp_gpu_plan(runtime.gguf),
        }
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _port_from_base_url(base: str) -> int:
    parsed = urlparse(base)
    return int(parsed.port or 8081)


def _track_managed_server(preset_id: str, base: str) -> None:
    """AUTO_START=1 일 때 idle 종료 대상으로 포트·프리셋 등록."""
    global _active_preset_id, _idle_managed_port, _last_activity_at
    if not _env_bool("JAVSTORY_LLAMACPP_AUTO_START", True):
        return
    with _lock:
        _active_preset_id = preset_id
        _idle_managed_port = _port_from_base_url(base)
        _last_activity_at = time.time()


def _finalize_server_ready(
    preset: LlamaCppModelPreset,
    base: str,
    *,
    runtime_id: str | None = None,
    config_key: str | None = None,
    logger_func: LoggerFunc | None = None,
) -> None:
    global _active_server_config_key, _spawning
    if config_key:
        _active_server_config_key = config_key
    _spawning = False
    _track_managed_server(runtime_id or preset.id, base)
    _ensure_idle_monitor_started(logger_func=logger_func)


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
    - 정상 완료: ``JAVSTORY_LLAMACPP_STOP_AFTER_JOB=1`` 일 때만 종료 (기본 0 — 유휴 타임아웃으로 자동 종료)
    """
    if cancelled or llamacpp_stop_after_job_enabled():
        stop_llamacpp_server(logger_func=logger_func)


def persona_chat_uses_managed_llamacpp() -> bool:
    """외부 OpenAI 호환 URL이 아닌, JAVSTORY가 기동·종료하는 llama-server 경로인지."""
    configured_base = (os.environ.get("JAVSTORY_PERSONA_CHAT_BASE_URL") or "").strip()
    if configured_base:
        return False
    return _env_bool("JAVSTORY_LLAMACPP_AUTO_START", True)


def cleanup_managed_llamacpp_after_job(
    *,
    cancelled: bool = False,
    logger_func: LoggerFunc | None = None,
) -> None:
    """페르소나챗 턴 종료 후 정리 — ``cleanup_llamacpp_after_job``과 달리
    ``JAVSTORY_LLAMACPP_STOP_AFTER_JOB``(번역/교정 배치용 플래그)은 무시한다.

    채팅은 턴마다 연속으로 이어지므로, 매 턴 정상 완료 시 서버를 내렸다 올리면
    (특히 대형 모델) 다음 메시지마다 VRAM을 통째로 재로딩하게 된다. 사용자가
    직접 중지(``cancelled=True``)했을 때만 즉시 종료하고, 그 외엔 유휴 타임아웃
    모니터가 자동으로 정리하게 둔다.
    """
    if not persona_chat_uses_managed_llamacpp():
        return
    if cancelled:
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


def _env_float(key: str, default: float) -> float:
    try:
        return float((os.environ.get(key, str(default)) or "").strip())
    except ValueError:
        return default


_gpu_count_cache: int | None = None


def _detected_cuda_gpu_count() -> int:
    """설치된 NVIDIA GPU 개수 (``nvidia-smi -L`` 기준, 프로세스 수명 동안 캐시)."""
    global _gpu_count_cache
    override = (os.environ.get("JAVSTORY_LLAMACPP_GPU_COUNT_OVERRIDE", "") or "").strip()
    if override:
        try:
            return max(0, int(override))
        except ValueError:
            pass
    if _gpu_count_cache is not None:
        return _gpu_count_cache
    count = 0
    try:
        cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0  # type: ignore[attr-defined]
        result = subprocess.run(
            ["nvidia-smi", "-L"],
            capture_output=True, text=True, check=False, timeout=5,
            creationflags=cflags,
        )
        count = sum(1 for ln in result.stdout.splitlines() if ln.strip().upper().startswith("GPU "))
    except Exception:
        count = 0
    _gpu_count_cache = count
    return count


def llamacpp_gpu_split_threshold_gb() -> float:
    return max(0.1, _env_float("JAVSTORY_LLAMACPP_GPU_SPLIT_THRESHOLD_GB", 12.0))


def _gguf_size_gb(gguf: Path | None) -> float:
    if gguf is None:
        return 0.0
    try:
        return gguf.stat().st_size / (1024**3)
    except OSError:
        return 0.0


def resolve_llamacpp_gpu_plan(gguf: Path | None = None) -> Dict[str, Any]:
    """GPU0(기본, 예: 3080Ti) + GPU1(보조, 예: 5060Ti) 분할 로딩 계획.

    기본은 GPU0 단독 사용. ``JAVSTORY_LLAMACPP_MULTI_GPU=auto``(기본)에서는
    GPU가 실제로 2장 이상 감지되고 GGUF 파일 크기가 임계값을 넘을 때만 GPU1을
    노출해 llama.cpp가 레이어를 분할 로딩하게 한다 — GPU가 1장뿐이면(예: 아직
    3080Ti를 재장착하기 전) 크기와 무관하게 항상 GPU0 단독으로 동작해 기존
    ``-fit``(VRAM 자동 맞춤) 동작을 그대로 보존한다.
    """
    gpu0 = max(0, _env_int("JAVSTORY_LLAMACPP_GPU0_INDEX", 0))
    gpu1 = max(0, _env_int("JAVSTORY_LLAMACPP_GPU1_INDEX", 1))
    mode = (os.environ.get("JAVSTORY_LLAMACPP_MULTI_GPU", "auto") or "auto").strip().lower()
    threshold_gb = llamacpp_gpu_split_threshold_gb()
    size_gb = _gguf_size_gb(gguf)
    gpu_count = _detected_cuda_gpu_count()

    if mode in ("on", "1", "true", "yes", "always"):
        multi = True
    elif mode in ("off", "0", "false", "no", "never"):
        multi = False
    else:
        multi = gpu_count > gpu1 and size_gb > threshold_gb

    cuda_visible = f"{gpu0},{gpu1}" if multi else str(gpu0)
    main_gpu = max(0, _env_int("JAVSTORY_LLAMACPP_MAIN_GPU", 0))
    # tensor_split을 명시하지 않은 채로 두면 -fit이 ngl과 GPU 분배 비율을 함께
    # 계산해 VRAM에 안전하게 맞춘다. 여기서 자동으로 비율을 계산해 넘기면(과거엔
    # GPU0 대역폭 가중치를 줬었음) llama.cpp가 "tensor_split already set by user"로
    # 보고 그 fit 계산 자체를 건너뛰어 버려서(-ngl 강제와 동일한 문제) VRAM
    # 오버플로 시 Windows 드라이버가 시스템 RAM으로 조용히 넘겨(spillover)
    # 10~50배 느려질 수 있다 — 그래서 명시적으로 지정한 경우에만 넘긴다.
    tensor_split = (os.environ.get("JAVSTORY_LLAMACPP_TENSOR_SPLIT", "") or "").strip() or None
    split_mode = (os.environ.get("JAVSTORY_LLAMACPP_SPLIT_MODE", "layer") or "layer").strip().lower()

    return {
        "multi_gpu": multi,
        "gpu0_index": gpu0,
        "gpu1_index": gpu1,
        "detected_gpu_count": gpu_count,
        "cuda_visible_devices": cuda_visible,
        "main_gpu": main_gpu,
        "tensor_split": tensor_split,
        "split_mode": split_mode,
        "gguf_size_gb": round(size_gb, 2),
        "threshold_gb": threshold_gb,
    }


def touch_llamacpp_activity() -> None:
    global _last_activity_at
    with _lock:
        _last_activity_at = time.time()


def begin_llamacpp_request() -> None:
    global _active_requests, _last_activity_at
    with _lock:
        _active_requests += 1
        _last_activity_at = time.time()


def end_llamacpp_request() -> None:
    global _active_requests, _last_activity_at
    with _lock:
        _active_requests = max(0, _active_requests - 1)
        _last_activity_at = time.time()


@contextmanager
def llamacpp_request_scope():
    begin_llamacpp_request()
    try:
        yield
    finally:
        end_llamacpp_request()


def get_active_llamacpp_requests() -> int:
    with _lock:
        return _active_requests


def _wait_for_llamacpp_idle(
    timeout: float = 30.0,
    *,
    poll_interval: float = 0.25,
    logger_func: LoggerFunc | None = None,
) -> bool:
    """진행 중인 요청(_active_requests)이 0이 될 때까지 대기.

    다른 기능(번역/교정/페르소나챗/페르소나카드)이 공유 llama-server를 쓰는 중에
    모델 교체를 위해 프로세스를 죽이지 않도록, kill 직전 호출한다. 타임아웃되면
    경고만 남기고 False를 반환 — 호출자는 그래도 진행한다(영원히 막지 않음).
    """
    if get_active_llamacpp_requests() <= 0:
        return True
    log = logger_func or print
    log("[llama.cpp] 다른 작업이 llama-server를 사용 중 — 완료 대기 중...")
    deadline = time.time() + max(0.0, timeout)
    while time.time() < deadline:
        if get_active_llamacpp_requests() <= 0:
            return True
        time.sleep(poll_interval)
    log(
        f"[llama.cpp] {timeout:.0f}초 대기 후에도 사용 중 — 진행(모델 교체를 계속합니다)"
    )
    return False


def llamacpp_base_url() -> str:
    if _active_base_url:
        return _active_base_url.rstrip("/")
    explicit = (os.environ.get("JAVSTORY_LLAMACPP_URL", "") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    host = (os.environ.get("JAVSTORY_LLAMACPP_HOST", "127.0.0.1") or "127.0.0.1").strip()
    port = _env_int("JAVSTORY_LLAMACPP_PORT", 8081)
    return f"http://{host}:{port}"


def llamacpp_openai_base_url() -> str:
    return f"{llamacpp_base_url().rstrip('/')}/v1"


def llamacpp_server_status() -> Dict[str, Any]:
    """Insight/Persona Chat 모델 드롭다운의 상태 폴링용 스냅샷.

    state: "stopped" | "spawning" | "ready" | "busy"
    """
    with _lock:
        proc = _server_proc
        preset_id = _active_preset_id
        spawning = _spawning
        active = _active_requests

    if proc is None and not spawning:
        state = "stopped"
    elif spawning:
        state = "spawning"
    elif active > 0:
        state = "busy"
    else:
        state = "ready"

    label = preset_id
    if preset_id and preset_id in LLAMACPP_MODEL_PRESETS:
        label = LLAMACPP_MODEL_PRESETS[preset_id].label

    return {
        "state": state,
        "active_preset_id": preset_id,
        "active_label": label,
        "base_url": llamacpp_base_url(),
        "active_requests": active,
        "persona_chat_managed": persona_chat_uses_managed_llamacpp(),
    }


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
    default_ctx: int = 8192
    # -1 = -ngl 생략·llama-server -fit on (VRAM에 맞게 자동). 명시 시에만 -ngl 전달.
    default_ngl: int = -1
    extra_args: tuple[str, ...] = ()
    serve_alias: str = ""


LLAMACPP_MODEL_PRESETS: Dict[str, LlamaCppModelPreset] = {
    "gemma-4-e4b": LlamaCppModelPreset(
        id="gemma-4-e4b",
        label="Gemma-4-E4B",
        gguf_env="JAVSTORY_LLAMACPP_GEMMA4_GGUF",
        default_ctx=LLAMACPP_DEFAULT_CTX_DENSE,
        default_ngl=-1,
        extra_args=("--flash-attn", "on"),
        serve_alias="gemma-4-e4b",
    ),
    # 자막 교정/페르소나 챗 전용
    "gemma-4-e4b-uncensored": LlamaCppModelPreset(
        id="gemma-4-e4b-uncensored",
        label="HauhauCS/Gemma-4-E4B-Uncensored-HauhauCS-Aggressive",
        gguf_env="JAVSTORY_LLAMACPP_GEMMA4_UNC_GGUF",
        default_ctx=LLAMACPP_DEFAULT_CTX_DENSE,
        default_ngl=-1,
        extra_args=("--flash-attn", "on"),
        serve_alias="gemma-4-e4b-uncensored",
    ),
    "qwen3-14b": LlamaCppModelPreset(
        id="qwen3-14b",
        label="Qwen3-14B (Dense)",
        gguf_env="JAVSTORY_LLAMACPP_QWEN3_14B_GGUF",
        default_ctx=LLAMACPP_DEFAULT_CTX_DENSE,
        default_ngl=-1,
        extra_args=("--flash-attn", "on"),
        serve_alias="qwen3-14b",
    ),
    "qwen3-14b-uncensored": LlamaCppModelPreset(
        id="qwen3-14b-uncensored",
        label="mradermacher/Qwen3-14B-Uncensored",
        gguf_env="JAVSTORY_LLAMACPP_QWEN3_14B_UNC_GGUF",
        default_ctx=LLAMACPP_DEFAULT_CTX_DENSE,
        default_ngl=-1,
        extra_args=("--flash-attn", "on"),
        serve_alias="qwen3-14b-uncensored",
    ),
    "qwen2.5-14b": LlamaCppModelPreset(
        id="qwen2.5-14b",
        label="Qwen2.5-14B-Instruct",
        gguf_env="JAVSTORY_LLAMACPP_QWEN25_14B_GGUF",
        default_ctx=16384,
        default_ngl=99,
        extra_args=("--flash-attn", "on"),
        serve_alias="qwen2.5-14b",
    ),
    # 듀얼 GPU(3080Ti 12GB + 5060Ti 16GB) 대형 모델 — GGUF 크기가
    # JAVSTORY_LLAMACPP_GPU_SPLIT_THRESHOLD_GB(기본 12GB)를 넘으면 자동으로
    # GPU0+GPU1 분할 로딩된다 (resolve_llamacpp_gpu_plan 참고).
    "gemma-3-12b": LlamaCppModelPreset(
        id="gemma-3-12b",
        label="Gemma-3-12B-Instruct",
        gguf_env="JAVSTORY_LLAMACPP_GEMMA3_12B_GGUF",
        default_ctx=LLAMACPP_DEFAULT_CTX_DENSE,
        default_ngl=-1,
        extra_args=("--flash-attn", "on"),
        serve_alias="gemma-3-12b",
    ),
    "gemma4-31b-uncensored": LlamaCppModelPreset(
        id="gemma4-31b-uncensored",
        label="HauhauCS/Gemma4-31B-QAT-Uncensored-Balanced",
        gguf_env="JAVSTORY_LLAMACPP_GEMMA4_31B_UNC_GGUF",
        default_ctx=LLAMACPP_DEFAULT_CTX_DENSE,
        default_ngl=-1,
        extra_args=("--flash-attn", "on"),
        serve_alias="gemma4-31b-uncensored",
    ),
    "qwen38-27b-hauhaucs-uncensored": LlamaCppModelPreset(
        id="qwen38-27b-hauhaucs-uncensored",
        label="HauhauCS/Qwen3.8-27B-Uncensored-Aggressive",
        gguf_env="JAVSTORY_LLAMACPP_QWEN38_27B_HAUHAU_GGUF",
        default_ctx=LLAMACPP_DEFAULT_CTX_DENSE,
        default_ngl=-1,
        extra_args=("--flash-attn", "on"),
        serve_alias="qwen38-27b-hauhaucs-uncensored",
    ),
    "qwen38-27b-obliterated": LlamaCppModelPreset(
        id="qwen38-27b-obliterated",
        label="OBLITERATUS/Qwen3.8-27B-OBLITERATED",
        gguf_env="JAVSTORY_LLAMACPP_QWEN38_27B_OBLITERATED_GGUF",
        default_ctx=LLAMACPP_DEFAULT_CTX_DENSE,
        default_ngl=-1,
        extra_args=("--flash-attn", "on"),
        serve_alias="qwen38-27b-obliterated",
    ),
    "qwen38-27b-orcarouter-uncensored": LlamaCppModelPreset(
        id="qwen38-27b-orcarouter-uncensored",
        label="orcarouter/Qwen3.8-27B-Uncensored",
        gguf_env="JAVSTORY_LLAMACPP_QWEN38_27B_ORCAROUTER_GGUF",
        default_ctx=LLAMACPP_DEFAULT_CTX_DENSE,
        default_ngl=-1,
        extra_args=("--flash-attn", "on"),
        serve_alias="qwen38-27b-orcarouter-uncensored",
    ),
    # mmproj(비전) 동봉본이지만 --mmproj 인자는 아직 배선되지 않아 텍스트 전용으로만 서빙됨.
    "qwen25-vl-7b-abliterated": LlamaCppModelPreset(
        id="qwen25-vl-7b-abliterated",
        label="Qwen2.5-VL-7B-Instruct-abliterated",
        gguf_env="JAVSTORY_LLAMACPP_QWEN25_VL_7B_GGUF",
        default_ctx=LLAMACPP_DEFAULT_CTX_DENSE,
        default_ngl=-1,
        extra_args=("--flash-attn", "on"),
        serve_alias="qwen25-vl-7b-abliterated",
    ),
    "qwen35-9b-uncensored": LlamaCppModelPreset(
        id="qwen35-9b-uncensored",
        label="Qwen3.5-9B-Uncensored-HauhauCS-Aggressive",
        gguf_env="JAVSTORY_LLAMACPP_QWEN35_9B_GGUF",
        default_ctx=LLAMACPP_DEFAULT_CTX_DENSE,
        default_ngl=-1,
        extra_args=("--flash-attn", "on"),
        serve_alias="qwen35-9b-uncensored",
    ),
    # MoE(A3B, 활성 파라미터 ~3B) — dense 프리셋과 동일한 argv로 기동(전용 --n-cpu-moe 오프로드 미구현).
    "qwen36-35b-a3b-uncensored": LlamaCppModelPreset(
        id="qwen36-35b-a3b-uncensored",
        label="Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive",
        gguf_env="JAVSTORY_LLAMACPP_QWEN36_35B_A3B_GGUF",
        default_ctx=LLAMACPP_DEFAULT_CTX_DENSE,
        default_ngl=-1,
        extra_args=("--flash-attn", "on"),
        serve_alias="qwen36-35b-a3b-uncensored",
    ),
    "translategemma-12b": LlamaCppModelPreset(
        id="translategemma-12b",
        label="TranslateGemma-12B-it",
        gguf_env="JAVSTORY_LLAMACPP_TRANSLATEGEMMA_12B_GGUF",
        default_ctx=LLAMACPP_DEFAULT_CTX_DENSE,
        default_ngl=-1,
        extra_args=("--flash-attn", "on"),
        serve_alias="translategemma-12b",
    ),
    "qwen38-27b-unsloth": LlamaCppModelPreset(
        id="qwen38-27b-unsloth",
        label="unsloth/Qwen3.8-27B-UD-Q4_K_XL",
        gguf_env="JAVSTORY_LLAMACPP_QWEN38_27B_UNSLOTH_GGUF",
        default_ctx=LLAMACPP_DEFAULT_CTX_DENSE,
        default_ngl=-1,
        extra_args=("--flash-attn", "on"),
        serve_alias="qwen38-27b-unsloth",
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
        return "qwen3-14b"
    if prof in ("qwen3_14", "qwen3-14", "qwen14", "qwen_14"):
        return "qwen3-14b"
    if prof in ("qwen25_14", "qwen2.5-14b", "qwen25-14b", "qwen2.5_14b"):
        return "qwen2.5-14b"
    if prof in ("budget", "gemma", "gemma4", "gemma_4"):
        return "gemma-4-e4b"
    if prof.startswith("llamacpp:"):
        return _llamacpp_preset_id_from_colon_value(prof)
    return None


GGUF_OPTION_PREFIX = "gguf:"
GGUF_SCAN_DIR_ENV = "JAVSTORY_LLAMACPP_GGUF_SCAN_DIR"
LLAMACPP_GGUF_PATH_ENV = "JAVSTORY_LLAMACPP_GGUF_PATH"
DEFAULT_GGUF_SCAN_DIR = Path(r"D:\Models")


def is_gguf_option_id(model_id: str) -> bool:
    return (model_id or "").strip().lower().startswith(GGUF_OPTION_PREFIX)


def gguf_option_id(path: Path | str) -> str:
    return GGUF_OPTION_PREFIX + str(Path(path).expanduser().resolve())


def parse_gguf_option_id(model_id: str) -> Path | None:
    s = (model_id or "").strip()
    if not s.lower().startswith(GGUF_OPTION_PREFIX):
        return None
    p = Path(s[len(GGUF_OPTION_PREFIX) :]).expanduser()
    return p.resolve() if p.is_file() else None


def resolve_translation_llamacpp_preset_id() -> str:
    """번역 설정·실행용 프리셋. 교정 Pass2 / Harvest 모델과 분리."""
    raw_model = (os.environ.get("JAVSTORY_LLAMACPP_MODEL", "") or "").strip()
    if raw_model:
        if is_gguf_option_id(raw_model):
            return raw_model
        raw_lower = raw_model.lower()
        if raw_lower in LLAMACPP_MODEL_PRESETS:
            return raw_lower
        try:
            return resolve_llamacpp_preset(raw_lower).id
        except Exception:
            pass

    prof_raw = (os.environ.get("JAVSTORY_TRANSLATION_PROFILE", "") or "").strip()
    pid = _llamacpp_preset_id_from_translation_profile(prof_raw)
    if pid and pid in LLAMACPP_MODEL_PRESETS:
        return pid

    return resolve_llamacpp_preset(None).id


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
        pid = "gemma-4-e4b"
    if pid not in LLAMACPP_MODEL_PRESETS:
        # 별칭: qwen, gemma, uncensored 교정
        if "uncensored" in pid or "hauhau" in pid:
            if "gemma" in pid:
                pid = "gemma-4-e4b-uncensored"
            else:
                pid = "qwen3-14b-uncensored"
        elif "gemma" in pid:
            pid = "gemma-4-e4b"
        elif "qwen2.5" in pid or "qwen25" in pid:
            pid = "qwen2.5-14b"
        elif "qwen" in pid:
            pid = "qwen3-14b"
        else:
            pid = "gemma-4-e4b"
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


def gguf_scan_dir_from_env() -> Path:
    raw = (os.environ.get(GGUF_SCAN_DIR_ENV, "") or "").strip()
    return Path(raw or DEFAULT_GGUF_SCAN_DIR).expanduser()


def discover_gguf_models(*, scan_dir: Path | None = None) -> List[Dict[str, str]]:
    """``scan_dir`` 아래 ``*.gguf`` 파일을 재귀 검색."""
    root = scan_dir or gguf_scan_dir_from_env()
    if not root.is_dir():
        return []
    out: List[Dict[str, str]] = []
    for p in sorted(root.rglob("*.gguf"), key=lambda x: x.name.lower()):
        if p.is_file():
            resolved = p.resolve()
            out.append(
                {
                    "id": gguf_option_id(resolved),
                    "label": p.name,
                    "gguf_path": str(resolved),
                    "gguf_env": "",
                }
            )
    return out


def list_translation_gguf_model_options() -> List[Dict[str, str]]:
    options = discover_gguf_models()
    current = (os.environ.get(LLAMACPP_GGUF_PATH_ENV, "") or "").strip()
    if not current:
        mid = (os.environ.get("JAVSTORY_LLAMACPP_MODEL", "") or "").strip()
        if is_gguf_option_id(mid):
            parsed = parse_gguf_option_id(mid)
            if parsed:
                current = str(parsed)
    if current:
        cp = Path(current).expanduser()
        if cp.is_file():
            cid = gguf_option_id(cp)
            if not any(o["id"] == cid for o in options):
                options.insert(
                    0,
                    {
                        "id": cid,
                        "label": f"{cp.name} (현재)",
                        "gguf_path": str(cp.resolve()),
                        "gguf_env": "",
                    },
                )
    return options


def _infer_preset_from_gguf_path(gguf: Path) -> LlamaCppModelPreset:
    name = gguf.name.lower()
    if "qwen2.5" in name or "qwen25" in name or "qwen-2.5" in name:
        return LLAMACPP_MODEL_PRESETS["qwen2.5-14b"]
    if "qwen3" in name or ("qwen" in name and "2.5" not in name and "25" not in name):
        return LLAMACPP_MODEL_PRESETS["qwen3-14b"]
    if "gemma" in name:
        return LLAMACPP_MODEL_PRESETS["gemma-4-e4b"]
    return LLAMACPP_MODEL_PRESETS["qwen2.5-14b"]


def _serve_alias_from_gguf(gguf: Path) -> str:
    alias = re.sub(r"[^\w\-.]", "_", gguf.stem, flags=re.ASCII)
    return alias[:64] or "gguf-model"


def resolve_preset_for_translation(model_id: str | None = None) -> LlamaCppModelPreset:
    mid = (model_id or resolve_translation_llamacpp_preset_id() or "").strip()
    if is_gguf_option_id(mid):
        gguf = parse_gguf_option_id(mid)
        if gguf:
            return _infer_preset_from_gguf_path(gguf)
    return resolve_llamacpp_preset(mid)


def resolve_translation_gguf_path(model_cfg: Dict[str, Any] | None = None) -> Path:
    direct = (os.environ.get(LLAMACPP_GGUF_PATH_ENV, "") or "").strip()
    if direct:
        p = Path(direct).expanduser()
        if p.is_file():
            return p.resolve()

    model_raw = ""
    if isinstance(model_cfg, dict):
        model_raw = str(
            model_cfg.get("llamacpp_preset") or model_cfg.get("model") or ""
        ).strip()
    if not model_raw:
        model_raw = (os.environ.get("JAVSTORY_LLAMACPP_MODEL", "") or "").strip()

    if is_gguf_option_id(model_raw):
        parsed = parse_gguf_option_id(model_raw)
        if parsed:
            return parsed

    preset_id = resolve_translation_llamacpp_preset_id()
    if is_gguf_option_id(preset_id):
        parsed = parse_gguf_option_id(preset_id)
        if parsed:
            return parsed

    preset = resolve_llamacpp_preset(preset_id)
    return resolve_gguf_path(preset)


@dataclass(frozen=True)
class TranslationLlamaCppRuntime:
    gguf: Path
    preset: LlamaCppModelPreset
    serve_alias: str
    runtime_id: str
    label: str


def resolve_translation_llamacpp_runtime(
    model_cfg: Dict[str, Any] | None = None,
) -> TranslationLlamaCppRuntime:
    mid = ""
    if isinstance(model_cfg, dict):
        mid = str(
            model_cfg.get("llamacpp_preset") or model_cfg.get("model") or ""
        ).strip()
    if not mid:
        mid = resolve_translation_llamacpp_preset_id()

    if not is_gguf_option_id(mid):
        preset = resolve_llamacpp_preset(mid)
        gguf = resolve_gguf_path(preset)
        return TranslationLlamaCppRuntime(
            gguf=gguf,
            preset=preset,
            serve_alias=preset.serve_alias or preset.id,
            runtime_id=preset.id,
            label=preset.label,
        )

    gguf = resolve_translation_gguf_path(model_cfg)
    base_preset = _infer_preset_from_gguf_path(gguf)
    alias = _serve_alias_from_gguf(gguf)
    preset = replace(base_preset, serve_alias=alias, label=gguf.name)
    return TranslationLlamaCppRuntime(
        gguf=gguf,
        preset=preset,
        serve_alias=alias,
        runtime_id=gguf_option_id(gguf),
        label=gguf.name,
    )


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
    multi_gpu: bool = False
    main_gpu: int = 0
    tensor_split: str | None = None
    split_mode: str = "layer"
    cuda_visible_devices: str = "0"
    reasoning_format: str = "deepseek"
    batch_size: int | None = None
    ubatch_size: int | None = None

    @classmethod
    def from_env(
        cls, preset: LlamaCppModelPreset, gguf: Path | None = None
    ) -> "LlamaCppServerConfig":
        base = urlparse(llamacpp_base_url())
        host = base.hostname or "127.0.0.1"
        port = base.port or _env_int("JAVSTORY_LLAMACPP_PORT", 8081)
        ctk = (os.environ.get("JAVSTORY_LLAMACPP_CACHE_TYPE_K", "turbo3") or "turbo3").strip()
        ctv = (os.environ.get("JAVSTORY_LLAMACPP_CACHE_TYPE_V", "q8_0") or "q8_0").strip()
        gpu_plan = resolve_llamacpp_gpu_plan(gguf)
        ngl_raw = (os.environ.get("JAVSTORY_LLAMACPP_N_GPU_LAYERS", "") or "").strip()
        if ngl_raw and gpu_plan["multi_gpu"]:
            # 듀얼 GPU 분할 로딩(대형 모델)에서는 -ngl 강제값을 무시하고 -fit에 맡긴다.
            # llama.cpp는 -ngl이 명시되면 "실제로 다 들어가는지" 자체 적합성 검사를
            # 건너뛰고 그대로 밀어붙이는데(로그: "failed to fit params to free device
            # memory: n_gpu_layers already set by user, abort"), 안 들어가면 Windows
            # 드라이버가 에러 없이 시스템 RAM으로 넘쳐서(spillover) 10~50배 느려진다.
            # 단일 GPU에 이미 다 들어가는 작은 모델에서는 강제값을 그대로 존중한다.
            ngl: int | None = None
        elif ngl_raw:
            ngl = max(0, int(ngl_raw))
        elif preset.default_ngl >= 0:
            ngl = preset.default_ngl
        else:
            ngl = None
        par_raw = (os.environ.get("JAVSTORY_LLAMACPP_PARALLEL", "") or "").strip()
        if par_raw:
            try:
                par = max(1, int(par_raw))
            except ValueError:
                par = 1
        else:
            # 명시적으로 지정하지 않았다면 harvest 동시 번역 개수만큼 슬롯을 확보해,
            # 워커마다 llama-server를 따로 띄우지 않고 서버 1개가 병렬 요청을 처리하게 한다.
            hc_raw = (os.environ.get("JAVSTORY_HARVEST_CONCURRENCY", "") or "").strip()
            try:
                hc = int(hc_raw) if hc_raw else 1
            except ValueError:
                hc = 1
            par = max(1, min(5, hc))
        ctx_raw = (os.environ.get("JAVSTORY_LLAMACPP_CTX", "") or "").strip()
        if ctx_raw:
            try:
                ctx = max(512, int(ctx_raw))
            except ValueError:
                ctx = preset.default_ctx
        else:
            slot_ctx = harvest_slot_ctx_from_env()
            if slot_ctx is not None:
                ctx = slot_ctx * par
            else:
                # 슬롯 수만큼 컨텍스트도 함께 늘려 슬롯당 컨텍스트가 preset 기본값 밑으로
                # 줄어들지 않게 한다(그렇지 않으면 --parallel만 올렸을 때 슬롯당 컨텍스트가
                # 부족해져 번역 응답이 잘릴 수 있음).
                ctx = preset.default_ctx * par
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
        reasoning_format = (
            os.environ.get("JAVSTORY_LLAMACPP_REASONING_FORMAT", "deepseek") or "deepseek"
        ).strip().lower()
        batch_raw = (os.environ.get("JAVSTORY_LLAMACPP_BATCH_SIZE", "") or "").strip()
        batch_size = None
        if batch_raw:
            try:
                batch_size = max(32, int(batch_raw))
            except ValueError:
                batch_size = None
        ubatch_raw = (os.environ.get("JAVSTORY_LLAMACPP_UBATCH_SIZE", "") or "").strip()
        ubatch_size = None
        if ubatch_raw:
            try:
                ubatch_size = max(32, int(ubatch_raw))
            except ValueError:
                ubatch_size = None
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
            multi_gpu=gpu_plan["multi_gpu"],
            main_gpu=gpu_plan["main_gpu"],
            tensor_split=gpu_plan["tensor_split"],
            split_mode=gpu_plan["split_mode"],
            cuda_visible_devices=gpu_plan["cuda_visible_devices"],
            reasoning_format=reasoning_format,
            batch_size=batch_size,
            ubatch_size=ubatch_size,
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
    if cfg.batch_size is not None:
        # -b: 프롬프트 처리(prefill) 배치 크기. 크게 잡을수록 GPU 연산 병렬성을 더
        # 활용해 prefill이 빨라지지만 VRAM을 더 씀 — 미지정 시 llama.cpp 기본값 사용.
        argv.extend(["-b", str(cfg.batch_size)])
    if cfg.ubatch_size is not None:
        argv.extend(["-ub", str(cfg.ubatch_size)])
    if cfg.n_gpu_layers is not None:
        argv.extend(["-ngl", str(cfg.n_gpu_layers)])
    elif cfg.fit_vram:
        argv.extend(["-fit", "on"])
    if cfg.multi_gpu:
        argv.extend(["--main-gpu", str(cfg.main_gpu)])
        if cfg.split_mode and cfg.split_mode != "none":
            argv.extend(["--split-mode", cfg.split_mode])
        if cfg.tensor_split:
            argv.extend(["--tensor-split", cfg.tensor_split])
    if preset.serve_alias:
        argv.extend(["--alias", preset.serve_alias])
    if cfg.reasoning_format and cfg.reasoning_format != "none":
        # <think>...</think> 등 모델의 reasoning 블록을 content가 아니라
        # delta.reasoning_content로 분리 — 안 하면 사고 과정이 그대로 content에
        # 섞여 나와 max_tokens를 갉아먹고(응답이 일찍 잘림) 답변에도 그대로 노출된다.
        argv.extend(["--reasoning-format", cfg.reasoning_format])
    threads_raw = (os.environ.get("JAVSTORY_LLAMACPP_THREADS", "") or "").strip()
    if threads_raw:
        try:
            argv.extend(["-t", str(max(1, int(threads_raw)))])
        except ValueError:
            pass
    tc_raw = (os.environ.get("JAVSTORY_LLAMACPP_TENSORCORES", "") or "").strip().lower()
    if tc_raw in ("1", "true", "yes", "on"):
        argv.extend(["--tensorcores", "on"])
    flash_on = _env_bool("JAVSTORY_LLAMACPP_FLASH_ATTN", True)
    extra = list(preset.extra_args)
    if not flash_on:
        filtered: List[str] = []
        skip_next = False
        for a in extra:
            if skip_next:
                skip_next = False
                continue
            if a in ("--flash-attn", "-fa"):
                skip_next = True
                continue
            filtered.append(a)
        extra = filtered
    elif not any("flash" in str(a).lower() or a in ("-fa",) for a in extra):
        extra.extend(["--flash-attn", "on"])
    argv.extend(extra)
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


def _port_has_listener(host: str, port: int, timeout: float = 1.0) -> bool:
    """Return True if any process is actively accepting connections on the port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except Exception:
            return False


def _port_is_listening_netstat(port: int) -> bool:
    """Windows-only: check via netstat if any process has port in LISTENING state.

    More reliable than socket.bind() on Windows where Hyper-V/Docker port exclusion
    ranges cause bind() to fail with WSAEACCES even when no server is listening.
    """
    if sys.platform != "win32":
        return False
    cflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, check=False,
            creationflags=cflags,
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0] == "TCP" and f":{port}" in parts[1] and "LISTEN" in parts[3]:
                return True
        return False
    except Exception:
        return False


def _wait_for_port_free(host: str, port: int, timeout: float = 15.0) -> bool:
    """Poll until the port is no longer in LISTENING state. Returns True if freed."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if sys.platform == "win32":
            if not _port_is_listening_netstat(port):
                return True
        else:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind((host, port))
                    return True
                except OSError:
                    pass
        time.sleep(1.0)
    return False


def _kill_port_owner_windows(
    port: int,
    *,
    logger_func: LoggerFunc | None = None,
) -> bool:
    """Windows-only: find and kill the llama-server process listening on port.

    Returns True if a process was found and killed. Silently skips if the owner
    is not llama-server (to avoid accidentally killing unrelated services).
    """
    if sys.platform != "win32":
        return False
    log = logger_func or print
    cflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    try:
        ns = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, check=False,
            creationflags=cflags,
        )
        pid_str = ""
        for line in ns.stdout.splitlines():
            parts = line.split()
            if len(parts) < 5 or parts[0] != "TCP":
                continue
            local_addr = parts[1]
            state = parts[3]
            pid_col = parts[4]
            if f":{port}" in local_addr and state == "LISTENING" and pid_col.isdigit():
                pid_str = pid_col
                break
        if not pid_str:
            return False
        tl = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid_str}", "/FO", "CSV"],
            capture_output=True, text=True, check=False,
            creationflags=cflags,
        )
        if "llama-server" not in tl.stdout.lower():
            log(f"[llama.cpp] 포트 {port} 점유 PID {pid_str}은 llama-server가 아님 — 강제 종료 건너뜀")
            return False
        subprocess.run(
            ["taskkill", "/PID", pid_str, "/T", "/F"],
            check=False, creationflags=cflags, capture_output=True,
        )
        log(f"[llama.cpp] 포트 {port} 점유 llama-server (PID {pid_str}) 강제 종료")
        time.sleep(1.0)
        return True
    except Exception as exc:
        log(f"[llama.cpp] 포트 {port} 점유 프로세스 종료 시도 실패: {exc}")
        return False


def _server_model_ids(base_url: str, timeout: float = 2.0) -> List[str]:
    try:
        r = httpx.get(f"{base_url.rstrip('/')}/v1/models", timeout=timeout)
        r.raise_for_status()
        payload = r.json()
    except Exception:
        return []
    data = payload.get("data") if isinstance(payload, dict) else []
    ids: List[str] = []
    for item in data or []:
        if isinstance(item, dict):
            value = str(item.get("id") or item.get("model") or "").strip()
            if value:
                ids.append(value)
    return ids


def _server_models_match_preset(
    model_ids: List[str],
    preset: LlamaCppModelPreset,
    *,
    serve_alias: str | None = None,
) -> bool:
    if not model_ids:
        return True
    joined = " ".join(model_ids).lower()
    alias = (serve_alias or preset.serve_alias or preset.id).lower()
    if alias in joined or preset.id.lower() in joined:
        return True
    if preset.id.startswith("qwen") and "qwen" in joined:
        return True
    if preset.id.startswith("gemma") and "gemma" in joined:
        return True
    return False


def _maybe_idle_shutdown(*, logger_func: LoggerFunc | None = None) -> bool:
    """유휴 시간 초과 시 llama-server 종료. 종료했으면 True."""
    global _idle_shutdown_logged
    if not llamacpp_idle_shutdown_enabled():
        return False
    timeout = llamacpp_idle_timeout_sec_from_env()
    with _lock:
        proc = _server_proc
        active = int(_active_requests or 0)
        idle_for = time.time() - float(_last_activity_at or 0.0)
        port = _idle_managed_port
        tracked = _active_preset_id is not None
    if active > 0 or idle_for < timeout:
        return False
    proc_alive = proc is not None and proc.poll() is None
    port_listening = bool(
        port and (sys.platform == "win32" and _port_is_listening_netstat(port))
    )
    if not proc_alive and not (tracked and port_listening):
        return False
    log = logger_func or print
    if not _idle_shutdown_logged:
        log(f"[llama.cpp] {timeout}초 이상 미사용 — llama-server 자동 종료")
        _idle_shutdown_logged = True
    stop_llamacpp_server(logger_func=log)
    return True


def _ensure_idle_monitor_started(*, logger_func: LoggerFunc | None = None) -> None:
    global _idle_thread, _idle_shutdown_logged
    if not llamacpp_idle_shutdown_enabled():
        return
    with _lock:
        if (
            _idle_thread is not None
            and _idle_thread.is_alive()
            and not _idle_stop_event.is_set()
        ):
            return
        _idle_stop_event.clear()
        _idle_shutdown_logged = False

    log = logger_func or print

    def _monitor() -> None:
        while not _idle_stop_event.wait(5.0):
            _maybe_idle_shutdown(logger_func=log)

    _idle_thread = threading.Thread(target=_monitor, daemon=True, name="llamacpp-idle-monitor")
    _idle_thread.start()


def _terminate_llamacpp_proc(
    proc: subprocess.Popen,
    *,
    logger_func: LoggerFunc | None = None,
    label: str = "llama-server",
) -> None:
    """Terminate the managed llama-server process, including its tree on Windows."""
    log = logger_func or print
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=15)
        log(f"[llama.cpp] {label} 종료")
        return
    except subprocess.TimeoutExpired:
        pass
    except Exception as e:
        log(f"[llama.cpp] {label} 종료 요청 오류(강제 종료 시도): {e}")

    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,  # type: ignore[attr-defined]
            )
        except Exception as e:
            log(f"[llama.cpp] taskkill 오류(무시): {e}")

    try:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
        log(f"[llama.cpp] {label} 강제 종료")
    except Exception as e:
        log(f"[llama.cpp] {label} 강제 종료 오류(무시): {e}")


def stop_llamacpp_server(*, logger_func: LoggerFunc | None = None) -> None:
    global _server_proc, _active_preset_id, _active_base_url, _active_requests, _idle_managed_port
    global _active_server_config_key, _spawning
    _wait_for_llamacpp_idle(logger_func=logger_func)
    _idle_stop_event.set()
    with _lock:
        proc = _server_proc
        port = _idle_managed_port
        _server_proc = None
        _active_preset_id = None
        _active_base_url = None
        _active_server_config_key = None
        _active_requests = 0
        _idle_managed_port = None
        _spawning = False
    if proc is not None:
        _terminate_llamacpp_proc(proc, logger_func=logger_func)
        return
    if port:
        _kill_port_owner_windows(port, logger_func=logger_func)


def register_llamacpp_app_shutdown(app: Any, *, logger_func: LoggerFunc | None = None) -> None:
    """Qt 앱 종료 시 llama-server를 명시적으로 정리한다."""
    try:
        app.aboutToQuit.connect(
            lambda: stop_llamacpp_server(logger_func=logger_func or print)
        )
    except Exception:
        pass


def _tail_server_log(max_lines: int = 24) -> str:
    if not _log_path or not _log_path.is_file():
        return ""
    try:
        lines = _log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception:
        return ""


def _port_conflict_in_tail(tail: str) -> bool:
    t = (tail or "").lower()
    return "couldn't bind" in t or "address already in use" in t or "bind: only one usage" in t


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
    if _port_conflict_in_tail(tail):
        return (
            "포트 8081이 이미 사용 중입니다. 이전 llama-server 인스턴스가 완전히 종료되지 않은 경우입니다. "
            "잠시 후 다시 시도하거나 작업 관리자에서 llama-server.exe를 종료한 뒤 재시작하세요."
        )
    return ""


def _llamacpp_child_env(cfg: "LlamaCppServerConfig") -> Dict[str, str]:
    """자식 프로세스 전용 env — 부모 프로세스(임베딩 등 in-process GPU 사용)에는 영향 없음.

    ``CUDA_DEVICE_ORDER=PCI_BUS_ID`` 를 강제해, 신형 GPU가 더 빠르다고 드라이버가
    임의로 앞 인덱스에 배치하는 것을 막고 ``JAVSTORY_LLAMACPP_GPU0/1_INDEX`` 가
    항상 물리 슬롯 순서(nvidia-smi 순서)와 일치하게 한다.
    """
    env = dict(os.environ)
    env["CUDA_VISIBLE_DEVICES"] = cfg.cuda_visible_devices
    env["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
    return env


def _spawn_server(
    argv: List[str],
    *,
    env: Dict[str, str] | None = None,
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
    if env is not None:
        log_f.write(f"CUDA_VISIBLE_DEVICES={env.get('CUDA_VISIBLE_DEVICES')}\n")
    log_f.flush()
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    proc = subprocess.Popen(
        argv,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
        env=env,
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

    ``_ensure_lock`` 으로 전체 호출을 직렬화해, 동시 호출자가 여러 llama-server를
    중복 기동하지 못하게 한다. 서버가 이미 떠 있으면 뒤따르는 호출은 헬스체크만
    하고 곧바로 반환하므로 정상 상황에서는 대기 비용이 거의 없다.
    """
    with _ensure_lock:
        return _ensure_llamacpp_server_ready_locked(
            model_cfg, logger_func=logger_func, wait_sec=wait_sec
        )


def _ensure_llamacpp_server_ready_locked(
    model_cfg: Dict[str, Any] | None = None,
    *,
    logger_func: LoggerFunc | None = None,
    wait_sec: float = 120.0,
) -> str:
    global _server_proc, _active_preset_id, _active_base_url, _last_activity_at, _active_server_config_key, _spawning
    if not _env_bool("JAVSTORY_LLAMACPP_AUTO_START", True):
        base = llamacpp_base_url()
        if not _server_health_ok(base):
            raise RuntimeError(
                f"llama-server가 응답하지 않습니다 ({base}). "
                "JAVSTORY_LLAMACPP_AUTO_START=1 이거나 수동으로 서버를 띄우세요."
            )
        runtime = resolve_translation_llamacpp_runtime(model_cfg)
        preset = runtime.preset
        model_ids = _server_model_ids(base)
        if not _server_models_match_preset(
            model_ids, preset, serve_alias=runtime.serve_alias
        ):
            raise RuntimeError(
                f"실행 중인 llama-server 모델({', '.join(model_ids)})이 선택한 모델({runtime.label})과 다릅니다. "
                "기존 llama-server를 종료하거나 활성 모델을 맞춘 뒤 다시 시도하세요."
            )
        return runtime.serve_alias

    runtime = resolve_translation_llamacpp_runtime(model_cfg)
    preset = runtime.preset
    gguf = runtime.gguf
    cfg = LlamaCppServerConfig.from_env(preset, gguf)
    base = llamacpp_base_url()
    expected_config_key = server_config_fingerprint(cfg, gguf)

    log = logger_func or print
    if cfg.multi_gpu:
        log(
            f"[llama.cpp] GGUF {gguf.name} ({_gguf_size_gb(gguf):.1f}GB > "
            f"{llamacpp_gpu_split_threshold_gb():.1f}GB) — 듀얼 GPU 분할 로딩 "
            f"(CUDA_VISIBLE_DEVICES={cfg.cuda_visible_devices}, main-gpu={cfg.main_gpu})"
        )

    proc_to_stop: subprocess.Popen | None = None
    check_proc: subprocess.Popen | None = None

    def _config_stale() -> bool:
        with _lock:
            active_key = _active_server_config_key
        if active_key is None:
            return False
        return active_key != expected_config_key

    with _lock:
        if _server_proc is not None and _server_proc.poll() is not None:
            _server_proc = None
            _active_preset_id = None

        # Only check process state inside the lock — health check (HTTP) must be outside.
        if _server_proc is not None and _active_preset_id == runtime.runtime_id:
            check_proc = _server_proc
        elif _server_proc is not None:
            proc_to_stop = _server_proc
            _server_proc = None
            _active_preset_id = None

    # Health check runs outside the lock so a slow /health response never
    # misidentifies a running server as crashed and triggers a spurious respawn.
    if check_proc is not None:
        check_proc_health_ok = _server_health_ok(base)
        if check_proc_health_ok and not _config_stale():
            _finalize_server_ready(
                preset,
                base,
                runtime_id=runtime.runtime_id,
                config_key=expected_config_key,
                logger_func=log,
            )
            return runtime.serve_alias
        if check_proc_health_ok and _config_stale():
            log(
                "[llama.cpp] parallel/ctx/ngl 변경 감지 — llama-server 재기동 "
                f"({expected_config_key})"
            )
        # Process alive but health check failed — treat as crashed and respawn.
        with _lock:
            if _server_proc is check_proc:
                _server_proc = None
                _active_preset_id = None
                _active_server_config_key = None
        proc_to_stop = check_proc

    if proc_to_stop is not None:
        _wait_for_llamacpp_idle(logger_func=log)
        _terminate_llamacpp_proc(proc_to_stop, logger_func=log)

    initial_health_ok = _server_health_ok(base)
    if initial_health_ok:
        model_ids = _server_model_ids(base)
        if not _server_models_match_preset(
            model_ids, preset, serve_alias=runtime.serve_alias
        ):
            running = ", ".join(model_ids) if model_ids else "unknown"
            raise RuntimeError(
                f"{base}에 이미 다른 llama-server 모델이 실행 중입니다: {running}. "
                f"선택한 모델은 {runtime.label}입니다. 기존 llama-server를 종료한 뒤 다시 시작하세요."
            )
        if _config_stale():
            log(
                "[llama.cpp] 실행 중 llama-server 설정 불일치 — 재기동 "
                f"({expected_config_key})"
            )
            _wait_for_llamacpp_idle(logger_func=log)
            if sys.platform == "win32":
                _kill_port_owner_windows(cfg.port, logger_func=log)
            if not _wait_for_port_free(cfg.host, cfg.port, timeout=15.0):
                raise RuntimeError(
                    f"포트 {cfg.port}의 기존 llama-server를 종료하지 못했습니다. "
                    "작업 관리자에서 llama-server.exe를 종료한 뒤 다시 시도하세요."
                )
            initial_health_ok = False
        else:
            touch_llamacpp_activity()
            # 청크마다 재사용 로그가 수백 줄 쌓이지 않도록 동일 base는 1회만 알림
            global _reuse_log_base
            if _reuse_log_base != base:
                log(f"[llama.cpp] 기존 llama-server 재사용 — {base}/v1")
                _reuse_log_base = base
            _finalize_server_ready(
                preset,
                base,
                runtime_id=runtime.runtime_id,
                config_key=expected_config_key,
                logger_func=log,
            )
            return runtime.serve_alias

    if sys.platform == "win32":
        bind_probe = _port_bind_probe(cfg.host, cfg.port)
        port_user_pinned = _llamacpp_port_is_user_pinned(cfg.host, cfg.port)
        bind_denied_without_listener = (
            not bind_probe.get("bind_ok")
            and bind_probe.get("winerror") == 10013
            and not _port_is_listening_netstat(cfg.port)
        )
        if bind_denied_without_listener and not port_user_pinned:
            old_port = cfg.port
            replacement = _find_bindable_llamacpp_port(cfg.host, old_port + 1)
            if replacement is None:
                raise RuntimeError(
                    f"포트 {old_port} 바인딩이 Windows에서 거부되었고 자동 대체 포트를 찾지 못했습니다. "
                    "JAVSTORY_LLAMACPP_PORT를 사용 가능한 포트로 지정하세요."
                )
            new_port, _ = replacement
            cfg.port = new_port
            base = f"http://{cfg.host}:{cfg.port}"
            with _lock:
                _active_base_url = base
        elif bind_denied_without_listener:
            raise RuntimeError(
                f"설정된 llama.cpp 포트 {cfg.port} 바인딩이 Windows에서 거부되었습니다(WinError 10013). "
                "해당 포트가 Windows 제외/예약 범위일 수 있으니 JAVSTORY_LLAMACPP_PORT를 다른 포트로 지정하세요."
            )

    # Pre-spawn: if port is in LISTENING state (netstat), a hung llama-server from a
    # previous session is blocking the port.  Kill it (Windows: llama-server only)
    # and wait for the port to free before attempting to bind.
    # Note: socket.bind() is NOT used here — on Windows, Hyper-V/Docker port exclusion
    # ranges cause bind() to raise WSAEACCES even when no server is listening.
    pre_spawn_port_listening = sys.platform == "win32" and _port_is_listening_netstat(cfg.port)
    if pre_spawn_port_listening:
        log(f"[llama.cpp] 포트 {cfg.port} LISTENING 감지 — 정리 시도")
        _kill_port_owner_windows(cfg.port, logger_func=log)
        if not _wait_for_port_free(cfg.host, cfg.port, timeout=15.0):
            raise RuntimeError(
                f"포트 {cfg.port}가 15초 이상 점유 중입니다. "
                "작업 관리자에서 llama-server.exe를 종료한 뒤 다시 시도하세요."
            )
        log(f"[llama.cpp] 포트 {cfg.port} 해제 확인 — 서버 시작")

    argv = build_server_argv(gguf, cfg, preset)
    child_env = _llamacpp_child_env(cfg)
    _spawning = True
    proc = _spawn_server(argv, env=child_env, logger_func=log)
    with _lock:
        # Register immediately so app shutdown can stop the server even while it is still loading.
        _server_proc = proc
        _active_preset_id = runtime.runtime_id
        _last_activity_at = time.time()
    deadline = time.time() + max(5.0, wait_sec)
    while time.time() < deadline:
        if proc.poll() is not None:
            with _lock:
                if _server_proc is proc:
                    _server_proc = None
                    _active_preset_id = None
            tail = _tail_server_log()
            # Port conflict: the spawned server couldn't bind because the previous
            # instance is still holding the port.  If that server is healthy and
            # matches our preset, reuse it rather than surfacing an error.
            if _port_conflict_in_tail(tail):
                # 1) Try to reuse a healthy existing server
                post_conflict_health_ok = _server_health_ok(base, timeout=5.0)
                if post_conflict_health_ok:
                    model_ids = _server_model_ids(base)
                    if _server_models_match_preset(
                        model_ids, preset, serve_alias=runtime.serve_alias
                    ):
                        _finalize_server_ready(
                            preset,
                            base,
                            runtime_id=runtime.runtime_id,
                            config_key=expected_config_key,
                            logger_func=log,
                        )
                        log(f"[llama.cpp] 포트 충돌 감지 → 기존 서버 재사용 — {base}/v1")
                        return runtime.serve_alias
                # 2) Not healthy: kill port owner (Windows: llama-server only) then retry
                if sys.platform == "win32":
                    _kill_port_owner_windows(cfg.port, logger_func=log)
                if _wait_for_port_free(cfg.host, cfg.port, timeout=15.0):
                    log(f"[llama.cpp] 포트 {cfg.port} 해제 — spawn 재시도")
                    proc2 = _spawn_server(argv, env=child_env, logger_func=log)
                    with _lock:
                        _server_proc = proc2
                        _active_preset_id = runtime.runtime_id
                        _last_activity_at = time.time()
                    retry_dl = time.time() + max(5.0, wait_sec)
                    while time.time() < retry_dl:
                        if proc2.poll() is not None:
                            break
                        if _server_health_ok(base, timeout=2.0):
                            _finalize_server_ready(
                            preset,
                            base,
                            runtime_id=runtime.runtime_id,
                            config_key=expected_config_key,
                            logger_func=log,
                        )
                            log(f"[llama.cpp] 재시작 성공 — {runtime.label} @ {base}/v1")
                            return runtime.serve_alias
                        time.sleep(0.5)
            hint = _server_exit_hint(tail)
            msg = f"llama-server가 조기 종료되었습니다 (code={proc.returncode}). 로그: {_log_path}"
            if hint:
                msg += f"\n{hint}"
            if tail:
                msg += f"\n--- log tail ---\n{tail}"
            _spawning = False
            raise RuntimeError(msg)
        if _server_health_ok(base, timeout=2.0):
            with _lock:
                _server_proc = proc
            _finalize_server_ready(
                preset,
                base,
                runtime_id=runtime.runtime_id,
                config_key=expected_config_key,
                logger_func=log,
            )
            log(f"[llama.cpp] 준비 완료 — {runtime.label} @ {base}/v1")
            return runtime.serve_alias
        time.sleep(0.5)

    _spawning = False
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
    mid = resolve_translation_llamacpp_preset_id()
    preset = resolve_preset_for_translation(mid)
    max_tokens = llamacpp_max_tokens_from_env(correction=False)
    model = preset.serve_alias or preset.id
    try:
        runtime = resolve_translation_llamacpp_runtime()
        model = runtime.serve_alias
    except FileNotFoundError:
        pass
    return {
        "rank": 99,
        "name": "translation_llamacpp_local",
        "model": model,
        "llamacpp_preset": mid,
        "provider": "llamacpp",
        "cost_tier": "free",
        "uncensored": True,
        "timeout": 600,
        "max_ctx": preset.default_ctx,
        "max_tokens": max_tokens,
    }


atexit.register(lambda: stop_llamacpp_server())
