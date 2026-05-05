"""번역 노트 자동 생성 — Gemini로 작품/배우 노트 초안 생성."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Optional

from javstory.llm.engine import MultiTierRouter
from javstory.config.app_config import (
    gemini_translation_llm_tier,
    ENV_OPENROUTER_API_KEY,
)
import os


_WORK_NOTE_INSTRUCTIONS = """다음 정보를 바탕으로 JAV 자막 번역에 사용할 "작품 번역 노트"를 한국어로 작성하라.

[출력 규칙]
- 정확히 아래 4개 섹션 헤더를 사용하고, 다른 섹션은 만들지 말 것.
- 각 섹션은 불릿(- )을 포함한 짧은 항목들로 구성. 절대 산문/장문 문단 금지.
- 추측이 어려운 항목은 비워둘 것(헤더만 출력하고 본문 생략).
- 출력은 노트 텍스트만. 사족·서문·결론·코드펜스 금지.

[작품 기본 컨텍스트]
- 핵심 장르: (장르 태그 2~5개)
- 전체 톤앤매너: (예: 매우 노골적이고 거친 구어체 / 부드러운 로맨틱 / 코믹 등)

[화자 프로필 및 관계]
- (남성 1) ...: 말투/페르소나
- (여성 1) ...: 말투/페르소나
- 관계: (상하/연인/처음 만난 사이 등)

[Whisper AI 오인식 교정 사전]
- (자주 잘못 인식되는 일본어) -> (올바른 단어/대체 표현)

[용어/은어 매핑]
- 원어 => 번역어
"""

_ACTRESS_NOTE_INSTRUCTIONS = """다음 일본 AV 배우의 "배우 번역 노트"를 한국어로 작성하라.

[출력 규칙]
- 아래 2개 섹션 헤더만 사용.
- 각 섹션은 불릿(- )짧은 항목들. 산문 금지.
- 추측이 어려운 항목은 빼고 출력하지 말 것.
- 사족·코드펜스 금지. 노트 텍스트만 출력.

[화자 프로필 및 관계]
- 평소 말투/페르소나 (활발/얌전/지배적 등)
- 자주 등장하는 캐릭터(직장인/누나/여동생 등)

