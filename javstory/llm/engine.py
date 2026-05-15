import json
import asyncio
import random
import re
import sys
import inspect
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
import httpx

from javstory.config.app_config import (
    LLM_TIERS, LLM_BACKOFF_STAGES, LLM_REFUSAL_PATTERNS,
    OPENROUTER_BASE_URL, OLLAMA_BASE_URL, GEMINI_BASE_URL,
)


async def ollama_unload_model(
    model: str,
    *,
    base_url: str = OLLAMA_BASE_URL,
    logger_func=None,
) -> None:
    """
    Ollama가 VRAM에 올려 둔 가중치를 내려보냄.
    네이티브 POST /api/generate + keep_alive=0 (응답 직후 언로드).
    """
    log = logger_func if logger_func else print
    url = f"{base_url.rstrip('/')}/api/generate"
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": ".",
        "stream": False,
        "keep_alive": 0,
        "options": {"num_predict": 1},
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
            r = await client.post(url, json=payload)
        if r.status_code >= 400:
            log(f"[Ollama] 모델 언로드 요청 실패 HTTP {r.status_code}: {(r.text or '')[:200]}")
        else:
            log(f"[Ollama] 모델 언로드(keep_alive=0) 완료: {model}")
    except Exception as e:
        log(f"[Ollama] 모델 언로드 예외(무시 가능): {e}")

async def ollama_ensure_model(
    model: str,
    *,
    base_url: str = OLLAMA_BASE_URL,
    logger_func=None,
) -> bool:
    """
    Ollama 모델이 있는지 확인하고 없으면 다운로드(pull) 시도.
    또한 모델을 VRAM에 미리 올리는(Warm-up) 역할 수행.
    """
    log = logger_func if logger_func else print
    base_url = base_url.rstrip('/')
    
    # 1. 모델 존재 확인 및 Pull (다운로드)
    log(f"[Ollama] 모델 상태 확인 중: {model}...")
    pull_url = f"{base_url}/api/pull"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(None)) as client:
            async with client.stream("POST", pull_url, json={"model": model, "stream": True}) as r:
                if r.status_code == 200:
                    async for line in r.aiter_lines():
                        if not line: continue
                        data = json.loads(line)
                        status = data.get("status", "")
                        if "downloading" in status:
                             p = data.get("completed", 0) / data.get("total", 1) * 100
                             log(f"  [Ollama] 다운로드 중: {p:.1f}%", end="\r")
                        elif status == "success":
                             log(f"[Ollama] 모델 준비 완료: {model}")
                else:
                    log(f"[Ollama] 모델 확인 실패 (HTTP {r.status_code})")
                    return False
    except Exception as e:
        log(f"[Ollama] 모델 확인 중 오류: {e}")
        return False

    # 2. 모델 예열 (Warm-up / VRAM 로딩)
    log(f"[Ollama] 모델 예열(VRAM Loading) 시작...")
    gen_url = f"{base_url}/api/generate"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            # 1개 토큰만 예측하도록 하여 메모리에만 올림 (keep_alive: -1로 명시적 유지)
            # num_ctx를 chat 호출과 동일하게 맞춰야 같은 컨텍스트로 로드됨(불일치 시 재로드 발생)
            import os as _os
            _num_ctx = int((_os.environ.get("OLLAMA_NUM_CTX") or "").strip() or 0) or 2048
            await client.post(gen_url, json={
                "model": model,
                "prompt": ".",
                "stream": False,
                "keep_alive": -1,
                "options": {"num_predict": 1, "num_ctx": _num_ctx}
            })
        log(f"[Ollama] 모델 VRAM 로딩 완료.")
        return True
    except Exception as e:
        log(f"[Ollama] 모델 예열 실패: {e}")
        return False

class AllTiersExhaustedError(Exception):
    """모든 LLM 모델 시도가 실패했을 때 발생하는 예외"""
    pass

class JSONValidationError(Exception):
    """JSON 형식이 유효하지 않거나 스키마가 일치하지 않을 때 발생하는 예외"""
    pass


def _merge_openrouter_headers(
    model_cfg: Dict[str, Any],
    extra_headers: Optional[Dict[str, str]],
) -> Dict[str, str]:
    """tier의 ``openrouter_extra_headers``를 먼저 넣고, ``extra_headers`` 인자로 같은 키를 덮어쓴다."""
    merged: Dict[str, str] = {}
    tier_hdr = model_cfg.get("openrouter_extra_headers")
    if isinstance(tier_hdr, dict):
        for k, v in tier_hdr.items():
            merged[str(k)] = str(v)
    if extra_headers:
        for k, v in extra_headers.items():
            merged[str(k)] = str(v)
    return merged


