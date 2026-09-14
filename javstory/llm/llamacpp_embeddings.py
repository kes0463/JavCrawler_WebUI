"""
llama-server 임베딩 백엔드.

채팅용 llama-server와 **별도 프로세스/포트**로 임베딩 전용 서버를 띄운다.
  POST {base}/v1/embeddings  (OpenAI 호환)

환경 변수:
  JAVSTORY_EMBEDDINGS_LLAMACPP_URL     기본 http://127.0.0.1:8082
  JAVSTORY_EMBEDDINGS_LLAMACPP_HOST / PORT
  JAVSTORY_EMBEDDINGS_LLAMACPP_GGUF    임베딩 GGUF 경로 (필수에 가깝음)
  JAVSTORY_EMBEDDINGS_MODEL            API model/alias (기본 nomic-embed-text)
  JAVSTORY_EMBEDDINGS_LLAMACPP_N_GPU_LAYERS  (-ngl, 미설정 시 -fit on)
  JAVSTORY_EMBEDDINGS_LLAMACPP_CTX     (-c, 기본 2048)
  JAVSTORY_EMBEDDINGS_LLAMACPP_MAX_CONCURRENT  동시 /v1/embeddings 요청 (기본 1)
  JAVSTORY_EMBEDDINGS_LLAMACPP_BATCH_SIZE  텍스트 여러 개를 한 요청에 묶어 보내는 배치 크기
                                           (기본 10) — 캐시 안 된 텍스트만 대상, 실패 시
                                           해당 배치만 1개씩 폴백
  JAVSTORY_EMBEDDINGS_LLAMACPP_AUTO_START  1|0 (기본 1)
  JAVSTORY_EMBEDDINGS_LLAMACPP_POOLING     mean|last|cls|… (미설정 시 모델별 자동)
                                           e5-mistral → last, nomic/e5/bge → mean
                                           (/v1/embeddings 는 pooling=none 불가)
  JAVSTORY_EMBEDDINGS_LLAMACPP_IDLE_SHUTDOWN      1|0 (미사용 시 자동 종료, 기본 1)
  JAVSTORY_EMBEDDINGS_LLAMACPP_IDLE_TIMEOUT_SEC   유휴 종료 대기(초, 기본 300=5분)

임베딩 llama-server는 앱 시작 시 선기동하지 않는다. 백필 큐 처리 등 실제 임베딩
작업이 시작될 때 ensure_embeddings_llamacpp_ready() 가 온디맨드로 기동하고,
JAVSTORY_EMBEDDINGS_LLAMACPP_IDLE_TIMEOUT_SEC 이상 미사용 시 자동 종료된다.
"""

from __future__ import annotations

import asyncio
import atexit
import hashlib
import os
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from javstory.llm.llamacpp_backend import (
    DEFAULT_GGUF_SCAN_DIR,
    GGUF_SCAN_DIR_ENV,
    gguf_option_id,
    llamacpp_bin_path,
    _find_bindable_llamacpp_port,
    _port_bind_probe,
    _port_is_listening_netstat,
)
from javstory.utils.cache_manager import cache_manager

LoggerFunc = Callable[[str], Any]

_lock = threading.Lock()
_ensure_lock = threading.Lock()
_embed_http_sem: threading.Semaphore | None = None
_server_proc: subprocess.Popen | None = None
_active_gguf: Optional[str] = None
_active_base_url: Optional[str] = None
_active_pooling: Optional[str] = None
_log_path: Optional[Path] = None
_last_activity_at: float = time.time()
_active_requests: int = 0
# 검색·백필 등 임베딩 요청마다 ensure_embeddings_llamacpp_ready()가 호출되는데, 이미
# 우리가 관리 중인 서버가 살아있는 게 최근에 확인됐다면 매번 HTTP 헬스체크를 왕복하지
# 않는다(로컬호스트라도 요청당 고정 오버헤드가 붙는다). (base, 확인 시각) 쌍으로 저장해
# 포트/URL이 바뀌면 자동으로 무효화되게 한다.
_last_health_ok: tuple[str, float] | None = None
_HEALTH_RECHECK_SEC = 5.0


def _recent_health_ok(base: str) -> bool:
    entry = _last_health_ok
    if entry is None:
        return False
    checked_base, checked_at = entry
    return checked_base == base and (time.time() - checked_at) < _HEALTH_RECHECK_SEC


def _mark_health_ok(base: str) -> None:
    global _last_health_ok
    _last_health_ok = (base, time.time())
_idle_thread: threading.Thread | None = None
_idle_stop_event = threading.Event()
_idle_shutdown_logged = False

