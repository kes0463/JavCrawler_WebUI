"""Local memory store for Persona Chat.

The memory is intentionally simple and local-first: it keeps compact notes
derived from chat turns so future prompts can reuse user preferences without
fine-tuning the model.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

import httpx

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
    "꼴",
    "미쳤",
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
_STRONG_REACTION_HINTS = (
    "개꼴",
    "꼴려",
    "꼴림",
    "미쳤",
    "미친",
    "미쳣",
    "도랐",
    "돌았",
    "지린",
    "오진",
    "쩐다",
    "최고",
    "최고야",
    "개좋",
    "존좋",
    "완전 좋",
    "레전드",
    "강하게 꽂",
)
_NEGATIVE_FEEDBACK_HINTS = (
    "별로",
    "싫",
    "안 맞",
    "취향 아님",
    "취향아님",
    "노잼",
    "그닥",
    "아쉽",
    "빼줘",
    "제외",
    "추천하지마",
    "추천하지 마",
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
        "strong_reaction_notes": [],
        "negative_feedback_notes": [],
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


def _matched_hints(text: str, hints: Sequence[str]) -> List[str]:
    lowered = text.lower()
    return [hint for hint in hints if hint.lower() in lowered]


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
        for key in (
            "preference_notes",
            "strong_reaction_notes",
            "negative_feedback_notes",
            "correction_notes",
            "style_notes",
        ):
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
        strong_reactions = [item for item in payload.get("strong_reaction_notes") or [] if isinstance(item, dict)]
        if query_codes:
            query_code_set = set(query_codes)
            related_reactions = [
                item
                for item in strong_reactions
                if query_code_set.intersection(set(item.get("product_codes") or []))
            ]
            other_reactions = [item for item in strong_reactions if item not in related_reactions]
            strong_reactions = related_reactions + other_reactions
        strong_reactions = strong_reactions[:max_items] if query_codes else strong_reactions[-max_items:]

        return {
            "turn_count": int(payload.get("turn_count") or 0),
            "related_products": (related_products + remaining)[:max_items],
            "preference_notes": (payload.get("preference_notes") or [])[-max_items:],
            "strong_reaction_notes": strong_reactions,
            "negative_feedback_notes": (payload.get("negative_feedback_notes") or [])[-max_items:],
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
        strong_reaction_notes = list(payload.get("strong_reaction_notes") or [])
        negative_feedback_notes = list(payload.get("negative_feedback_notes") or [])
        correction_notes = list(payload.get("correction_notes") or [])
        style_notes = list(payload.get("style_notes") or [])
        reaction_hits = _matched_hints(user_text, _STRONG_REACTION_HINTS)
        negative_hits = _matched_hints(user_text, _NEGATIVE_FEEDBACK_HINTS)

        if user_codes or reaction_hits or _has_any(user_text, _PREFERENCE_HINTS):
            _append_unique(
                preference_notes,
                {"text": f"사용자 취향 단서: {_clip_inline(user_text, 220)}", "created_at": now},
                max_items=self.max_notes,
            )
        strong_reaction_codes = [code for code in user_codes + assistant_codes if code]
        strong_reaction_codes = list(dict.fromkeys(strong_reaction_codes))
        if reaction_hits:
            _append_unique(
                strong_reaction_notes,
                {
                    "text": f"사용자 강렬 반응: {_clip_inline(user_text, 220)}",
                    "triggers": reaction_hits[:5],
                    "product_codes": strong_reaction_codes[:5],
                    "intensity": min(10, 5 + len(reaction_hits) + (2 if strong_reaction_codes else 0)),
                    "created_at": now,
                },
                max_items=self.max_notes,
            )
        if negative_hits:
            _append_unique(
                negative_feedback_notes,
                {
                    "text": f"사용자 부정 피드백: {_clip_inline(user_text, 220)}",
                    "triggers": negative_hits[:5],
                    "product_codes": user_codes[:5],
                    "created_at": now,
                },
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
        payload["strong_reaction_notes"] = strong_reaction_notes[-self.max_notes :]
        payload["negative_feedback_notes"] = negative_feedback_notes[-self.max_notes :]
        payload["correction_notes"] = correction_notes[-self.max_notes :]
        payload["style_notes"] = style_notes[-self.max_notes :]
        self.save(payload)


_ENHANCED_SCHEMA_VERSION = 1


def _tokenize_memory_text(text: str) -> List[str]:
    return [
        token
        for token in re.findall(r"[A-Za-z0-9가-힣ぁ-んァ-ン一-龥]{2,}", str(text or "").lower())
        if token not in {"사용자", "작품", "추천", "요약", "대화", "assistant", "user"}
    ]


def _term_vector(text: str) -> Dict[str, float]:
    vec: Dict[str, float] = {}
    for token in _tokenize_memory_text(text):
        vec[token] = vec.get(token, 0.0) + 1.0
    return vec


def _cosine_similarity_text(a: str, b: str) -> float:
    va = _term_vector(a)
    vb = _term_vector(b)
    if not va or not vb:
        return 0.0
    dot = sum(va.get(k, 0.0) * vb.get(k, 0.0) for k in set(va) & set(vb))
    norm_a = math.sqrt(sum(v * v for v in va.values()))
    norm_b = math.sqrt(sum(v * v for v in vb.values()))
    if norm_a <= 0 or norm_b <= 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _episode_text(episode: Mapping[str, Any]) -> str:
    parts = [
        str(episode.get("summary") or ""),
        " ".join(str(v) for v in episode.get("new_preferences") or []),
        " ".join(str(v) for v in episode.get("important_context") or []),
        " ".join(str(v) for v in episode.get("special_requests") or []),
    ]
    return " ".join(parts)


@dataclass
class EnhancedPersonaMemory:
    """Three-tier Persona Chat memory store.

    - working_memory: recent conversational turns.
    - episodic_memory: compressed session summaries.
    - semantic_memory: preference facts mapped to weights.
    """

    working_memory: List[Dict[str, Any]] = field(default_factory=list)
    episodic_memory: List[Dict[str, Any]] = field(default_factory=list)
    semantic_memory: Dict[str, float] = field(default_factory=dict)
    max_working_turns: int = 12
    similarity_threshold: float = 0.7

    def add_turn(self, user_msg: str, assistant_msg: str) -> None:
        """Add a recent turn and keep only the latest 8-12 turns."""
        user_text = _clip_inline(user_msg, 1600)
        assistant_text = _clip_inline(assistant_msg, 2400)
        if not user_text and not assistant_text:
            return
        self.working_memory.append(
            {
                "user": user_text,
                "assistant": assistant_text,
                "timestamp": _now_iso(),
            }
        )
        del self.working_memory[:-max(8, min(12, int(self.max_working_turns or 12)))]
        self._update_semantic_memory(user_text)

    def compress_session_to_episode(self, session_turns: list) -> dict:
        """Summarize turns into an episodic memory entry and store it."""
        turns = [turn for turn in session_turns if isinstance(turn, Mapping)]
        summary_payload = self._summarize_session_with_llm(turns) or self._fallback_session_summary(turns)
        episode = {
            "timestamp": _now_iso(),
            "summary": str(summary_payload.get("summary") or "").strip(),
            "turn_count": len(turns),
            "new_preferences": list(summary_payload.get("new_preferences") or []),
            "important_context": list(summary_payload.get("important_context") or []),
            "special_requests": list(summary_payload.get("special_requests") or []),
        }
        self.episodic_memory.append(episode)
        for pref in episode["new_preferences"]:
            key = str(pref or "").strip()
            if key:
                self.semantic_memory[key] = float(self.semantic_memory.get(key, 0.0)) + 1.0
        return episode

    def retrieve_relevant_context(self, current_query: str, max_items: int = 3) -> str:
        """Return relevant episodes whose cosine similarity is at least 0.7."""
        query = str(current_query or "").strip()
        if not query:
            return ""
        scored: List[tuple[float, Dict[str, Any]]] = []
        for episode in self.episodic_memory:
            if not isinstance(episode, Mapping):
                continue
            score = _cosine_similarity_text(query, _episode_text(episode))
            if score >= self.similarity_threshold:
                scored.append((score, dict(episode)))
        scored.sort(key=lambda item: item[0], reverse=True)
        lines: List[str] = []
        for score, episode in scored[: max(1, int(max_items or 3))]:
            lines.append(
                json.dumps(
                    {
                        "similarity": round(score, 4),
                        "timestamp": episode.get("timestamp", ""),
                        "summary": episode.get("summary", ""),
                        "turn_count": int(episode.get("turn_count") or 0),
                        "new_preferences": episode.get("new_preferences") or [],
                        "important_context": episode.get("important_context") or [],
                        "special_requests": episode.get("special_requests") or [],
                    },
                    ensure_ascii=False,
                )
            )
        return "\n".join(lines)

    def save_to_json(self, path: str) -> None:
        """Save enhanced memory while keeping legacy JSON keys readable."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": _ENHANCED_SCHEMA_VERSION,
            "updated_at": _now_iso(),
            "working_memory": self.working_memory,
            "episodic_memory": self.episodic_memory,
            "semantic_memory": self.semantic_memory,
            # Legacy-compatible keys for older PersonaChatMemory consumers.
            "recent_messages": self._working_memory_as_recent_messages(),
            "preference_notes": [
                {"text": key, "weight": weight}
                for key, weight in sorted(self.semantic_memory.items(), key=lambda item: item[1], reverse=True)
            ],
        }
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)

    def load_from_json(self, path: str) -> None:
        """Load enhanced memory, accepting the existing PersonaChatMemory JSON shape."""
        source = Path(path)
        if not source.exists():
            return
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(payload, dict):
            return

        if isinstance(payload.get("working_memory"), list):
            self.working_memory = [
                dict(item)
                for item in payload.get("working_memory") or []
                if isinstance(item, Mapping)
            ][-self.max_working_turns :]
        else:
            self.working_memory = self._recent_messages_to_working_memory(payload.get("recent_messages") or [])

        self.episodic_memory = [
            dict(item)
            for item in payload.get("episodic_memory") or []
            if isinstance(item, Mapping)
        ]

        semantic = payload.get("semantic_memory")
        if isinstance(semantic, Mapping):
            self.semantic_memory = {
                str(k): float(v)
                for k, v in semantic.items()
                if str(k).strip()
            }
        else:
            self.semantic_memory = {}
            for note in payload.get("preference_notes") or []:
                if isinstance(note, Mapping):
                    text = str(note.get("text") or "").strip()
                    if text:
                        self.semantic_memory[text] = float(note.get("weight") or 1.0)

    def _summarize_session_with_llm(self, turns: List[Mapping[str, Any]]) -> Dict[str, Any]:
        if not turns:
            return {}
        try:
            from javstory.config.app_config import OLLAMA_BASE_URL
        except Exception:
            return {}

        model = (os.environ.get("JAVSTORY_PERSONA_MEMORY_MODEL", "") or "").strip()
        model = model or (os.environ.get("JAVSTORY_OLLAMA_MODEL", "") or "").strip() or "qwen3:8b"
        prompt = (
            "아래 페르소나 챗 세션을 한국어 JSON 객체 하나로 요약하라.\n"
            "필드는 summary, new_preferences, important_context, special_requests만 사용한다.\n"
            "new_preferences/important_context/special_requests는 문자열 배열이다.\n"
            "내부 추론이나 설명 없이 JSON만 출력한다.\n\n"
            + json.dumps(turns, ensure_ascii=False, default=str)
        )
        try:
            resp = httpx.post(
                f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=90,
            )
            resp.raise_for_status()
            text = str((resp.json() or {}).get("response") or "").strip()
            parsed = self._parse_json_object(text)
            if parsed:
                return parsed
        except Exception:
            return {}
        return {}

    def _fallback_session_summary(self, turns: List[Mapping[str, Any]]) -> Dict[str, Any]:
        user_text = "\n".join(str(turn.get("user") or turn.get("content") or "") for turn in turns)
        preferences = []
        for token in _tokenize_memory_text(user_text):
            if token in preferences:
                continue
            if _has_any(token, _PREFERENCE_HINTS) or len(preferences) < 5:
                preferences.append(token)
            if len(preferences) >= 8:
                break
        special_requests = [
            str(turn.get("user") or "")
            for turn in turns
            if isinstance(turn, Mapping) and _has_any(str(turn.get("user") or ""), _STYLE_HINTS)
        ][:4]
        return {
            "summary": _clip(user_text, 700, preserve_lines=False),
            "new_preferences": preferences,
            "important_context": [_clip(user_text, 300, preserve_lines=False)] if user_text else [],
            "special_requests": [_clip_inline(item, 180) for item in special_requests],
        }

    def _update_semantic_memory(self, text: str) -> None:
        if not _has_any(text, _PREFERENCE_HINTS + _STRONG_REACTION_HINTS + _NEGATIVE_FEEDBACK_HINTS):
            return
        for token in _tokenize_memory_text(text)[:12]:
            self.semantic_memory[token] = float(self.semantic_memory.get(token, 0.0)) + 0.25

    def _working_memory_as_recent_messages(self) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        for turn in self.working_memory:
            user = str(turn.get("user") or "").strip()
            assistant = str(turn.get("assistant") or "").strip()
            if user:
                messages.append({"role": "user", "content": user, "status": "ok"})
            if assistant:
                messages.append({"role": "assistant", "content": assistant, "status": "ok"})
        return messages[-40:]

    def _recent_messages_to_working_memory(self, messages: Sequence[Any]) -> List[Dict[str, Any]]:
        turns: List[Dict[str, Any]] = []
        pending_user = ""
        for item in messages:
            if not isinstance(item, Mapping):
                continue
            role = str(item.get("role") or "").strip()
            content = str(item.get("content") or "").strip()
            if role == "user":
                if pending_user:
                    turns.append({"user": pending_user, "assistant": "", "timestamp": item.get("created_at") or ""})
                pending_user = content
            elif role == "assistant":
                turns.append(
                    {
                        "user": pending_user,
                        "assistant": content,
                        "timestamp": item.get("created_at") or "",
                    }
                )
                pending_user = ""
        if pending_user:
            turns.append({"user": pending_user, "assistant": "", "timestamp": _now_iso()})
        return turns[-self.max_working_turns :]

    @staticmethod
    def _parse_json_object(text: str) -> Dict[str, Any]:
        raw = str(text or "").strip()
        if not raw:
            return {}
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE).strip()
        raw = re.sub(r"\s*```$", "", raw).strip()
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            raw = match.group(0)
        try:
            parsed = json.loads(raw)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
