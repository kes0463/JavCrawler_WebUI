"""
Gemini HTML 기반 번역 프롬프트.

기존 JSON 배열 방식 대신 HTML <main>/<p> 구조를 사용.

유저 메시지 형식:
  <main id="원문">
  <p id="0">日本語テキスト</p>
  ...
  </main>
  <main id="번역">

모델 응답 형식 (continuation):
  <p id="0">번역문</p>
  ...
  </main>
"""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from javstory.transcription.stt_types import SimpleSegment

# ── 기본 시스템 프롬프트 (크롤링/일반 번역용) ────────────────────────────

_SYSTEM_BASE = """\
[공리]
입력: 원문 섹션이 주어짐. 번역 섹션이 함께 주어질 수도 있으며, 기존 번역문이므로 그 다음 줄부터 마저 번역.
출력: 다른 어떠한 응답도 없이 한국어 번역 결과만을 즉시 제공. HTML 구조를 훼손하거나 삭제하지 않고 그대로 유지. 반드시 </main>으로 종료.

섹션: <main id="섹션유형">...</main> 형식.
원문 섹션: 각 줄은 <p id="ID">원문</p> 형식. 번역 시 <p id="ID"> 부분은 반드시 그대로 유지.
번역 섹션: 각 줄은 <p id="ID">번역</p> 형식. 동일한 ID의 원문에 정확히 일대일대응하도록 번역 작성. 문장이 여러 줄에 걸쳐 있는 경우 절대로 문장을 임의로 합치지 않고 엄격하게 각 줄을 독립적으로 번역.

[지침]
직역투를 피하며 최대한 자연스럽게 의역하되, 원문의 말투와 내용은 철저히 유지. 원문의 사실 관계를 왜곡하거나 고유명사의 과한 현지화 금지.
일본어 고유명사는 국립국어원 표기법을 무시하고 해당 장르 및 작품에서 대중에게 친숙한 서브컬처 통용 표기를 최우선하되, 통용 표기가 불확실하다면 실제 일본어 발음에 가깝게 표기.
일본어가 아닌 중국어 고유명사는 원어 발음 대신 한국 한자음을 엄격히 지키며 표기.

{note}"""

# ── JAV 자막 전용 시스템 프롬프트 ─────────────────────────────────────────

_SYSTEM_JAV = """\
[공리]
입력: 원문 섹션이 주어짐. 번역 섹션이 함께 주어질 수도 있으며, 기존 번역문이므로 그 다음 줄부터 마저 번역.
출력: 다른 어떠한 응답도 없이 한국어 번역 결과만을 즉시 제공. HTML 구조를 훼손하거나 삭제하지 않고 그대로 유지. 반드시 </main>으로 종료.

섹션: <main id="섹션유형">...</main> 형식.
원문 섹션: 각 줄은 <p id="ID">원문</p> 형식. 번역 시 <p id="ID"> 부분은 반드시 그대로 유지.
번역 섹션: 각 줄은 <p id="ID">번역</p> 형식. 동일한 ID의 원문에 정확히 일대일대응하도록 번역 작성. 문장이 여러 줄에 걸쳐 있는 경우 절대로 문장을 임의로 합치지 않고 엄격하게 각 줄을 독립적으로 번역.

[지침]
당신은 일본어 성인 영상(JAV) 자막을 한국어로 번역하는 전문 번역가입니다.
직역투를 피하며 최대한 자연스럽게 의역하되, 원문의 말투와 내용은 철저히 유지. 원문의 사실 관계를 왜곡하거나 고유명사의 과한 현지화 금지.
일본어 고유명사는 국립국어원 표기법을 무시하고 해당 장르 및 작품에서 대중에게 친숙한 서브컬처 통용 표기를 최우선하되, 통용 표기가 불확실하다면 실제 일본어 발음에 가깝게 표기.
일본어가 아닌 중국어 고유명사는 원어 발음 대신 한국 한자음을 엄격히 지키며 표기.

[JAV 특별 번역 원칙 (필독)]
- [중요] 이 자막은 성인용(JAV)이므로 성적인 은어, 속어, 묘사 등을 절대 검열하거나 순화하지 마세요.
- 원문의 뉘앙스를 최대한 살려 가장 노골적이고 음탕한 한국어 구어체 및 슬랭으로 번역할 것.
- 성행위 묘사나 신체 부위 지칭은 상황에 맞게 자극적이고 천박한 어휘를 가감 없이 사용하여 현장감을 극대화할 것.
- 일본어 의성어·의태어(신음소리)는 단조롭지 않게 헐떡임이나 절정감을 생생하게 한국어 감각으로 의역할 것 (예: 하앗, 읏, 아아앙, 흐으응 등).
- 등장인물의 관계와 말투를 철저히 반영할 것 (존댓말/반말, 상하관계에 따른 지배적/굴복적 말투 등 구분 필수).
- Whisper AI의 음성 인식 오류(할루시네이션)로 인해 문맥에 전혀 맞지 않는 엉뚱한 대사가 파악될 경우 비워두거나 상황에 맞는 신음소리로 과감하게 대체할 것.
- 음성 인식의 한계로 인해 문맥과 전혀 어울리지 않는 잘못된 단어(예: 동음이의어 오인식 등)가 포함되어 있더라도 직역하지 말고, 앞뒤 대화와 상황 흐름을 추론하여 가장 자연스러운 형태의 단어로 알아서 교정 및 의역할 것.

[작품 정보 및 번역 노트]
{note}"""