DEFAULT_EMBED_PORT = 8082
DEFAULT_EMBED_MODEL = "nomic-embed-text"
EMBEDDINGS_GGUF_SCAN_DIR_ENV = "JAVSTORY_EMBEDDINGS_LLAMACPP_GGUF_SCAN_DIR"
_EMBED_GGUF_NAME_HINTS = ("embed", "nomic", "e5", "bge", "gte")
_GGUF_DISCOVERY_CACHE: dict[str, Any] = {"at": 0.0, "key": "", "options": []}
_GGUF_DISCOVERY_TTL_SEC = 60.0


def _gguf_scan_cache_key(dirs: List[Path]) -> str:
    parts: list[str] = []
    for root in dirs:
        try:
            st = root.stat()
            parts.append(f"{root.resolve()}|{int(st.st_mtime)}")
        except OSError:
            parts.append(str(root))
    return "|".join(parts)


def _iter_gguf_files(root: Path):
    """D:\\Models 등 — 1단계 하위만 스캔(rglob 전체 트리 방지)."""
    try:
        yield from root.glob("*.gguf")
        for sub in root.iterdir():
            if sub.is_dir():
                yield from sub.glob("*.gguf")
    except OSError:
        return


def invalidate_embeddings_gguf_cache() -> None:
    _GGUF_DISCOVERY_CACHE["at"] = 0.0


def _looks_like_embedding_gguf(name: str) -> bool:
    n = (name or "").lower()
    if "mmproj" in n:
        return False
    return any(h in n for h in _EMBED_GGUF_NAME_HINTS)


def embeddings_gguf_scan_dirs() -> List[Path]:
    """임베딩 GGUF 검색 후보 디렉터리(중복 제거)."""
    dirs: List[Path] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        raw = (raw or "").strip()
        if not raw:
            return
        p = Path(raw).expanduser()
        candidate = p.parent if p.is_file() else p
        try:
            key = str(candidate.resolve()).lower()
        except OSError:
            key = str(candidate).lower()
        if key in seen or not candidate.is_dir():
            return
        seen.add(key)
        dirs.append(candidate)

    for env_key in (EMBEDDINGS_GGUF_SCAN_DIR_ENV, GGUF_SCAN_DIR_ENV):
        _add(os.environ.get(env_key, ""))

    for env_key in (
        "JAVSTORY_EMBEDDINGS_LLAMACPP_GGUF",
        "JAVSTORY_LLAMACPP_GGUF_PATH",
    ):
        _add(os.environ.get(env_key, ""))

    _add(str(DEFAULT_GGUF_SCAN_DIR))
    return dirs


def discover_embeddings_gguf_models(*, use_cache: bool = True) -> List[Dict[str, str]]:
    """임베딩용 GGUF 후보 — embed/e5/bge 계열 우선, 없으면 전체 .gguf."""
    dirs = embeddings_gguf_scan_dirs()
    cache_key = _gguf_scan_cache_key(dirs)
    now = time.time()
    if use_cache:
        cached = _GGUF_DISCOVERY_CACHE
        if (
            cached.get("key") == cache_key
            and (now - float(cached.get("at") or 0.0)) < _GGUF_DISCOVERY_TTL_SEC
            and isinstance(cached.get("options"), list)
        ):
            return list(cached["options"])

    out: List[Dict[str, str]] = []
    seen_ids: set[str] = set()
    for root in dirs:
        try:
            paths = sorted(_iter_gguf_files(root), key=lambda x: x.name.lower())
        except OSError:
            continue
        for p in paths:
            if not p.is_file():
                continue
            try:
                resolved = p.resolve()
            except OSError:
                continue
            oid = gguf_option_id(resolved)
            if oid in seen_ids:
                continue
            seen_ids.add(oid)
            out.append(
                {
                    "id": oid,
                    "label": p.name,
                    "gguf_path": str(resolved),
                    "gguf_env": "",
                }
            )
    embed = [o for o in out if _looks_like_embedding_gguf(o["label"])]
    result = embed if embed else out
    _GGUF_DISCOVERY_CACHE.update({"at": now, "key": cache_key, "options": result})
    return result


def list_embeddings_gguf_options() -> List[Dict[str, str]]:
    """스캔 디렉터리의 임베딩 GGUF 목록 (+ 현재 설정된 경로)."""
    options = discover_embeddings_gguf_models()
    current = (os.environ.get("JAVSTORY_EMBEDDINGS_LLAMACPP_GGUF", "") or "").strip()
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
    model_hint = embeddings_model_from_env().strip().lower()
    if model_hint:
        for i, opt in enumerate(options):
            stem = Path(opt["label"]).stem.lower()
            if stem == model_hint or model_hint in stem:
                if i > 0:
                    options.insert(0, options.pop(i))
                break
    return [
        {
            "id": "",
            "label": "(자동 탐색 — e5 / nomic / bge 등)",
            "gguf_path": "",
            "gguf_env": "",
        },
        *options,
    ]


