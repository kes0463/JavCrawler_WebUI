"""
자막 교정·번역 파이프라인 오케스트레이터.

Harvest 시 Grok이 추출한 캐시 JSON을 작품 분석의 유일한 소스로 사용.
중간 LLM 분석(배경 합성, 스토리 리포트, 레퍼런스 수집)은 모두 제거됨.

흐름:
  1. Grok 캐시 로드 (data/cache/story_context/) — LLM 호출 없음
  2. DB 메타에서 배경 JSON 직접 생성 — LLM 호출 없음
  3. JA 교정: Pass1(Grok) → Pass2(GLM) → [선택]Pass3(Claude)
  4. KO 번역: 배경(DB직접) + Grok힌트 + 씬톤
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pysrt

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from javstory.llm.engine import MultiTierRouter

from javstory.translation.correction_chunk import correct_ja_segments_async
from javstory.translation.ko_translation_chunk import translate_ja_segments_to_ko_async
from javstory.translation.story_grok_module import (
    load_cached_grok_json,
    merge_story_context_tier,
)
from javstory.translation.story_context_prompts import format_story_context_for_translation
from javstory.transcription.stt_types import SimpleSegment


def _load_simple_segments_from_srt(path: Path) -> list[SimpleSegment]:
    subs = pysrt.open(str(path), encoding="utf-8")
    return [
        SimpleSegment(s.start.ordinal / 1000.0, s.end.ordinal / 1000.0, s.text)
        for s in subs
    ]


def _write_simple_segments_srt(segments: list[SimpleSegment], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subs = pysrt.SubRipFile()
    for i, seg in enumerate(segments, start=1):
        item = pysrt.SubRipItem(index=i, text=seg.text)
        item.start.ordinal = int(round(seg.start * 1000))
        item.end.ordinal = int(round(seg.end * 1000))
        subs.append(item)
    subs.save(str(out_path), encoding="utf-8")


def _resolve_ja_corrected_output_path(ja_srt: Path, kwargs: dict[str, Any]) -> Path:
    explicit = kwargs.get("ja_corrected_srt_path")
    if explicit:
        return Path(str(explicit)).expanduser().resolve()
    # 유저 요청: .corrected 없이 원본 .ja.srt를 덮어쓰거나 해당 이름으로 저장
    work_dir = kwargs.get("work_dir")
    if work_dir:
        return Path(str(work_dir)).expanduser().resolve() / ja_srt.name
    return ja_srt


def _resolve_ko_translation_input_path(kwargs: dict[str, Any]) -> Path | None:
    override = kwargs.get("translate_ja_srt_path")
    if override and str(override).strip():
        p = Path(str(override)).expanduser().resolve()
        return p if p.is_file() else None
    raw = kwargs.get("ja_srt_path")
    if raw is None or not str(raw).strip():
        return None
    ja_path = Path(str(raw)).expanduser().resolve()
    if not ja_path.is_file():
        return None
    corrected = _resolve_ja_corrected_output_path(ja_path, kwargs)
    if corrected.is_file():
        return corrected
    return ja_path


def _resolve_ko_srt_output_path(ja_input: Path, kwargs: dict[str, Any]) -> Path:
    explicit = kwargs.get("ko_srt_path")
    if explicit and str(explicit).strip():
        return Path(str(explicit)).expanduser().resolve()
    
    work_dir = kwargs.get("work_dir")
    stem = ja_input.stem
    # .ja.srt 또는 .ja.corrected.srt 등에서 .ko.srt를 유도
    if stem.endswith(".corrected"):
        stem = stem[: -len(".corrected")]
    if stem.endswith(".ja"):
        stem = stem[: -len(".ja")]
    
    name = f"{stem}.ko.srt"
    if work_dir:
        return Path(str(work_dir)).expanduser().resolve() / name
    return ja_input.with_name(name)


def _correction_forward_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "llm_tier",
        "pass1_tier",
        "pass2_tier",
        "pass3_tier",
        "claude_polish",
        "enable_pass3",
        "speaker_prefix_mode",
        "logger_func",
        "should_cancel",
    )
    return {k: kwargs[k] for k in keys if k in kwargs}


def _translation_forward_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "translation_provider",
        "translation_tier",
        "should_cancel",
        "logger_func",
        "log_full_translation_prompt",
        "log_translation_start_details",
        "story_context_grok_json",
        "translation_note_global",
        "translation_note_actress",
        "translation_note_work",
        "apply_glossary_post",
    )
    return {k: kwargs[k] for k in keys if k in kwargs}


def _gather_translation_notes(product_code: str) -> dict[str, str]:
    """전역/배우/작품 번역 노트를 디스크·DB에서 수집해 dict로 반환.

    - 전역: `translation_notes.load_global_note()` (파일 + .env 폴백)
    - 배우: `actresses.translation_note` (해당 작품 모든 배우 합산)
    - 작품: `LibraryCanonical.translation_note` (library_state.json)
    """
    res = {"global": "", "actress": "", "work": ""}
    pc = (product_code or "").strip().upper()

    try:
        from javstory.translation.translation_notes import load_global_note
        res["global"] = load_global_note() or ""
    except Exception:
        res["global"] = ""

    if not pc:
        return res

    try:
        from javstory.library.detail_persist import load_canonical_for_product
        st = load_canonical_for_product(pc)
        res["work"] = (getattr(st, "translation_note", "") or "")
    except Exception:
        res["work"] = ""

    try:
        from javstory.harvest.database import get_db_session, JAVMetadata, Actress
        session = get_db_session()
        try:
            row = session.query(JAVMetadata).filter_by(product_code=pc).first()
            jas: list[str] = []
            if row and row.actors_ja:
                jas = [x.strip() for x in str(row.actors_ja).split(",") if x.strip()]
            if jas:
                blocks: list[str] = []
                for ja in jas:
                    a = session.query(Actress).filter_by(japanese=ja).first()
                    note = (getattr(a, "translation_note", None) or "") if a is not None else ""
                    if note.strip():
                        blocks.append(f"[화자: {ja}]\n{note.strip()}")
                if blocks:
                    res["actress"] = "\n\n".join(blocks)
        finally:
            session.close()
    except Exception:
        res["actress"] = ""

    return res


def _build_background_from_db(product_code: str) -> str:
    """DB 메타데이터에서 배경 JSON을 LLM 없이 직접 생성."""
    pc = (product_code or "").strip().upper()
    bg: dict[str, Any] = {"product_code": pc}
    try:
        from javstory.harvest.database import get_db_session, JAVMetadata
        session = get_db_session()
        try:
            row = session.query(JAVMetadata).filter_by(product_code=pc).first()
            if row:
                bg["title_ko"] = getattr(row, "title_ko", "") or ""
                bg["title_ja"] = getattr(row, "title_ja", "") or getattr(row, "original_title", "") or ""
                bg["synopsis_short"] = (getattr(row, "synopsis_ko", "") or getattr(row, "synopsis", "") or "")[:500]
                bg["actors"] = getattr(row, "actresses_ko", "") or getattr(row, "actresses", "") or ""
                bg["genres"] = getattr(row, "genres_ko", "") or getattr(row, "genres", "") or ""
                bg["maker"] = getattr(row, "maker_ko", "") or getattr(row, "maker", "") or ""
                bg["release_date"] = getattr(row, "release_date", "") or ""
        finally:
            session.close()
    except Exception:
        pass
    return json.dumps(bg, ensure_ascii=False, sort_keys=True)


def _load_grok_cache(product_code: str, tier_raw: Any = None) -> tuple[dict | None, str]:
    """Grok 캐시 JSON 로드 + 번역 힌트 문자열 생성. LLM 호출 없음."""
    pc = (product_code or "").strip()
    if not pc:
        return None, ""
    data = load_cached_grok_json(pc, tier_raw if isinstance(tier_raw, dict) else None)
    if not isinstance(data, dict):
        return None, ""
    hints = format_story_context_for_translation(data)
    return data, hints or ""


class SubtitlePipelineOrchestrator:
    def __init__(self, router: MultiTierRouter) -> None:
        self.router = router

    async def run_for_product(self, product_code: str, **kwargs: Any) -> None:
        """Grok 캐시 + DB 메타 직접 로드 → JA 교정 → KO 번역."""
        merged: dict[str, Any] = {**kwargs, "product_code": product_code}
        log = kwargs.get("logger_func") or print

        tier_raw = merged.get("story_context_tier") or merged.get("story_analysis_tier")
        grok_json, hints_text = _load_grok_cache(product_code, tier_raw)
        merged["story_context_grok_json"] = grok_json
        merged["story_context_report_text"] = hints_text
        if grok_json:
            log(f"[Orchestrator] Grok 캐시 로드 완료: {product_code}")

        merged["background_json_str"] = _build_background_from_db(product_code)

        await self._correct_ja_chunks(**merged)
        await self._translate_ko_chunks(**merged)

    async def _correct_ja_chunks(self, **kwargs: Any) -> None:
        raw = kwargs.get("ja_srt_path")
        if raw is None or str(raw).strip() == "":
            return

        ja_path = Path(str(raw)).expanduser().resolve()
        log = kwargs.get("logger_func")
        if not callable(log):
            log = print  # type: ignore[assignment]

        if not ja_path.is_file():
            log(f"[Orchestrator] JA 교정 스킵: 파일 없음 — {ja_path}")
            return

        out_path = _resolve_ja_corrected_output_path(ja_path, kwargs)

        product_code = str(kwargs.get("product_code") or "Unknown")
        
        from javstory.config.app_config import correction_skip_enabled
        if correction_skip_enabled():
            log(f"[Orchestrator] JA 교정 건너뛰기 (설정됨): {product_code}")
            # 교정 없이 원본을 출력 경로에 복사/저장하여 번역 단계로 넘김
            segments = _load_simple_segments_from_srt(ja_path)
            _write_simple_segments_srt(segments, out_path)
            return

        segments = _load_simple_segments_from_srt(ja_path)
        forward = _correction_forward_kwargs(kwargs)

        log(f"[Orchestrator] JA 교정 시작: {ja_path.name} → {out_path.name}")
        corrected = await correct_ja_segments_async(
            segments,
            product_code=product_code,
            router=self.router,
            **forward,
        )
        _write_simple_segments_srt(corrected, out_path)
        log(f"[Orchestrator] JA 교정 저장: {out_path}")

    async def _translate_ko_chunks(self, **kwargs: Any) -> None:
        log = kwargs.get("logger_func")
        if not callable(log):
            log = print  # type: ignore[assignment]

        bg_str = kwargs.get("background_json_str")
        if not bg_str or not str(bg_str).strip():
            log("[Orchestrator] KO 번역 스킵: background_json_str 없음")
            return

        ja_in = _resolve_ko_translation_input_path(kwargs)
        if ja_in is None:
            log("[Orchestrator] KO 번역 스킵: 번역 입력 SRT 없음 (ja_srt_path 또는 translate_ja_srt_path)")
            return

        out_path = _resolve_ko_srt_output_path(ja_in, kwargs)
        product_code = str(kwargs.get("product_code") or "Unknown")
        segments = _load_simple_segments_from_srt(ja_in)
        forward = _translation_forward_kwargs(kwargs)

        # 전역+배우+작품 번역 노트 수집(이미 kwargs에 있으면 그대로 사용)
        if not any(
            k in forward for k in ("translation_note_global", "translation_note_actress", "translation_note_work")
        ):
            notes = _gather_translation_notes(product_code)
            forward["translation_note_global"] = notes["global"]
            forward["translation_note_actress"] = notes["actress"]
            forward["translation_note_work"] = notes["work"]
            log(
                "[Orchestrator] 번역 노트 — "
                f"전역 {len(notes['global'])}자 / 배우 {len(notes['actress'])}자 / 작품 {len(notes['work'])}자"
            )

        log(f"[Orchestrator] KO 번역 시작: {ja_in.name} → {out_path.name}")
        hints = kwargs.get("story_context_report_text")
        await translate_ja_segments_to_ko_async(
            segments,
            product_code=product_code,
            router=self.router,
            background_json_str=str(bg_str),
            story_context_hints=hints if isinstance(hints, str) and hints.strip() else None,
            **forward,
        )
        _write_simple_segments_srt(segments, out_path)
        log(f"[Orchestrator] KO 번역 저장: {out_path}")
