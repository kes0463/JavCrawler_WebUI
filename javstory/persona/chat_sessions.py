"""Persona Chat 대화 이력(세션) — 일반 AI 서비스처럼 여러 대화를 목록으로 관리.

세션당 JSON 파일 하나(``data/cache/persona_chat_sessions/<id>.json``)에 메시지 전체를
저장한다. 취향/선호 메모리(``EnhancedPersonaMemory``)와는 별개 — 그건 세션과 무관하게
계속 누적되는 페르소나의 "기억"이고, 여기는 순수 대화 로그(사이드바 목록용)다.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from javstory.config.app_config import DATA_ROOT

SESSIONS_DIR = DATA_ROOT / "cache" / "persona_chat_sessions"
DEFAULT_TITLE = "새 대화"
_TITLE_MAX_LEN = 40
_SESSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class ChatTurnMessage:
    role: str
    content: str
    reasoning: str = ""
    ts: str = field(default_factory=_now_iso)


@dataclass
class ChatSession:
    id: str
    title: str = DEFAULT_TITLE
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    messages: List[Dict[str, Any]] = field(default_factory=list)


def _is_valid_id(session_id: str) -> bool:
    return bool(_SESSION_ID_RE.match(session_id or ""))


def _session_path(session_id: str) -> Path | None:
    if not _is_valid_id(session_id):
        return None
    return SESSIONS_DIR / f"{session_id}.json"


def _write(session: ChatSession) -> None:
    path = _session_path(session.id)
    if path is None:
        return
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(asdict(session), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _read(session_id: str) -> ChatSession | None:
    path = _session_path(session_id)
    if path is None or not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    return ChatSession(
        id=str(raw.get("id") or session_id),
        title=str(raw.get("title") or DEFAULT_TITLE),
        created_at=str(raw.get("created_at") or _now_iso()),
        updated_at=str(raw.get("updated_at") or _now_iso()),
        messages=list(raw.get("messages") or []),
    )


def list_sessions() -> List[Dict[str, Any]]:
    """{id, title, created_at, updated_at} 목록 — updated_at 내림차순."""
    if not SESSIONS_DIR.is_dir():
        return []
    out: List[Dict[str, Any]] = []
    for path in SESSIONS_DIR.glob("*.json"):
        if not _is_valid_id(path.stem):
            continue
        session = _read(path.stem)
        if session is None:
            continue
        out.append(
            {
                "id": session.id,
                "title": session.title,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            }
        )
    out.sort(key=lambda s: s["updated_at"], reverse=True)
    return out


def create_session() -> Dict[str, Any]:
    session = ChatSession(id=uuid.uuid4().hex)
    _write(session)
    return asdict(session)


def get_session(session_id: str) -> Dict[str, Any] | None:
    session = _read(session_id)
    return asdict(session) if session else None


def delete_session(session_id: str) -> bool:
    path = _session_path(session_id)
    if path is None or not path.is_file():
        return False
    path.unlink()
    return True


def rename_session(session_id: str, title: str) -> Dict[str, Any] | None:
    session = _read(session_id)
    if session is None:
        return None
    session.title = (title or "").strip()[:_TITLE_MAX_LEN] or DEFAULT_TITLE
    session.updated_at = _now_iso()
    _write(session)
    return asdict(session)


def _auto_title_from(text: str) -> str:
    collapsed = " ".join((text or "").split())
    if len(collapsed) <= _TITLE_MAX_LEN:
        return collapsed or DEFAULT_TITLE
    return collapsed[: _TITLE_MAX_LEN - 1].rstrip() + "…"


def append_turn(
    session_id: str,
    user_text: str,
    assistant_text: str,
    *,
    reasoning: str = "",
) -> Dict[str, Any] | None:
    """세션에 (user, assistant) 한 턴을 추가. 세션이 없으면 새로 만든다.

    세션 제목이 아직 기본값이면 첫 사용자 메시지로 자동 타이틀링한다.
    """
    session = _read(session_id) if _is_valid_id(session_id) else None
    if session is None:
        session = ChatSession(id=session_id if _is_valid_id(session_id) else uuid.uuid4().hex)

    if session.title == DEFAULT_TITLE and user_text.strip():
        session.title = _auto_title_from(user_text)

    session.messages.append({"role": "user", "content": user_text, "ts": _now_iso()})
    session.messages.append(
        {"role": "assistant", "content": assistant_text, "reasoning": reasoning, "ts": _now_iso()}
    )
    session.updated_at = _now_iso()
    _write(session)
    return asdict(session)