def embeddings_gguf_scan_dir() -> str:
    dirs = embeddings_gguf_scan_dirs()
    if not dirs:
        return str(DEFAULT_GGUF_SCAN_DIR)
    if len(dirs) == 1:
        return str(dirs[0])
    return "; ".join(str(d) for d in dirs)


def _env_bool(key: str, default: bool = False) -> bool:
    raw = (os.environ.get(key, "") or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def embeddings_idle_shutdown_enabled() -> bool:
    return _env_bool("JAVSTORY_EMBEDDINGS_LLAMACPP_IDLE_SHUTDOWN", True)


def embeddings_idle_timeout_sec_from_env() -> int:
    raw = (os.environ.get("JAVSTORY_EMBEDDINGS_LLAMACPP_IDLE_TIMEOUT_SEC", "") or "").strip()
    try:
        return max(30, int(raw)) if raw else 300
    except ValueError:
        return 300


def touch_embeddings_activity() -> None:
    global _last_activity_at
    with _lock:
        _last_activity_at = time.time()


def _begin_embeddings_request() -> None:
    global _active_requests, _last_activity_at
    with _lock:
        _active_requests += 1
        _last_activity_at = time.time()


def _end_embeddings_request() -> None:
    global _active_requests, _last_activity_at
    with _lock:
        _active_requests = max(0, _active_requests - 1)
        _last_activity_at = time.time()


@contextmanager
def embeddings_request_scope():
    _begin_embeddings_request()
    try:
        yield
    finally:
        _end_embeddings_request()


def _maybe_idle_shutdown(*, logger_func: LoggerFunc | None = None) -> bool:
    """유휴 시간 초과 시 임베딩 llama-server 종료. 종료했으면 True."""
    global _idle_shutdown_logged
    if not embeddings_idle_shutdown_enabled():
        return False
    timeout = embeddings_idle_timeout_sec_from_env()
    with _lock:
        proc = _server_proc
        active = int(_active_requests or 0)
        idle_for = time.time() - float(_last_activity_at or 0.0)
    if active > 0 or idle_for < timeout:
        return False
    if proc is None or proc.poll() is not None:
        return False
    log = logger_func or print
    if not _idle_shutdown_logged:
        log(f"[llama.cpp:embed] {timeout}초 이상 미사용 — llama-server 자동 종료")
        _idle_shutdown_logged = True
    stop_embeddings_llamacpp_server(logger_func=log)
    return True


def _ensure_idle_monitor_started(*, logger_func: LoggerFunc | None = None) -> None:
    global _idle_thread, _idle_shutdown_logged
    if not embeddings_idle_shutdown_enabled():
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

    _idle_thread = threading.Thread(
        target=_monitor, daemon=True, name="llamacpp-embed-idle-monitor"
    )
    _idle_thread.start()


def embeddings_model_from_env() -> str:
    for key in (
        "JAVSTORY_EMBEDDINGS_MODEL",
        "JAVSTORY_EMBEDDINGS_OLLAMA_MODEL",  # 하위 호환
    ):
        v = (os.environ.get(key, "") or "").strip()
        if v:
            return v
    return DEFAULT_EMBED_MODEL


def _embed_port_is_user_pinned() -> bool:
    """URL 또는 기본값이 아닌 PORT를 명시했으면 자동 대체 포트 탐색을 건너뛴다."""
    if (os.environ.get("JAVSTORY_EMBEDDINGS_LLAMACPP_URL", "") or "").strip():
        return True
    raw_port = (os.environ.get("JAVSTORY_EMBEDDINGS_LLAMACPP_PORT", "") or "").strip()
    if raw_port:
        try:
            return int(raw_port) != DEFAULT_EMBED_PORT
        except ValueError:
            return True
    return False


def embeddings_llamacpp_base_url() -> str:
    raw = (os.environ.get("JAVSTORY_EMBEDDINGS_LLAMACPP_URL", "") or "").strip()
    if raw:
        return raw.rstrip("/")
    host = (os.environ.get("JAVSTORY_EMBEDDINGS_LLAMACPP_HOST", "") or "").strip() or "127.0.0.1"
    port_raw = (os.environ.get("JAVSTORY_EMBEDDINGS_LLAMACPP_PORT", "") or "").strip()
    try:
        port = int(port_raw) if port_raw else DEFAULT_EMBED_PORT
    except ValueError:
        port = DEFAULT_EMBED_PORT
    return f"http://{host}:{port}"


def _resolve_embed_gguf() -> Path:
    raw = (os.environ.get("JAVSTORY_EMBEDDINGS_LLAMACPP_GGUF", "") or "").strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"임베딩 GGUF 없음: {p}")
        return p.resolve()

    # 스캔 디렉터리에서 embed / e5 / nomic 계열 자동 탐색
    candidates: List[Path] = []
    for root in embeddings_gguf_scan_dirs():
        try:
            for p in _iter_gguf_files(root):
                if not p.is_file():
                    continue
                if _looks_like_embedding_gguf(p.name):
                    candidates.append(p)
        except OSError:
            continue
    if candidates:
        model_hint = embeddings_model_from_env().strip().lower()

        def _rank(path: Path) -> tuple:
            name = path.name.lower()
            stem = path.stem.lower()
            if model_hint and (stem == model_hint or model_hint in stem):
                return (0, name)
            if "nomic" in name and "embed" in name:
                return (1, name)
            if "e5" in name and "mistral" in name:
                return (2, name)
            if "e5" in name:
                return (3, name)
            if "bge" in name:
                return (4, name)
            if "embed" in name:
                return (5, name)
            return (6, name)

        candidates.sort(key=_rank)
        return candidates[0].resolve()

    scan_hint = embeddings_gguf_scan_dir()
    raise FileNotFoundError(
        "임베딩 GGUF 경로가 없습니다. "
        "JAVSTORY_EMBEDDINGS_LLAMACPP_GGUF 에 nomic-embed 등 GGUF를 지정하거나 "
        f"{scan_hint} 아래에 *nomic*embed*.gguf 를 두세요."
    )


