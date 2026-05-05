"""
플랜 정식: `Transcription/correction_chunk.py` — 일본어 자막 LLM 교정(청크·JSON 출력·CORRECTION_MODE).

Pass1: Grok 계열 — 시놉시스·자막 샘플 → 보조 컨텍스트 JSON.
Pass2(및 선택적 Pass3): 플랜 프롬프트(reference_strong | reference_weak | baseline_only), 출력은 JSON 배열만.
`claude_polish=True`면 플랜 Pass2 기본 모델(GLM 5.1 등)을 건너뛰고 Claude(Pass3 티어)로 주교정만 수행한다.
`Transcription/json_extract.py`로 펜스·괄호 균형 파싱. API는 지수 백오프 재시도.

속도 조절(환경변수):
- JAVSTORY_CORRECTION_PASS2_CONCURRENCY: Pass2 동시 요청 (미설정 시 GLM=3, 그 외 OpenRouter=2, Ollama=1, 상한 8). 429 시 백오프.
- JAVSTORY_CORRECTION_PASS3_CONCURRENCY: Pass3 동시 요청 (기본 1).
- JAVSTORY_CORRECTION_CHUNK_TARGET_SEC / _OVERLAP_SEC: 청크 길이·겹침(초) 강제. 미설정 시 DeepSeek V3.2 18s/5s, DeepSeek 기타 16s/4s, GLM-5.1 14s/4s, Ollama는 `_ollama_chunk_params_by_model` (Qwen3.5:9B 16/4.5, Qwen3:8B 15/4, Qwen3:14B 18/5, Qwen2.5:14B 17/4.5, Gemma3:12B 16/4.5, Gemma4 16/4 등), 기타 Ollama ~300s/20s, MiniMax ~30s/6s, 그 외 ~50s/10s.
- GLM 입력 축소·출력 상한: JAVSTORY_GLM_REF_STRONG_MAXCHARS(2200), _REF_WEAK_(900), _CTX_JSON_(1800), _CTX_LINES_(22), _CTX_MAXCHARS_(1400), _MAX_TOKENS_(8192), _TEMPERATURE_(0.1).

SoT: `.cursor/plans/transcription_stable-ts_이식_d9a90db7.plan.md`
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any, Callable, Dict, List, Optional

from javstory.translation.json_extract import parse_json_array, parse_json_object
from javstory.translation.llm_backoff import route_with_backoff
from javstory.transcription.stt_types import STTCancelled, SimpleSegment

CancelCheck = Optional[Callable[[], bool]]
OptionalLogger = Optional[Callable[[str], None]]


def _ollama_chunk_params_by_model(model: str) -> tuple[float, float]:
    """Ollama 태그 문자열 기준 청크·겹침(초). 번역·교정 공통."""
    m = (model or "").lower()
    if "gemma4" in m:
        return 16.0, 4.0
    if "gemma3" in m:
        return 16.0, 4.5
    if "gemma" in m:
        return 16.0, 4.0
    if "qwen3.5" in m or "qwen3_5" in m:
        return 16.0, 4.5
    if "qwen2.5" in m or "qwen2_5" in m:
        return 17.0, 4.5
    if "qwen3:8b" in m or "qwen3-8b" in m:
        return 15.0, 4.0
    if "qwen3:14b" in m or "qwen3-14b" in m:
        return 18.0, 5.0
    if "qwen" in m:
        return 18.0, 5.0
    if "ja-ko-vn" in m or "jkv" in m:
        return 16.0, 4.5
    return 300.0, 20.0


def _chunk_params_for_tier(tier: Dict[str, Any]) -> tuple[float, float]:
    model = (tier.get("model") or "").lower()
    if tier.get("provider") == "ollama":
        return _ollama_chunk_params_by_model(model)
    if "minimax" in model:
        return 30.0, 6.0
    if _is_glm_tier(tier):
        return 14.0, 4.0
    if "deepseek" in model and ("v3.2" in model or "deepseek-v3.2" in model):
        return 18.0, 5.0
    if "deepseek" in model:
        return 16.0, 4.0
    return 50.0, 10.0


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _effective_chunk_durations(tier_p2: Dict[str, Any]) -> tuple[float, float]:
    """티어 기본값 + JAVSTORY_CORRECTION_CHUNK_* 환경변수로 덮어쓰기."""
    target_dur, overlap_dur = _chunk_params_for_tier(tier_p2)
    if os.environ.get("JAVSTORY_CORRECTION_CHUNK_TARGET_SEC"):
        target_dur = max(5.0, _env_float("JAVSTORY_CORRECTION_CHUNK_TARGET_SEC", target_dur))
    if os.environ.get("JAVSTORY_CORRECTION_CHUNK_OVERLAP_SEC"):
        overlap_dur = max(0.0, _env_float("JAVSTORY_CORRECTION_CHUNK_OVERLAP_SEC", overlap_dur))
    return target_dur, overlap_dur


def _correction_concurrency(pass_label: str, default: int) -> int:
    key = (
        "JAVSTORY_CORRECTION_PASS2_CONCURRENCY"
        if pass_label == "pass2"
        else "JAVSTORY_CORRECTION_PASS3_CONCURRENCY"
    )
    try:
        n = int(os.environ.get(key, str(default)))
    except ValueError:
        n = default
    return max(1, min(n, 8))


def _is_minimax_tier(tier: Dict[str, Any]) -> bool:
    return "minimax" in ((tier.get("model") or "").lower())


def _is_glm_tier(tier: Dict[str, Any]) -> bool:
    return "glm" in ((tier.get("model") or "").lower())


def _default_pass2_concurrency(tier: Dict[str, Any]) -> int:
    if tier.get("provider") == "ollama":
        return 1
    if tier.get("provider") == "openrouter":
        return 3 if _is_glm_tier(tier) else 2
    return 1


def _truncate_chars(s: str, max_chars: int) -> str:
    if not isinstance(s, str):
        return ""
    if max_chars <= 0:
        return ""
    s = s.strip()
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1].rstrip() + "…"


def _truncate_multiline(s: str, *, max_lines: int, max_chars: int) -> str:
    if not isinstance(s, str):
        return ""
    s = s.strip()
    if not s:
        return ""
    lines = [ln.rstrip() for ln in s.splitlines() if ln.strip()]
    if max_lines > 0:
        lines = lines[:max_lines]
    joined = "\n".join(lines).strip()
    return _truncate_chars(joined, max_chars)


def _speaker_rule_text(speaker_prefix_mode: str) -> str:
    if (speaker_prefix_mode or "").lower() == "on":
        return (
            "대화 턴이 분명히 바뀔 때만 해당 줄의 text 앞에 '- '(하이픈+공백) 접두어를 허용한다. "
            "그 외에는 접두어를 넣지 않는다."
        )
    return "화자 접두어는 넣지 마라."


def _build_system_prompt_pass2(
    mode: str,
    *,
    ref_strong_block: str,
    ref_weak_block: str,
    speaker_rule: str,
    tier: Dict[str, Any] | None = None,
) -> str:
    model_name = (tier.get("model") or "").lower() if tier else ""

    # 1. Qwen 3 235B 특화 프롬프트
    if "qwen3-235b" in model_name:
        return f"""너는 10년 경력의 전문 JAV 자막 번역·교정 전문가다. 아래 규칙을 **절대적으로 준수**해야 한다. 어떤 이유로도 규칙을 어기면 안 된다.

