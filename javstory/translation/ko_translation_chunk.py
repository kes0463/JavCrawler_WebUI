"""
한국어 자막 청크 번역 (JA cue JSON → KO text, 타임코드 불변).

구현 완료 항목:
- `resolve_translation_llm_tier` — 프로필·OpenRouter/Ollama (`core.app_config` 참고)
- 교정 파이프라인과 동일한 시간 청크·JSON 적용(`correction_chunk._apply_json_chunk`)
- 번역 프롬프트 상수·함수 인라인 (system_prompt_translation_chunk, render_glm_translation_chunk_user 등)
- Ollama: ensure / unload, 동시성 1 기본

환경: `JAVSTORY_TRANSLATION_PROFILE`(default|keeper|deepseek_chat|budget|qwen35|qwen3_14|gemma3_12|jkv_12b), `JAVSTORY_TRANSLATION_OPENROUTER_MODEL`,
`JAVSTORY_TRANSLATION_PROVIDER`, `JAVSTORY_TRANSLATION_OLLAMA_MODEL`,
`JAVSTORY_TRANSLATION_CHUNK_TARGET_SEC` / `_OVERLAP_SEC` (미설정 시 `JAVSTORY_CORRECTION_CHUNK_*` → 티어 기본: DeepSeek V3.2 18s/5s, DeepSeek Chat 16s/4s, GLM-5.1 14s/4s, Ollama는 `correction_chunk._ollama_chunk_params_by_model` 과 동일 — Qwen3:14B 18/5, Qwen3.5:9B 16/4.5, Qwen3:8B 15/4, Qwen2.5:14B 17/4.5, Gemma3:12B 16/4.5, Gemma4 16/4, llama.cpp Qwen ~10s/3s · Gemma ~12s/3.5s(짧은 n_ctx·fit 대비), 기타 Ollama 300s/20s, 그 외 OpenRouter 50s/10s),
`JAVSTORY_TRANSLATION_QWEN_MAX_TOKENS`(Qwen만, `JAVSTORY_TRANSLATION_OLLAMA_MAX_TOKENS` 미설정 시 Ollama 기본 2048 / llama.cpp 기본 768),
`JAVSTORY_TRANSLATION_LOCAL_HINT_MAX_CHARS`(로컬 스토리 힌트 상한, 기본 900),
`JAVSTORY_TRANSLATION_CONCURRENCY`, `JAVSTORY_LOG_FULL_TRANSLATION_PROMPT`(1/true 시 청크마다 system+user 전체 로그),
`JAVSTORY_LOG_TRANSLATION_START_DETAILS`(1/true 시 번역 시작 직후 시스템 프롬프트·번역 노트(전역/배우/작품/결합)·스토리 힌트 요약 로그),
`JAVSTORY_SUBTITLE_COLLAPSE_VOCAL_REPEAT`(0/false 시 번역 직후 동일 한글 반복 압축 비활성; 기본 1),
`JAVSTORY_TRANSLATION_QWEN_TEMPERATURE`(Ollama+Qwen 번역 시 온도, 기본 0.22 — 다국어 혼입 완화)
`JAVSTORY_TRANSLATION_OLLAMA_NO_NEUTRAL_FALLBACK`(1/true 시 Ollama+Qwen도 기존 강한 system으로만 재시도; 기본은 JSON 실패 시 완화 system)

스토리 맥락: `story_context_hints` → `[TranslationHints]`에 레퍼런스 힌트와 합쳐 전달 (`subtitle_pipeline_orchestrator`가 자동 주입).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from javstory.translation.correction_chunk import (
    _apply_json_chunk,
    _ollama_chunk_params_by_model,
    collapse_repeated_vocal_sounds,
)
from javstory.translation.translation_prompt_config import (
    build_translation_system_prompt,
    prompt_mode_from_env,
    prompt_variant_from_env,
    uses_html_translation_prompt,
)
from javstory.translation.llm_backoff import route_with_backoff
from javstory.transcription.stt_types import STTCancelled, SimpleSegment
from javstory.translation.story_context_prompts import resolve_grok_scene_for_chunk

CancelCheck = Optional[Callable[[], bool]]
ContentLineFn = Optional[Callable[[dict[str, object]], None]]
OptionalLogger = Optional[Callable[[str], None]]
_CACHE_SCHEMA_VERSION = 2
_CACHE_PROMPT_VERSION = "ko_translation_chunk_cache_v5"

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
RETRY_TRANSLATION_PROMPT_EN = (
    "Previous reply was not valid JSON. Output ONLY "
    '[{\"index\":0,\"text\":\"...\"}, ...] with every index present. '
    "No markdown, no explanation, no thinking."
)
RETRY_TRANSLATION_PROMPT_STRICT_EN = (
    "JSON parse failed again. Strict rules:\n"
    "1) Start with [ and end with ]\n"
    "2) Each item is {\"index\": number, \"text\": \"Korean Hangul only\"}\n"
    "3) Include EVERY index from the source JSON — incomplete arrays fail\n"
    "4) Do not copy Japanese kana/kanji into text\n"
    "5) No prose outside the JSON array"
)
RETRY_TRANSLATION_GEMMA_APPEND = (
    "\n\n[Gemma] JSON array only. No greeting/explanation/markdown. "
    "Translate into Korean Hangul; never echo Japanese source text."
)
RETRY_TRANSLATION_KO_MIX_APPEND = (
    "\n\n[重要] text値は100%韓国語のみ。"
    "日本語・英語・中国語が混入した場合は自然な韓国語に直してください。"
)
RETRY_TRANSLATION_KO_MIX_APPEND_EN = (
    "\n\n[IMPORTANT] Every text value must be 100% Korean Hangul. "
    "Rewrite any Japanese/English/Chinese leakage into natural Korean."
)
RETRY_TRANSLATION_KO_PURE_APPEND = (
    "\n\n[중요] 번역문은 100% 한글만 사용하세요. "
    "영어·로마자·일본어 가나·한자(漢字)를 절대 넣지 마세요. "
    "혼합 표기(예: 바anko, 濡라줘)는 금지입니다."
)
RETRY_TRANSLATION_KO_PURE_APPEND_EN = (
    "\n\n[CRITICAL] Previous texts still contain Japanese or non-Hangul. "
    "Re-output the full JSON array with 100% Korean Hangul only. "
    "No Latin letters, no kana, no kanji, no mixed spellings."
)
_KO_CONTAM_LATIN = re.compile(r"[a-zA-Z]")
_KO_CONTAM_KANA = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff]")
_KO_CONTAM_CJK = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
_KO_CONTAM_THAI = re.compile(r"[\u0e00-\u0e7f]")
_HANGUL_SYLLABLE = re.compile(r"[\uac00-\ud7a3]")
_NON_LEXICAL_LINE = re.compile(r"^[\s.。．…・~～\-—–!！?？♪♡♥❤\*＊]+$")


def has_ko_subtitle_contamination(text: str) -> bool:
    """한글 자막에 로마자·가나·한자·태국어 등 비한글 혼입 여부."""
    t = (text or "").strip()
    if not t:
        return False
    if _KO_CONTAM_LATIN.search(t):
        return True
    if _KO_CONTAM_KANA.search(t):
        return True
    if _KO_CONTAM_CJK.search(t):
        return True
    if _KO_CONTAM_THAI.search(t):
        return True
    return False


def scrub_ja_residue_from_ko_line(text: str) -> str:
    """한글이 있는 줄에서 남은 가나·한자만 제거(Gemma 혼합 출력 보정).

    한글이 전혀 없으면 원문을 유지해 품질 검사가 실패하도록 둔다.
    """
    t = (text or "").strip()
    if not t or not _HANGUL_SYLLABLE.search(t):
        return t
    if not (_KO_CONTAM_KANA.search(t) or _KO_CONTAM_CJK.search(t)):
        return t
    cleaned = _KO_CONTAM_KANA.sub("", t)
    cleaned = _KO_CONTAM_CJK.sub("", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip(" ,，、")
    return cleaned if cleaned and _HANGUL_SYLLABLE.search(cleaned) else t


def postprocess_ko_translation_text(text: str) -> str:
    """번역 text 후처리: 반복 신음 압축 + 일본어 잔여 문자 제거."""
    t = collapse_repeated_vocal_sounds(text)
    return scrub_ja_residue_from_ko_line(t)


def is_acceptable_ko_subtitle_line(text: str, *, source_ja: str | None = None) -> bool:
    """번역 완료로 인정할 한 줄: 비어 있지 않고, 한글이 있으며, 비한글 혼입 없음.

    원문이 기호·점만인 줄은 번역도 동일하게 비어있지 않은 기호 줄이면 허용한다.
    """
    t = (text or "").strip()
    if not t:
        return False
    if source_ja is not None:
        src = (source_ja or "").strip()
        if src and _NON_LEXICAL_LINE.match(src) and _NON_LEXICAL_LINE.match(t):
            return True
    if not _HANGUL_SYLLABLE.search(t):
        return False
    return not has_ko_subtitle_contamination(t)


def segments_translation_quality_ok(
    segs: List[SimpleSegment],
    *,
    source_texts: List[str] | None = None,
) -> bool:
    if not segs:
        return False
    for i, s in enumerate(segs):
        src = source_texts[i] if source_texts is not None and i < len(source_texts) else None
        if not is_acceptable_ko_subtitle_line(s.text or "", source_ja=src):
            return False
    return True


def segments_have_ko_contamination(segs: List[SimpleSegment]) -> bool:
    return any(has_ko_subtitle_contamination(s.text or "") for s in segs)


def _source_texts_from_chunk_json(chunk_json: str, n: int) -> List[str]:
    out = [""] * n
    try:
        data = json.loads(chunk_json)
    except json.JSONDecodeError:
        return out
    if not isinstance(data, list):
        return out
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        if 0 <= idx < n:
            out[idx] = str(item.get("text") or "")
    return out


def _restore_ja_texts_from_chunk_json(tgt_segs: List[SimpleSegment], chunk_json: str) -> None:
    try:
        data = json.loads(chunk_json)
    except json.JSONDecodeError:
        return
    if not isinstance(data, list):
        return
    by_idx: dict[int, str] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            by_idx[int(item.get("index"))] = str(item.get("text") or "")
        except (TypeError, ValueError):
            continue
    for i, seg in enumerate(tgt_segs):
        if i in by_idx:
            seg.text = by_idx[i]


def _is_local_gemma_tier(tier: Dict[str, Any]) -> bool:
    prov = str(tier.get("provider") or "").lower()
    model = str(tier.get("model") or "").lower()
    return prov in ("ollama", "llamacpp") and "gemma" in model


def system_prompt_translation_chunk(tier: Dict[str, Any]) -> str:
    if _is_local_gemma_tier(tier):
        return system_prompt_translation_local_gemma()
    base = (
        "あなたは日本語→韓国語の字幕翻訳の専門家です。\n"
        "入力はJSON配列 `[{\"index\":N, \"text\":\"日本語セリフ\"}, ...]` です。\n"
        "各要素の `text` を自然で流暢な韓国語に翻訳し、同じJSON配列形式で出力してください。\n"
        "index値は変更しないでください。JSON以外のテキストは含めないでください。\n"
        "翻訳時のルール:\n"
        "- 口語的・会話的な韓国語を使うこと(字幕なので文語体は不可)\n"
        "- 敬語/半語は文脈と話者の関係に合わせること\n"
        "- 感嘆詞・擬音語は韓国語の自然な等価表現に変換\n"
        "- 呻き・喘ぎ・意味のない発声: 同じハングル音節の連続は最大2回まで。"
        "長い場合は「…」1つにまとめる(例: 아…)。同一文字を何十回も繰り返して画面幅を埋めないこと\n"
        "- text値は100%韓国語のみ(日本語・英語混入禁止)\n"
    )
    return base


def system_prompt_translation_local_gemma() -> str:
    """Gemma(E4B 등)는 일본어 system보다 짧은 영문 JSON-only 지시가 형식 준수율이 높다."""
    return (
        "You are a Japanese→Korean subtitle translator.\n"
        "Input: JSON array [{\"index\":N,\"text\":\"Japanese line\"}, ...]\n"
        "Output: ONLY the same JSON array with each text translated to natural colloquial Korean.\n"
        "Hard rules:\n"
        "- Start with [ and end with ]. No markdown fences, no explanation, no thinking.\n"
        "- Keep index values unchanged. Do not add start/end fields.\n"
        "- Include EVERY index from the input. Partial arrays are invalid.\n"
        "- text must be 100% Korean Hangul (no Japanese kana/kanji, no English letters).\n"
        "- Never copy the Japanese source into text.\n"
        "- Moans/gasps: at most 2 repeated Hangul syllables, or one syllable + “…”.\n"
    )


def system_prompt_translation_local_gemma_retry() -> str:
    """1차 Gemma system과 구분 — 일본어 에코·부분 JSON을 강하게 금지."""
    return (
        "CRITICAL RETRY — previous output failed validation.\n"
        "Return ONLY a complete JSON array. Translate every line into Korean Hangul.\n"
        "Rules:\n"
        "- [{\"index\":N,\"text\":\"한국어\"}, ...] covering ALL source indices\n"
        "- Do NOT copy Japanese. Do NOT omit indices. Do NOT wrap in markdown.\n"
        "- text = Hangul only (no Latin/kana/kanji)\n"
    )


def system_prompt_translation_ollama_qwen_neutral() -> str:
    return (
        "You are a professional subtitle translator (Japanese→Korean).\n"
        "Input: JSON array `[{\"index\":N,\"text\":\"JA line\"}, ...]`\n"
        "Output: same JSON array with `text` replaced by natural Korean.\n"
        "Rules:\n"
        "- Output ONLY the JSON array, nothing else\n"
        "- Keep index values unchanged\n"
        "- Include every index from the input\n"
        "- Translate all text to 100% Korean (no Japanese/English)\n"
        "- Use colloquial Korean suitable for subtitles\n"
        "- Moans, gasps, non-lexical sounds: at most 2 repeated syllables, or one syllable + “…”; "
        "never fill the line with the same character dozens of times\n"
    )


def _chunk_json_for_translation(segs: List[SimpleSegment]) -> str:
    """번역 입력은 index+text만 — start/end를 넣으면 소형 로컬 모델이 형식을 자주 깨뜨린다."""
    arr = [{"index": i, "text": s.text} for i, s in enumerate(segs)]
    return json.dumps(arr, ensure_ascii=False)


def render_glm_translation_chunk_user(
    background_json_str: str,
    chunk_json: str,
    chunk_idx: int,
    scene_id: str,
    scene_tone: str,
    extra_hints: str,
    *,
    compact_translation_hints: bool = False,
    english_local: bool = False,
) -> str:
    parts: List[str] = []
    if english_local:
        parts.append(f"[Background]\n{background_json_str}")
        if scene_id:
            parts.append(f"[Scene] id={scene_id} tone={scene_tone}")
        if extra_hints and extra_hints.strip():
            if compact_translation_hints:
                parts.append("[TranslationHints]\n(same as chunk 0 — omitted)")
            else:
                parts.append(f"[TranslationHints]\n{extra_hints.strip()}")
        parts.append("[Output language] Korean Hangul only (100%)")
        parts.append(
            "[Output format] JSON array only. "
            'Each item: {"index":N,"text":"한국어"}. No start/end. No markdown/explanation.'
        )
        parts.append(f"[Source JSON]\n{chunk_json}")
        return "\n\n".join(parts)

    parts.append(f"[作品背景]\n{background_json_str}")
    if scene_id:
        parts.append(f"[シーン] id={scene_id} tone={scene_tone}")
    if extra_hints and extra_hints.strip():
        if compact_translation_hints:
            parts.append("[TranslationHints]\n(チャンク0のヒントと同一 — 省略)")
        else:
            parts.append(f"[TranslationHints]\n{extra_hints.strip()}")
    parts.append(f"[出力 言語] 韓国語のみ (100% Korean)")
    parts.append(
        "[出力形式] JSON配列のみ。"
        ' 各要素は {"index":N,"text":"한국어"} 。start/end 禁止。説明・マークダウン禁止。'
    )
    parts.append(f"[翻訳対象 JSON]\n{chunk_json}")
    return "\n\n".join(parts)


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _translation_chunk_cache_enabled() -> bool:
    raw = os.environ.get("JAVSTORY_TRANSLATION_CHUNK_CACHE", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _translation_chunk_cache_dir() -> Path:
    from javstory.config.app_config import DATA_ROOT

    path = DATA_ROOT / "cache" / "subtitle_translation_chunks"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_cache_part(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return text[:80] or "unknown"


def _translation_chunk_cache_path(product_code: str, fingerprint: Dict[str, Any]) -> Path | None:
    if not _translation_chunk_cache_enabled():
        return None
    try:
        raw = json.dumps(fingerprint, ensure_ascii=False, sort_keys=True, default=str)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        pc = _safe_cache_part((product_code or "").strip().upper())
        return _translation_chunk_cache_dir() / f"{pc}_{digest}.json"
    except Exception:
        return None


def _cached_items_from_segments(tgt_segs: List[SimpleSegment]) -> List[Dict[str, Any]]:
    return [
        {
            "index": i,
            "start": round(float(s.start), 3),
            "end": round(float(s.end), 3),
            "text": str(s.text or ""),
        }
        for i, s in enumerate(tgt_segs)
    ]


def _apply_cached_translation(
    tgt_segs: List[SimpleSegment],
    cache_path: Path | None,
    *,
    chunk_json: str,
    log: Callable[[str], None],
    chunk_idx: int,
    total_chunks: int,
) -> bool:
    if cache_path is None or not cache_path.is_file():
        return False
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        if int(payload.get("schema_version") or 0) != _CACHE_SCHEMA_VERSION:
            return False
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            return False
        raw = json.dumps(items, ensure_ascii=False)
        if _apply_json_chunk(
            tgt_segs,
            raw,
            log=log,
            log_prefix="[KO-TRANSLATE CACHE]",
            require_start_end=False,
            require_complete=True,
        ):
            src_texts = _source_texts_from_chunk_json(chunk_json, len(tgt_segs))
            if not segments_translation_quality_ok(tgt_segs, source_texts=src_texts):
                log(
                    f"[KO-TRANSLATE] 캐시 품질 불량(일본어·혼입) — 무시: {cache_path.name}"
                )
                _restore_ja_texts_from_chunk_json(tgt_segs, chunk_json)
                return False
            log(
                f"[KO-TRANSLATE] 현재 {chunk_idx + 1} / {total_chunks} — 캐시 사용 "
                f"({cache_path.name})"
            )
            return True
    except Exception as e:
        log(f"[KO-TRANSLATE] 캐시 로드 실패: {cache_path.name} ({e})")
    return False


def _store_translation_chunk_cache(
    cache_path: Path | None,
    *,
    product_code: str,
    tier: Dict[str, Any],
    chunk_idx: int,
    total_chunks: int,
    tgt_segs: List[SimpleSegment],
    fingerprint: Dict[str, Any],
    log: Callable[[str], None],
) -> None:
    if cache_path is None:
        return
    try:
        payload = {
            "schema_version": _CACHE_SCHEMA_VERSION,
            "product_code": product_code,
            "chunk_idx": chunk_idx,
            "total_chunks": total_chunks,
            "provider": tier.get("provider") or "",
            "model": tier.get("model") or "",
            "fingerprint_sha256": hashlib.sha256(
                json.dumps(fingerprint, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest(),
            "items": _cached_items_from_segments(tgt_segs),
            "created_at": int(time.time()),
        }
        tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=0), encoding="utf-8")
        os.replace(tmp, cache_path)
    except Exception as e:
        log(f"[KO-TRANSLATE] 캐시 저장 실패: {cache_path.name} ({e})")


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


def _local_translation_provider(tier: Dict[str, Any]) -> bool:
    return str(tier.get("provider") or "").lower() in ("ollama", "llamacpp")


def _local_hint_max_chars() -> int:
    raw = (os.environ.get("JAVSTORY_TRANSLATION_LOCAL_HINT_MAX_CHARS", "") or "").strip()
    if raw:
        try:
            return max(200, int(raw))
        except ValueError:
            pass
    return 900


def _clip_text(text: str, max_chars: int) -> str:
    t = text or ""
    if max_chars <= 0 or len(t) <= max_chars:
        return t
    return t[: max(0, max_chars - 1)].rstrip() + "…"


def _compact_background_json_for_local(background_json_str: str) -> str:
    """로컬 n_ctx가 짧을 때 배경 JSON 필드 축약."""
    raw = (background_json_str or "").strip()
    if not raw:
        return raw
    try:
        obj = json.loads(raw)
    except Exception:
        return _clip_text(raw, 600)
    if not isinstance(obj, dict):
        return _clip_text(raw, 600)
    out: Dict[str, Any] = {}
    for key in (
        "product_code",
        "title_ko",
        "title_ja",
        "actors",
        "maker",
        "release_date",
        "genres",
        "synopsis_short",
    ):
        val = obj.get(key)
        if val is None or val == "":
            continue
        s = str(val).strip()
        if not s:
            continue
        if key == "synopsis_short":
            s = _clip_text(s, 180)
        elif key == "genres":
            s = _clip_text(s, 120)
        elif key.startswith("title"):
            s = _clip_text(s, 100)
        out[key] = s
    return json.dumps(out, ensure_ascii=False, sort_keys=True)


def _story_hints_for_tier(
    tier: Dict[str, Any],
    story_context_hints: Optional[str],
    story_context_grok_json: Optional[Dict[str, Any]],
) -> str:
    """로컬 모델은 Grok 씬 본문을 생략한 compact 힌트로 컨텍스트 초과를 막는다."""
    if not _local_translation_provider(tier):
        return _merge_translation_hints(story_context_hints, "")
    hints_body = ""
    if isinstance(story_context_grok_json, dict) and story_context_grok_json:
        from javstory.translation.story_context_prompts import format_story_context_for_translation

        hints_body = format_story_context_for_translation(
            story_context_grok_json,
            compact=True,
            max_chars=_local_hint_max_chars(),
        )
    elif story_context_hints and str(story_context_hints).strip():
        hints_body = _clip_text(str(story_context_hints).strip(), _local_hint_max_chars())
    return _merge_translation_hints(hints_body or None, "")


def _default_chunk_durations(tier: Dict[str, Any]) -> tuple[float, float]:
    model_l = (tier.get("model") or "").lower()
    if tier.get("provider") == "ollama":
        return _ollama_chunk_params_by_model(model_l)
    if tier.get("provider") == "llamacpp":
        # Qwen 14B: fit으로 n_ctx가 줄어들 수 있어 청크를 짧게.
        # Gemma E4B: 상대적으로 가벼워 청크를 키워 왕복·파싱 실패 횟수를 줄인다.
        if "qwen" in model_l:
            return 10.0, 3.0
        if "gemma" in model_l:
            return 12.0, 3.5
        return 14.0, 3.5
    if tier.get("provider") == "gemini":
        try:
            from javstory.config.app_config import gemini_default_chunk_params

            tgt, ov, _ = gemini_default_chunk_params(tier.get("model") or "")
            return float(tgt), float(ov)
        except Exception:
            return 45.0, 10.0
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
    if tier.get("provider") == "llamacpp":
        if os.environ.get("JAVSTORY_TRANSLATION_LLAMACPP_CHUNK_TARGET_SEC"):
            target_dur = max(
                5.0,
                _env_float("JAVSTORY_TRANSLATION_LLAMACPP_CHUNK_TARGET_SEC", target_dur),
            )
        elif os.environ.get("JAVSTORY_CORRECTION_LLAMACPP_CHUNK_TARGET_SEC"):
            target_dur = max(
                5.0,
                _env_float("JAVSTORY_CORRECTION_LLAMACPP_CHUNK_TARGET_SEC", target_dur),
            )
        if os.environ.get("JAVSTORY_TRANSLATION_LLAMACPP_CHUNK_OVERLAP_SEC"):
            overlap_dur = max(
                0.0,
                _env_float("JAVSTORY_TRANSLATION_LLAMACPP_CHUNK_OVERLAP_SEC", overlap_dur),
            )
        elif os.environ.get("JAVSTORY_CORRECTION_LLAMACPP_CHUNK_OVERLAP_SEC"):
            overlap_dur = max(
                0.0,
                _env_float("JAVSTORY_CORRECTION_LLAMACPP_CHUNK_OVERLAP_SEC", overlap_dur),
            )
        return target_dur, overlap_dur
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
    prov = str(tier.get("provider") or "").lower()
    if prov in ("ollama", "llamacpp"):
        # 로컬 모델은 VRAM·순서 안정을 위해 항상 순차 처리
        return 1
    raw = os.environ.get("JAVSTORY_TRANSLATION_CONCURRENCY", "").strip()
    if raw:
        try:
            return max(1, min(int(raw), 8))
        except ValueError:
            pass
    if prov == "gemini":
        try:
            from javstory.config.app_config import gemini_default_chunk_params

            _, _, conc = gemini_default_chunk_params(tier.get("model") or "")
            return max(1, min(int(conc), 8))
        except Exception:
            return 2
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
    """attempt 1=첫 재시도, 2=2차 재시도. Gemma는 영문 JSON 강조(일본어 재시도 문구가 에코를 유발함)."""
    gemma = _is_local_gemma_tier(tier)
    if gemma:
        base = RETRY_TRANSLATION_PROMPT_EN if attempt == 1 else RETRY_TRANSLATION_PROMPT_STRICT_EN
        return base + RETRY_TRANSLATION_GEMMA_APPEND + RETRY_TRANSLATION_KO_MIX_APPEND_EN
    tail = RETRY_TRANSLATION_KO_MIX_APPEND
    if attempt == 1:
        return RETRY_TRANSLATION_PROMPT + tail
    return RETRY_TRANSLATION_PROMPT_STRICT + tail


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


def _want_translation_start_details_log(explicit: Optional[bool]) -> bool:
    if explicit is True:
        return True
    if explicit is False:
        return False
    return os.environ.get("JAVSTORY_LOG_TRANSLATION_START_DETAILS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _log_translation_start_details(
    log: Callable[[str], None],
    *,
    tier: Dict[str, Any],
    background_json_str: str,
    extra_hints: str,
    combined_user_note: str,
    translation_note_global: str,
    translation_note_actress: str,
    translation_note_work: str,
) -> None:
    """번역 첫 청크 전에 시스템 프롬프트와 노트 구성을 한 번 출력."""
    sep = "=" * 72
    prov = str(tier.get("provider") or "").lower()

    def _note_block(title: str, body: str) -> None:
        b = (body or "").strip()
        log(f"[KO-TRANSLATE] ─ {title} ({len(b)}자)" + ("" if b else " — 비어 있음"))
        if b:
            log(b)

    log(sep)
    log(
        f"[KO-TRANSLATE] 번역 시작 상세 — provider={prov or '(기본)'} "
        f"model={tier.get('model') or ''}"
    )
    _note_block("번역 노트 · 전역", translation_note_global)
    _note_block("번역 노트 · 배우", translation_note_actress)
    _note_block("번역 노트 · 작품", translation_note_work)
    _note_block("번역 노트 · 결합(combine_translation_notes)", combined_user_note)
    if (extra_hints or "").strip():
        _note_block("스토리/참조 힌트 → Gemini merged_hints·JSON [TranslationHints]에 포함", extra_hints)
    else:
        log("[KO-TRANSLATE] ─ 스토리/참조 힌트 — 비어 있음")

    if uses_html_translation_prompt(tier):
        from javstory.translation import gemini_prompts

        merged_hints = "\n\n".join(
            [s for s in (extra_hints, combined_user_note) if s and str(s).strip()]
        )
        note = gemini_prompts.build_translation_note(background_json_str, merged_hints)
        sys_prompt = build_translation_system_prompt(note, variant=prompt_variant_from_env())
        log(f"[KO-TRANSLATE] ─ 시스템 프롬프트 (HTML, {len(sys_prompt)}자)")
        log(sys_prompt)
    else:
        sys_body = system_prompt_translation_chunk(tier)
        log(f"[KO-TRANSLATE] ─ 시스템 프롬프트 (JSON 번역 경로, {len(sys_body)}자)")
        log(sys_body)
    log(sep)


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


def _notify_ko_content_lines(
    all_segments: List[SimpleSegment],
    chunk_segments: List[SimpleSegment],
    on_content_line: ContentLineFn,
) -> None:
    if not on_content_line:
        return
    for seg in chunk_segments:
        text = (seg.text or "").strip()
        if not text:
            continue
        try:
            idx = all_segments.index(seg)
        except ValueError:
            idx = -1
        on_content_line(
            {
                "lang": "ko",
                "text": text,
                "start": float(seg.start),
                "end": float(seg.end),
                "index": idx,
            }
        )


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
    translation_note_global: Optional[str] = None,
    translation_note_actress: Optional[str] = None,
    translation_note_work: Optional[str] = None,
    apply_glossary_post: bool = True,
    logger_func: OptionalLogger = None,
    should_cancel: CancelCheck = None,
    log_full_translation_prompt: Optional[bool] = None,
    log_translation_start_details: Optional[bool] = None,
    on_content_line: ContentLineFn = None,
) -> List[SimpleSegment]:
    """
    일본어 세그먼트 리스트를 한국어로 번역한다. 세그먼트 객체가 제자리에서 갱신된다.
    `story_context_grok_json`: Grok 캐시 JSON(dict) — 청크 시각에 맞춰 scene_id/tone 주입.
    """
    from javstory.config.app_config import resolve_translation_llm_tier
    from javstory.llm.ollama_ko_vram import after_ko_translate_work, before_ko_translate_work

    log = logger_func or print
    log_full_prompt = _want_full_translation_prompt_log(log_full_translation_prompt)
    log_start_details = _want_translation_start_details_log(log_translation_start_details)
    if not segments:
        log("[KO-TRANSLATE] 세그먼트 없음 — 스킵")
        return segments

    tier = resolve_translation_llm_tier(
        translation_provider=translation_provider,
        translation_tier=translation_tier,
    )
    prov_l = str(tier.get("provider") or "").lower()
    if prov_l in ("ollama", "llamacpp") and "qwen" in (tier.get("model") or "").lower():
        qt = os.environ.get("JAVSTORY_TRANSLATION_QWEN_TEMPERATURE", "0.22").strip()
        try:
            tier = {**tier, "temperature": float(qt)}
        except ValueError:
            tier = {**tier, "temperature": 0.22}
        if not (os.environ.get("JAVSTORY_TRANSLATION_OLLAMA_MAX_TOKENS", "") or "").strip():
            if prov_l == "llamacpp":
                from javstory.llm.llamacpp_backend import llamacpp_max_tokens_from_env

                # fit으로 n_ctx가 ~2k로 줄 때 생성 여유를 남기기 위해 기본 768
                qmt = (os.environ.get("JAVSTORY_TRANSLATION_QWEN_MAX_TOKENS", "") or "").strip()
                if qmt:
                    try:
                        tier = {**tier, "max_tokens": max(512, int(qmt))}
                    except ValueError:
                        tier = {**tier, "max_tokens": llamacpp_max_tokens_from_env(default=768)}
                else:
                    tier = {**tier, "max_tokens": llamacpp_max_tokens_from_env(default=768)}
            else:
                qmt = (os.environ.get("JAVSTORY_TRANSLATION_QWEN_MAX_TOKENS", "") or "").strip() or "2048"
                try:
                    tier = {**tier, "max_tokens": max(512, int(qmt))}
                except ValueError:
                    tier = {**tier, "max_tokens": 2048}

    extra_hints = _story_hints_for_tier(tier, story_context_hints, story_context_grok_json)
    if _local_translation_provider(tier):
        background_json_str = _compact_background_json_for_local(background_json_str)
        if extra_hints.strip():
            log(
                f"[KO-TRANSLATE] 로컬 컨텍스트 절약 — 힌트 {len(extra_hints)}자 / "
                f"배경 {len(background_json_str)}자 (Grok 씬 본문 생략)"
            )

    # 전역+배우+작품 노트 결합 — Gemini {{note}} + JSON [TranslationHints] + 글로서리
    try:
        from javstory.translation.translation_notes import (
            combine_translation_notes,
            extract_glossary,
            apply_glossary_to_text,
        )
        combined_user_note = combine_translation_notes(
            global_note=translation_note_global or "",
            actress_note=translation_note_actress or "",
            work_note=translation_note_work or "",
        )
    except Exception:
        combined_user_note = ""
        extract_glossary = None  # type: ignore[assignment]
        apply_glossary_to_text = None  # type: ignore[assignment]

    # JSON/로컬 경로에도 번역 노트를 힌트로 주입 (로컬은 길이 제한)
    if combined_user_note.strip():
        note_for_hints = combined_user_note
        if _local_translation_provider(tier):
            note_for_hints = _clip_text(combined_user_note, 1400)
        note_block = f"[번역 노트]\n{note_for_hints}"
        extra_hints = "\n\n".join(
            p for p in (extra_hints.strip(), note_block) if p
        )
        log(f"[KO-TRANSLATE] 번역 노트 힌트 주입 ({len(note_for_hints)}자)")

    # 후처리 글로서리 — LLM이 놓친 토큰을 강제 치환.
    glossary_pairs: list[tuple[str, str]] = []
    if apply_glossary_post and combined_user_note and extract_glossary:
        try:
            glossary_pairs = extract_glossary(combined_user_note)
        except Exception:
            glossary_pairs = []

    if tier.get("provider") == "ollama":
        await before_ko_translate_work(tier["model"], logger_func=log)
    elif tier.get("provider") == "llamacpp":
        from javstory.llm.llamacpp_backend import llamacpp_ensure_model

        await llamacpp_ensure_model(tier, logger_func=log)

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
    if log_start_details:
        _log_translation_start_details(
            log,
            tier=tier,
            background_json_str=background_json_str,
            extra_hints=extra_hints,
            combined_user_note=combined_user_note,
            translation_note_global=translation_note_global or "",
            translation_note_actress=translation_note_actress or "",
            translation_note_work=translation_note_work or "",
        )
    if prov_l in ("ollama", "llamacpp") and "qwen" in (tier.get("model") or "").lower():
        log(
            "[KO-TRANSLATE] 로컬 Qwen(llama.cpp/Ollama)은 GPU·모델 크기에 따라 청크당 매우 느릴 수 있습니다. "
            "실사용 속도가 필요하면 OpenRouter 프로필(default/keeper 등) 권장. "
            "로컬 유지 시: VRAM 여유면 JAVSTORY_TRANSLATION_CONCURRENCY=2, "
            "컨텍스트 초과 시 JAVSTORY_LLAMACPP_CTX 상향 또는 JAVSTORY_LLAMACPP_FIT=off, "
            "여전히 느리면 JAVSTORY_TRANSLATION_QWEN_MAX_TOKENS=512 등으로 추가 하향."
        )

    async def _route(messages: List[dict[str, str]], tier_use: Dict[str, Any] = tier) -> str:
        return await route_with_backoff(
            router,
            messages,
            tier_use,
            log=_translation_retry_log(log),
            should_cancel=should_cancel,
        )

    async def _one(idx: int, chunk: dict) -> None:
        if should_cancel and should_cancel():
            raise STTCancelled()
        async with semaphore:
            if should_cancel and should_cancel():
                raise STTCancelled()
            tgt_segs: List[SimpleSegment] = chunk["target"]
            chunk_json = _chunk_json_for_translation(tgt_segs) if tgt_segs else "[]"
            try:
                await _one_chunk(idx, chunk)
            except STTCancelled:
                raise
            except Exception as e:
                log(
                    f"[KO-TRANSLATE] 청크 {idx + 1}/{total_chunks} 오류 — {type(e).__name__}: {e}"
                )
                if tgt_segs:
                    _restore_ja_texts_from_chunk_json(tgt_segs, chunk_json)

    async def _one_chunk(idx: int, chunk: dict) -> None:
            if should_cancel and should_cancel():
                raise STTCancelled()
            tgt_segs = chunk["target"]
            if not tgt_segs:
                return

            chunk_json = _chunk_json_for_translation(tgt_segs)
            anchor_sec = (tgt_segs[0].start + tgt_segs[-1].end) / 2.0 if tgt_segs else 0.0
            scene_id, scene_tone = resolve_grok_scene_for_chunk(
                anchor_sec,
                grok_data,
                video_end_sec=video_end_sec,
            )
            compact_hints = _use_compact_translation_hints(idx)
            cache_fingerprint = {
                "schema": _CACHE_SCHEMA_VERSION,
                "prompt_version": _CACHE_PROMPT_VERSION,
                "product_code": product_code,
                "provider": tier.get("provider") or "",
                "model": tier.get("model") or "",
                "temperature": tier.get("temperature"),
                "max_tokens": tier.get("max_tokens"),
                "target_dur": round(float(target_dur), 3),
                "overlap_dur": round(float(overlap_dur), 3),
                "chunk_idx": idx,
                "chunk_json": chunk_json,
                "background": background_json_str,
                "extra_hints": extra_hints,
                "combined_user_note": combined_user_note,
                "scene_id": scene_id,
                "scene_tone": scene_tone,
                "compact_hints": compact_hints,
                "prompt_mode": prompt_mode_from_env(),
                "prompt_variant": prompt_variant_from_env(),
            }
            cache_path = _translation_chunk_cache_path(product_code, cache_fingerprint)
            if _apply_cached_translation(
                tgt_segs,
                cache_path,
                chunk_json=chunk_json,
                log=log,
                chunk_idx=idx,
                total_chunks=total_chunks,
            ):
                _notify_ko_content_lines(segments, tgt_segs, on_content_line)
                return

            # ── HTML 번역 경로 (Gemini / llamacpp 등) ─────────────────
            if uses_html_translation_prompt(tier):
                from javstory.translation import gemini_prompts

                applied_ok = False
                merged_hints = "\n\n".join(
                    [s for s in (extra_hints, combined_user_note) if s and s.strip()]
                )
                note = gemini_prompts.build_translation_note(background_json_str, merged_hints)
                sys_prompt = build_translation_system_prompt(note, variant=prompt_variant_from_env())
                user_msg = gemini_prompts.segments_to_html_user_message(tgt_segs)
                messages_g: List[dict[str, str]] = [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_msg},
                ]
                if log_full_prompt:
                    _log_full_glm_prompt(
                        log, chunk_idx=idx, total_chunks=total_chunks, messages=messages_g
                    )
                t_req = time.monotonic()
                log(
                    f"[KO-TRANSLATE] 청크 {idx + 1}/{total_chunks} HTML LLM 대기 중… "
                    f"~{tgt_segs[0].start:.1f}–{tgt_segs[-1].end:.1f}s"
                )
                res = await _route(messages_g)
                log(
                    f"[KO-TRANSLATE] 청크 {idx + 1}/{total_chunks} HTML 응답 수신 "
                    f"({time.monotonic() - t_req:.1f}s)"
                )
                if log_full_prompt:
                    pr = res or ""
                    log(
                        f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — HTML 응답:\n"
                        f"{pr[:12000]}{'…' if len(pr) > 12000 else ''}"
                    )
                applied_ok = gemini_prompts.parse_html_translation_response(res or "", tgt_segs)
                if not applied_ok:
                    log(
                        f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — HTML 파싱 실패 — 재시도"
                    )
                    retry_msgs: List[dict[str, str]] = messages_g + [
                        {"role": "assistant", "content": res or ""},
                        {
                            "role": "user",
                            "content": (
                                '번역이 불완전합니다. <p id="N">번역문</p> 형식으로 '
                                "모든 줄을 빠짐없이 번역하고 </main>으로 종료해 주세요."
                            ),
                        },
                    ]
                    res2 = await _route(retry_msgs)
                    applied_ok = gemini_prompts.parse_html_translation_response(res2 or "", tgt_segs)
                    if not applied_ok:
                        log(
                            f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} "
                            "— HTML 최종 실패 — 해당 구간 일본어 유지"
                        )
                if applied_ok and not segments_translation_quality_ok(tgt_segs):
                    log(
                        f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — "
                        "번역 품질 불량(일본어·혼입·한글 없음) — 순수 한글 재번역"
                    )
                    _restore_ja_texts_from_chunk_json(tgt_segs, chunk_json)
                    pure_user = (
                        gemini_prompts.segments_to_html_user_message(tgt_segs)
                        + RETRY_TRANSLATION_KO_PURE_APPEND
                    )
                    pure_msgs: List[dict[str, str]] = [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": pure_user},
                    ]
                    res3 = await _route(pure_msgs)
                    applied_ok = gemini_prompts.parse_html_translation_response(res3 or "", tgt_segs)
                    if applied_ok and not segments_translation_quality_ok(tgt_segs):
                        log(
                            f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — "
                            "품질 재시도 후에도 불량"
                        )
                        applied_ok = False
                if glossary_pairs and apply_glossary_to_text is not None:
                    for s in tgt_segs:
                        try:
                            s.text = apply_glossary_to_text(s.text or "", glossary_pairs)
                        except Exception:
                            pass
                if not applied_ok:
                    _restore_ja_texts_from_chunk_json(tgt_segs, chunk_json)
                elif not segments_translation_quality_ok(tgt_segs):
                    log(
                        f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — "
                        "최종 품질 불량 — 해당 구간 일본어 유지"
                    )
                    _restore_ja_texts_from_chunk_json(tgt_segs, chunk_json)
                    applied_ok = False
                if applied_ok:
                    _notify_ko_content_lines(segments, tgt_segs, on_content_line)
                    _store_translation_chunk_cache(
                        cache_path,
                        product_code=product_code,
                        tier=tier,
                        chunk_idx=idx,
                        total_chunks=total_chunks,
                        tgt_segs=tgt_segs,
                        fingerprint=cache_fingerprint,
                        log=log,
                    )
                log(f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — 완료")
                return
            # ── 기존 JSON 번역 경로 ───────────────────────────────────
            use_en_local = _is_local_gemma_tier(tier)
            src_texts = _source_texts_from_chunk_json(chunk_json, len(tgt_segs))
            lp = "[KO-TRANSLATE]"

            def _apply_ko_json(raw: str) -> bool:
                return _apply_json_chunk(
                    tgt_segs,
                    raw,
                    log=log,
                    log_prefix=lp,
                    postprocess_text=postprocess_ko_translation_text,
                    require_start_end=False,
                    require_complete=True,
                )

            def _quality_ok() -> bool:
                return segments_translation_quality_ok(tgt_segs, source_texts=src_texts)

            user_p = render_glm_translation_chunk_user(
                background_json_str,
                chunk_json,
                idx,
                scene_id,
                scene_tone,
                extra_hints,
                compact_translation_hints=compact_hints,
                english_local=use_en_local,
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
            from javstory.translation.llm_backoff import is_context_size_exceeded

            try:
                res = await _route(messages)
            except Exception as e:
                if not is_context_size_exceeded(e):
                    raise
                log(
                    f"[KO-TRANSLATE] 청크 {idx + 1}/{total_chunks} 컨텍스트 초과 — "
                    "힌트·배경 제거 후 1회 재시도"
                )
                lean_bg = json.dumps(
                    {"product_code": product_code},
                    ensure_ascii=False,
                )
                lean_user = render_glm_translation_chunk_user(
                    lean_bg,
                    chunk_json,
                    idx,
                    scene_id,
                    scene_tone,
                    "",
                    compact_translation_hints=True,
                    english_local=use_en_local,
                )
                lean_tier = {
                    **tier,
                    "max_tokens": min(int(tier.get("max_tokens") or 768), 512),
                }
                messages = [
                    {"role": "system", "content": system_prompt_translation_chunk(tier)},
                    {"role": "user", "content": lean_user},
                ]
                user_p = lean_user
                res = await _route(messages, lean_tier)
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
            json_ok = _apply_ko_json(processed)
            quality_failed = False
            if json_ok and not _quality_ok():
                quality_failed = True
                log(
                    f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — "
                    "번역 품질 불량(일본어·혼입·한글 없음) — 순수 한글 재번역"
                )
                _restore_ja_texts_from_chunk_json(tgt_segs, chunk_json)
                pure_append = (
                    RETRY_TRANSLATION_KO_PURE_APPEND_EN
                    if use_en_local
                    else RETRY_TRANSLATION_KO_PURE_APPEND
                )
                pure_msgs: List[dict[str, str]] = [
                    {"role": "system", "content": system_prompt_translation_chunk(tier)},
                    {"role": "user", "content": user_p},
                    {"role": "assistant", "content": processed or ""},
                    {"role": "user", "content": pure_append},
                ]
                res_pure = await _route(pure_msgs)
                processed_pure = re.sub(
                    r"<think>.*?</think>",
                    "",
                    res_pure or "",
                    flags=re.DOTALL,
                )
                processed_pure = re.sub(
                    r"<redacted_thinking>.*?</redacted_thinking>",
                    "",
                    processed_pure,
                    flags=re.DOTALL,
                )
                json_ok = _apply_ko_json(processed_pure)
                if json_ok and not _quality_ok():
                    json_ok = False
                    quality_failed = True
                    _restore_ja_texts_from_chunk_json(tgt_segs, chunk_json)
            if not json_ok:
                reason = "품질 재시도 실패" if quality_failed else "JSON 적용 실패"
                log(f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — {reason} — 재시도")
                model_l = (tier.get("model") or "").lower()
                prov_l_chunk = str(tier.get("provider") or "").lower()
                use_neutral_local = (
                    prov_l_chunk in ("ollama", "llamacpp")
                    and ("qwen" in model_l or "gemma" in model_l)
                    and not _env_truthy("JAVSTORY_TRANSLATION_OLLAMA_NO_NEUTRAL_FALLBACK")
                )
                if use_neutral_local:
                    label = "Gemma" if "gemma" in model_l else "Qwen"
                    log(
                        f"[KO-TRANSLATE] 로컬 {label}: {reason} — 강화 system으로 재시도"
                        + (" (거절 문구 감지)" if _looks_like_model_refusal(processed) else "")
                    )
                    neutral_sys = (
                        system_prompt_translation_local_gemma_retry()
                        if "gemma" in model_l
                        else system_prompt_translation_ollama_qwen_neutral()
                    )
                    base_for_retry: List[dict[str, str]] = [
                        {"role": "system", "content": neutral_sys},
                        {"role": "user", "content": user_p},
                    ]
                else:
                    base_for_retry = messages

                retry_messages = base_for_retry + [
                    {"role": "assistant", "content": processed or ""},
                    {"role": "user", "content": _retry_translation_user_content(tier, attempt=1)},
                ]
                if log_full_prompt:
                    _log_full_glm_prompt(
                        log,
                        chunk_idx=idx,
                        total_chunks=total_chunks,
                        messages=retry_messages,
                        label="(재시도)",
                    )
                res2 = await _route(retry_messages)
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
                json_ok = _apply_ko_json(processed2)
                if json_ok and not _quality_ok():
                    json_ok = False
                    quality_failed = True
                    _restore_ja_texts_from_chunk_json(tgt_segs, chunk_json)
                if not json_ok:
                    log(
                        f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — "
                        f"{'품질' if quality_failed else 'JSON'} 적용 실패 — 2차 재시도"
                    )
                    retry2 = base_for_retry + [
                        {"role": "assistant", "content": processed2 or processed or ""},
                        {"role": "user", "content": _retry_translation_user_content(tier, attempt=2)},
                    ]
                    res3 = await _route(retry2)
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
                    json_ok = _apply_ko_json(processed3)
                    if json_ok and not _quality_ok():
                        json_ok = False
                        quality_failed = True
                    if not json_ok:
                        log(
                            f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — 최종 실패 — 해당 구간 일본어 유지"
                        )
            applied_ok = bool(json_ok)
            # OpenRouter/Ollama 경로에도 동일하게 사용자 노트 글로서리 강제 치환
            if glossary_pairs and apply_glossary_to_text is not None:
                for s in tgt_segs:
                    try:
                        s.text = apply_glossary_to_text(s.text or "", glossary_pairs)
                    except Exception:
                        pass
            if applied_ok and not _quality_ok():
                log(
                    f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — "
                    "최종 품질 불량 — 해당 구간 일본어 유지"
                )
                _restore_ja_texts_from_chunk_json(tgt_segs, chunk_json)
                applied_ok = False
            elif not applied_ok:
                _restore_ja_texts_from_chunk_json(tgt_segs, chunk_json)
            if applied_ok:
                _notify_ko_content_lines(segments, tgt_segs, on_content_line)
                _store_translation_chunk_cache(
                    cache_path,
                    product_code=product_code,
                    tier=tier,
                    chunk_idx=idx,
                    total_chunks=total_chunks,
                    tgt_segs=tgt_segs,
                    fingerprint=cache_fingerprint,
                    log=log,
                )
            log(f"[KO-TRANSLATE] 현재 {idx + 1} / {total_chunks} — 완료")

    tasks = [asyncio.create_task(_one(i, c)) for i, c in enumerate(chunks_data)]
    try:
        await asyncio.gather(*tasks)
    except Exception:
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    finally:
        if tier.get("provider") == "ollama":
            await after_ko_translate_work(tier["model"], logger_func=log)
        elif tier.get("provider") == "llamacpp":
            from javstory.llm.llamacpp_backend import cleanup_llamacpp_after_job

            cancelled = bool(should_cancel and should_cancel())
            cleanup_llamacpp_after_job(cancelled=cancelled, logger_func=log)

    return segments