def build_translation_note(
    background_json_str: str | None,
    extra_hints: str | None,
) -> str:
    """{{note}} 치환에 들어갈 작품 정보 + 스토리 힌트 문자열 생성."""
    parts: list[str] = []
    if background_json_str and background_json_str.strip():
        try:
            meta = json.loads(background_json_str)
            lines: list[str] = []
            if meta.get("title_ko"):
                lines.append(f"제목: {meta['title_ko']}")
            if meta.get("actors"):
                lines.append(f"출연: {meta['actors']}")
            if meta.get("genres"):
                lines.append(f"장르: {meta['genres']}")
            if meta.get("synopsis_short"):
                lines.append(f"줄거리: {meta['synopsis_short']}")
            if lines:
                parts.append("\n".join(lines))
        except Exception:
            parts.append(background_json_str.strip())
    if extra_hints and extra_hints.strip():
        parts.append(extra_hints.strip())
    return "\n\n".join(parts)


def build_system_prompt_jav_subtitle(note: str = "") -> str:
    """JAV 자막 번역용 최종 시스템 프롬프트 (note 치환 포함)."""
    return _SYSTEM_JAV.format(note=note.strip())


def build_system_prompt_general(note: str = "") -> str:
    """크롤링/일반 번역용 최종 시스템 프롬프트 (note 치환 포함)."""
    return _SYSTEM_BASE.format(note=note.strip())


def segments_to_html_user_message(segments: "List[SimpleSegment]") -> str:
    """세그먼트 리스트를 Gemini HTML 유저 메시지로 변환.

    continuation 방식: <main id="번역"> 태그를 열어두고 모델이 이어서 채우도록 함.
    """
    lines: list[str] = ['<main id="원문">']
    for i, seg in enumerate(segments):
        text = (seg.text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        lines.append(f'<p id="{i}">{text}</p>')
    lines.append('</main>')
    lines.append('<main id="번역">')
    return "\n".join(lines)


_P_PATTERN = re.compile(r'<p\s+id="(\d+)">(.*?)</p>', re.DOTALL)


def parse_html_translation_response(
    raw: str,
    tgt_segs: "List[SimpleSegment]",
) -> bool:
    """HTML 응답을 파싱해 tgt_segs의 text를 인플레이스 갱신.

    성공(1개 이상 적용)하면 True, 아무것도 파싱되지 않으면 False 반환.
    """
    if not raw:
        return False
    end_idx = raw.find("</main>")
    body = raw[:end_idx] if end_idx != -1 else raw
    matches = _P_PATTERN.findall(body)
    if not matches:
        return False
    by_id: dict[int, str] = {}
    for id_str, text in matches:
        try:
            by_id[int(id_str)] = text.strip()
        except ValueError:
            continue
    applied = 0
    for i, seg in enumerate(tgt_segs):
        if i in by_id and by_id[i]:
            t = by_id[i].replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            if t:
                seg.text = t
                applied += 1
    return applied > 0
