"""
한국어 자막 청크 번역 (JA cue JSON → KO text, 타임코드 불변).

구현 완료 항목:
- `resolve_translation_llm_tier` — 프로필·OpenRouter/Ollama (`core.app_config` 참고)
- 교정 파이프라인과 동일한 시간 청크·JSON 적용(`correction_chunk._apply_json_chunk`)
- 번역 프롬프트 상수·함수 인라인 (system_prompt_translation_chunk, render_glm_translation_chunk_user 등)
- Ollama: ensure / unload, 동시성 1 기본

환경: `JAVSTORY_TRANSLATION_PROFILE`(default|keeper|deepseek_chat|budget|qwen35|qwen3_14|gemma3_12|jkv_12b), `JAVSTORY_TRANSLATION_OPENROUTER_MODEL`,
`JAVSTORY_TRANSLATION_PROVIDER`, `JAVSTORY_TRANSLATION_OLLAMA_MODEL`,
`JAVSTORY_TRANSLATION_CHUNK_TARGET_SEC` / `_OVERLAP_SEC` (미설정 시 `JAVSTORY_CORRECTION_CHUNK_*` → 티어 기본: DeepSeek V3.2 18s/5s, DeepSeek Chat 16s/4s, GLM-5.1 14s/4s, Ollama는 `correction_chunk._ollama_chunk_params_by_model` 과 동일 — Qwen3:14B 18/5, Qwen3.5:9B 16/4.5, Qwen3:8B 15/4, Qwen2.5:14B 17/4.5, Gemma3:12B 16/4.5, Gemma4 16/4, 기타 Ollama 300s/20s, 그 외 OpenRouter 50s/10s),
`JAVSTORY_TRANSLATION_QWEN_MAX_TOKENS`(Qwen만, `JAVSTORY_TRANSLATION_OLLAMA_MAX_TOKENS` 미설정 시 기본 2048),
`JAVSTORY_TRANSLATION_CONCURRENCY`, `JAVSTORY_LOG_FULL_TRANSLATION_PROMPT`(1/true 시 system+user 전체 로그),
`JAVSTORY_TRANSLATION_QWEN_TEMPERATURE`(Ollama+Qwen 번역 시 온도, 기본 0.22 — 다국어 혼입 완화)
`JAVSTORY_TRANSLATION_OLLAMA_NO_NEUTRAL_FALLBACK`(1/true 시 Ollama+Qwen도 기존 강한 system으로만 재시도; 기본은 JSON 실패 시 완화 system)

스토리 맥락: `story_context_hints` → `[TranslationHints]`에 레퍼런스 힌트와 합쳐 전달 (`subtitle_pipeline_orchestrator`가 자동 주입).
"""
from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional

from javstory.translation.correction_chunk import (
    _apply_json_chunk,
    _chunk_json_for_segments,
    _ollama_chunk_params_by_model,
)
from javstory.translation.llm_backoff import route_with_backoff
from javstory.translation.story_context_prompts import resolve_grok_scene_for_chunk
from javstory.transcription.stt_types import STTCancelled, SimpleSegment

CancelCheck = Optional[Callable[[], bool]]
OptionalLogger = Optional[Callable[[str], None]]

# ── 번역 프롬프트 상수·함수 (구 background_prompts.py에서 인라인) ──

RETRY_TRANSLATION_PROMPT = (
    "前回の応答はJSONとしてパースできませんでした。"
    "もう一度、必ず `[{\"index\":…, \"text\":\"…\"}, …]` の形式のみで出力してください。"
    "JSON以外のテキストは含めないでください。"
)
RETRY_TRANSLATION_PROMPT_STRICT = (
    "前回もJSONパースに失敗しました。次のルールを厳守してください:\n"
    "1) 出力は `[` で始まり `]` で終わること\n"
    "2) 各要素は `{\"index\": 数字, \"text\": \"韓国語テキスト\"}` のみ\n"
    "3) JSON以外(説明・前置き・注釈)は一切含めないこと"
)
RETRY_TRANSLATION_GEMMA_APPEND = (
    "\n\n[Gemma追加指示] 出力はJSONのみ。挨拶・説明・マークダウン不要。"
    " `[{\"index\":0,\"text\":\"...\"},...]` だけ出力。"
)
RETRY_TRANSLATION_KO_MIX_APPEND = (
    "\n\n[重要] text値は100%韓国語のみ。"
    "日本語・英語・中国語が混入した場合は自然な韓国語に直してください。"
)


