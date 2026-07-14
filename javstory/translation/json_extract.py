"""
모델 응답에서 JSON 배열/객체 후보 추출(플랜: 펜스 제거 + 괄호 균형).
단순 정규식 `\\[.*\\]` 는 쓰지 않는다.
"""
from __future__ import annotations

import json
import re
from typing import Any


def strip_code_fences(text: str) -> str:
    """``` / ```json 구분 라인만 제거한다. 펜스 안 본문은 유지한다."""
    if not text:
        return ""
    out: list[str] = []
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            continue
        out.append(line)
    return "\n".join(out)


def strip_llm_noise_for_json(text: str) -> str:
    """
    thinking/코드펜스 잔여물을 제거해 JSON 추출 성공률을 올린다.
    (씬 검증·번역 등 공통)
    """
    if not text:
        return ""
    t = text.strip()
    t = re.sub(r"`<redacted_thinking>`.*?`</redacted_thinking>`", "", t, flags=re.DOTALL | re.IGNORECASE)
    t = re.sub(r"<redacted_thinking>.*?</redacted_thinking>", "", t, flags=re.DOTALL | re.IGNORECASE)
    t = re.sub(r"<think>.*?</think>", "", t, flags=re.DOTALL | re.IGNORECASE)
    t = re.sub(r"<thinking>.*?</thinking>", "", t, flags=re.DOTALL | re.IGNORECASE)
    t = re.sub(r"<\|[^|>]+\|>", "", t)
    return t.strip()


# Qwen 등이 앞에 영어 "Thinking Process:"·분석 문단을 붙일 때, 큐 JSON이 시작하는 위치로 자른다.
_CUE_JSON_HEAD = re.compile(
    r"\[[\s\r\n]*\{[\s\r\n]*[\"']index[\"']\s*:",
    re.IGNORECASE,
)


def strip_cot_preamble_before_cue_json(text: str) -> str:
    """
    응답 앞부분의 CoT·영어 설명을 제거하고 `[{"index": ...` 로 시작하는 구간만 남긴다.
    없으면 원문을 그대로 반환(다중 `[` 스캔 폴백은 `extract_json_array_candidate`에 위임).
    """
    if not text:
        return ""
    t = strip_code_fences(text).strip()
    t = strip_llm_noise_for_json(t)
    m = _CUE_JSON_HEAD.search(t)
    if m:
        return t[m.start() :]
    return t


def _balanced_slice_from(
    text: str,
    *,
    open_ch: str,
    close_ch: str,
    start_idx: int,
) -> str | None:
    """`start_idx` 위치의 여는 괄호부터 균형 잡힌 슬라이스."""
    if start_idx < 0 or start_idx >= len(text) or text[start_idx] != open_ch:
        return None
    depth = 0
    in_str = False
    esc = False
    i = start_idx
    n = len(text)
    while i < n:
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return text[start_idx : i + 1]
        i += 1
    return None


def _balanced_slice(
    text: str,
    *,
    open_ch: str,
    close_ch: str,
) -> str | None:
    start = text.find(open_ch)
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        i += 1
    return None


def _is_subtitle_cue_json_array(data: Any) -> bool:
    """CoT·설명 안의 `["a","b"]` 등과 구분: `[{ \"index\", \"start\", ... }, ...]` 형태만 채택."""
    if not isinstance(data, list) or not data:
        return False
    first = data[0]
    if not isinstance(first, dict):
        return False
    return "index" in first and ("start" in first or "text" in first)


def extract_json_array_candidate(text: str) -> str | None:
    """
    응답 전체에서 **첫 번째 `[` 한 군데만** 보면 안 된다.
    Qwen 등이 앞에 영어 사고 과정·마크다운을 붙이면 그 안의 `[`가 먼저 잡혀 JSON 파싱이 깨진다.
    균형 잡힌 `[...]` 후보를 모두 시도해 자막 큐 배열로 보이는 것만 채택한다.
    """
    t = strip_cot_preamble_before_cue_json(text)
    for i, ch in enumerate(t):
        if ch != "[":
            continue
        sl = _balanced_slice_from(t, open_ch="[", close_ch="]", start_idx=i)
        if not sl:
            continue
        try:
            data = json.loads(sl)
        except json.JSONDecodeError:
            continue
        if _is_subtitle_cue_json_array(data):
            return sl
    return None


def extract_json_object_candidate(text: str) -> str | None:
    t = strip_code_fences(text).strip()
    return _balanced_slice(t, open_ch="{", close_ch="}")


def _iter_json_object_candidates(text: str) -> list[str]:
    """첫 `{`만이 아니라, 응답 안의 각 `{` 위치에서 균형 객체 후보를 수집한다."""
    t = strip_code_fences(text).strip()
    out: list[str] = []
    for i, ch in enumerate(t):
        if ch != "{":
            continue
        sl = _balanced_slice_from(t, open_ch="{", close_ch="}", start_idx=i)
        if sl:
            out.append(sl)
    return out


