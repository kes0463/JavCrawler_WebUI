"""Local memory store for Persona Chat.

The memory is intentionally simple and local-first: it keeps compact notes
derived from chat turns so future prompts can reuse user preferences without
fine-tuning the model.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from javstory.config.app_config import DATA_ROOT
from javstory.persona.library_search import extract_product_codes, normalize_product_code

_SCHEMA_VERSION = 1
_FALSE_VALUES = {"0", "false", "no", "off", "disable", "disabled"}

_CORRECTION_HINTS = (
    "틀",
    "잘못",
    "아니",
    "다른 작품",
    "전혀 다른",
    "정확",
    "수정",
    "오류",
)
_PREFERENCE_HINTS = (
    "좋",
    "취향",
    "끌",
    "비슷",
    "추천",
    "선호",
    "별로",
    "싫",
    "더",
)
_STYLE_HINTS = (
    "말투",
    "톤",
    "짧게",
    "자세히",
    "직설",
    "부드럽",
    "분석",
    "추천 위주",
)
_REASONING_LEAK_HINTS = (
    "here's a thinking process",
    "here is a thinking process",
    "thinking process",
    "reasoning process",
    "internal reasoning",
    "analyze request",
    "analyze the request",
    "recall current state context",
    "scan library search results",
    "analyze the context",
    "analyze the search results",
    "synthesize and structure",
    "drafting the analysis",
    "self correction",
    "final polish",
    "분석 과정",
    "추론 과정",
    "<think>",
    "</think>",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clip(text: str, limit: int, *, preserve_lines: bool = True) -> str:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if preserve_lines:
        lines = [" ".join(line.split()) for line in raw.split("\n")]
        cleaned = "\n".join(line for line in lines if line)
    else:
        cleaned = " ".join(raw.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "..."


def _clip_inline(text: str, limit: int) -> str:
    return _clip(text, limit, preserve_lines=False)


def _memory_enabled() -> bool:
    raw = (os.environ.get("JAVSTORY_PERSONA_CHAT_MEMORY_ENABLED", "1") or "").strip().lower()
    return raw not in _FALSE_VALUES


def _empty_payload() -> Dict[str, Any]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "updated_at": "",
        "turn_count": 0,
        "recent_messages": [],
        "product_mentions": {},
        "preference_notes": [],
        "correction_notes": [],
        "style_notes": [],
    }


def _append_unique(notes: List[Dict[str, Any]], note: Dict[str, Any], *, max_items: int) -> None:
    text = str(note.get("text") or "").strip()
    if not text:
        return
    notes[:] = [item for item in notes if str(item.get("text") or "").strip() != text]
    notes.append(note)
    del notes[:-max_items]


def _has_any(text: str, hints: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(hint.lower() in lowered for hint in hints)


def _looks_like_reasoning_leak(text: str) -> bool:
    return _has_any(text, _REASONING_LEAK_HINTS)


@dataclass
class PersonaChatMemory:
    """Persist compact Persona Chat memory under ``data/cache``."""

    path: Path = field(default_factory=lambda: DATA_ROOT / "cache" / "persona_chat_memory.json")
    max_recent_messages: int = 40
    max_notes: int = 24
    max_products: int = 80

    def load(self) -> Dict[str, Any]:
        if not _memory_enabled() or not self.path.exists():
            return _empty_payload()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return _empty_payload()
        if not isinstance(data, dict):
            return _empty_payload()

        payload = _empty_payload()
        payload.update(data)
        payload["recent_messages"] = [
            msg for msg in payload.get("recent_messages") or [] if isinstance(msg, dict)
        ][-self.max_recent_messages :]
        for key in ("preference_notes", "correction_notes", "style_notes"):
            payload[key] = [item for item in payload.get(key) or [] if isinstance(item, dict)][-self.max_notes :]
        if not isinstance(payload.get("product_mentions"), dict):
            payload["product_mentions"] = {}
        return payload

    def save(self, payload: Mapping[str, Any]) -> None:
        if not _memory_enabled():
            return
        data = dict(payload)
        data["schema_version"] = _SCHEMA_VERSION
        data["updated_at"] = _now_iso()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def load_recent_messages(self) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        for item in self.load().get("recent_messages") or []:
            role = str(item.get("role") or "").strip()
            content = str(item.get("content") or "").strip()
            status = str(item.get("status") or "ok").strip() or "ok"
            if role == "assistant" and _looks_like_reasoning_leak(content):
                continue
            if role in {"user", "assistant"} and content:
                out.append({"role": role, "content": content, "status": status})
        return out[-self.max_recent_messages :]

    def clear_recent_messages(self) -> None:
        payload = self.load()
        payload["recent_messages"] = []
        self.save(payload)

    def clear_all(self) -> None:
        self.save(_empty_payload())

    def prompt_context(self, query: str, *, max_items: int = 10) -> Dict[str, Any]:
        payload = self.load()
        product_mentions = payload.get("product_mentions") or {}
        query_codes = [normalize_product_code(code) for code in extract_product_codes(query or "")]
        related_products: List[Dict[str, Any]] = []

        for code in query_codes:
            item = product_mentions.get(code)
            if isinstance(item, dict):
                related_products.append({"product_code": code, **item})

        remaining = [
            {"product_code": code, **item}
            for code, item in product_mentions.items()
            if code not in query_codes and isinstance(item, dict)
        ]
        remaining.sort(key=lambda item: (int(item.get("count") or 0), str(item.get("last_seen_at") or "")), reverse=True)

        return {
            "turn_count": int(payload.get("turn_count") or 0),
            "related_products": (related_products + remaining)[:max_items],
            "preference_notes": (payload.get("preference_notes") or [])[-max_items:],
            "correction_notes": (payload.get("correction_notes") or [])[-max_items:],
            "style_notes": (payload.get("style_notes") or [])[-max_items:],
        }

    def record_turn(self, user_message: str, assistant_message: str) -> None:
        if not _memory_enabled():
            return
        user_text = _clip(user_message, 1200)
        assistant_text = _clip(assistant_message, 8000)
        if not user_text or not assistant_text or _looks_like_reasoning_leak(assistant_text):
            return

        payload = self.load()
        now = _now_iso()
        payload["turn_count"] = int(payload.get("turn_count") or 0) + 1

        recent = list(payload.get("recent_messages") or [])
        recent.extend(
            [
                {"role": "user", "content": user_text, "status": "ok", "created_at": now},
                {"role": "assistant", "content": assistant_text, "status": "ok", "created_at": now},
            ]
        )
        payload["recent_messages"] = recent[-self.max_recent_messages :]

        product_mentions = dict(payload.get("product_mentions") or {})
        user_codes = [normalize_product_code(code) for code in extract_product_codes(user_text)]
        assistant_codes = [normalize_product_code(code) for code in extract_product_codes(assistant_text)]
        for code in [c for c in user_codes + assistant_codes if c]:
            item = dict(product_mentions.get(code) or {})
            item["count"] = int(item.get("count") or 0) + 1
            item["last_seen_at"] = now
            if code in user_codes:
                item["last_user_message"] = _clip_inline(user_text, 240)
            item["last_assistant_reply"] = _clip_inline(assistant_text, 240)
            product_mentions[code] = item

        if len(product_mentions) > self.max_products:
            ordered = sorted(
                product_mentions.items(),
                key=lambda pair: (int((pair[1] or {}).get("count") or 0), str((pair[1] or {}).get("last_seen_at") or "")),
                reverse=True,
            )
            product_mentions = dict(ordered[: self.max_products])
        payload["product_mentions"] = product_mentions

        preference_notes = list(payload.get("preference_notes") or [])
        correction_notes = list(payload.get("correction_notes") or [])
        style_notes = list(payload.get("style_notes") or [])

        if user_codes or _has_any(user_text, _PREFERENCE_HINTS):
            _append_unique(
                preference_notes,
                {"text": f"사용자 취향 단서: {_clip_inline(user_text, 220)}", "created_at": now},
                max_items=self.max_notes,
            )
        if _has_any(user_text, _CORRECTION_HINTS):
            _append_unique(
                correction_notes,
                {"text": f"사용자 교정/불만: {_clip_inline(user_text, 220)}", "created_at": now},
                max_items=self.max_notes,
            )
        if _has_any(user_text, _STYLE_HINTS):
            _append_unique(
                style_notes,
                {"text": f"선호 답변 방식: {_clip_inline(user_text, 180)}", "created_at": now},
                max_items=self.max_notes,
            )

        payload["preference_notes"] = preference_notes[-self.max_notes :]
        payload["correction_notes"] = correction_notes[-self.max_notes :]
        payload["style_notes"] = style_notes[-self.max_notes :]
        self.save(payload)