def _ctx_size() -> int:
    raw = (os.environ.get("JAVSTORY_EMBEDDINGS_LLAMACPP_CTX", "") or "").strip()
    try:
        return max(512, int(raw)) if raw else 2048
    except ValueError:
        return 2048


def embedding_max_input_chars(*, ctx: int | None = None) -> int:
    """
    llama-server /v1/embeddings 입력 글자 상한.
    CJK는 대략 1자≈1토큰이므로 ctx에서 여유 토큰을 뺀 값을 쓴다.
    JAVSTORY_EMBEDDINGS_MAX_INPUT_CHARS 로 덮어쓸 수 있다.
    """
    raw = (os.environ.get("JAVSTORY_EMBEDDINGS_MAX_INPUT_CHARS", "") or "").strip()
    if raw:
        try:
            return max(256, int(raw))
        except ValueError:
            pass
    c = ctx if ctx is not None else _ctx_size()
    # llama-server는 n_prompt_tokens < n_ctx 만 허용(경계값 2048/2048도 400).
    # CJK ≈ 1자/토큰 + BOS 등 소량 오버헤드 → 여유 128 토큰.
    return max(256, c - 128)


def truncate_embedding_input(text: str, *, ctx: int | None = None, max_chars: int | None = None) -> str:
    """컨텍스트 초과 400 방지 — 앞부분만 유지."""
    t = (text or "").strip()
    if not t:
        return t
    limit = max_chars if max_chars is not None else embedding_max_input_chars(ctx=ctx)
    if len(t) <= limit:
        return t
    return t[:limit]


def _embed_http_semaphore() -> threading.Semaphore:
    """llama-server embedding 슬롯(기본 parallel=1) 보호 — 동시 요청 500 방지."""
    global _embed_http_sem
    if _embed_http_sem is None:
        raw = (os.environ.get("JAVSTORY_EMBEDDINGS_LLAMACPP_MAX_CONCURRENT", "") or "").strip()
        try:
            n = int(raw) if raw else 1
        except ValueError:
            n = 1
        n = max(1, min(4, n))
        _embed_http_sem = threading.Semaphore(n)
    return _embed_http_sem