def _repair_trailing_commas(s: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", s)


def _normalize_jsonish_quotes(s: str) -> str:
    """스마트 따옴표·전각 따옴표를 ASCII로."""
    return (
        s.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\uff02", '"')
        .replace("\uff07", "'")
    )


def _repair_truncated_json_array(s: str) -> str | None:
    """max_tokens 절단으로 닫히지 않은 배열을 마지막 완전 객체까지만 살려 닫는다."""
    t = (s or "").strip()
    if not t.startswith("["):
        return None
    last = t.rfind("}")
    if last < 0:
        return None
    trimmed = t[: last + 1].rstrip()
    if trimmed.endswith(","):
        trimmed = trimmed[:-1].rstrip()
    repaired = _repair_trailing_commas(trimmed) + "]"
    try:
        data = json.loads(repaired)
        return repaired if isinstance(data, list) and data else None
    except json.JSONDecodeError:
        return None


def _repair_missing_index_after_colon(s: str) -> str:
    """
    LLM이 `"index":,` 처럼 값을 빠뜨리면 json.loads가 실패한다.
    배열에서 `},{`로 구분된 **몇 번째 객체인지**로 index를 채운다(앞 줄은 정상 index여도 무방).
    """

    def _repl(m: re.Match) -> str:
        prefix = s[: m.start()]
        idx = len(re.findall(r"\}\s*,\s*\{", prefix))
        return f'"index": {idx},'

    return re.sub(r'"index"\s*:\s*,', _repl, s)


def _loads_cue_array_literal(s: str) -> list[Any] | None:
    """Gemma 등이 단일따옴표 Python dict 스타일로 낼 때."""
    import ast

    try:
        data = ast.literal_eval(s)
    except Exception:
        return None
    if isinstance(data, list) and _is_subtitle_cue_json_array(data):
        return data
    return None


def _loads_array_variants(raw: str) -> list[Any] | None:
    candidates = [
        raw,
        _normalize_jsonish_quotes(raw),
        _repair_trailing_commas(raw),
        _repair_trailing_commas(_normalize_jsonish_quotes(raw)),
        _repair_missing_index_after_colon(raw),
        _repair_trailing_commas(_repair_missing_index_after_colon(_normalize_jsonish_quotes(raw))),
    ]
    truncated = _repair_truncated_json_array(_normalize_jsonish_quotes(raw))
    if truncated:
        candidates.append(truncated)
    seen: set[str] = set()
    for cand in candidates:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        try:
            data = json.loads(cand)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            lit = _loads_cue_array_literal(cand)
            if lit is not None:
                return lit
            continue
        lit = _loads_cue_array_literal(cand)
        if lit is not None:
            return lit
    lit = _loads_cue_array_literal(_normalize_jsonish_quotes(raw))
    if lit is not None:
        return lit
    return None


def parse_json_array(text: str) -> list[Any] | None:
    cand = extract_json_array_candidate(text)
    if cand:
        got = _loads_array_variants(cand)
        if got is not None:
            return got
    # 균형 슬라이스가 실패해도(절단·단일따옴표) 본문 전체에서 한 번 더 시도
    t = strip_cot_preamble_before_cue_json(text)
    if t and t != cand:
        got = _loads_array_variants(t)
        if got is not None:
            return got
    # 단일따옴표 배열: bracket-depth 스캐너가 깨질 수 있어 [ ... ] 구간 literal_eval
    if t:
        start = t.find("[")
        end = t.rfind("]")
        if start >= 0 and end > start:
            lit = _loads_cue_array_literal(_normalize_jsonish_quotes(t[start : end + 1]))
            if lit is not None:
                return lit
            repaired = _repair_truncated_json_array(_normalize_jsonish_quotes(t[start:]))
            if repaired:
                got = _loads_array_variants(repaired)
                if got is not None:
                    return got
    return None


def _loads_object_variants(raw: str) -> dict[str, Any] | None:
    for attempt in (0, 1, 2):
        if attempt == 0:
            s = raw
        elif attempt == 1:
            s = _repair_trailing_commas(raw)
        else:
            s = _repair_trailing_commas(raw.replace("\r\n", "\n"))
        try:
            data = json.loads(s)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            continue
    return None


def parse_json_object(text: str) -> dict[str, Any] | None:
    base = strip_llm_noise_for_json(text)
    if not base:
        return None

    # 1) 단일 객체: 첫 번째 균형 `{...}`
    cand = extract_json_object_candidate(base)
    if cand:
        got = _loads_object_variants(cand)
        if isinstance(got, dict):
            return got

    # 2) `[{ ... }]` 한 요소만 (모델이 배열로만 줄 때)
    arr = parse_json_array(base)
    if isinstance(arr, list) and len(arr) == 1 and isinstance(arr[0], dict):
        return arr[0]

    # 3) 응답 안 여러 `{...}` 중 파싱 성공하는 것 (앞에 깨진/짧은 객체가 있을 때)
    for sub in _iter_json_object_candidates(base):
        if sub == cand:
            continue
        got = _loads_object_variants(sub)
        if isinstance(got, dict) and got:
            return got

    return None
