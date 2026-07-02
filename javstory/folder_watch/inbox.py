"""폴더 연결 알림 인박스 영속화."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from javstory.config.app_config import DATA_ROOT

_INBOX_PATH = DATA_ROOT / "folder_binding_inbox.json"


@dataclass
class FolderBindingInboxItem:
    product_code: str
    old_path: str = ""
    candidates: list[str] = field(default_factory=list)


def _normalize_item(raw: dict) -> FolderBindingInboxItem | None:
    if not isinstance(raw, dict):
        return None
    pc = str(raw.get("product_code") or raw.get("productCode") or "").strip().upper()
    if not pc:
        return None
    op = str(raw.get("old_path") or raw.get("oldPath") or "")
    raw_c = raw.get("candidates")
    cands = [str(x) for x in raw_c if x is not None] if isinstance(raw_c, list) else []
    return FolderBindingInboxItem(product_code=pc, old_path=op, candidates=cands)


def load_inbox() -> list[FolderBindingInboxItem]:
    if not _INBOX_PATH.is_file():
        return []
    try:
        data = json.loads(_INBOX_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        out: list[FolderBindingInboxItem] = []
        for item in data:
            norm = _normalize_item(item)
            if norm:
                out.append(norm)
        return out
    except Exception:
        return []


def save_inbox(items: list[FolderBindingInboxItem]) -> None:
    try:
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
        arr = [
            {
                "product_code": i.product_code,
                "old_path": i.old_path,
                "candidates": list(i.candidates),
            }
            for i in items
        ]
        tmp = _INBOX_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(arr, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_INBOX_PATH)
    except Exception:
        pass


def upsert_inbox_item(product_code: str, old_path: str, candidates: list[str]) -> list[FolderBindingInboxItem]:
    pc = (product_code or "").strip().upper()
    if not pc:
        return load_inbox()
    items = load_inbox()
    found = False
    for i, item in enumerate(items):
        if item.product_code == pc:
            items[i] = FolderBindingInboxItem(
                product_code=pc,
                old_path=old_path or "",
                candidates=list(candidates),
            )
            found = True
            break
    if not found:
        items.append(
            FolderBindingInboxItem(
                product_code=pc,
                old_path=old_path or "",
                candidates=list(candidates),
            )
        )
    save_inbox(items)
    return items


def remove_inbox_item(product_code: str) -> list[FolderBindingInboxItem]:
    pc = (product_code or "").strip().upper()
    items = [i for i in load_inbox() if i.product_code != pc]
    save_inbox(items)
    return items


def clear_inbox() -> None:
    save_inbox([])


def get_inbox_item(product_code: str) -> FolderBindingInboxItem | None:
    pc = (product_code or "").strip().upper()
    if not pc:
        return None
    for item in load_inbox():
        if item.product_code == pc:
            return item
    return None


def inbox_contains(product_code: str) -> bool:
    return get_inbox_item(product_code) is not None