def _n_gpu_layers() -> int | None:
    raw = (os.environ.get("JAVSTORY_EMBEDDINGS_LLAMACPP_N_GPU_LAYERS", "") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _resolve_pooling(gguf: Path) -> str:
    """
    /v1/embeddings 는 pooling=none 을 거부한다.
    모델 계열에 맞는 기본값을 고른다 (JAVSTORY_EMBEDDINGS_LLAMACPP_POOLING 로 덮어쓰기).
    """
    explicit = (os.environ.get("JAVSTORY_EMBEDDINGS_LLAMACPP_POOLING", "") or "").strip()
    if explicit:
        return explicit
    name = gguf.name.lower()
    # e5-mistral / causal LM 계열 임베딩은 last-token pooling
    if "mistral" in name and ("e5" in name or "embed" in name or "instruct" in name):
        return "last"
    if any(k in name for k in ("nomic", "e5", "bge", "gte", "embed")):
        return "mean"
    # OAI 호환을 위해 none 금지 — 안전한 기본값
    return "mean"


def _build_embed_argv(gguf: Path, host: str, port: int, alias: str) -> List[str]:
    bin_p = llamacpp_bin_path()
    argv: List[str] = [
        str(bin_p),
        "-m",
        str(gguf),
        "--host",
        host,
        "--port",
        str(port),
        "-c",
        str(_ctx_size()),
        "--embedding",
        "--alias",
        alias,
    ]
    ngl = _n_gpu_layers()
    if ngl is not None:
        argv.extend(["-ngl", str(ngl)])
    else:
        argv.extend(["-fit", "on"])
    argv.extend(["--pooling", _resolve_pooling(gguf)])
    return argv


def _parse_host_port(base_url: str) -> tuple[str, int]:
    parsed = urlparse(base_url)
    host = (parsed.hostname or "127.0.0.1").strip()
    port = int(parsed.port or DEFAULT_EMBED_PORT)
    return host, port


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


def _probe_embeddings_ok(base_url: str, model: str, timeout: float = 30.0) -> bool:
    """/v1/embeddings 가 pooling=none 등으로 400 인지 확인."""
    url = f"{base_url.rstrip('/')}/v1/embeddings"
    payload = {"model": model or "embedding", "input": "ping"}
    try:
        r = httpx.post(url, json=payload, timeout=timeout)
        if r.status_code >= 400:
            return False
        data = r.json()
        items = data.get("data") if isinstance(data, dict) else None
        if isinstance(items, list) and items:
            emb = items[0].get("embedding") if isinstance(items[0], dict) else None
            return isinstance(emb, list) and bool(emb)
        emb = data.get("embedding") if isinstance(data, dict) else None
        return isinstance(emb, list) and bool(emb)
    except Exception:
        return False


def _terminate_listener_on_port(port: int, *, logger_func: LoggerFunc | None = None) -> None:
    """우리가 추적하지 않는 외부 llama-server(잘못된 pooling)를 포트 기준으로 종료."""
    log = logger_func or print
    if sys.platform != "win32":
        log(f"[llama.cpp:embed] 포트 {port} 외부 프로세스 종료는 Windows에서만 지원합니다.")
        return
    try:
        out = subprocess.check_output(
            ["netstat", "-ano"],
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,  # type: ignore[attr-defined]
        )
    except Exception as e:
        log(f"[llama.cpp:embed] netstat 실패: {e}")
        return
    needle = f":{port}"
    pids: set[int] = set()
    for line in out.splitlines():
        if "LISTENING" not in line.upper():
            continue
        if needle not in line:
            continue
        parts = line.split()
        if not parts:
            continue
        try:
            pids.add(int(parts[-1]))
        except ValueError:
            continue
    for pid in pids:
        if pid <= 0:
            continue
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                check=False,
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,  # type: ignore[attr-defined]
            )
            log(f"[llama.cpp:embed] 포트 {port} 리스너 종료 (pid={pid})")
        except Exception as e:
            log(f"[llama.cpp:embed] pid={pid} 종료 실패: {e}")


def _spawn_server(argv: List[str], *, logger_func: LoggerFunc | None = None) -> subprocess.Popen:
    global _log_path
    log = logger_func or print
    log_dir = Path(__file__).resolve().parents[2] / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    _log_path = log_dir / "llama-server-embeddings.log"
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
    log(f"[llama.cpp:embed] llama-server 시작 (pid={proc.pid}, log={_log_path})")
    return proc


def stop_embeddings_llamacpp_server(*, logger_func: LoggerFunc | None = None) -> None:
    global _server_proc, _active_gguf, _active_base_url, _active_pooling, _active_requests
    log = logger_func or print
    _idle_stop_event.set()
    with _lock:
        proc = _server_proc
        _server_proc = None
        _active_gguf = None
        _active_base_url = None
        _active_pooling = None
        _active_requests = 0
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=8)
            log("[llama.cpp:embed] llama-server 종료")
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    # tracked Popen이 없어도 포트에 orphan이 남을 수 있음
    try:
        _h, port = _parse_host_port(embeddings_llamacpp_base_url())
        _terminate_listener_on_port(port, logger_func=log)
    except Exception:
        pass


def ensure_embeddings_llamacpp_ready(
    *,
    logger_func: LoggerFunc | None = None,
    wait_sec: float = 90.0,
) -> str:
    """임베딩용 llama-server가 떠 있는지 확인하고 없으면 기동. Returns model alias."""
    with _ensure_lock:
        return _ensure_embeddings_llamacpp_ready_locked(
            logger_func=logger_func, wait_sec=wait_sec
        )


