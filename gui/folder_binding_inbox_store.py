"""폴더 연결 알림 인박스 목록 영속화 (앱 재시작 후에도 미처리 항목 유지)."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QObject, Slot

from javstory.config.app_config import DATA_ROOT

_PATH = DATA_ROOT / "folder_binding_inbox.json"


class FolderBindingInboxStore(QObject):
    @Slot(result=str)
    def loadJson(self) -> str:
        if not _PATH.is_file():
            return "[]"
        try:
            raw = _PATH.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, list):
                return json.dumps(data, ensure_ascii=False)
        except Exception:
            pass
        return "[]"

    @Slot(str)
    def saveJson(self, payload: str) -> None:
        try:
            data = json.loads(payload)
            if not isinstance(data, list):
                return
            norm: list[dict[str, object]] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                pc = str(item.get("product_code") or item.get("productCode") or "").strip().upper()
                op = str(item.get("old_path") or item.get("oldPath") or "")
                raw_c = item.get("candidates")
                if isinstance(raw_c, list):
                    cands = [str(x) for x in raw_c if x is not None]
                else:
                    cands = []
                if not pc:
                    continue
                norm.append({"product_code": pc, "old_path": op, "candidates": cands})
            DATA_ROOT.mkdir(parents=True, exist_ok=True)
            tmp = _PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(norm, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(_PATH)
        except Exception:
            pass