[최우선 규칙 - 절대 위반 금지]
1. 타임스탬프(start, end)는 입력된 값과 **100% 정확히 동일하게** 유지한다. 절대 변경, 조정, 삭제하지 마라.
2. 한 줄당 최대 50자 이내로 유지한다. 의미를 해치지 않는 최소한의 자연스러운 축약만 허용한다.
3. 대사 창작, 각색, 없는 내용 추가를 절대 하지 마라.
4. 신음, 의성어, 짧은 호흡은 과도하게 문어체로 바꾸지 말고 원문의 리듬과 느낌을 최대한 살린다.
5. 말투와 리듬은 STT 원문에 최대한 가깝게 유지한다.

[다국어 혼입 금지 - 매우 중요]
- 출력은 **100% 한국어**로만 작성한다.
- 일본어, 영어, 중국어, 로마자, 일본어 한자, 영어 단어 등을 절대 섞지 마라.
- 모든 대사는 자연스러운 한국어 회화체로 완전히 번역·교정해야 한다.
- 신음이나 의성어도 한국어 느낌으로 자연스럽게 표현한다.

[성인 콘텐츠 어조 유지]
성인 콘텐츠 특유의 자극적이고 유려한 한국어 비속어나 감탄사를 적절히 사용하되, 어투가 지나치게 딱딱하거나 점잖아지지 않도록 자연스럽게 유지한다.

[출력 형식 - 가장 중요한 규칙]
- 오직 **하나의 JSON 배열**만 출력한다. 배열 바깥에 어떤 글자도, 생각 과정도, 설명도, 마크다운도 절대 출력하지 마라.
- 각 객체는 정확히 다음 형식만 사용한다: 
  {{"index": 정수, "start": "원본과 완전히 동일한 문자열", "end": "원본과 완전히 동일한 문자열", "text": "교정된 한국어 문장"}}