def _ensure_embeddings_llamacpp_ready_locked(
    *,
    logger_func: LoggerFunc | None = None,
    wait_sec: float = 90.0,
) -> str:
    global _server_proc, _active_gguf, _active_base_url, _active_pooling
    log = logger_func or print
    alias = embeddings_model_from_env()
    base = embeddings_llamacpp_base_url()

    from javstory.library.embeddings.harvest_coordination import (
        embeddings_pause_during_harvest_from_env,
        is_embedding_harvest_paused,
    )

    if embeddings_pause_during_harvest_from_env() and is_embedding_harvest_paused():
        health = _server_health_ok(base)
        # Harvest 중에는 임베딩 서버를 재사용하지 않는다(번역용 VRAM/RAM 확보).
        if health or (_server_proc is not None):
            try:
                stop_embeddings_llamacpp_server(logger_func=log)
            except Exception:
                pass
            try:
                _h, _p = _parse_host_port(base)
                _terminate_listener_on_port(_p, logger_func=log)
            except Exception:
                pass
        raise RuntimeError(
            "Harvest 진행 중 — 임베딩 llama-server 시작을 보류합니다. "
            "Harvest 완료 후 자동으로 재개됩니다."
        )

    host, port = _parse_host_port(base)

    if not _env_bool("JAVSTORY_EMBEDDINGS_LLAMACPP_AUTO_START", True):
        if not _server_health_ok(base):
            raise RuntimeError(
                f"임베딩 llama-server가 응답하지 않습니다 ({base}). "
                "JAVSTORY_EMBEDDINGS_LLAMACPP_AUTO_START=1 이거나 수동으로 "
                "`llama-server -m <embed.gguf> --embedding` 을 띄우세요."
            )
        return alias

    gguf = _resolve_embed_gguf()
    gguf_key = str(gguf)
    pooling = _resolve_pooling(gguf)

    with _lock:
        if _server_proc is not None and _server_proc.poll() is not None:
            _server_proc = None
            _active_gguf = None
            _active_pooling = None
        if (
            _server_proc is not None
            and _active_gguf == gguf_key
            and _active_base_url == base
            and _active_pooling == pooling
        ):
            check_proc = _server_proc
        else:
            check_proc = None
            if _server_proc is not None:
                old = _server_proc
                _server_proc = None
                _active_gguf = None
                _active_base_url = None
                _active_pooling = None
                try:
                    old.terminate()
                except Exception:
                    pass

    if check_proc is not None and (_recent_health_ok(base) or _server_health_ok(base)):
        _mark_health_ok(base)
        touch_embeddings_activity()
        _ensure_idle_monitor_started(logger_func=log)
        return alias

    # 이미 외부에서 떠 있는 경우: pooling이 맞는지 프로브 후 재사용
    if _server_health_ok(base):
        if _probe_embeddings_ok(base, alias):
            with _lock:
                _active_gguf = gguf_key
                _active_base_url = base
                _active_pooling = pooling
            log(f"[llama.cpp:embed] 기존 서버 재사용 ({base}, pooling={pooling})")
            touch_embeddings_activity()
            _ensure_idle_monitor_started(logger_func=log)
            return alias
        log(
            f"[llama.cpp:embed] 기존 서버가 /v1/embeddings 에 실패"
            f"(pooling 미설정 가능). 재기동합니다 ({base})."
        )
        _terminate_listener_on_port(port, logger_func=log)

    # Windows(Hyper-V/WSL2/Docker)는 동적 포트 제외 범위를 예약해, 아무도 리스닝하지
    # 않는데도 bind()가 WSAEACCES(10013)로 거부되는 경우가 있다. netstat에 잡히는
    # 리스너가 없다면 프로세스를 죽여도 소용없으므로 대체 포트를 찾는다.
    if sys.platform == "win32":
        bind_probe = _port_bind_probe(host, port)
        if not bind_probe.get("bind_ok") and not _port_is_listening_netstat(port):
            if _embed_port_is_user_pinned():
                raise RuntimeError(
                    f"임베딩 포트 {port} 바인딩이 Windows에서 거부되었습니다(WinError "
                    f"{bind_probe.get('winerror')}). 해당 포트가 Windows 제외/예약 범위일 "
                    "수 있으니 JAVSTORY_EMBEDDINGS_LLAMACPP_PORT를 다른 포트로 지정하세요."
                )
            log(
                f"[llama.cpp:embed] 포트 {port} 바인딩 거부(WinError "
                f"{bind_probe.get('winerror')}, 리스너 없음) — Windows 포트 제외 범위로 "
                "추정, 대체 포트 탐색"
            )
            replacement = _find_bindable_llamacpp_port(host, port + 1)
            if replacement is None:
                raise RuntimeError(
                    f"임베딩 포트 {port} 바인딩이 Windows에서 거부되었고 대체 포트를 찾지 "
                    "못했습니다. JAVSTORY_EMBEDDINGS_LLAMACPP_PORT를 사용 가능한 포트로 지정하세요."
                )
            port, _ = replacement
            base = f"http://{host}:{port}"
            os.environ["JAVSTORY_EMBEDDINGS_LLAMACPP_PORT"] = str(port)
            os.environ.pop("JAVSTORY_EMBEDDINGS_LLAMACPP_URL", None)
            log(f"[llama.cpp:embed] 임베딩 서버 포트를 {port} 로 자동 전환")

    argv = _build_embed_argv(gguf, host, port, alias)
    proc = _spawn_server(argv, logger_func=log)
    with _lock:
        _server_proc = proc
        _active_gguf = gguf_key
        _active_base_url = base
        _active_pooling = pooling

    deadline = time.time() + max(5.0, wait_sec)
    retried_port_clear = False
    while time.time() < deadline:
        if proc.poll() is not None:
            if not retried_port_clear:
                retried_port_clear = True
                log(
                    f"[llama.cpp:embed] llama-server 즉시 종료 — 포트 {port} 점유 "
                    "프로세스(고아 프로세스 가능성) 정리 후 1회 재시도"
                )
                _terminate_listener_on_port(port, logger_func=log)
                time.sleep(0.5)
                argv = _build_embed_argv(gguf, host, port, alias)
                proc = _spawn_server(argv, logger_func=log)
                with _lock:
                    _server_proc = proc
                    _active_gguf = gguf_key
                    _active_base_url = base
                    _active_pooling = pooling
                continue
            raise RuntimeError(
                f"임베딩 llama-server가 즉시 종료되었습니다 (log={_log_path}). "
                "GGUF 경로·VRAM·포트 충돌을 확인하세요."
            )
        if _server_health_ok(base, timeout=1.5):
            log(f"[llama.cpp:embed] 준비 완료 ({base}, model={alias})")
            touch_embeddings_activity()
            _ensure_idle_monitor_started(logger_func=log)
            return alias
        time.sleep(0.4)

    raise RuntimeError(
        f"임베딩 llama-server 기동 시간 초과 ({wait_sec:.0f}s, {base}). "
        f"로그: {_log_path}"
    )