def _chat_completions_accepts_extra_headers(client: Any) -> bool:
    try:
        fn = client.chat.completions.create
        sig = inspect.signature(fn)
        return "extra_headers" in sig.parameters
    except Exception:
        return False


def _safe_log_text(s: str) -> str:
    """Windows cp949 등에서 이모지·서로게이트 출력 시 UnicodeEncodeError 방지."""
    enc = getattr(sys.stdout, "encoding", None) or getattr(sys.stderr, "encoding", None) or "utf-8"
    try:
        return s.encode(enc, errors="replace").decode(enc, errors="replace")
    except Exception:
        return s.encode("ascii", errors="replace").decode("ascii")


def _coalesce_chat_message_text(msg: Any) -> str:
    """
    OpenAI 호환 응답에서 본문 문자열을 꺼낸다.
    Ollama + Qwen3 등 'thinking' 모델은 `content`가 비고 `reasoning` / `reasoning_content`에
    실제 생성문이 들어가는 경우가 있어, 비었을 때만 대체 필드를 사용한다.
    """
    raw = getattr(msg, "content", None)
    if isinstance(raw, list):
        parts: List[str] = []
        for p in raw:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(str(p.get("text") or ""))
            elif isinstance(p, str):
                parts.append(p)
        joined = "".join(parts).strip()
        if joined:
            return joined
    elif isinstance(raw, str) and raw.strip():
        return raw

    for attr in ("reasoning_content", "reasoning"):
        alt = getattr(msg, attr, None)
        if isinstance(alt, str) and alt.strip():
            return alt

    try:
        d = msg.model_dump()  # pydantic v2
    except Exception:
        d = None
    if isinstance(d, dict):
        rc = d.get("content")
        if isinstance(rc, list):
            joined = "".join(
                str(x.get("text", x) if isinstance(x, dict) else x) for x in rc
            ).strip()
            if joined:
                return joined
        if isinstance(rc, str) and rc.strip():
            return rc
        for k in ("reasoning_content", "reasoning"):
            v = d.get(k)
            if isinstance(v, str) and v.strip():
                return v
    return ""