def system_prompt_translation_chunk(tier: Dict[str, Any]) -> str:
    prov = str(tier.get("provider") or "").lower()
    model = str(tier.get("model") or "").lower()
    base = (
        "あなたは日本語→韓国語の字幕翻訳の専門家です。\n"
        "入力はJSON配列 `[{\"index\":N, \"text\":\"日本語セリフ\"}, ...]` です。\n"
        "各要素の `text` を自然で流暢な韓国語に翻訳し、同じJSON配列形式で出力してください。\n"
        "index値は変更しないでください。JSON以外のテキストは含めないでください。\n"
        "翻訳時のルール:\n"
        "- 口語的・会話的な韓国語を使うこと(字幕なので文語体は不可)\n"
        "- 敬語/半語は文脈と話者の関係に合わせること\n"
        "- 感嘆詞・擬音語は韓国語の自然な等価表現に変換\n"
        "- text値は100%韓国語のみ(日本語・英語混入禁止)\n"
    )
    if prov == "ollama" and "gemma" in model:
        base += (
            "\n[Gemma専用] 出力はJSONのみ。挨拶・説明・マークダウン不要。"
            " `[{\"index\":0,\"text\":\"...\"},...]` だけ出力。\n"
        )
    return base


def system_prompt_translation_ollama_qwen_neutral() -> str:
    return (
        "You are a professional subtitle translator (Japanese→Korean).\n"
        "Input: JSON array `[{\"index\":N,\"text\":\"JA line\"}, ...]`\n"
        "Output: same JSON array with `text` replaced by natural Korean.\n"
        "Rules:\n"
        "- Output ONLY the JSON array, nothing else\n"
        "- Keep index values unchanged\n"
        "- Translate all text to 100% Korean (no Japanese/English)\n"
        "- Use colloquial Korean suitable for subtitles\n"
    )


def render_glm_translation_chunk_user(
    background_json_str: str,
    chunk_json: str,
    chunk_idx: int,
    scene_id: str,
    scene_tone: str,
    extra_hints: str,
    *,
    compact_translation_hints: bool = False,
) -> str:
    parts: List[str] = []
    parts.append(f"[作品背景]\n{background_json_str}")
    if scene_id:
        parts.append(f"[シーン] id={scene_id} tone={scene_tone}")
    if extra_hints and extra_hints.strip():
        if compact_translation_hints:
            parts.append("[TranslationHints]\n(チャンク0のヒントと同一 — 省略)")
        else:
            parts.append(f"[TranslationHints]\n{extra_hints.strip()}")
    parts.append(f"[出力 言語] 韓国語のみ (100% Korean)")
    parts.append(f"[翻訳対象 JSON]\n{chunk_json}")
    return "\n\n".join(parts)


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _looks_like_model_refusal(text: str) -> bool:
    """로컬 모델이 정책 거절·사과만 할 때(유효 JSON 없음)."""
    if not text or not str(text).strip():
        return False
    s = str(text).strip()
    if s.startswith("[") and '"index"' in s[:1200]:
        return False
    head = s[:4000]
    kl = head.lower()
    if any(
        x in head
        for x in (
            "죄송하지만",
            "수행할 수 없",
            "지원하지 않습니다",
            "도와드릴 수 없",
            "성적으로 명시",
            "성인 콘텐츠",
        )
    ):
        return True
    return any(
        x in kl
        for x in (
            "i'm sorry",
            "i cannot",
            "i can't assist",
            "cannot fulfill",
            "unable to comply",
            "can't help with",
            "explicit sexual",
            "adult content",
        )
    )


