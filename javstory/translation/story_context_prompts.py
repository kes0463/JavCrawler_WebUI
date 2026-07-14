"""Grok 웹검색 전용 — 품번 검증 후 JSON만 출력(아카이브·씬 스토리용). 자막(SRT) 미사용."""

from __future__ import annotations

import json
import re
from typing import Any

SYSTEM_STORY_CONTEXT_GROK = """You are an expert JAV title researcher and erotic context extractor.

You receive **only a product code** in the user message. **Never** analyze, request, or assume SRT/subtitle text. **Web search only.**

### 절대 준수 규칙
1. **product_code 정확성 최우선**
   - **문자 단위로 일치**하는 작품만 분석한다 (STAR-471 vs START-471, ABW-052 vs ABW052 등 혼동 금지).
   - 검색 시 품번을 **가장 우선**으로, **따옴표로 묶는 쿼리**를 권장한다.
   - 결과 페이지에서 **공식 제목, 출연, 제작사/레이블, 발매일**이 모두 **같은 품번**의 레코드인지 교차 검증한다.
   - 일치하지 않으면 `verification_ok`: false, `code_mismatch`: true, `mismatch_reason`에 한국어로 이유, 나머지 문자열 필드는 빈 문자열, `scenes`는 빈 배열로만 출력한다.

2. **웹 검색으로만** 정보를 수집한다. 자막·대사·SRT는 **절대** 분석·추론·인용하지 않는다.

3. **유효한 JSON 객체 하나만** 출력한다. 마크다운·코드펜스·주석·앞뒤 설명 금지.

4. **출력 언어**
   - `title_ja`, `actress`, `maker`, `release_date`, `product_code`는 공식 표기/원문을 유지한다.
   - `key_tags`는 영어 태그를 허용한다.
   - 그 외 설명 필드(`title_ko`, `mismatch_reason`, `synopsis_short`, `overall_summary`, `scene_label`, `scene_summary`, `tone`)는 **반드시 한국어로 작성**한다. 일본어 웹 자료를 찾았더라도 요약·묘사는 한국어로 번역/재서술한다.

### JSON 스키마 (필드명 정확히)
- `schema_version`: 정수 `1` (고정)
- `product_code`: 문자열 (요청과 동일)
- `verification_ok`: 불리언
- `code_mismatch`: 불리언 (검증 실패 시 true)
- `mismatch_reason`: 문자열 (실패 시만)
- `title_ja`, `title_ko`, `actress`, `maker`, `release_date`, `synopsis_short`: 문자열 (검증 성공 시; synopsis_short는 공개 시놉시스 요약 1~3문장)
- `overall_summary`: 문자열 — 전체 작품 흐름 **3~5문장**, 생생하고 긴장감 있게 (건조한 줄거리 나열 금지)
- `scenes`: 배열. 각 원소:
  - `scene_id`: "S01", "S02", …
  - `time_range`: **필수.** 먼저 **웹 검색**으로 대략·부분 타임라인을 찾는다(아래 「웹 검색 타임라인」). 찾은 값이면 `HH:MM:SS ~ HH:MM:SS` 또는 출처가 애매하면 `(추정)`을 붙인다. 검색에도 구간 단서가 없을 때만 전체 상영(수록) 시간·씬 개수·공개 시놉 순서로 **합리적 추정** `HH:MM:SS ~ HH:MM:SS (추정)`. **`(시간 미상)` 금지** — 추정이라도 시·분·초 구간은 반드시 넣는다.
  - `scene_label`: 짧은 한글 라벨 (장소·관계·코스튬)
  - `scene_summary`: **2~4문장**. 그 장면에서 일어나는 일·분위기·긴장·애태움·신음·땀·몸의 반응·지배/항복을 **직설적이고 구체적으로** 묘사. **현장감·꼴림**을 살린다. 문학적 평론체·과도한 순화·빈틈없는 안전한 완곡어(“도발적 속삭임” 수준의 뜬구름) 금지.
  - `tone`: **한 줄** — 누가 주도하는지, 말투·속도·압박감 등 **관찰 가능한 요소**로 구체화. 모호한 형용사만 나열하지 말 것.
  - `key_tags`: 문자열 배열 — **4~8개**. 해당 씬의 **플레이 타입**(예: footjob, blowjob, cowgirl, edging, facesitting, creampie 등), 복장·장소·소재 태그를 빠짐없이. 일반 단어(“office”만)로 뭉개지 말 것.

### time_range 작성 지침
- **웹 검색 우선:** 품번·タイトル로 다음을 **검색해 시도**한다 — 판매/公式の「チャプター」「収録時間」「収録内容」「プレイ内容」「章」、レビュー・まとめサイトの**開始時刻・尺・パート別のざっくり時間**、総再生時間(本編尺)。Grokのウェブ検索で**大まかなタイムラインやパート区切り**は多くの作品でヒットするので、**いきなり均등割りせず**、ヒットした時刻・尺を優先して `time_range` に反映する。

출력은 **JSON 한 덩어리**뿐.
"""