class MultiTierRouter:
    """
    [Phase 5] 5-Tier 폴백 및 비동기 순차 연동 엔진.
    - Tier 순서: DeepSeek -> Hermes Free -> Hermes 70B -> Hermes 405B -> Local Qwen
    - 비동기 호출 및 청크 단위 순차 처리 지원.
    """
    def __init__(self, api_key: str, logger_func=None):
        self.api_key = api_key
        _raw = logger_func if logger_func else print

        def logger(msg: str) -> None:
            _raw(_safe_log_text(str(msg)))

        self.logger = logger
        # OpenRouter 비동기 클라이언트
        self.or_client = AsyncOpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=api_key,
            timeout=httpx.Timeout(180.0, connect=5.0)
        )
        # Ollama 비동기 클라이언트
        self.ol_client = AsyncOpenAI(
            base_url=f"{OLLAMA_BASE_URL}/v1",
            api_key="ollama",
            timeout=httpx.Timeout(300.0, connect=5.0)
        )
        # Gemini 비동기 클라이언트 (API 키 미설정 시 None)
        import os as _os
        _gemini_key = (_os.environ.get("JAVSTORY_GEMINI_API_KEY") or "").strip()
        self.gemini_client: Optional[AsyncOpenAI] = (
            AsyncOpenAI(
                base_url=GEMINI_BASE_URL,
                api_key=_gemini_key,
                timeout=httpx.Timeout(180.0, connect=5.0),
            )
            if _gemini_key else None
        )

    async def close(self) -> None:
        """비동기 클라이언트 리소스를 명시적으로 해제합니다.
        asyncio.run() 종료 직후 백그라운드 aclose가 루프 종료와 맞물리면
        Event loop is closed 가 날 수 있어 무시합니다.
        """
        for cl in (self.or_client, self.ol_client, self.gemini_client):
            if cl is None:
                continue
            try:
                await cl.close()
            except RuntimeError as e:
                if "Event loop is closed" in str(e):
                    continue
                self.logger(f"  [Router] 리소스 해제 RuntimeError: {e}")
            except Exception as e:
                self.logger(f"  [Router] 리소스 해제 중 오류 (무시 가능): {e}")

    async def is_refusal(self, response_text: str) -> bool:
        """검열 감지 로직 (None 방어 포함)"""
        if not response_text:
            return False
            
        try:
            json.loads(response_text)
            return False
        except Exception:
            pass

        first_part = response_text[:200].lower().strip()
        for pattern in LLM_REFUSAL_PATTERNS:
            if re.search(pattern, first_part):
                return True
        return False

    def get_backoff_delay(self, attempt: int) -> float:
        if attempt >= len(LLM_BACKOFF_STAGES):
            base = LLM_BACKOFF_STAGES[-1]
        else:
            base = LLM_BACKOFF_STAGES[attempt]
        jitter = random.uniform(0, 1)
        return float(base + jitter)

    async def call_model(
        self,
        model_cfg: Dict[str, Any],
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> str:
        """개별 모델 비동기 호출 (None 방어 포함)

        extra_headers: 요청별 HTTP 헤더. tier ``openrouter_extra_headers``와 병합되며 동일 키는 이 인자가 우선.
        """
        provider = model_cfg.get("provider", "openrouter")

        if provider == "gemini":
            if self.gemini_client is None:
                raise ValueError(
                    "Gemini API 키가 설정되지 않았습니다. "
                    "설정 화면에서 Gemini API 키를 입력하고 저장해주세요."
                )
            client = self.gemini_client
        elif provider == "ollama":
            client = self.ol_client
        else:
            client = self.or_client

        # Gemini는 HTML 출력 방식 — json_mode 미사용
        resp_fmt = {"type": "json_object"} if json_mode and provider == "openrouter" else None

        kwargs: Dict[str, Any] = {
            "model": model_cfg["model"],
            "messages": messages,
            "temperature": temperature,
            "response_format": resp_fmt,
        }
        if isinstance(max_tokens, int) and max_tokens > 0:
            kwargs["max_tokens"] = max_tokens

        # OpenRouter/Ollama OpenAI 호환: provider별 extra_body 지원 (Gemini는 불필요)
        if provider == "ollama":
            xb = model_cfg.get("ollama_extra_body") or {}
            ot = model_cfg.get("ollama_think", None)
            
            # [수정] 청크마다 VRAM 로드/언로드를 반복하지 않도록 keep_alive 기본값 설정
            # ollama_ko_vram 모듈에서 명시적으로 언로드하기 전까지 유지하도록 -1(또는 충분한 시간) 사용
            eb = dict(xb)
            if "keep_alive" not in eb:
                eb["keep_alive"] = -1
            
            if ot is not None and "think" not in eb:
                eb["think"] = bool(ot)

            # [추가] CPU 부하 방지를 위해 num_thread 명시적 제한 (환경변수 기반)
            if "num_thread" not in eb:
                import os
                raw_nt = os.environ.get("OLLAMA_NUM_THREAD", "").strip()
                if raw_nt.isdigit():
                    eb["num_thread"] = int(raw_nt)

            # [추가] VRAM 효율을 위해 번역 시 불필요하게 큰 문맥(Context) 제한
            if "num_ctx" not in eb:
                _raw_ctx = (os.environ.get("OLLAMA_NUM_CTX") or "").strip()
                eb["num_ctx"] = int(_raw_ctx) if _raw_ctx.isdigit() else 2048
            
            kwargs["extra_body"] = eb
        elif provider == "openrouter":
            oxb = model_cfg.get("openrouter_extra_body")
            if isinstance(oxb, dict) and oxb:
                kwargs["extra_body"] = dict(oxb)

        merged_headers = _merge_openrouter_headers(model_cfg, extra_headers)
        if merged_headers and provider == "openrouter" and _chat_completions_accepts_extra_headers(client):
            kwargs["extra_headers"] = merged_headers

        # Gemini: response_format=None 보장 (HTML 출력)
        if provider == "gemini":
            kwargs.pop("response_format", None)

        try:
            response = await client.chat.completions.create(**kwargs)
        except TypeError as e:
            err_l = str(e).lower()
            if "extra_headers" in kwargs and (
                "extra_headers" in err_l or "unexpected keyword" in err_l
            ):
                kwargs.pop("extra_headers", None)
                self.logger(f"  [Router] extra_headers 미지원 — 헤더 없이 재시도: {e}")
                response = await client.chat.completions.create(**kwargs)
            elif "extra_body" in kwargs and ("extra_body" in err_l or "unexpected keyword" in err_l):
                kwargs.pop("extra_body", None)
                self.logger(f"  [Router] extra_body 미지원 — think 옵션 없이 재시도: {e}")
                response = await client.chat.completions.create(**kwargs)
            else:
                raise
        except Exception as e:
            raise

        content = _coalesce_chat_message_text(response.choices[0].message)
        # Qwen 등: 본문이 reasoning 쪽에만 있을 때 `<think>` 래퍼가 남는 경우
        content = re.sub(
            r"<redacted_thinking>.*?</redacted_thinking>", "", content, flags=re.DOTALL | re.IGNORECASE
        )
        content = content.strip()
        if not content:
            raise ValueError("모델 응답이 비어있습니다. (빈 문자열 반환)")
        return content

    async def route(self, messages: List[Dict[str, str]], tier_override: Optional[Dict[str, Any]] = None, json_mode: bool = False) -> str:
        """
        단건 요청에 대한 5-Tier 자동 폴백 및 수동 모드 처리.
        """
        if tier_override:
            tiers_to_try = [tier_override]
        else:
            tiers_to_try = sorted(LLM_TIERS, key=lambda x: x["rank"])

        for tier in tiers_to_try:
            model_name = tier["name"]
            model_id = tier["model"]
            temperature = float(tier.get("temperature", 0.3))
            max_tokens = tier.get("max_tokens", None)

            for attempt in range(4):
                try:
                    # [로깅 고도화] 매 시도마다 시각적 피드백 제공
                    if attempt == 0:
                        self.logger(f"  [Router] 사용 중: {model_name} ({model_id})")
                    else:
                        self.logger(f"  [Router] 사용 중: {model_name} | {attempt+1}/4회차 재시도 중...")

                    content = await self.call_model(
                        tier,
                        messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        json_mode=json_mode,
                    )
                    
                    if await self.is_refusal(content):
                        if tier.get("uncensored"):
                            # 무검열 모델 거절은 프롬프트/안전장치 원인일 때가 많아,
                            # 같은 모델로 무의미한 반복 호출을 줄이고 다음 티어로 전환한다.
                            if attempt == 0:
                                self.logger(
                                    f"    ⚠️ [Refusal] 무검열 모델 {model_name} 거절. 1회만 재시도 후 전환."
                                )
                                continue
                            self.logger(
                                f"    ⚠️ [Refusal] 무검열 모델 {model_name} 2회 연속 거절. 다음 티어로 전환."
                            )
                            break
                        else:
                            self.logger(f"    🚫 [Censored] {model_name} 검열. 다음 티어로 전환.")
                            break 

                    if attempt > 0:
                        self.logger(f"  ✅ [Router] {model_name} 재시도 성공!")

                    return content 

                except Exception as e:
                    delay = self.get_backoff_delay(attempt)
                    if tier_override:
                         self.logger(f"    ❌ [Manual Mode] {model_name} 오류: {e} | {delay:.1f}s 후 재시도 ({attempt+1}/4)")
                    else:
                         self.logger(f"    ❌ {model_name} 오류: {e} | {delay:.1f}s 후 재시도 ({attempt+1}/4)")
                    
                    await asyncio.sleep(delay)
            
            if tier_override: # 수동 모드 실패
                 break

            self.logger(f"  [Router] {model_name} 실패. 다음 티어로 롤백...")

        raise AllTiersExhaustedError("모든 AI 티어가 응답에 실패했거나 검열되었습니다.")

    async def process_chunks(self, chunks: List[List[Dict]], system_prompt: str, meta_context: str, tier_override: Optional[Dict] = None, sleep_sec: float = 1.0) -> List[str]:
        """
        [Phase 5 핵심] 청크 리스트를 받아 순차적으로 LLM에 전달.
        결과 리스트를 반환하며 각 호출 사이 sleep_sec 대기.
        """
        results = []
        for i, chunk in enumerate(chunks):
            self.logger(f"  [Router] Chunk {i+1}/{len(chunks)} 처리 중...")
            
            chunk_data = json.dumps(chunk, ensure_ascii=False)
            user_prompt = f"[Metadata]\n{meta_context}\n\n[Transcript Chunk]\n{chunk_data}"
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            response = await self.route(messages, tier_override=tier_override)
            results.append(response)
            
            if i < len(chunks) - 1 and sleep_sec > 0:
                self.logger(f"  [Router] {sleep_sec}초 비동기 대기 (Rate Limit 방어)...")
                await asyncio.sleep(sleep_sec)
                
        return results
