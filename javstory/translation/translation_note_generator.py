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


# ── 파이프라인: JA 자막 + Grok → 6섹션 작품 번역 노트 ──────────────

_PIPELINE_NOTE_SECTIONS = (
    "기본 번역 규칙",
    "줄거리 요약",
    "등장 인물 요약",
    "말투에 대한 규칙",
    "용어 사전",
    "번역 스타일 지침",
)

_PIPELINE_NOTE_INSTRUCTIONS = """일본어 원본 자막 샘플과 (있으면) Grok 스토리 컨텍스트·작품 메타를 분석해,
JA→KO 자막 번역에 쓸 "작품 번역 노트"를 한국어로 작성하라.

[출력 규칙]
- 아래 6개 섹션 헤더를 **정확히** 이 이름으로, 이 순서대로 사용한다. 다른 섹션 금지.
- 각 섹션은 불릿(- ) 짧은 항목. 산문 장문 금지.
- 근거가 약한 항목은 생략(헤더만 두고 본문 비워도 됨).
- 사족·서문·결론·코드펜스·영어 장문 금지. 노트 텍스트만 출력.
- 용어 사전은 `원어 => 한국어` 형식만 사용.

[기본 번역 규칙]
- 직역 금지, 한글 전용, 고유명사 표기 등 작품 공통 규칙
- 존댓말/반말의 **세부 매핑은 [말투에 대한 규칙]에만** 적고, 여기에는 "말투 섹션 준수" 한 줄만

[줄거리 요약]
- 전체 흐름 3~6줄 (제목·시놉시스·Grok 요약 기반, 자막과 충돌 시 자막 우선 안내 포함)

[등장 인물 요약]
- 주요 인물별 한 줄 (이름/역할/관계). 자막·메타·Grok에서 확인되는 것만
- 가능하면 (여성1)/(남성1) 등 화자 라벨을 고정해 [말투]와 맞춰 쓴다

[말투에 대한 규칙]
- **필수**: 확인되는 화자마다 `화자 → 청자: 존댓말|반말|혼용` 형식으로 쓴다 (예: 여주 → 남주: 반말)
- 일본어 단서(です/ます, だ/よ, 敬語, タメ口)가 보이면 근거로 한 줄 덧붙인다
- 호칭(오빠/선생님/이름+さん 등)과 KO 고정 표기를 화자별로
- 씬·관계 변화에 따라 말투가 바뀌면 `초반/중반/후반` 또는 `친밀해진 뒤`처럼 조건을 명시
- "유연하게 적용" 같은 추상 문구만 쓰지 말 것. 구체 매핑이 우선

[용어 사전]
- 반복되는 고유명사·은어·호칭: 원어 => 한국어

[번역 스타일 지침]
- 구어체 밀도, 신음/의성어 처리, 과도한 순화 금지 등 스타일 포인트
"""

_PIPELINE_NOTE_INSTRUCTIONS_NO_GROK = """제목·시놉시스·일본어 원본 자막 샘플만 분석해,
JA→KO 자막 번역에 쓸 "작품 번역 노트"를 한국어로 작성하라.
(Grok 스토리 컨텍스트는 제공되지 않음 — 추측으로 채우지 말고 제목·시놉·자막에 근거가 있는 항목만.)

[출력 규칙]
- 아래 6개 섹션 헤더를 **정확히** 이 이름으로, 이 순서대로 사용한다. 다른 섹션 금지.
- 각 섹션은 불릿(- ) 짧은 항목. 산문 장문 금지.
- 근거가 약한 항목은 생략(헤더만 두고 본문 비워도 됨).
- 사족·서문·결론·코드펜스·영어 장문 금지. 노트 텍스트만 출력.
- 용어 사전은 `원어 => 한국어` 형식만 사용.
- **[말투에 대한 규칙]은 이 노트에서 가장 중요**하므로, 자막에서 확인되는 범위에서 최대한 상세히 쓴다.

[기본 번역 규칙]
- 직역 금지, 한글 전용, 고유명사 표기 등 작품 공통 규칙
- 존댓말/반말은 [말투에 대한 규칙]의 화자→청자 매핑을 따를 것 (여기에는 "말투 섹션 준수"만)

[줄거리 요약]
- 제목·시놉시스·자막에서 확인되는 흐름 3~6줄 (충돌 시 자막 우선)

[등장 인물 요약]
- 주요 인물별 한 줄 (역할/관계). 제목·시놉·자막 근거만
- 가능하면 (여성1)/(남성1) 또는 이름·역할 라벨을 고정해 [말투]와 동일하게 쓴다

[말투에 대한 규칙]
자막의 경어·종결(です/ます/だ/よ/ね/わ 등)·호칭·시놉의 관계를 보고 아래를 **불릿으로 상세히** 쓴다.
- **화자→청자 매핑(필수)**: `A → B: 존댓말` / `A → B: 반말` / `A → B: 혼용(조건)`
  예: `- (여성1) → (남성1): 반말` / `- (남성1) → (여성1): 존댓말(초면), 반말(친밀 후)`
- **일본어 근거**: 해당 말투를 뒷받침하는 원문 패턴 1줄 (예: 여주 종결 `…だよ`/`…て` → KO 반말)
- **호칭**: 누가 누구를 뭐라고 부르는지 + KO 고정 (예: `お姉さん => 누나`, `先生 => 선생님`)
- **톤**: 주도/복종, 애교, 거친 구어, 사무적 등 화자별 1줄
- **변화**: 초반↔후반·관계 진전에 따라 존댓↔반말이 바뀌면 조건을 명시
- 금지: "관계·분위기에 따라 유연하게"처럼만 적고 끝내기. 매핑 불릿이 없으면 실패로 간주하고 다시 쓸 것

[용어 사전]
- 반복되는 고유명사·은어·호칭: 원어 => 한국어

[번역 스타일 지침]
- 구어체 밀도, 신음/의성어 처리, 과도한 순화 금지 등 스타일 포인트
"""