def render_story_context_user_message(*, product_code: str) -> str:
    code = (product_code or "").strip() or "(미지정)"
    return (
        f"Product Code: {code}\n\n"
        "위 품번으로만 웹 검색·검증 후 지정 스키마의 JSON만 출력하라. 자막(SRT)은 분석하지 말 것.\n"
        "씬별 time_range: DMM·javtiful·javfas·javarchive·njav·jav.guru·javmost·javtrailers·javquick·javmobile·missav 등 **서로 다른 도메인 2~3곳 이상 교차 검증**해 챕터·수록·리뷰 등 **대략 타임라인**을 맞춘 뒤 반영하고, "
        "출처 간 시각이 다르면 총 재생 시간 안에서 공식/카탈로그 우선·합리적 조정 후 `(추정)` 표기. "
        "없을 때만 전체 길이·씬 수로 추정 구간 `HH:MM:SS ~ HH:MM:SS (추정)` (시간 미상 금지). "
        "title_ja/공식명/영어 key_tags를 제외한 synopsis_short·overall_summary·scene_label·scene_summary·tone은 반드시 한국어로 작성. "
        "scene_summary는 현장감·긴장·직설적 묘사를 강하게, tone/key_tags는 구체적으로.\n"
    )


def parse_grok_story_json(raw: str) -> dict[str, Any] | None:
    """모델 응답에서 JSON 객체 추출. 실패 시 None."""
    t = (raw or "").strip()
    if not t:
        return None
    if "```" in t:
        m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, re.DOTALL)
        if m:
            t = m.group(1).strip()
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start = t.find("{")
    end = t.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(t[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _clip_story_text(text: str, max_chars: int) -> str:
    t = (text or "").strip()
    if max_chars <= 0 or len(t) <= max_chars:
        return t
    return t[: max(0, max_chars - 1)].rstrip() + "…"


def format_story_context_for_translation(
    data: dict[str, Any],
    *,
    compact: bool = False,
    max_chars: int | None = None,
) -> str:
    """
    KO 번역용 TranslationHints 문자열 — JSON 전체를 읽기 쉬운 한국어 블록으로 변환.

    compact=True: 로컬 LLM(짧은 n_ctx)용 — 씬 본문 생략·요약 축약.
    청크별 scene_id/tone은 번역 호출 쪽에서 별도 주입한다.
    """
    if not isinstance(data, dict):
        return ""

    if data.get("code_mismatch") is True or data.get("verification_ok") is False:
        reason = (data.get("mismatch_reason") or data.get("reason") or "").strip() or "품번과 공개 정보 불일치"
        return (
            "[스토리 맥락 · Grok 웹 메타]\n"
            f"코드 불일치/검증 실패 — 웹 기반 인물·줄거리 힌트를 쓰지 마라. 이유: {reason}\n"
            "번역은 자막 큐와 [Background] JSON만 우선한다.\n"
        )

    syn_cap = 180 if compact else 0
    overall_cap = 260 if compact else 0

    lines: list[str] = [
        "[스토리 맥락 · Grok 웹 메타]",
        f"품번: {data.get('product_code', '')}",
        f"제목(JA): {data.get('title_ja', '')}",
        f"제목(KO): {data.get('title_ko', '')}",
        f"출연: {data.get('actress', '')}",
        f"제작/레이블: {data.get('maker', '')}",
        f"발매: {data.get('release_date', '')}",
    ]
    syn = (data.get("synopsis_short") or "").strip()
    if syn:
        if syn_cap:
            syn = _clip_story_text(syn, syn_cap)
        lines.append(f"시놉시스(공개): {syn}")
    overall = (data.get("overall_summary") or "").strip()
    if overall:
        if overall_cap:
            overall = _clip_story_text(overall, overall_cap)
        lines.append("")
        lines.append("[전체 요약]")
        lines.append(overall)

    scenes = data.get("scenes")
    if isinstance(scenes, list) and scenes:
        lines.append("")
        lines.append("[씬별(아카이브·톤 참고)]")
        for sc in scenes:
            if not isinstance(sc, dict):
                continue
            sid = sc.get("scene_id", "")
            tr = sc.get("time_range", "")
            lab = sc.get("scene_label", "")
            sm = sc.get("scene_summary", "")
            tone = sc.get("tone", "")
            tags = sc.get("key_tags")
            tag_s = ""
            if isinstance(tags, list):
                tag_s = ", ".join(str(x) for x in tags if x)
            lines.append(f"- {sid} [{tr}] {lab}")
            if not compact:
                if sm:
                    lines.append(f"  {sm}")
                if tone or tag_s:
                    lines.append(f"  (톤: {tone} / 태그: {tag_s})")
            elif tone:
                lines.append(f"  (톤: {_clip_story_text(str(tone), 80)})")

    lines.append("")
    lines.append(
        "번역 시: 위 씬 톤·호칭·분위기를 자막 큐와 맞출 것. 웹 메타와 대사가 충돌하면 대사 우선."
    )
    out = "\n".join(lines).strip()
    if max_chars is not None and max_chars > 0:
        out = _clip_story_text(out, max_chars)
    return out


def story_context_json_dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _hms_to_sec(part: str) -> float | None:
    part = (part or "").strip()
    m = re.match(r"^(\d{1,2}):(\d{2}):(\d{2}(?:\.\d+)?)$", part)
    if not m:
        return None
    h, mi, se = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mi * 60 + se


def _parse_scene_time_range_ends(time_range: object) -> tuple[float | None, float | None]:
    """Grok `time_range`에서 시작·끝 초. 파싱 불가·시간 미상이면 (None, None)."""
    tr = str(time_range or "").strip()
    if not tr or "미상" in tr:
        return None, None
    m = re.search(
        r"(\d{1,2}:\d{2}:\d{2}(?:\.\d+)?)\s*[~〜～⸺\-]\s*(\d{1,2}:\d{2}:\d{2}(?:\.\d+)?)",
        tr,
    )
    if not m:
        return None, None
    a, b = _hms_to_sec(m.group(1)), _hms_to_sec(m.group(2))
    if a is None or b is None:
        return None, None
    return a, b


def resolve_grok_scene_for_chunk(
    anchor_sec: float,
    grok_data: dict[str, Any] | None,
    *,
    video_end_sec: float,
) -> tuple[str, str]:
    """
    청크 대표 시각(초)에 맞는 Grok `scene_id`와 `tone` 문자열.
    time_range 파싱 가능하면 구간 매칭·가장 가까운 구간; 없으면 타임라인을 씬 개수로 균등 분할.
    """
    if not isinstance(grok_data, dict):
        return "", ""
    if grok_data.get("code_mismatch") is True or grok_data.get("verification_ok") is False:
        return "", ""

    scenes = grok_data.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        return "", ""

    scene_dicts = [x for x in scenes if isinstance(x, dict)]
    if not scene_dicts:
        return "", ""

    intervals: list[tuple[dict[str, Any], float, float]] = []
    for sc in scene_dicts:
        a, b = _parse_scene_time_range_ends(sc.get("time_range"))
        if a is not None and b is not None and b >= a:
            intervals.append((sc, a, b))

    def emit(sc: dict[str, Any]) -> tuple[str, str]:
        return (str(sc.get("scene_id") or "").strip(), str(sc.get("tone") or "").strip())

    if intervals:
        for sc, a, b in intervals:
            if a <= anchor_sec <= b:
                return emit(sc)
        best_sc = None
        best_d = float("inf")
        for sc, a, b in intervals:
            if anchor_sec < a:
                d = a - anchor_sec
            elif anchor_sec > b:
                d = anchor_sec - b
            else:
                d = 0.0
            if d < best_d:
                best_d = d
                best_sc = sc
        if best_sc is not None:
            return emit(best_sc)

    n = len(scene_dicts)
    end = max(float(video_end_sec), 0.001)
    ratio = max(0.0, min(1.0, float(anchor_sec) / end))
    idx = min(int(ratio * n), n - 1)
    return emit(scene_dicts[idx])
