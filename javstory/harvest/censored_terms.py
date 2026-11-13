"""Restore storefront masks before metadata translation.

Known adult compounds are rewritten here. Any mask still left can be sent to a
short restore call, except spans that must stay masked: those are neither
rewritten nor included in that call.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

# One masked character, as used on storefront titles.
_MASK = r"[●○◯〇×✕✖xX＊*]"

# Leftover scan is stricter than the rule mask so plain ASCII "x" / "*" is not a hit.
_CENSOR_CHARS = frozenset("●○◯〇×✕✖＊")

_CONTEXT = 8
# Separate windows must not overlap after context is added on both sides.
_CLUSTER_GAP = _CONTEXT * 2

# Longer lookalikes win by match length. 強●羞恥 is 強制, not 強姦.
# Bare 強● is left for the restore call.
_RULES: tuple[tuple[str, str, str], ...] = (
    (rf"家庭{_MASK}師", "家庭教師", "가정교사"),
    (rf"奴{_MASK}契約", "奴隷契約", "노예 계약"),
    (rf"逆レ{_MASK}プ", "逆レイプ", "역강간"),
    (rf"口マ{_MASK}コ", "口マンコ", "입보지"),
    (rf"口ま{_MASK}こ", "口まんこ", "입보지"),
    (rf"おま{_MASK}こ", "おまんこ", "보지"),
    (rf"おま{_MASK}コ", "おまんこ", "보지"),
    (rf"オマ{_MASK}コ", "オマンコ", "보지"),
    (rf"オマ{_MASK}こ", "オマンコ", "보지"),
    (rf"マ{_MASK}コ", "マンコ", "보지"),
    (rf"ま{_MASK}こ", "まんこ", "보지"),
    (rf"チ{_MASK}ポ", "チンポ", "자지"),
    (rf"ち{_MASK}ぽ", "ちんぽ", "자지"),
    (rf"レ{_MASK}プ", "レイプ", "강간"),
    (rf"犯{_MASK}られた", "犯された", "범해진"),
    (rf"犯{_MASK}られて", "犯されて", "범해져서"),
    (rf"犯{_MASK}れた", "犯された", "범해진"),
    (rf"犯{_MASK}れて", "犯されて", "범해져서"),
    (rf"犯{_MASK}れ", "犯され", "범해져"),
    (rf"夜{_MASK}い", "夜這い", "야바이"),
    (rf"輪{_MASK}", "輪姦", "윤간"),
    (rf"強{_MASK}羞恥", "強制羞恥", "강제 수치"),
    (rf"強{_MASK}射精", "強制射精", "강제 사정"),
    (rf"強{_MASK}勃起", "強制勃起", "강제 발기"),
    (rf"強{_MASK}快楽", "強制快楽", "강제 쾌락"),
    (rf"強{_MASK}絶頂", "強制絶頂", "강제 절정"),
    (rf"強{_MASK}イラマ", "強制イラマ", "강제 이라마"),
    (rf"強{_MASK}童貞", "強制童貞", "강제 동정"),
    (rf"強{_MASK}変態", "強制変態", "강제 변태"),
    (rf"強{_MASK}される", "強姦される", "강간당하다"),
    (rf"強{_MASK}され", "強姦され", "강간당해"),
    (rf"強{_MASK}レ{_MASK}プ", "強姦レイプ", "강간"),
    (rf"痴{_MASK}", "痴漢", "치한"),
    (rf"昏{_MASK}", "昏睡", "혼수"),
    (rf"凌{_MASK}", "凌辱", "능욕"),
    (rf"媚{_MASK}", "媚薬", "미약"),
    (rf"奴{_MASK}", "奴隷", "노예"),
)

# These stay as written. Do not send them to the restore model.
_EXCLUSIONS: tuple[re.Pattern[str], ...] = (
    re.compile(rf"女子{_MASK}生"),
    re.compile(rf"[JＪｊ]{_MASK}"),
    re.compile(rf"シ{_MASK}タ"),
    re.compile(rf"し{_MASK}た"),
    re.compile(rf"少{_MASK}"),
    re.compile(rf"[ロろ]{_MASK}(?!ション)"),
)

_COMPILED: tuple[tuple[re.Pattern[str], str, str], ...] = tuple(
    (re.compile(pattern), restored, ko) for pattern, restored, ko in _RULES
)

_RESTORE_SYSTEM = """You restore censored characters in Japanese adult-video title snippets.
Replace only mask characters (● ○ × ◯ 〇 ✕ ✖ ＊). Every other character must stay identical.
The restored string must be the same length as the snippet.
If you are not sure, return the snippet unchanged and set confidence to "low".
Return only JSON: {"items":[{"id":"0","restored":"...","confidence":"high"}]}
confidence is "high" or "low".
"""


@dataclass(frozen=True)
class CensoredRestore:
    text: str
    terms: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class RestoreWindow:
    field: str
    start: int
    end: int
    snippet: str


def restore_censored_text(text: str) -> CensoredRestore:
    """Replace allowlisted masks. Returns restored text and (japanese, korean) pairs."""
    src = text or ""
    if not src:
        return CensoredRestore("", ())

    pieces: list[str] = []
    terms: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    i = 0
    n = len(src)
    while i < n:
        best_end = -1
        best_restored = ""
        best_ko = ""
        for pattern, restored, ko in _COMPILED:
            matched = pattern.match(src, i)
            if matched is None or matched.end() <= best_end:
                continue
            best_end = matched.end()
            best_restored = restored
            best_ko = ko
        if best_end < 0:
            pieces.append(src[i])
            i += 1
            continue
        pieces.append(best_restored)
        pair = (best_restored, best_ko)
        if pair not in seen:
            seen.add(pair)
            terms.append(pair)
        i = best_end
    return CensoredRestore("".join(pieces), tuple(terms))


def merged_terms(*texts: str) -> tuple[tuple[str, str], ...]:
    """Unique (japanese, korean) pairs from several fields, in first-seen order."""
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for text in texts:
        for pair in restore_censored_text(text).terms:
            if pair in seen:
                continue
            seen.add(pair)
            out.append(pair)
    return tuple(out)


def dedupe_terms(*groups: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for group in groups:
        for pair in group:
            if pair in seen:
                continue
            seen.add(pair)
            out.append(pair)
    return tuple(out)


def _exclusion_spans(text: str) -> tuple[tuple[int, int], ...]:
    spans: list[tuple[int, int]] = []
    for pattern in _EXCLUSIONS:
        for matched in pattern.finditer(text):
            spans.append((matched.start(), matched.end()))
    if not spans:
        return ()
    spans.sort()
    merged: list[tuple[int, int]] = [spans[0]]
    for start, end in spans[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return tuple(merged)


def _covered(index: int, spans: tuple[tuple[int, int], ...]) -> bool:
    return any(start <= index < end for start, end in spans)


def _windows_for(field: str, text: str) -> tuple[RestoreWindow, ...]:
    if not text:
        return ()
    excluded = _exclusion_spans(text)
    positions = [
        i for i, ch in enumerate(text) if ch in _CENSOR_CHARS and not _covered(i, excluded)
    ]
    if not positions:
        return ()

    clusters: list[list[int]] = [[positions[0]]]
    for pos in positions[1:]:
        if pos - clusters[-1][-1] <= _CLUSTER_GAP:
            clusters[-1].append(pos)
        else:
            clusters.append([pos])

    windows: list[RestoreWindow] = []
    n = len(text)
    for cluster in clusters:
        core_start = cluster[0]
        core_end = cluster[-1] + 1
        start = max(0, core_start - _CONTEXT)
        end = min(n, core_end + _CONTEXT)
        blocked = False
        for ex_start, ex_end in excluded:
            if ex_end <= start or ex_start >= end:
                continue
            if ex_end <= core_start:
                start = max(start, ex_end)
            elif ex_start >= core_end:
                end = min(end, ex_start)
            else:
                blocked = True
                break
        if blocked or start > core_start or end < core_end or start >= end:
            continue
        if windows and start < windows[-1].end:
            start = windows[-1].end
        if start >= end or start > core_start:
            continue
        snippet = text[start:end]
        if not any(ch in _CENSOR_CHARS for ch in snippet):
            continue
        windows.append(RestoreWindow(field, start, end, snippet))
    return tuple(windows)


def collect_restore_windows(title: str, synopsis: str) -> tuple[RestoreWindow, ...]:
    """Mask windows still eligible for the short restore call."""
    return _windows_for("title", title or "") + _windows_for("synopsis", synopsis or "")


def build_mask_restore_messages(windows: tuple[RestoreWindow, ...] | list[RestoreWindow]) -> list[dict]:
    items = [{"id": str(i), "snippet": window.snippet} for i, window in enumerate(windows)]
    return [
        {"role": "system", "content": _RESTORE_SYSTEM},
        {
            "role": "user",
            "content": json.dumps({"items": items}, ensure_ascii=False) + "\n\n/no_think",
        },
    ]


def accept_mask_restore(snippet: str, restored: str, confidence: str) -> str | None:
    """Accept a fill only when length matches, only masks changed, and confidence is high."""
    if str(confidence or "").strip().lower() != "high":
        return None
    if not isinstance(restored, str) or len(restored) != len(snippet):
        return None
    changed = False
    for src, dst in zip(snippet, restored):
        if src in _CENSOR_CHARS:
            if dst in _CENSOR_CHARS or dst.isspace():
                return None
            changed = True
            continue
        if src != dst:
            return None
    if not changed:
        return None
    return restored


def parse_restore_items(data: object) -> dict[str, tuple[str, str]]:
    raw_items: object
    if isinstance(data, dict):
        raw_items = data.get("items") or []
    elif isinstance(data, list):
        raw_items = data
    else:
        return {}
    if not isinstance(raw_items, list):
        return {}
    out: dict[str, tuple[str, str]] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        restored = item.get("restored")
        if not isinstance(restored, str):
            continue
        out[str(item.get("id", ""))] = (restored, str(item.get("confidence", "")))
    out.pop("", None)
    return out


def apply_restore_response(
    title: str,
    synopsis: str,
    windows: tuple[RestoreWindow, ...] | list[RestoreWindow],
    items: dict[str, tuple[str, str]],
) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    """Apply accepted window fills. Rejected items leave the original mask."""
    edits: dict[str, list[tuple[int, int, str]]] = {"title": [], "synopsis": []}
    applied: list[tuple[str, str]] = []
    for index, window in enumerate(windows):
        pair = items.get(str(index))
        if pair is None:
            continue
        accepted = accept_mask_restore(window.snippet, pair[0], pair[1])
        if not accepted:
            continue
        edits[window.field].append((window.start, window.end, accepted))
        applied.append((window.snippet, accepted))

    def _apply(src: str, field: str) -> str:
        text = src or ""
        for start, end, replacement in sorted(edits[field], key=lambda row: row[0], reverse=True):
            text = text[:start] + replacement + text[end:]
        return text

    return _apply(title, "title"), _apply(synopsis, "synopsis"), tuple(applied)