def sample_ja_dialogue_from_segments(
    segments: list[Any],
    *,
    max_chars: int = 2800,
    max_lines: int = 80,
) -> str:
    """자막 세그먼트에서 초반+중반+후반을 고르게 뽑아 노트 분석용 샘플을 만든다."""
    texts = [(getattr(s, "text", None) or "").strip() for s in (segments or [])]
    texts = [t for t in texts if t]
    if not texts:
        return ""
    if len(texts) <= max_lines:
        picked = texts
    else:
        n = max_lines
        step = max(1, len(texts) // n)
        picked = [texts[i] for i in range(0, len(texts), step)][:n]
        # 초반 대사는 말투 파악에 중요
        head = texts[: min(12, len(texts))]
        for h in reversed(head):
            if h not in picked:
                picked.insert(0, h)
        picked = picked[:n]
    lines: list[str] = []
    total = 0
    for i, t in enumerate(picked):
        row = f"{i}: {t}"
        if total + len(row) + 1 > max_chars:
            break
        lines.append(row)
        total += len(row) + 1
    return "\n".join(lines)


def load_product_title_synopsis(product_code: str) -> dict[str, str]:
    """DB에서 제목·시놉시스만 로드 (Grok 없이 노트 생성용)."""
    pc = (product_code or "").strip().upper()
    out = {"title_ja": "", "title_ko": "", "synopsis": ""}
    if not pc:
        return out
    try:
        from javstory.harvest.database import get_db_session, JAVMetadata

        session = get_db_session()
        try:
            row = session.query(JAVMetadata).filter_by(product_code=pc).first()
            if not row:
                return out
            out["title_ko"] = str(getattr(row, "title_ko", "") or "").strip()
            out["title_ja"] = str(
                getattr(row, "title_ja", "") or getattr(row, "original_title", "") or ""
            ).strip()
            syn = (
                getattr(row, "synopsis_ko", "")
                or getattr(row, "synopsis", "")
                or getattr(row, "synopsis_ja", "")
                or ""
            )
            out["synopsis"] = str(syn or "").strip()[:1200]
        finally:
            session.close()
    except Exception:
        pass
    return out


def _pipeline_note_user_payload(
    *,
    product_code: str,
    grok_json: dict[str, Any] | None,
    ja_sample: str,
    title_ja: str = "",
    title_ko: str = "",
    synopsis: str = "",
) -> str:
    from javstory.translation.story_context_prompts import format_story_context_for_translation

    has_grok = isinstance(grok_json, dict) and bool(grok_json)
    instructions = _PIPELINE_NOTE_INSTRUCTIONS if has_grok else _PIPELINE_NOTE_INSTRUCTIONS_NO_GROK
    parts = [instructions, "", "[자료]"]
    parts.append(f"품번: {(product_code or '').strip()}")
    title_line = " / ".join(x for x in (title_ko.strip(), title_ja.strip()) if x)
    if title_line:
        parts.append(f"제목: {title_line}")
    if (synopsis or "").strip():
        parts.append(f"시놉시스:\n{(synopsis or '').strip()}")
    if has_grok:
        grok_block = format_story_context_for_translation(grok_json, compact=False)
        if len(grok_block) > 3500:
            grok_block = grok_block[:3499].rstrip() + "…"
        parts.append("")
        parts.append("[Grok 스토리 컨텍스트]")
        parts.append(grok_block)
    parts.append("")
    parts.append("[일본어 원본 자막 샘플]")
    parts.append((ja_sample or "").strip() or "(샘플 없음)")
    return "\n".join(parts)


def _env_truthy(name: str, default: bool = True) -> bool:
    raw = (os.environ.get(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def translation_auto_note_enabled() -> bool:
    return _env_truthy("JAVSTORY_TRANSLATION_AUTO_NOTE", True)


def _pipeline_note_max_tokens(default: int = 4096) -> int:
    raw = (os.environ.get("JAVSTORY_TRANSLATION_NOTE_MAX_TOKENS", "") or "").strip()
    try:
        n = int(raw) if raw else default
    except ValueError:
        n = default
    return max(1024, min(n, 8192))


def pipeline_note_looks_incomplete(note: str) -> bool:
    """max_tokens 절단·조기 종료로 6섹션이 비어 있거나 본문이 끊긴 노트 감지."""
    from javstory.translation.translation_notes import PIPELINE_NOTE_SECTIONS

    text = (note or "").strip()
    if not text:
        return True
    headers = sum(
        1
        for h in PIPELINE_NOTE_SECTIONS
        if re.search(rf"^\[{re.escape(h)}\]\s*$", text, re.MULTILINE)
    )
    if headers < 5:
        return True
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return True
    last = lines[-1].strip()
    # 마지막 줄이 불릿인데 문장이 끝나지 않았고, 섹션도 6개 미만이면 절단으로 간주
    if headers < 6 and last.startswith("-") and len(last) < 80:
        if not re.search(r"[.!?…다요음임함됨]$", last):
            return True
    # 말투 섹션에 화자→청자 매핑이 없으면(추상 문구만) 재생성 대상
    m = re.search(
        r"\[말투에 대한 규칙\]\s*\n([\s\S]*?)(?=\n\[[^\]]+\]|\Z)",
        text,
    )
    if m:
        speech = (m.group(1) or "").strip()
        if speech and ("→" not in speech and "->" not in speech):
            return True
    return False


async def generate_pipeline_translation_note_async(
    *,
    product_code: str,
    grok_json: dict[str, Any] | None,
    ja_segments: list[Any],
    router: Optional[MultiTierRouter] = None,
    max_tokens: int | None = None,
    title_ja: str = "",
    title_ko: str = "",
    synopsis: str = "",
) -> str:
    """JA 자막 + (있으면) Grok / 없으면 제목·시놉시스 → 6섹션 작품 번역 노트.

    Gemini 우선, 없으면 OpenRouter(스토리/번역 티어) 폴백.
    """
    from javstory.translation.translation_notes import PIPELINE_NOTE_SECTIONS

    has_grok = isinstance(grok_json, dict) and bool(grok_json)
    ja_sample = sample_ja_dialogue_from_segments(
        ja_segments,
        max_chars=3800 if not has_grok else 2800,
        max_lines=110 if not has_grok else 80,
    )
    meta_ok = bool((title_ja or title_ko or synopsis or "").strip())
    if not ja_sample and not has_grok and not meta_ok:
        return ""

    if router is None:
        router = _make_router()
        owns_router = True
    else:
        owns_router = False

    tok = int(max_tokens) if isinstance(max_tokens, int) and max_tokens > 0 else _pipeline_note_max_tokens()
    sys_msg = (
        "당신은 일본 성인영상(JAV) JA→KO 자막 번역 가이드 노트를 작성하는 도우미입니다. "
        "지정한 6개 섹션을 모두, 끝까지 출력하십시오. 중간에 끊지 마십시오. "
        "서문·결론·코드펜스를 넣지 마십시오."
    )
    usr_msg = _pipeline_note_user_payload(
        product_code=product_code,
        grok_json=grok_json,
        ja_sample=ja_sample,
        title_ja=title_ja,
        title_ko=title_ko,
        synopsis=synopsis,
    )
    messages = [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": usr_msg},
    ]

    async def _once(limit: int) -> str:
        out_local = ""
        if router.gemini_client is not None:
            try:
                out_local = await router.call_model(
                    _gemini_tier("gemini-2.5-flash"),
                    messages,
                    temperature=0.35,
                    max_tokens=limit,
                )
            except Exception:
                out_local = ""
        if not (out_local or "").strip():
            from javstory.config.app_config import library_story_context_batch_tier

            tier = dict(library_story_context_batch_tier() or {})
            if not tier.get("provider"):
                tier = {
                    "provider": "openrouter",
                    "model": os.environ.get(
                        "JAVSTORY_TRANSLATION_NOTE_MODEL",
                        "google/gemini-2.5-flash",
                    ).strip()
                    or "google/gemini-2.5-flash",
                    "name": "translation_note_openrouter",
                }
            # 스토리 티어의 웹검색 한도와 분리 — 노트 생성만의 max_tokens 사용
            tier = {**tier, "max_tokens": limit}
            out_local = await router.call_model(
                tier,
                messages,
                temperature=0.35,
                max_tokens=limit,
            )
        out_local = _strip_codefence(out_local or "")
        return _clip_section_headers(out_local, allowed=list(PIPELINE_NOTE_SECTIONS))

    try:
        out = await _once(tok)
        if pipeline_note_looks_incomplete(out):
            retry_tok = min(8192, max(tok + 1024, int(tok * 1.5)))
            retry_msg = (
                usr_msg
                + "\n\n[재시도] 이전에 출력이 중간에 끊겼습니다. "
                "6개 섹션 헤더를 모두 포함해 처음부터 끝까지 다시 작성하십시오."
            )
            messages = [
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": retry_msg},
            ]
            out2 = await _once(retry_tok)
            if out2.strip() and (
                not pipeline_note_looks_incomplete(out2)
                or len(out2.strip()) > len((out or "").strip())
            ):
                out = out2
        return out
    finally:
        if owns_router:
            try:
                await router.close()
            except Exception:
                pass


async def ensure_pipeline_work_note_async(
    *,
    product_code: str,
    grok_json: dict[str, Any] | None,
    ja_segments: list[Any],
    router: Optional[MultiTierRouter] = None,
    logger_func: Any = None,
    force: bool = False,
) -> str:
    """작품 노트가 비어 있거나 불완전하면 JA+(Grok 또는 제목/시놉)으로 생성·저장 후 반환."""
    from javstory.translation.translation_notes import (
        load_work_translation_note,
        save_work_translation_note,
    )

    log = logger_func or print
    if not translation_auto_note_enabled() and not force:
        return load_work_translation_note(product_code)

    existing = load_work_translation_note(product_code)
    if existing.strip() and not force and not pipeline_note_looks_incomplete(existing):
        log(f"[Orchestrator] 작품 번역 노트 기존 사용 ({len(existing)}자)")
        return existing
    if existing.strip() and pipeline_note_looks_incomplete(existing) and not force:
        log(
            f"[Orchestrator] 작품 번역 노트 불완전 감지 ({len(existing)}자) — 재생성"
        )

    meta = load_product_title_synopsis(product_code)
    has_grok = isinstance(grok_json, dict) and bool(grok_json)
    if has_grok:
        log("[Orchestrator] 작품 번역 노트 생성 중 — JA 자막 + Grok 컨텍스트 분석")
    else:
        log("[Orchestrator] 작품 번역 노트 생성 중 — 제목·시놉시스·JA 자막 분석 (Grok 없음)")
    note = await generate_pipeline_translation_note_async(
        product_code=product_code,
        grok_json=grok_json,
        ja_segments=ja_segments,
        router=router,
        title_ja=meta.get("title_ja", ""),
        title_ko=meta.get("title_ko", ""),
        synopsis=meta.get("synopsis", ""),
    )
    note = (note or "").strip()
    if not note:
        log("[Orchestrator] 작품 번역 노트 생성 실패/빈 결과 — 노트 없이 번역 계속")
        return existing
    if pipeline_note_looks_incomplete(note):
        log(
            f"[Orchestrator] 작품 번역 노트 여전히 짧음/불완전 ({len(note)}자) — "
            "저장은 하되 다음 실행 시 재시도 가능"
        )
    try:
        save_work_translation_note(product_code, note)
        log(f"[Orchestrator] 작품 번역 노트 저장 완료 ({len(note)}자)")
    except Exception as e:
        log(f"[Orchestrator] 작품 번역 노트 저장 실패(무시): {e}")
    return note
