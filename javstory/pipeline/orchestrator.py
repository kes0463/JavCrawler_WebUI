"""
Harvest / STT / 자막(교정·KO 번역) 단계 오케스트레이터.

- **일괄(원스톱)**: 세 단계를 순서대로 실행 (`run_product_pipeline_async`, stages=`all`).
- **개별**: `stages`에 `{HARVEST}`, `{STT}`, `{SUBTITLE}` 조합.
- **스킵**: `skip_if_outputs_exist=True`이면 DB·파일 산출물이 있으면 해당 단계 생략(`force=True`로 무시).
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Literal, TypedDict

from javstory.llm.engine import MultiTierRouter
from javstory.translation.subtitle_pipeline_orchestrator import SubtitlePipelineOrchestrator


class PipelineStage(str, Enum):
    HARVEST = "harvest"
    STT = "stt"
    SUBTITLE = "subtitle"


class PipelineResult(TypedDict, total=False):
    harvest: dict[str, Any] | str
    stt: dict[str, Any] | str
    subtitle: str | None


def build_default_router(logger_func: Callable[[str], None] | None = None) -> MultiTierRouter:
    """OpenRouter 키로 `MultiTierRouter` 생성."""
    from javstory.config import secrets_manager

    key = (secrets_manager.get_openrouter_api_key() or "").strip()
    return MultiTierRouter(key, logger_func=logger_func or print)


def _ja_srt_next_to_video(video: Path) -> Path:
    base = str(video.with_suffix(""))
    return Path(base + ".ja.srt")


def _srt_next_to_video(video: Path) -> Path:
    base = str(video.with_suffix(""))
    return Path(base + ".srt")


def _expand_stages(stages: set[PipelineStage] | Literal["all"]) -> set[PipelineStage]:
    if stages == "all":
        return {PipelineStage.HARVEST, PipelineStage.STT, PipelineStage.SUBTITLE}
    return set(stages)


def _ko_output_path(ja_srt: Path, work_dir: Path | None) -> Path:
    from javstory.translation.subtitle_pipeline_orchestrator import (
        _resolve_ja_corrected_output_path,
        _resolve_ko_srt_output_path,
    )

    wd = str(work_dir.resolve()) if work_dir else None
    kwargs: dict[str, Any] = {"work_dir": wd}
    corrected = _resolve_ja_corrected_output_path(ja_srt, kwargs)
    ja_in = corrected if corrected.is_file() else ja_srt
    return _resolve_ko_srt_output_path(ja_in, kwargs)


@dataclass
class ProductPipelineStatus:
    product_code: str
    video_path: Path | None
    harvest_in_db: bool
    ja_srt_path: Path | None
    ja_srt_exists: bool
    ko_srt_path: Path | None
    ko_srt_exists: bool
    srt_fallback_exists: bool = False


def get_pipeline_status(
    *,
    product_code: str,
    video_path: str | Path | None = None,
    work_dir: Path | None = None,
    harvest_ok: bool | None = None,
) -> ProductPipelineStatus:
    """
    품번·영상 경로 기준 산출물 존재 여부(스킵 판단용).
    `video_path`가 없으면 STT/자막 파일 존재는 판단하지 않는다.
    `harvest_ok`가 제공되면 DB 조회를 생략한다.
    """
    pc = (product_code or "").strip().upper()
    vp = Path(video_path).expanduser().resolve() if video_path else None
    ja: Path | None = None
    ko: Path | None = None
    srt_exists = False
    if vp and vp.is_file():
        ja = _ja_srt_next_to_video(vp)
        ko = _ko_output_path(ja, work_dir)
        srt_plain = _srt_next_to_video(vp)
        srt_exists = srt_plain.is_file()

    ok = harvest_ok
    if ok is None:
        ok = False
        try:
            from javstory.harvest.database import get_db_session, JAVMetadata
            session = get_db_session()
            try:
                row = session.query(JAVMetadata).filter_by(product_code=pc).first()
                ok = bool(row and (row.title_ko or row.title_ja or row.original_title))
            finally:
                session.close()
        except Exception:
            pass

    return ProductPipelineStatus(
        product_code=pc,
        video_path=vp,
        harvest_in_db=ok,
        ja_srt_path=ja,
        ja_srt_exists=bool(ja and ja.is_file()),
        ko_srt_path=ko,
        ko_srt_exists=bool(ko and ko.is_file()),
        srt_fallback_exists=srt_exists,
    )


def _should_skip_harvest(status: ProductPipelineStatus, *, force: bool) -> bool:
    if force:
        return False
    return status.harvest_in_db


def _should_skip_stt(status: ProductPipelineStatus, *, force: bool) -> bool:
    if force:
        return False
    return status.ja_srt_exists


def _should_skip_subtitle(status: ProductPipelineStatus, *, force: bool) -> bool:
    if force:
        return False
    return status.ko_srt_exists


async def run_product_pipeline_async(
    *,
    product_code: str,
    video_path: str | Path | None = None,
    product_code_override: str | None = None,
    stages: set[PipelineStage] | Literal["all"] = "all",
    router: MultiTierRouter | None = None,
    work_dir: Path | None = None,
    skip_if_outputs_exist: bool = True,
    force: bool = False,
    harvest_kwargs: dict[str, Any] | None = None,
    subtitle_kwargs: dict[str, Any] | None = None,
    logger_func: Callable[[str], None] | None = None,
) -> PipelineResult:
    """
    품번 단위로 Harvest → stable-ts STT → `SubtitlePipelineOrchestrator.run_for_product` 를 연결한다.

    Parameters
    ----------
    product_code
        작품 품번(대문자 권장).
    video_path
        로컬 영상 파일. STT·자막 단계에 필요. Harvest만 할 때는 품번 문자열 경로만 넘긴 기존 코디네이터 호출과 동일하게 **파일 없이** 둘 수 있다.
    product_code_override
        폴더명 품번 등 `run_crawler_for_video_path(..., product_code=...)`에 그대로 전달.
    stages
        `"all"` 또는 `PipelineStage` 부분 집합.
    router
        자막 단계용. 생략 시 STT·자막이 포함될 때 `build_default_router`로 생성.
    work_dir
        STT 임시 WAV 등에 사용. 기본은 영상과 같은 디렉터리.
    skip_if_outputs_exist / force
        단계별로 산출물이 있으면 스킵. `force=True`면 항상 실행.
    harvest_kwargs
        `run_crawler_for_video_path`에 추가 전달.
    subtitle_kwargs
        `SubtitlePipelineOrchestrator.run_for_product`에 그대로 병합.
    """
    log = logger_func or print
    want = _expand_stages(stages)
    hk = dict(harvest_kwargs or {})
    sk = dict(subtitle_kwargs or {})

    vp: Path | None = Path(video_path).expanduser().resolve() if video_path else None
    if vp and not vp.exists():
        raise FileNotFoundError(f"video_path 없음: {vp}")

    need_video_file = bool(want & {PipelineStage.STT, PipelineStage.SUBTITLE})
    if need_video_file and (vp is None or not vp.is_file()):
        raise ValueError("STT 또는 자막 단계는 존재하는 영상 파일 경로(video_path)가 필요합니다.")

    stt_out_dir = (work_dir or (vp.parent if vp else None))
    if PipelineStage.STT in want and stt_out_dir is None:
        raise ValueError("STT 단계에는 work_dir 또는 유효한 video_path가 필요합니다.")

    status = get_pipeline_status(
        product_code=product_code, video_path=vp, work_dir=work_dir
    )
    skip_harvest = skip_if_outputs_exist and _should_skip_harvest(status, force=force)
    skip_stt = skip_if_outputs_exist and _should_skip_stt(status, force=force)
    skip_sub = skip_if_outputs_exist and _should_skip_subtitle(status, force=force)

    out: PipelineResult = {}

    # --- Harvest ---
    if PipelineStage.HARVEST in want:
        if skip_harvest:
            out["harvest"] = "skipped: 이미 DB에 메타가 있습니다."
            log(f"[Pipeline] Harvest 스킵 — {status.product_code}")
        else:
            from javstory.harvest.coordinator import run_crawler_for_video_path

            crawl_target = vp if vp is not None else product_code
            hr = await run_crawler_for_video_path(
                crawl_target,
                product_code=product_code_override,
                **hk,
            )
            out["harvest"] = hr
            if isinstance(hr, dict) and hr.get("error"):
                log(f"[Pipeline] Harvest 실패 — 이후 단계 중단: {hr.get('error')}")
                return out

    # --- STT ---
    if PipelineStage.STT in want:
        if skip_stt:
            out["stt"] = "skipped: .ja.srt 가 이미 있습니다."
            log(f"[Pipeline] STT 스킵 — {status.ja_srt_path}")
        else:
            from javstory.transcription.engine import process_video_to_segments

            if vp is None or stt_out_dir is None:
                raise ValueError("STT 단계에는 존재하는 video_path 및 유효한 출력 디렉터리가 필요합니다.")
            wd = stt_out_dir
            wd.mkdir(parents=True, exist_ok=True)

            def _run_stt() -> Any:
                return process_video_to_segments(
                    str(vp),
                    str(wd),
                    logger_func=log,
                    should_cancel=None,
                )

            segs = await asyncio.to_thread(_run_stt)
            out["stt"] = {"segments": len(segs), "ja_srt": str(_ja_srt_next_to_video(vp))}

    # --- Subtitle (교정 + KO 등 run_for_product 전체) ---
    if PipelineStage.SUBTITLE in want:
        if skip_sub:
            out["subtitle"] = "skipped: .ko.srt 가 이미 있습니다."
            log(f"[Pipeline] 자막 파이프라인 스킵 — {status.ko_srt_path}")
        else:
            if vp is None:
                raise ValueError("자막 단계에는 존재하는 video_path가 필요합니다.")
            ja_path = _ja_srt_next_to_video(vp)
            if not ja_path.is_file():
                raise FileNotFoundError(
                    f"자막 단계 입력 .ja.srt 가 없습니다: {ja_path} (STT 단계를 먼저 실행하세요)"
                )

            r = router or build_default_router(logger_func=log)
            router_owned = router is None
            orch = SubtitlePipelineOrchestrator(r)

            sk.pop("product_code", None)
            merged = {
                **sk,
                "ja_srt_path": str(ja_path),
                "work_dir": str(work_dir) if work_dir else str(vp.parent),
                "logger_func": log,
            }
            try:
                await orch.run_for_product(status.product_code, **merged)
            finally:
                if router_owned:
                    await r.close()
            out["subtitle"] = "ok"

    return out


def run_product_pipeline_sync(**kwargs: Any) -> PipelineResult:
    """비동기 래퍼 — 스크립트·동기 맥락용."""
    return asyncio.run(run_product_pipeline_async(**kwargs))