def _merge_translation_hints(story_hints: Optional[str], ref_hints: str) -> str:
    parts: List[str] = []
    if story_hints and str(story_hints).strip():
        parts.append(
            "[스토리 맥락 리포트 · Grok 웹 전용]\n"
            "(품번 검증·공개 웹 메타: 상황·말투·인물·호칭·번역 가이드; 자막 본문 미사용)\n"
            f"{str(story_hints).strip()}"
        )
    if ref_hints.strip():
        parts.append(f"[레퍼런스 힌트]\n{ref_hints.strip()}")
    return "\n\n".join(parts)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _is_glm_tier(tier: Dict[str, Any]) -> bool:
    return "glm" in ((tier.get("model") or "").lower())


def _use_compact_translation_hints(chunk_idx: int) -> bool:
    """ChunkIndex>0에서 긴 Grok 힌트 반복을 생략(토큰·컨텍스트 절약). 전 구간 풀 힌트는 env로 복구."""
    if chunk_idx <= 0:
        return False
    if os.environ.get("JAVSTORY_TRANSLATION_REPEAT_FULL_HINTS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False
    return True


def _default_chunk_durations(tier: Dict[str, Any]) -> tuple[float, float]:
    model_l = (tier.get("model") or "").lower()
    if tier.get("provider") == "ollama":
        return _ollama_chunk_params_by_model(model_l)
    if "minimax" in model_l:
        return 30.0, 6.0
    if _is_glm_tier(tier):
        return 14.0, 4.0
    if "deepseek" in model_l and ("v3.2" in model_l or "deepseek-v3.2" in model_l):
        return 18.0, 5.0
    if "deepseek" in model_l:
        return 16.0, 4.0
    return 50.0, 10.0


def _effective_translation_chunk_durations(tier: Dict[str, Any]) -> tuple[float, float]:
    target_dur, overlap_dur = _default_chunk_durations(tier)
    # 번역 전용 → 없으면 교정과 동일 env 폴백
    if os.environ.get("JAVSTORY_TRANSLATION_CHUNK_TARGET_SEC"):
        target_dur = max(5.0, _env_float("JAVSTORY_TRANSLATION_CHUNK_TARGET_SEC", target_dur))
    elif os.environ.get("JAVSTORY_CORRECTION_CHUNK_TARGET_SEC"):
        target_dur = max(5.0, _env_float("JAVSTORY_CORRECTION_CHUNK_TARGET_SEC", target_dur))
    if os.environ.get("JAVSTORY_TRANSLATION_CHUNK_OVERLAP_SEC"):
        overlap_dur = max(0.0, _env_float("JAVSTORY_TRANSLATION_CHUNK_OVERLAP_SEC", overlap_dur))
    elif os.environ.get("JAVSTORY_CORRECTION_CHUNK_OVERLAP_SEC"):
        overlap_dur = max(0.0, _env_float("JAVSTORY_CORRECTION_CHUNK_OVERLAP_SEC", overlap_dur))
    return target_dur, overlap_dur


def _translation_concurrency(tier: Dict[str, Any]) -> int:
    raw = os.environ.get("JAVSTORY_TRANSLATION_CONCURRENCY", "").strip()
    if raw:
        try:
            return max(1, min(int(raw), 8))
        except ValueError:
            pass
    if tier.get("provider") == "ollama":
        return 1
    if tier.get("provider") == "openrouter":
        return 3 if _is_glm_tier(tier) else 2
    return 1


def _build_chunks(segments: List[SimpleSegment], target_dur: float, overlap_dur: float) -> List[dict]:
    chunks_data: List[dict] = []
    if not segments:
        return chunks_data
    current_time = 0.0
    video_end = segments[-1].end
    while current_time < video_end:
        tgt = [s for s in segments if current_time <= s.start < (current_time + target_dur)]
        if tgt:
            chunks_data.append(
                {
                    "context": [
                        s for s in segments if (current_time - overlap_dur) <= s.start < current_time
                    ],
                    "target": tgt,
                }
            )
        current_time += target_dur
    return chunks_data


def _translation_retry_log(logger: Callable[[str], None]) -> Callable[[str], None]:
    return lambda m: logger(f"[KO-TRANSLATE] {m}")


def _retry_translation_user_content(tier: Dict[str, Any], *, attempt: int) -> str:
    """attempt 1=첫 재시도, 2=2차 재시도. Gemma는 JSON 강조, 전 티어에 한국어 단일 출력 재확인."""
    prov = str(tier.get("provider") or "").lower()
    model = str(tier.get("model") or "").lower()
    gemma_extra = prov == "ollama" and "gemma" in model
    tail = RETRY_TRANSLATION_KO_MIX_APPEND
    if attempt == 1:
        base = RETRY_TRANSLATION_PROMPT
        return base + (RETRY_TRANSLATION_GEMMA_APPEND if gemma_extra else "") + tail
    base = RETRY_TRANSLATION_PROMPT_STRICT
    return base + (RETRY_TRANSLATION_GEMMA_APPEND if gemma_extra else "") + tail


def _want_full_translation_prompt_log(explicit: Optional[bool]) -> bool:
    if explicit is True:
        return True
    if explicit is False:
        return False
    return os.environ.get("JAVSTORY_LOG_FULL_TRANSLATION_PROMPT", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _compact_translation_user_content_for_log(content: str, *, chunk_idx: int) -> str:
    """
    `JAVSTORY_LOG_FULL_TRANSLATION_PROMPT` 덤프 시 `[TranslationHints]`(Grok 스토리 힌트 전체)가
    청크마다 반복되어 로그가 폭증하는 것을 막는다. 청크 1에서만 전체를 남긴다.
    """
    if chunk_idx <= 0:
        return content
    m = re.search(r"\n\n\[TranslationHints\]\n[\s\S]*?(?=\n\n\[출력 언어\])", content)
    if not m:
        return content
    omitted = len(m.group(0))
    return (
        content[: m.start()]
        + "\n\n[TranslationHints]\n"
        + f"(청크 1 로그와 동일 — 생략, 약 {omitted}자)\n"
        + content[m.end() :]
    )


def _log_full_glm_prompt(
    log: Callable[[str], None],
    *,
    chunk_idx: int,
    total_chunks: int,
    messages: List[Dict[str, str]],
    label: str = "",
) -> None:
    sep = "=" * 72
    extra = f" {label}" if label else ""
    log(sep)
    log(f"[KO-TRANSLATE] 번역 LLM 전체 프롬프트{extra} — 현재 {chunk_idx + 1} / {total_chunks}")
    for m in messages:
        role = (m.get("role") or "").upper()
        body = m.get("content", "") or ""
        if role == "USER":
            body = _compact_translation_user_content_for_log(body, chunk_idx=chunk_idx)
        log(f"[{role}]\n{body}")
    log(sep)


async def translate_ja_segments_to_ko_async(
    segments: List[SimpleSegment],
    *,
    product_code: str,
    router: Any,
    background_json_str: str,
    translation_tier: Optional[Dict[str, Any]] = None,
    translation_provider: Optional[str] = None,
    story_context_hints: Optional[str] = None,
    story_context_grok_json: Optional[Dict[str, Any]] = None,
    logger_func: OptionalLogger = None,
    should_cancel: CancelCheck = None,
    log_full_translation_prompt: Optional[bool] = None,
) -> List[SimpleSegment]:
    """
    일본어 세그먼트 리스트를 한국어로 번역한다. 세그먼트 객체가 제자리에서 갱신된다.
    `story_context_grok_json`: Grok 캐시 JSON(dict) — 청크 시각에 맞춰 scene_id/tone 주입.
    """
    from javstory.config.app_config import resolve_translation_llm_tier
    from javstory.llm.ollama_ko_vram import after_ko_translate_work, before_ko_translate_work

    log = logger_func or print
    log_full_prompt = _want_full_translation_prompt_log(log_full_translation_prompt)
    if not segments:
        log("[KO-TRANSLATE] 세그먼트 없음 — 스킵")
        return segments

    tier = resolve_translation_llm_tier(
        translation_provider=translation_provider,
        translation_tier=translation_tier,
    )
    if str(tier.get("provider") or "").lower() == "ollama" and "qwen" in (tier.get("model") or "").lower():
        qt = os.environ.get("JAVSTORY_TRANSLATION_QWEN_TEMPERATURE", "0.22").strip()
        try:
            tier = {**tier, "temperature": float(qt)}
        except ValueError:
            tier = {**tier, "temperature": 0.22}
        if not (os.environ.get("JAVSTORY_TRANSLATION_OLLAMA_MAX_TOKENS", "") or "").strip():
            qmt = (os.environ.get("JAVSTORY_TRANSLATION_QWEN_MAX_TOKENS", "") or "").strip() or "2048"
            try:
                tier = {**tier, "max_tokens": max(512, int(qmt))}
            except ValueError:
                tier = {**tier, "max_tokens": 2048}

    extra_hints = _merge_translation_hints(story_context_hints, "")

    if tier.get("provider") == "ollama":
        await before_ko_translate_work(tier["model"], logger_func=log)

    target_dur, overlap_dur = _effective_translation_chunk_durations(tier)
    chunks_data = _build_chunks(segments, target_dur, overlap_dur)
    conc = _translation_concurrency(tier)
    semaphore = asyncio.Semaphore(conc)
    total_chunks = len(chunks_data)
    grok_data = story_context_grok_json if isinstance(story_context_grok_json, dict) else None
    video_end_sec = segments[-1].end if segments else 0.0
    log(
        f"[KO-TRANSLATE] 시작 — {tier.get('name')} / {tier.get('model')} "
        f"(청크≈{target_dur:.0f}s, 겹침≈{overlap_dur:.0f}s, 동시≤{conc}, 총 청크 {total_chunks})"
    )
    if tier.get("provider") == "ollama" and "qwen" in (tier.get("model") or "").lower():
        log(
            "[KO-TRANSLATE] 로컬 Qwen(Ollama)은 GPU·모델 크기에 따라 청크당 매우 느릴 수 있습니다. "
            "실사용 속도가 필요하면 OpenRouter 프로필(default/keeper 등) 권장. "
            "로컬 유지 시: VRAM 여유면 JAVSTORY_TRANSLATION_CONCURRENCY=2, "
            "여전히 느리면 JAVSTORY_TRANSLATION_QWEN_MAX_TOKENS=1536 등으로 추가 하향."
        )

    async def _one(idx: int, chunk: dict) -> None:
        async with semaphore:
            if should_cancel and should_cancel():
                raise STTCancelled()
            tgt_segs: List[SimpleSegment] = chunk["target"]
            if not tgt_segs:
                return
            chunk_json = _chunk_json_for_segments(tgt_segs)
            anchor_sec = (tgt_segs[0].start + tgt_segs[-1].end) / 2.0 if tgt_segs else 0.0
            scene_id, scene_tone = resolve_grok_scene_for_chunk(
                anchor_sec,
                grok_data,
                video_end_sec=video_end_sec,
            )
            user_p = render_glm_translation_chunk_user(
                background_json_str,
                chunk_json,
                idx,
                scene_id,
                scene_tone,
                extra_hints,
                compact_translation_hints=_use_compact_translation_hints(idx),
            )
            messages: List[dict[str, str]] = [
                {"role": "system", "content": system_prompt_translation_chunk(tier)},
                {"role": "user", "content": user_p},
            ]
            if log_full_prompt:
                _log_full_glm_prompt(log, chunk_idx=idx, total_chunks=total_chunks, messages=messages)
            t_req = time.monotonic()
            log(
                f"[KO-TRANSLATE] 청크 {idx + 1}/{total_chunks} LLM 대기 중… "
                f"~{tgt_segs[0].start:.1f}–{tgt_segs[-1].end:.1f}s"
            )
            res = await route_with_backoff(
                router, messages, tier, log=_translation_retry_log(log)
            )
            log(
                f"[KO-TRANSLATE] 청크 {idx + 1}/{total_chunks} 응답 수신 "
                f"({time.monotonic() - t_req:.1f}s)"
            )
            processed = re.sub(r"<redacted_thinking>.*?</redacted_thinking>", "", res or "", flags=re.DOTALL)
            if log_full_prompt:
                pr = processed or ""
                plen = len(pr)
                log(f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — 모델 응답 길이: {plen}자")
                cap = 12000
                if plen <= cap:
                    log(f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — 응답 본문:\n{pr}")
                else:
                    log(
                        f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — 응답 앞 {cap//2}자:\n{pr[: cap // 2]}\n"
                        f"... [{plen - cap}자 생략] ...\n"
                        f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — 응답 뒤 {cap//2}자:\n{pr[-(cap // 2) :]}"
                    )
            lp = "[KO-TRANSLATE]"
            if not _apply_json_chunk(tgt_segs, processed, log=log, log_prefix=lp):
                log(f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — JSON 적용 실패 — 재시도")
                use_neutral_ollama_qwen = (
                    str(tier.get("provider") or "").lower() == "ollama"
                    and "qwen" in (tier.get("model") or "").lower()
                    and not _env_truthy("JAVSTORY_TRANSLATION_OLLAMA_NO_NEUTRAL_FALLBACK")
                )
                if use_neutral_ollama_qwen:
                    log(
                        "[KO-TRANSLATE] Ollama+Qwen: JSON 실패 — 완화 system(JSON 전용)으로 재시도"
                        + (" (거절 문구 감지)" if _looks_like_model_refusal(processed) else "")
                    )
                    base_for_retry: List[dict[str, str]] = [
                        {
                            "role": "system",
                            "content": system_prompt_translation_ollama_qwen_neutral(),
                        },
                        {"role": "user", "content": user_p},
                    ]
                else:
                    base_for_retry = messages

                retry_messages = base_for_retry + [
                    {"role": "user", "content": _retry_translation_user_content(tier, attempt=1)}
                ]
                if log_full_prompt:
                    _log_full_glm_prompt(
                        log,
                        chunk_idx=idx,
                        total_chunks=total_chunks,
                        messages=retry_messages,
                        label="(재시도)",
                    )
                res2 = await route_with_backoff(
                    router, retry_messages, tier, log=_translation_retry_log(log)
                )
                processed2 = re.sub(
                    r"<redacted_thinking>.*?</redacted_thinking>",
                    "",
                    res2 or "",
                    flags=re.DOTALL,
                )
                if log_full_prompt:
                    p2 = processed2 or ""
                    log(f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — 재시도 응답 길이: {len(p2)}자")
                    log(
                        f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — 재시도 응답 본문:\n"
                        f"{p2[:12000]}{'…' if len(p2) > 12000 else ''}"
                    )
                if not _apply_json_chunk(tgt_segs, processed2, log=log, log_prefix=lp):
                    log(f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — JSON 적용 실패 — 2차 재시도")
                    retry2 = base_for_retry + [
                        {"role": "user", "content": _retry_translation_user_content(tier, attempt=1)},
                        {"role": "user", "content": _retry_translation_user_content(tier, attempt=2)},
                    ]
                    res3 = await route_with_backoff(
                        router, retry2, tier, log=_translation_retry_log(log)
                    )
                    processed3 = re.sub(
                        r"<redacted_thinking>.*?</redacted_thinking>",
                        "",
                        res3 or "",
                        flags=re.DOTALL,
                    )
                    if log_full_prompt:
                        p3 = processed3 or ""
                        log(
                            f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — 2차 재시도 응답 길이: {len(p3)}자"
                        )
                        log(
                            f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — 2차 재시도 응답 본문:\n"
                            f"{p3[:12000]}{'…' if len(p3) > 12000 else ''}"
                        )
                    if not _apply_json_chunk(tgt_segs, processed3, log=log, log_prefix=lp):
                        log(
                            f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — 최종 실패 — 해당 구간 일본어 유지"
                        )
            log(f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — 완료")

    try:
        await asyncio.gather(*[_one(i, c) for i, c in enumerate(chunks_data)])
    finally:
        if tier.get("provider") == "ollama":
            await after_ko_translate_work(tier["model"], logger_func=log)

    return segments