- 대사 안에 큰따옴표(")가 들어갈 경우 반드시 \\"로 이스케이프 처리하여 JSON 형식을 깨뜨리지 않도록 한다.
- 출력은 순수하고 유효한 JSON 배열 하나여야 한다. ```json, "여기 결과입니다", 생각 과정 등 어떤 부가 텍스트도 금지된다.
- JSON이 깨지거나 배열 바깥에 텍스트가 있으면 규칙 위반이다.

[레퍼런스 활용]
보조 분석 JSON의 인물/관계/어조 정보는 참고만 한다. STT 원문과 충돌할 경우 **무조건 STT 원문을 우선**한다. (레퍼런스: {ref_strong_block} / {ref_weak_block})

[입력 데이터]
보조 분석 JSON: (user 프롬프트에서 제공)
직전 맥락: (user 프롬프트에서 제공)
청크 자막: (user 프롬프트에서 제공)

위 규칙과 데이터를 바탕으로 교정 작업을 수행한 후, **순수 JSON 배열 하나만** 출력하라.

마지막으로 다시 강조한다: 출력은 **100% 한국어만** 사용해야 하며, 어떤 외국어도 절대 혼입되지 않아야 한다. 출력은 순수 JSON 배열 하나여야 한다."""

    # 2. DeepSeek V3.2 특화 프롬프트
    if "deepseek-v3.2" in model_name:
        return f"""너는 10년 경력의 전문 JAV 자막 번역·교정 전문가다. 아래 규칙을 **절대적으로 준수**해야 한다.

[최우선 규칙 - 절대 위반 금지]
1. 타임스탬프(start, end)는 입력된 값과 **100% 정확히 동일하게** 유지한다. 절대 변경하지 마라.
2. 한 줄당 최대 50자 이내로 유지한다. 의미를 해치지 않는 최소한의 자연스러운 축약만 허용한다.
3. 대사 창작, 각색, 없는 내용 추가를 절대 하지 마라.
4. 신음, 의성어, 짧은 호흡은 원문의 리듬과 느낌을 최대한 살린다. 과도하게 문어체로 바꾸지 마라.
5. 말투와 리듬은 STT 원문에 최대한 가깝게 유지한다.

[다국어 혼입 금지 - 매우 중요]
- 출력은 **100% 한국어**로만 작성한다.
- 일본어, 영어, 중국어, 로마자, 외래어 등을 절대 섞지 마라.
- 모든 대사는 자연스러운 한국어 회화체로 완전히 번역·교정한다.
- 신음이나 의성어도 한국어 느낌으로 자연스럽게 표현한다.

[성인 콘텐츠 어조 유지]
성인 콘텐츠 특유의 자극적이고 유려한 한국어 비속어나 감탄사를 적절히 사용하되, 어투가 지나치게 딱딱하거나 점잖아지지 않도록 자연스럽게 유지한다.

[출력 형식 - 가장 중요한 규칙]
- 오직 **하나의 JSON 배열**만 출력한다. 배열 바깥에 어떤 글자도, 설명도, 생각 과정도, 마크다운도 절대 출력하지 마라.
- 각 객체는 정확히 다음 형식만 사용한다: 
  {{"index": 정수, "start": "원본과 완전히 동일한 문자열", "end": "원본과 완전히 동일한 문자열", "text": "교정된 한국어 문장"}}
- 대사 안에 큰따옴표(")가 들어갈 경우 반드시 \\"로 이스케이프 처리한다.
- 출력은 순수하고 유효한 JSON 배열 하나여야 한다.

[레퍼런스 활용]
보조 분석 JSON의 인물/관계/어조 정보는 참고만 한다. STT 원문과 충돌할 경우 **무조건 STT 원문을 우선**한다. (레퍼런스: {ref_strong_block} / {ref_weak_block})

[입력 데이터]
보조 분석 JSON: (user 프롬프트에서 제공)
직전 맥락: (user 프롬프트에서 제공)
청크 자막: (user 프롬프트에서 제공)

위 규칙과 데이터를 바탕으로 교정 작업을 수행한 후, **순수 JSON 배열 하나만** 출력하라.

마지막으로 다시 강조한다: 출력은 **100% 한국어만** 사용해야 하며, 어떤 외국어도 절대 혼입되지 않아야 한다. 출력은 순수 JSON 배열 하나여야 한다."""

    # 3. 기본 프롬프트 (GLM 5.1 등)
    common_top = """역할: 일본어 STT 자막 청크를 교정한다.

[최우선]
- 각 원소의 start·end 타임스탬프 문자열은 입력과 동일하게 유지한다(변경 금지).
- 한 줄(text)당 최대 50자(일본어 기준 목표). 초과 시 의미 보존 범위에서만 축약.
- 대사 창작·각색·없는 내용 추가 금지. 신음·의성어를 과도하게 문어로 바꾸지 마라.
- 말투·리듬·짧은 호흡은 STT 원문에 최대한 맞춘다.
"""

    out_suffix = f"""
{{SPEAKER_RULE}}

출력: 입력과 동일한 순서·개수의 JSON 배열만. 원소 형식:
{{"index": 정수, "start": "원본과 동일", "end": "원본과 동일", "text": "교정된 문자열"}}
설명 문장·마크다운·JSON 바깥 텍스트 금지.
""".replace("{SPEAKER_RULE}", speaker_rule)

    if mode == "reference_strong":
        weak_sec = ""
        if ref_weak_block.strip():
            weak_sec = (
                "\n[레퍼런스 — 약한 힌트]\n"
                "아래는 참고용이다. STT와 모순되면 무시한다.\n---\n"
                f"{ref_weak_block}\n---\n"
            )
        return (
            common_top
            + "\n[레퍼런스 — 강한 모드]\n"
            "아래는 출처·품번이 검증된 작품 컨텍스트다. 인물·어조 정리에만 사용하라. "
            "STT 텍스트·타임코드와 충돌하면 STT를 따른다.\n---\n"
            f"{ref_strong_block}\n---\n"
            + weak_sec
            + out_suffix
        )

    if mode == "reference_weak":
        return (
            common_top
            + "\n[레퍼런스 — 약한 힌트]\n"
            "아래는 참고용이다. 단정하거나 설정을 확장하지 마라. STT와 모순이면 레퍼런스를 버리고 STT만 따른다.\n---\n"
            f"{ref_weak_block}\n---\n"
            + out_suffix
        )

    # baseline_only
    return (
        "역할: 일본어 STT 자막 청크에서 명백한 전사 오류만 최소한으로 고친다.\n\n"
        "규칙:\n"
        "- start·end 문자열은 입력과 절대 동일하게 유지한다.\n"
        "- 한 줄 50자 이하. 원소 개수·순서·index 유지.\n"
        "- 대사 추가·삭제·각색 금지. 외부 작품 정보로 보강하지 않는다.\n"
        "- 동음이의·띄어쓰기·명백한 오타 수준만 수정한다.\n\n"
        f"{speaker_rule}\n\n"
        "출력: [{\"index\": int, \"start\": str, \"end\": str, \"text\": str}, ...] 만. 그 외 텍스트 금지.\n"
    )


def _chunk_json_for_segments(segs: List[SimpleSegment]) -> str:
    arr = []
    for i, s in enumerate(segs):
        arr.append(
            {
                "index": i,
                "start": f"{s.start:.2f}",
                "end": f"{s.end:.2f}",
                "text": s.text,
            }
        )
    return json.dumps(arr, ensure_ascii=False)


# 모델이 start/end를 "10341.1"처럼 반올림하거나 소수 자릿수만 다르게 내보내도 허용
_TS_MATCH_TOL = 0.08


def _ts_field_matches(seg_val: float, raw: Any) -> bool:
    if raw is None:
        return True
    try:
        if isinstance(raw, (int, float)):
            tv = float(raw)
        else:
            tv = float(str(raw).strip().replace(",", "."))
        return abs(tv - seg_val) < _TS_MATCH_TOL
    except Exception:
        return False


def _start_end_ok(seg: SimpleSegment, item: dict[str, Any]) -> bool:
    st = item.get("start")
    en = item.get("end")
    ok = True
    if st is not None:
        ok = ok and _ts_field_matches(seg.start, st)
    if en is not None:
        ok = ok and _ts_field_matches(seg.end, en)
    return ok


# 한글 호환 자모 + 음절(가-힣): 동일 문자 4회 이상 연속 → 1회 + … (신음·의성 과다 반복 완화)
_RE_KO_SAME_CHAR_RUN = re.compile(r"([\u3131-\u318E\uAC00-\uD7A3])\1{3,}")


def collapse_repeated_vocal_sounds(text: str) -> str:
    """같은 한글 음절/자모가 한 줄에 과도 반복될 때(아아아아…) 짧게 접는다. JAVSTORY_SUBTITLE_COLLAPSE_VOCAL_REPEAT=0 이면 비활성."""
    if not text:
        return text
    v = (os.environ.get("JAVSTORY_SUBTITLE_COLLAPSE_VOCAL_REPEAT", "1") or "1").strip().lower()
    if v in ("0", "false", "no", "off"):
        return text
    return _RE_KO_SAME_CHAR_RUN.sub(r"\1…", text)


def _apply_json_chunk(
    tgt_segs: List[SimpleSegment],
    raw: str,
    *,
    log: Callable[[str], None],
    log_prefix: str = "[CORRECTION]",
    postprocess_text: Optional[Callable[[str], str]] = None,
) -> bool:
    arr = parse_json_array(raw)
    if not arr:
        log(f"{log_prefix} JSON 배열 파싱 실패")
        return False
    by_idx: dict[int, dict[str, Any]] = {}
    for item in arr:
        if isinstance(item, dict) and isinstance(item.get("index"), int):
            by_idx[item["index"]] = item
    n = len(tgt_segs)
    applied = 0
    for j in range(n):
        item = by_idx.get(j)
        if item is None and j < len(arr) and isinstance(arr[j], dict):
            item = arr[j]
        if not isinstance(item, dict):
            log(f"{log_prefix} index {j} 항목 없음")
            continue
        if not _start_end_ok(tgt_segs[j], item):
            log(f"{log_prefix} index {j} start/end 불일치 — text 스킵")
            continue
        tx = item.get("text")
        if isinstance(tx, str) and tx.strip():
            t = tx.strip()
            if postprocess_text is not None:
                t = postprocess_text(t)
            tgt_segs[j].text = t
            applied += 1
    if applied == 0 and n > 0:
        return False
    return True


def _correction_retry_log(logger: Callable[[str], None]) -> Callable[[str], None]:
    return lambda m: logger(f"[CORRECTION] {m}")


async def _run_pass2_chunk(
    *,
    idx: int,
    total: int,
    chunk: dict,
    tier: Dict[str, Any],
    correction_mode: str,
    ref_strong: str,
    ref_weak: str,
    speaker_rule: str,
    ctx_str: str,
    router: Any,
    log: Callable[[str], None],
    should_cancel: CancelCheck,
    semaphore: asyncio.Semaphore,
) -> None:
    async with semaphore:
        if should_cancel and should_cancel():
            raise STTCancelled()
        tgt_segs: List[SimpleSegment] = chunk["target"]
        if not tgt_segs:
            return

        sys_p = _build_system_prompt_pass2(
            correction_mode,
            ref_strong_block=ref_strong,
            ref_weak_block=ref_weak,
            speaker_rule=speaker_rule,
            tier=tier,
        )
        ctx_block_raw = "\n".join(f"[{s.start:.2f}] {s.text}" for s in chunk["context"])
        if _is_minimax_tier(tier):
            ctx_block = _truncate_multiline(ctx_block_raw, max_lines=12, max_chars=800)
        elif _is_glm_tier(tier):
            try:
                glm_ctx_lines = int(os.environ.get("JAVSTORY_GLM_CTX_LINES", "22"))
            except ValueError:
                glm_ctx_lines = 22
            try:
                glm_ctx_mc = int(os.environ.get("JAVSTORY_GLM_CTX_MAXCHARS", "1400"))
            except ValueError:
                glm_ctx_mc = 1400
            ctx_block = _truncate_multiline(
                ctx_block_raw, max_lines=max(4, glm_ctx_lines), max_chars=max(200, glm_ctx_mc)
            )
        else:
            ctx_block = ctx_block_raw
        chunk_json = _chunk_json_for_segments(tgt_segs)
        
        model_name = (tier.get("model") or "").lower()
        is_high_tier = "qwen3-235b" in model_name or "deepseek-v3.2" in model_name
        
        if is_high_tier:
            user_p = f"보조 분석 JSON:\n{ctx_str}\n\n직전 맥락:\n{ctx_block}\n\n청크 자막:\n{chunk_json}"
        else:
            user_p = f"보조 분석 JSON:\n{ctx_str}\n\n직전 맥락(참고):\n{ctx_block}\n\n청크 자막(JSON):\n{chunk_json}"
            
        messages = [
            {"role": "system", "content": sys_p},
            {"role": "user", "content": user_p},
        ]
        res = await route_with_backoff(router, messages, tier, log=_correction_retry_log(log))
        processed = re.sub(r"<redacted_thinking>.*?</redacted_thinking>", "", res or "", flags=re.DOTALL)
        if not _apply_json_chunk(tgt_segs, processed, log=log):
            log(f"[CORRECTION] Pass2 청크 {idx + 1} JSON 적용 실패 — 1회 재요청")
            retry_msg = messages + [
                {
                    "role": "user",
                    "content": "이전 응답이 유효한 JSON 배열이 아니거나 타임스탬프가 어긋났다. "
                    "동일한 규칙으로 JSON 배열만 다시 출력하라.",
                }
            ]
            res2 = await route_with_backoff(router, retry_msg, tier, log=_correction_retry_log(log))
            processed2 = re.sub(
                r"<redacted_thinking>.*?</redacted_thinking>",
                "",
                res2 or "",
                flags=re.DOTALL,
            )
            if not _apply_json_chunk(tgt_segs, processed2, log=log):
                log(f"[CORRECTION] Pass2 청크 {idx + 1} 최종 실패 — 원문 유지")
        log(f"[CORRECTION] [Pass 2] {idx + 1}/{total} 청크 완료")


async def _run_pass3_chunk(
    *,
    idx: int,
    total: int,
    chunk: dict,
    tier: Dict[str, Any],
    correction_mode: str,
    ref_strong: str,
    ref_weak: str,
    speaker_rule: str,
    ctx_str: str,
    router: Any,
    log: Callable[[str], None],
    should_cancel: CancelCheck,
    semaphore: asyncio.Semaphore,
) -> None:
    async with semaphore:
        if should_cancel and should_cancel():
            raise STTCancelled()
        tgt_segs = chunk["target"]
        if not tgt_segs:
            return
        sys_p = _build_system_prompt_pass2(
            correction_mode,
            ref_strong_block=ref_strong,
            ref_weak_block=ref_weak,
            speaker_rule=speaker_rule,
            tier=tier,
        ) + (
            "\n\n[Pass3] 표기·読みやすさの最小調整のみ。意味・事実は変えない。"
        )
        ctx_block = "\n".join(f"[{s.start:.2f}] {s.text}" for s in chunk["context"])
        chunk_json = _chunk_json_for_segments(tgt_segs)
        model_name = (tier.get("model") or "").lower()
        is_high_tier = "qwen3-235b" in model_name or "deepseek-v3.2" in model_name
        
        if is_high_tier:
            user_p = (
                f"## 보조 분석 JSON\n{ctx_str}\n\n"
                f"## 직전 맥락\n{ctx_block}\n\n"
                f"청크 자막:\n{chunk_json}"
            )
        else:
            user_p = (
                f"## 보조 분석 JSON\n{ctx_str}\n\n"
                f"## 직전 맥락\n{ctx_block}\n\n"
                f"청크 자막:\n{chunk_json}"
            )
        messages = [
            {"role": "system", "content": sys_p},
            {"role": "user", "content": user_p},
        ]
        res = await route_with_backoff(router, messages, tier, log=_correction_retry_log(log))
        processed = re.sub(r"<redacted_thinking>.*?</redacted_thinking>", "", res or "", flags=re.DOTALL)
        if not _apply_json_chunk(tgt_segs, processed, log=log):
            res2 = await route_with_backoff(
                router,
                messages
                + [
                    {
                        "role": "user",
                        "content": "JSON 배열만 다시 출력. start/end는 입력과 문자列で完全一致。",
                    }
                ],
                tier,
                log=_correction_retry_log(log),
            )
            processed2 = re.sub(
                r"<redacted_thinking>.*?</redacted_thinking>",
                "",
                res2 or "",
                flags=re.DOTALL,
            )
            if not _apply_json_chunk(tgt_segs, processed2, log=log):
                log(f"[CORRECTION] Pass3 청크 {idx + 1} 실패 — 원문 유지")
        log(f"[CORRECTION] [Pass 3] {idx + 1}/{total} 청크 완료")


async def correct_ja_segments_async(
    segments: List[SimpleSegment],
    *,
    product_code: str = "Unknown",
    router: Any = None,
    llm_tier: Optional[Dict[str, Any]] = None,
    pass1_tier: Optional[Dict[str, Any]] = None,
    pass2_tier: Optional[Dict[str, Any]] = None,
    pass3_tier: Optional[Dict[str, Any]] = None,
    claude_polish: bool = False,
    enable_pass3: Optional[bool] = None,
    speaker_prefix_mode: str = "off",
    logger_func: OptionalLogger = None,
    should_cancel: CancelCheck = None,
) -> List[SimpleSegment]:
    from javstory.config.app_config import (
        KEYRING_ACCOUNT_OPENROUTER,
        KEYRING_SERVICE_NAME,
        correction_llm_tier,
    )
    from javstory.llm.engine import MultiTierRouter, ollama_ensure_model, ollama_unload_model
    from javstory.harvest.database import JAVMetadata, get_db_session_ctx

    log = logger_func or print

    if enable_pass3 is None:
        enable_pass3 = os.environ.get("JAVSTORY_CORRECTION_ENABLE_PASS3", "").lower() in (
            "1",
            "true",
            "yes",
        )

    # 오케스트레이터가 보유한 router를 주입받는 것이 기본.
    # 하위 호환: router 미지정이면 여기서 OpenRouter 키를 로드해 생성.
    if router is None:
        import keyring

        api_key = keyring.get_password(KEYRING_SERVICE_NAME, KEYRING_ACCOUNT_OPENROUTER) or ""
        router = MultiTierRouter(api_key=api_key, logger_func=log)

    tier_p1 = pass1_tier or correction_llm_tier(1)
    tier_p3 = pass3_tier or correction_llm_tier(3)
    if claude_polish:
        tier_p2 = tier_p3
        if pass2_tier or llm_tier:
            log(
                "[CORRECTION] claude_polish=True: 주교정만 Claude(Pass3 티어) 사용. "
                "Pass2용 llm_tier/pass2_tier 오버라이드는 적용하지 않습니다."
            )
    else:
        tier_p2 = pass2_tier or llm_tier or correction_llm_tier(2)

    ollama_models_to_unload: List[str] = []

    def _ensure_ollama(tier: Dict[str, Any]) -> None:
        if tier.get("provider") == "ollama":
            ollama_models_to_unload.append(tier["model"])

    async def _maybe_ensure_ollama(tier: Dict[str, Any]) -> None:
        if tier.get("provider") == "ollama":
            await ollama_ensure_model(tier["model"], logger_func=log)

    await _maybe_ensure_ollama(tier_p1)
    await _maybe_ensure_ollama(tier_p2)
    _ensure_ollama(tier_p1)
    _ensure_ollama(tier_p2)

    synopsis = "情報なし"
    title_ja = ""
    try:
        with get_db_session_ctx() as session:
            pc_upper = (product_code or "").strip().upper()
            row = session.query(JAVMetadata).filter_by(product_code=pc_upper).first() if pc_upper else None
            if row:
                synopsis = (row.synopsis_ja or row.synopsis_ko or row.synopsis or "").strip()
                if not synopsis:
                    synopsis = "情報なし"
                title_ja = str(row.title_ja or row.title or row.title_ko or "").strip()
    except Exception as e:
        log(f"[CORRECTION] DB 로드 실패: {e}")

    correction_mode = "normal"
    ref_strong = ""
    ref_weak = ""

    try:
        import gc
        import torch

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        log("[CORRECTION] VRAM 정리 (STT 이후)")
    except Exception:
        pass

    log(f"[CORRECTION] [Pass 1] 컨텍스트 — {tier_p1.get('name')} / {tier_p1.get('model')}")

    MAX_CHARS = 3000
    sample_lines: List[str] = []
    total_chars = 0
    for s in segments:
        line = f"[{s.start:.1f}s] {s.text}"
        if total_chars + len(line) > MAX_CHARS:
            break
        sample_lines.append(line)
        total_chars += len(line)
    raw_subtitles = "\n".join(sample_lines)

    sys_p1 = (
        "あなたはアダルトビデオ専門の字幕校正アシスタントです。\n"
        "与えられたシノプシスと字幕サンプルをもとに、登場人物の関係と口調を分析してください。\n"
        "結果は必ずJSON形式のみで出力してください。"
    )
    user_p1 = (
        f"## シノプシス\n{synopsis}\n\n"
        f"## 字幕サンプル\n{raw_subtitles}\n\n"
        "## 出力フォーマット\n"
        '{"characters": [{"name": "名前", "kana": "よみがな", "role": "役割"}], '
        '"proper_nouns": ["固有名詞"], '
        '"story_summary": "概要200字以内"}'
    )

    context_json: Dict[str, Any] = {}
    try:
        messages_p1 = [
            {"role": "system", "content": sys_p1},
            {"role": "user", "content": user_p1},
        ]
        raw_res = await route_with_backoff(
            router, messages_p1, tier_p1, log=_correction_retry_log(log)
        )
        if raw_res:
            processed = re.sub(
                r"<redacted_thinking>.*?</redacted_thinking>",
                "",
                raw_res,
                flags=re.DOTALL,
            ).strip()
            obj = parse_json_object(processed)
            if obj:
                context_json = obj
            else:
                m = re.search(r"(\{.*\})", processed, re.DOTALL)
                if m:
                    try:
                        context_json = json.loads(m.group(1))
                    except json.JSONDecodeError:
                        pass
            log("[CORRECTION] [Pass 1] 완료")
    except Exception as e:
        log(f"[CORRECTION] Pass 1 실패: {e}")

    # MiniMax 전용 안정화(환경변수 JAVSTORY_MINIMAX_*): ref/ctx는 Pass1 이후에만 적용한다.
    ref_strong_p2 = ref_strong
    ref_weak_p2 = ref_weak
    ctx_str_p2 = json.dumps(context_json, ensure_ascii=False)
    if (not claude_polish) and _is_minimax_tier(tier_p2):
        ref_strong_p2 = _truncate_chars(
            ref_strong or "",
            int(os.environ.get("JAVSTORY_MINIMAX_REF_STRONG_MAXCHARS", "1200")),
        )
        ref_weak_p2 = _truncate_chars(
            ref_weak or "",
            int(os.environ.get("JAVSTORY_MINIMAX_REF_WEAK_MAXCHARS", "600")),
        )
        ctx_str_p2 = _truncate_chars(
            ctx_str_p2,
            int(os.environ.get("JAVSTORY_MINIMAX_CTX_JSON_MAXCHARS", "1200")),
        )
        try:
            max_tokens = int(os.environ.get("JAVSTORY_MINIMAX_MAX_TOKENS", "2500"))
        except Exception:
            max_tokens = 2500
        tier_p2 = {
            **tier_p2,
            "temperature": float(os.environ.get("JAVSTORY_MINIMAX_TEMPERATURE", "0.3")),
            "max_tokens": max_tokens,
        }
    elif (not claude_polish) and _is_glm_tier(tier_p2):
        ref_strong_p2 = _truncate_chars(
            ref_strong or "",
            int(os.environ.get("JAVSTORY_GLM_REF_STRONG_MAXCHARS", "2200")),
        )
        ref_weak_p2 = _truncate_chars(
            ref_weak or "",
            int(os.environ.get("JAVSTORY_GLM_REF_WEAK_MAXCHARS", "900")),
        )
        ctx_str_p2 = _truncate_chars(
            ctx_str_p2,
            int(os.environ.get("JAVSTORY_GLM_CTX_JSON_MAXCHARS", "1800")),
        )
        try:
            glm_max_tok = int(os.environ.get("JAVSTORY_GLM_MAX_TOKENS", "8192"))
        except ValueError:
            glm_max_tok = 8192
        tier_p2 = {
            **tier_p2,
            "temperature": float(os.environ.get("JAVSTORY_GLM_TEMPERATURE", "0.3")),
            "max_tokens": max(1024, glm_max_tok),
        }

    target_dur, overlap_dur = _effective_chunk_durations(tier_p2)
    p2_conc = _correction_concurrency("pass2", _default_pass2_concurrency(tier_p2))
    p2_label = "Pass 2 (Claude 단독, 플랜 Pass2 생략)" if claude_polish else "Pass 2"
    log(
        f"[CORRECTION] [{p2_label}] 시작 — {tier_p2.get('name')} / {tier_p2.get('model')} "
        f"(청크≈{target_dur:.0f}s, 동시요청≤{p2_conc})"
    )

    chunks_data: List[dict] = []
    if segments:
        current_time = 0.0
        video_end = segments[-1].end
        while current_time < video_end:
            chunks_data.append(
                {
                    "context": [
                        s for s in segments if (current_time - overlap_dur) <= s.start < current_time
                    ],
                    "target": [
                        s for s in segments if current_time <= s.start < (current_time + target_dur)
                    ],
                }
            )
            current_time += target_dur

    semaphore_p2 = asyncio.Semaphore(p2_conc)
    total_chunks = len(chunks_data)
    speaker_rule = _speaker_rule_text(speaker_prefix_mode)

    async def _pass2_one(i: int, c: dict) -> None:
        await _run_pass2_chunk(
            idx=i,
            total=total_chunks,
            chunk=c,
            tier=tier_p2,
            correction_mode=correction_mode,
            ref_strong=ref_strong_p2,
            ref_weak=ref_weak_p2,
            speaker_rule=speaker_rule,
            ctx_str=ctx_str_p2,
            router=router,
            log=log,
            should_cancel=should_cancel,
            semaphore=semaphore_p2,
        )

    await asyncio.gather(*[_pass2_one(i, c) for i, c in enumerate(chunks_data)])

    if enable_pass3 and not claude_polish:
        await _maybe_ensure_ollama(tier_p3)
        _ensure_ollama(tier_p3)
        p3_conc = _correction_concurrency("pass3", 1)
        semaphore_p3 = asyncio.Semaphore(p3_conc)
        log(
            f"[CORRECTION] [Pass 3] 시작 — {tier_p3.get('name')} / {tier_p3.get('model')} "
            f"(플랜 Step3 · 동시요청≤{p3_conc})"
        )

        async def _pass3_one(i: int, c: dict) -> None:
            await _run_pass3_chunk(
                idx=i,
                total=total_chunks,
                chunk=c,
                tier=tier_p3,
                correction_mode=correction_mode,
                ref_strong=ref_strong_p2,
                ref_weak=ref_weak_p2,
                speaker_rule=speaker_rule,
                ctx_str=ctx_str_p2,
                router=router,
                log=log,
                should_cancel=should_cancel,
                semaphore=semaphore_p3,
            )

        await asyncio.gather(*[_pass3_one(i, c) for i, c in enumerate(chunks_data)])

    for model_name in dict.fromkeys(ollama_models_to_unload):
        await ollama_unload_model(model_name, logger_func=log)

    return segments


def correct_ja_segments_sync(
    segments: List[SimpleSegment],
    **kwargs: Any,
) -> List[SimpleSegment]:
    from javstory.utils.async_utils import run_coroutine_sync

    return run_coroutine_sync(correct_ja_segments_async(segments, **kwargs))
