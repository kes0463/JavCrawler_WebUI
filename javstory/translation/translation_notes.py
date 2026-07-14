"""
번역 노트(Translation Note) 저장소·로더·결합기.

노트는 3계층으로 관리:
- 전역(Global): `data/notes/translation_note_global.txt` 파일 1개. 모든 작품에 공통 적용.
- 배우(Actress): DB `actresses.translation_note` 컬럼. 같은 배우의 모든 작품에 공통 적용.
- 작품(Work): `library_state.json`의 `translation_note` 필드. 해당 품번 한정.

우선순위(중복/충돌 시): 작품 > 배우 > 전역
최종 결합 결과는 Gemini 프롬프트의 `{{note}}`에 들어간다.

섹션 헤더(권장):
- [기본 번역 규칙]
- [줄거리 요약]
- [등장 인물 요약]
- [말투에 대한 규칙]
- [용어 사전]
- [번역 스타일 지침]
- (레거시) [작품 기본 컨텍스트] [화자 프로필 및 관계] [Whisper AI 오인식 교정 사전]
  [용어/은어 매핑] [고정 표기/호칭 사전] [전역 규칙]

사용자가 자유 텍스트로 적어도 동작하지만, 위 헤더를 쓰면 자동 합치기 시
같은 섹션 내용을 한 곳에 모아준다. 헤더가 없는 자유 텍스트는 [기타]로 묶인다.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable

from javstory.config.app_config import DATA_ROOT

# ── 저장 경로 ─────────────────────────────────────────────────────

NOTES_DIR = DATA_ROOT / "notes"
GLOBAL_NOTE_PATH = NOTES_DIR / "translation_note_global.txt"


# ── 길이 가드(토큰 폭증 방지) ────────────────────────────────────

MAX_GLOBAL = 800
MAX_ACTRESS = 600
MAX_WORK = 4500
MAX_COMBINED = 7000


# ── 섹션 헤더 ─────────────────────────────────────────────────────

# 표시 순서(고정). 사용자가 임의 헤더 쓰면 [기타]로 합쳐짐.
KNOWN_SECTIONS: tuple[str, ...] = (
    "기본 번역 규칙",
    "줄거리 요약",
    "등장 인물 요약",
    "말투에 대한 규칙",
    "용어 사전",
    "번역 스타일 지침",
    # 레거시
    "작품 기본 컨텍스트",
    "화자 프로필 및 관계",
    "Whisper AI 오인식 교정 사전",
    "용어/은어 매핑",
    "고정 표기/호칭 사전",
    "전역 규칙",
)

PIPELINE_NOTE_SECTIONS: tuple[str, ...] = (
    "기본 번역 규칙",
    "줄거리 요약",
    "등장 인물 요약",
    "말투에 대한 규칙",
    "용어 사전",
    "번역 스타일 지침",
)

_SECTION_HEADER_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")


# ── 파일 입출력(전역 노트) ───────────────────────────────────────


def load_global_note() -> str:
    """파일 우선, 없으면 환경변수 폴백(기존 호환). 둘 다 없으면 빈 문자열."""
    try:
        if GLOBAL_NOTE_PATH.is_file():
            return GLOBAL_NOTE_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        pass
    return os.environ.get("JAVSTORY_TRANSLATION_NOTE_GLOBAL", "") or ""


def save_global_note(text: str) -> None:
    """전역 노트를 파일로 저장. 빈 문자열이면 파일 삭제."""
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    s = (text or "").strip()
    if not s:
        try:
            if GLOBAL_NOTE_PATH.is_file():
                GLOBAL_NOTE_PATH.unlink()
        except OSError:
            pass
        return
    GLOBAL_NOTE_PATH.write_text(s + "\n", encoding="utf-8")


# ── 섹션 파싱·재결합 ─────────────────────────────────────────────


@dataclass
class NoteSections:
    """섹션 헤더별 본문 텍스트 매핑(자유 텍스트 + 헤더 인식)."""

    sections: dict[str, list[str]] = field(default_factory=dict)

    def add(self, header: str, body: str) -> None:
        body = (body or "").strip()
        if not body:
            return
        h = (header or "기타").strip()
        self.sections.setdefault(h, []).append(body)

    def merge(self, other: NoteSections) -> None:
        for h, parts in other.sections.items():
            for p in parts:
                self.add(h, p)

    def to_text(self) -> str:
        """알려진 섹션 우선 → 그 외 알파벳 순. 빈 섹션은 생략."""
        out: list[str] = []
        ordered: list[str] = []
        for known in KNOWN_SECTIONS:
            if known in self.sections:
                ordered.append(known)
        for h in sorted(self.sections.keys()):
            if h in ordered:
                continue
            ordered.append(h)
        for h in ordered:
            parts = [p for p in self.sections[h] if p.strip()]
            if not parts:
                continue
            out.append(f"[{h}]")
            out.append("\n\n".join(parts))
            out.append("")
        return "\n".join(out).rstrip()


def parse_note_sections(text: str) -> NoteSections:
    """`[섹션명]` 헤더로 구획된 자유 텍스트를 섹션 딕셔너리로 분해."""
    res = NoteSections()
    if not text or not text.strip():
        return res

    lines = (text or "").splitlines()
    current_header = "기타"
    buf: list[str] = []

    def _flush() -> None:
        if buf:
            res.add(current_header, "\n".join(buf).strip())

    for line in lines:
        m = _SECTION_HEADER_RE.match(line)
        if m:
            _flush()
            buf = []
            current_header = m.group(1).strip() or "기타"
        else:
            buf.append(line)
    _flush()
    return res


# ── 용어 매핑 추출 ────────────────────────────────────────────────

# `원어 => 번역어` 또는 `원어 -> 번역어` 또는 `원어 :: 번역어`
_GLOSS_LINE_RE = re.compile(
    r"^\s*[-*•]?\s*(?P<src>[^=>:\-\n][^=>:\n]*?)\s*(?:=>|->|::)\s*(?P<dst>.+?)\s*$"
)


def extract_glossary(text: str) -> list[tuple[str, str]]:
    """[용어 사전] / [용어/은어 매핑] / [고정 표기/호칭 사전] 섹션에서 (원어, 번역어) 쌍 추출.

    형식 허용:
      - 원어 => 번역어
      - 원어 -> 번역어
      - 원어 :: 번역어

    중복 키는 마지막 값 우선. 키/값이 비어있으면 무시.
    """
    res: dict[str, str] = {}
    sects = parse_note_sections(text)
    for header in ("용어 사전", "용어/은어 매핑", "고정 표기/호칭 사전"):
        for body in sects.sections.get(header, []):
            for line in body.splitlines():
                if not line.strip():
                    continue
                m = _GLOSS_LINE_RE.match(line)
                if not m:
                    continue
                src = (m.group("src") or "").strip()
                dst = (m.group("dst") or "").strip()
                # 괄호 주석 제거(예: "원어 (설명) => 번역어")
                src = re.sub(r"\s*\([^)]*\)\s*", "", src).strip()
                if src and dst:
                    res[src] = dst
    # 긴 키 우선 적용을 위해 길이 내림차순 정렬
    return sorted(res.items(), key=lambda kv: len(kv[0]), reverse=True)


def apply_glossary_to_text(text: str, glossary: Iterable[tuple[str, str]]) -> str:
    """LLM 번역 결과에 남아있는 원어를 강제 치환.

    안전 가드:
    - 정확히 동일한 부분 문자열만 치환(정규식 대신 단순 replace).
    - 한국어/공백 사이에 끼어있어도 부분 일치하면 치환되므로,
      매핑은 사용자 책임 하에 명확한 토큰만 등록할 것.
    """
    out = text or ""
    for src, dst in glossary:
        if not src:
            continue
        if src in out:
            out = out.replace(src, dst)
    return out


# ── 결합기(전역+배우+작품) ───────────────────────────────────────


def _truncate(s: str, max_chars: int) -> str:
    s = (s or "").strip()
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1].rstrip() + "…"


def combine_translation_notes(
    *,
    global_note: str = "",
    actress_note: str = "",
    work_note: str = "",
) -> str:
    """3계층 노트를 섹션 단위로 합쳐 단일 텍스트로 반환.

    - 길이 제한: 각 계층 상한 + 합산 상한.
    - 동일 섹션이 여러 계층에 있을 때, 표시는 작품 → 배우 → 전역 순으로 누적.
      (모델은 위쪽을 더 강하게 본다고 가정 → 작품 우선)
    """
    g = _truncate(global_note, MAX_GLOBAL)
    a = _truncate(actress_note, MAX_ACTRESS)
    w = _truncate(work_note, MAX_WORK)

    combined = NoteSections()

    if w:
        combined.merge(parse_note_sections(w))
    if a:
        # 배우 노트는 [캐릭터 가이드] 같은 섹션이 자주 들어감 → 그대로 합침
        combined.merge(parse_note_sections(a))
    if g:
        # 전역은 보통 [전역 규칙] 섹션이 우세
        combined.merge(parse_note_sections(g))

    text = combined.to_text()
    return _truncate(text, MAX_COMBINED)


# ── 배경(JSON) → 노트 보조 ────────────────────────────────────────


def background_to_note_summary(background_json: dict[str, Any] | None) -> str:
    """기존 `background_json_str`을 사람 읽기 쉬운 4~6줄 요약으로 변환.

    오케스트레이터가 만드는 `_build_background_from_db` 결과와 호환.
    """
    if not isinstance(background_json, dict):
        return ""
    parts: list[str] = []
    pc = str(background_json.get("product_code", "") or "").strip()
    if pc:
        parts.append(f"품번: {pc}")
    title_ko = str(background_json.get("title_ko", "") or "").strip()
    title_ja = str(background_json.get("title_ja", "") or "").strip()
    if title_ko or title_ja:
        if title_ko and title_ja:
            parts.append(f"제목: {title_ko} / {title_ja}")
        else:
            parts.append(f"제목: {title_ko or title_ja}")
    actors = str(background_json.get("actors", "") or "").strip()
    if actors:
        parts.append(f"출연: {actors}")
    genres = str(background_json.get("genres", "") or "").strip()
    if genres:
        parts.append(f"장르: {genres}")
    syn = str(background_json.get("synopsis_short", "") or "").strip()
    if syn:
        parts.append(f"줄거리: {_truncate(syn, 400)}")
    return "\n".join(parts).strip()


def save_work_translation_note(product_code: str, note: str) -> Path | None:
    """작품 단위 번역 노트를 library_state.json에 저장. 성공 시 경로."""
    pc = (product_code or "").strip().upper()
    if not pc:
        return None
    from javstory.library.canonical.store import save_library_state
    from javstory.library.detail_persist import load_canonical_for_product
    from javstory.library.paths import library_state_path

    state = load_canonical_for_product(pc)
    state = replace(state, translation_note=str(note or "").strip())
    path = library_state_path(pc)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_library_state(path, state)
    return path


def load_work_translation_note(product_code: str) -> str:
    pc = (product_code or "").strip().upper()
    if not pc:
        return ""
    try:
        from javstory.library.detail_persist import load_canonical_for_product

        return str(getattr(load_canonical_for_product(pc), "translation_note", "") or "").strip()
    except Exception:
        return ""