[고정 표기/호칭 사전]
- 원어 => 번역어
"""


def _strip_codefence(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"^```(?:\w+)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    return s.strip()


def _clip_section_headers(s: str, allowed: list[str]) -> str:
    """알려진 섹션 헤더만 남기고, 다른 [..]헤더가 있으면 그 본문은 [기타]로 합쳐 보존."""
    if not s:
        return ""
    lines = s.splitlines()
    out: list[str] = []
    cur = None
    keep = set(allowed)
    for line in lines:
        m = re.match(r"^\s*\[([^\]]+)\]\s*$", line)
        if m:
            h = m.group(1).strip()
            if h in keep:
                cur = h
                out.append(f"[{h}]")
            else:
                cur = "기타"
                out.append("[기타]")
        else:
            if cur is None:
                continue
            out.append(line)
    return "\n".join(out).strip()


@dataclass
class WorkNoteContext:
    """작품 노트 자동 생성 입력."""

    product_code: str = ""
    title_ja: str = ""
    title_ko: str = ""
    actress_ko: str = ""
    actress_ja: str = ""
    maker: str = ""
    genres: str = ""
    synopsis: str = ""
    overall_summary: str = ""
    sample_dialogue_ja: str = ""

    def to_context_block(self) -> str:
        parts: list[str] = []
        if self.product_code:
            parts.append(f"품번: {self.product_code}")
        if self.title_ja or self.title_ko:
            t = " / ".join(x for x in (self.title_ko, self.title_ja) if x)
            parts.append(f"제목: {t}")
        if self.actress_ko or self.actress_ja:
            a = " / ".join(x for x in (self.actress_ko, self.actress_ja) if x)
            parts.append(f"출연: {a}")
        if self.maker:
            parts.append(f"제작사: {self.maker}")
        if self.genres:
            parts.append(f"장르: {self.genres}")
        if self.synopsis:
            parts.append(f"줄거리(짧음): {self.synopsis[:600]}")
        if self.overall_summary:
            parts.append(f"전체 요약: {self.overall_summary[:1200]}")
        if self.sample_dialogue_ja:
            parts.append(f"대사 샘플(일):\n{self.sample_dialogue_ja[:1200]}")
        return "\n".join(parts).strip()


@dataclass
class ActressNoteContext:
    """배우 노트 자동 생성 입력."""

    japanese: str = ""
    korean: str = ""
    romaji: str = ""
    sample_titles: str = ""  # 다른 작품 제목들

    def to_context_block(self) -> str:
        parts: list[str] = []
        if self.japanese or self.korean:
            n = " / ".join(x for x in (self.korean, self.japanese) if x)
            parts.append(f"배우: {n}")
        if self.romaji:
            parts.append(f"로마자: {self.romaji}")
        if self.sample_titles:
            parts.append(f"대표 출연작 제목:\n{self.sample_titles[:1200]}")
        return "\n".join(parts).strip()


# ── 라우터 헬퍼 ──────────────────────────────────────────────────


def _make_router() -> MultiTierRouter:
    api_key = os.environ.get(ENV_OPENROUTER_API_KEY, "") or ""
    return MultiTierRouter(api_key=api_key, logger_func=print)


def _gemini_tier(model_id: str | None = None) -> dict[str, Any]:
    """기본은 Flash Lite — 노트는 짧고 RPM 여유 큼."""
    mid = (model_id or "").strip() or "gemini-2.5-flash"
    return gemini_translation_llm_tier(mid)


# ── 공개 API ──────────────────────────────────────────────────────


async def generate_work_translation_note_async(
    ctx: WorkNoteContext,
    *,
    model_id: Optional[str] = None,
    router: Optional[MultiTierRouter] = None,
    max_tokens: int = 1200,
) -> str:
    """Gemini로 작품 노트 초안 생성. 빈 문자열 반환 가능."""
    if router is None:
        router = _make_router()
        owns_router = True
    else:
        owns_router = False
    try:
        if router.gemini_client is None:
            raise RuntimeError("Gemini API 키가 설정되지 않았습니다.")
        sys_msg = (
            "당신은 일본 성인영상(JAV) 자막 번역 가이드 노트를 작성하는 도우미입니다. "
            "지시한 섹션 외 다른 섹션·서문·결론을 절대 출력하지 마십시오."
        )
        usr_msg = _WORK_NOTE_INSTRUCTIONS + "\n\n[자료]\n" + ctx.to_context_block()
        tier = _gemini_tier(model_id)
        out = await router.call_model(
            tier,
            [
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": usr_msg},
            ],
            temperature=0.4,
            max_tokens=max_tokens,
        )
        out = _strip_codefence(out)
        return _clip_section_headers(
            out,
            allowed=[
                "작품 기본 컨텍스트",
                "화자 프로필 및 관계",
                "Whisper AI 오인식 교정 사전",
                "용어/은어 매핑",
            ],
        )
    finally:
        if owns_router:
            try:
                await router.close()
            except Exception:
                pass


async def generate_actress_translation_note_async(
    ctx: ActressNoteContext,
    *,
    model_id: Optional[str] = None,
    router: Optional[MultiTierRouter] = None,
    max_tokens: int = 700,
) -> str:
    """Gemini로 배우 노트 초안 생성."""
    if router is None:
        router = _make_router()
        owns_router = True
    else:
        owns_router = False
    try:
        if router.gemini_client is None:
            raise RuntimeError("Gemini API 키가 설정되지 않았습니다.")
        sys_msg = (
            "당신은 일본 성인영상(JAV) 자막 번역 가이드 노트를 작성하는 도우미입니다. "
            "지시한 섹션 외 다른 섹션·서문·결론을 절대 출력하지 마십시오."
        )
        usr_msg = _ACTRESS_NOTE_INSTRUCTIONS + "\n\n[자료]\n" + ctx.to_context_block()
        tier = _gemini_tier(model_id)
        out = await router.call_model(
            tier,
            [
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": usr_msg},
            ],
            temperature=0.4,
            max_tokens=max_tokens,
        )
        out = _strip_codefence(out)
        return _clip_section_headers(
            out,
            allowed=["화자 프로필 및 관계", "고정 표기/호칭 사전"],
        )
    finally:
        if owns_router:
            try:
                await router.close()
            except Exception:
                pass


def generate_work_translation_note_blocking(ctx: WorkNoteContext, **kw: Any) -> str:
    return asyncio.run(generate_work_translation_note_async(ctx, **kw))


def generate_actress_translation_note_blocking(ctx: ActressNoteContext, **kw: Any) -> str:
    return asyncio.run(generate_actress_translation_note_async(ctx, **kw))