atexit.register(lambda: stop_embeddings_llamacpp_server(logger_func=lambda *_: None))


def _is_connect_error(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name in {"ConnectError", "ConnectTimeout"}:
        return True
    return "connection" in str(exc).lower()


def _parse_embedding_response(data: Any, *, expected: int) -> List[List[float]]:
    if not isinstance(data, dict):
        raise ValueError("llamacpp embed: response is not an object")
    items = data.get("data")
    if not isinstance(items, list) or not items:
        # 일부 빌드는 단일 embedding 필드
        emb = data.get("embedding")
        if isinstance(emb, list) and emb and expected == 1:
            return [[float(x) for x in emb]]
        raise ValueError("llamacpp embed: data[] missing in response")
    # index 순 정렬
    ordered = sorted(
        (it for it in items if isinstance(it, dict)),
        key=lambda it: int(it.get("index") or 0),
    )
    out: List[List[float]] = []
    for it in ordered:
        emb = it.get("embedding")
        if not isinstance(emb, list) or not emb:
            raise ValueError("llamacpp embed: embedding missing in item")
        out.append([float(x) for x in emb])
    if len(out) != expected:
        raise ValueError(f"llamacpp embed: expected {expected} vectors, got {len(out)}")
    return out


def _response_body_text(exc: BaseException) -> str:
    resp = getattr(exc, "response", None)
    if resp is None:
        return ""
    try:
        return (resp.text or "").strip()
    except Exception:
        return ""


def _is_pooling_incompatible_error(exc: BaseException) -> bool:
    text = str(exc)
    if "Pooling type" in text and "OAI compatible" in text:
        return True
    body = _response_body_text(exc)
    return "Pooling type" in body and "OAI compatible" in body


def _is_context_exceed_error(exc: BaseException) -> bool:
    text = f"{exc} {_response_body_text(exc)}".lower()
    return any(
        marker in text
        for marker in (
            "exceed_context_size",
            "exceeds the available context size",
            "context size has been exceeded",
        )
    )


def _is_server_overload_error(exc: BaseException) -> bool:
    resp = getattr(exc, "response", None)
    if resp is not None and resp.status_code == 500 and _is_context_exceed_error(exc):
        return True
    return False


def _raise_embed_http_error(exc: BaseException) -> None:
    resp = getattr(exc, "response", None)
    if resp is not None:
        body = _response_body_text(exc)
        hint = ""
        if _is_context_exceed_error(exc):
            hint = (
                f" (입력이 ctx={_ctx_size()} 토큰 한도를 초과했습니다. "
                f"JAVSTORY_EMBEDDINGS_LLAMACPP_CTX 를 늘리거나 "
                f"자막/문서 길이를 줄이세요. 자동 truncate 상한≈{embedding_max_input_chars()}자)"
            )
        elif _is_server_overload_error(exc):
            hint = (
                " (llama-server embedding 슬롯 부족 — 동시 요청 과다일 수 있습니다. "
                "JAVSTORY_EMBEDDINGS_LLAMACPP_MAX_CONCURRENT=1 유지, "
                "JAVSTORY_EMBEDDING_QUEUE_CONCURRENCY=1 권장)"
            )
        msg = f"llamacpp /v1/embeddings HTTP {resp.status_code}"
        if body:
            msg = f"{msg}: {body[:500]}{hint}"
        raise RuntimeError(msg) from exc
    raise exc


_EMBED_BATCH_SIZE_ENV = "JAVSTORY_EMBEDDINGS_LLAMACPP_BATCH_SIZE"


def embedding_batch_size() -> int:
    raw = (os.environ.get(_EMBED_BATCH_SIZE_ENV, "") or "").strip()
    try:
        n = int(raw) if raw else 10
    except ValueError:
        n = 10
    return max(1, min(64, n))


async def llamacpp_embed_texts(
    *,
    texts: List[str],
    model: str | None = None,
    base_url: str | None = None,
    timeout_sec: float = 300.0,
) -> List[List[float]]:
    """여러 텍스트를 llama-server /v1/embeddings 로 임베딩.

    캐시 안 된 텍스트만 모아 배치(기본 10개, JAVSTORY_EMBEDDINGS_LLAMACPP_BATCH_SIZE)로
    한 번에 요청한다 — 텍스트 수만큼 순차 왕복하는 것보다 GPU 배치 처리 이득이 있다.
    배치 요청이 실패하면(컨텍스트 초과 등 원인을 개별 텍스트 단위로 격리해야 하므로)
    해당 배치만 항목별 순차 요청+재시도로 폴백한다.
    """
    cleaned = [truncate_embedding_input((t or "").strip()) for t in texts]
    if not cleaned or any(not t for t in cleaned):
        raise ValueError("llamacpp_embed_texts: empty text")
    m = (model or "").strip() or embeddings_model_from_env()
    base = (base_url or "").strip().rstrip("/") or embeddings_llamacpp_base_url()
    url = f"{base}/v1/embeddings"

    results: List[Optional[List[float]]] = [None] * len(cleaned)

    async def _post(payload_texts: List[str]) -> Any:
        payload: Dict[str, Any] = {
            "model": m,
            "input": payload_texts if len(payload_texts) > 1 else payload_texts[0],
        }

        def _sync_post() -> Any:
            with _embed_http_semaphore(), embeddings_request_scope():
                with httpx.Client(timeout=httpx.Timeout(timeout_sec, connect=5.0)) as client:
                    r = client.post(url, json=payload)
                    r.raise_for_status()
                    return r.json()

        return await asyncio.to_thread(_sync_post)

    async def _embed_one(text: str) -> List[float]:
        limit = embedding_max_input_chars()
        retry_limits: List[int | None] = [None, limit // 2, max(256, limit // 4)]
        last_exc: BaseException | None = None

        for attempt, char_limit in enumerate(retry_limits):
            if attempt > 0:
                await asyncio.sleep(0.25 * attempt)
            try:
                payload_text = truncate_embedding_input(text, max_chars=char_limit)
                data = await _post([payload_text])
                vectors = _parse_embedding_response(data, expected=1)
                vec = vectors[0]
                cache_manager.set_embedding(hashlib.md5(payload_text.encode()).hexdigest(), vec)
                return vec
            except Exception as e:
                last_exc = e
                if _is_connect_error(e) or _is_pooling_incompatible_error(e):
                    await asyncio.to_thread(ensure_embeddings_llamacpp_ready, wait_sec=90.0)
                    continue
                if _is_context_exceed_error(e) and attempt + 1 < len(retry_limits):
                    continue
                if getattr(e, "response", None) is not None:
                    _raise_embed_http_error(e)
                raise

        if last_exc is not None:
            if getattr(last_exc, "response", None) is not None:
                _raise_embed_http_error(last_exc)
            raise last_exc
        raise RuntimeError("llamacpp embed: unexpected empty retry loop")

    # 1) 캐시 히트 먼저 채우고, 나머지만 배치 대상으로 남긴다.
    pending_idx: List[int] = []
    for i, t in enumerate(cleaned):
        cached = cache_manager.get_embedding(hashlib.md5(t.encode()).hexdigest())
        if cached is not None:
            results[i] = [float(x) for x in cached.tolist()]
        else:
            pending_idx.append(i)

    batch_size = embedding_batch_size()
    for start in range(0, len(pending_idx), batch_size):
        chunk_idx = pending_idx[start : start + batch_size]
        chunk_texts = [cleaned[i] for i in chunk_idx]
        try:
            data = await _post(chunk_texts)
            vectors = _parse_embedding_response(data, expected=len(chunk_texts))
            for i, vec in zip(chunk_idx, vectors):
                results[i] = vec
                cache_manager.set_embedding(hashlib.md5(cleaned[i].encode()).hexdigest(), vec)
        except Exception as e:
            if _is_connect_error(e) or _is_pooling_incompatible_error(e):
                await asyncio.to_thread(ensure_embeddings_llamacpp_ready, wait_sec=90.0)
            # 배치 실패 — 원인(컨텍스트 초과 등)을 개별 텍스트 단위로 격리하기 위해
            # 이 배치만 항목별 순차 요청+재시도로 폴백한다.
            for i in chunk_idx:
                results[i] = await _embed_one(cleaned[i])

    return [r if r is not None else [] for r in results]
