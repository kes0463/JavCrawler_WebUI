"""Translation system prompt template / mode configuration."""

from __future__ import annotations

import os
from typing import Any

from javstory.translation.translation_notes import GLOBAL_NOTE_PATH, load_global_note, save_global_note

PROMPT_MODES: tuple[str, ...] = ("auto", "html", "json")
PROMPT_VARIANTS: tuple[str, ...] = ("general", "jav")

PROMPT_MODE_LABELS: dict[str, str] = {
    "auto": "자동 (Gemini=HTML, 그 외=JSON)",
    "html": "HTML (<main>/<p> continuation)",
    "json": "JSON 배열 (레거시)",
}

PROMPT_VARIANT_LABELS: dict[str, str] = {
    "general": "일반 (공리+지침)",
    "jav": "JAV 자막 (성인 콘텐츠 지침 포함)",
}

SYSTEM_PROMPT_PATH = GLOBAL_NOTE_PATH.parent / "translation_system_prompt.txt"


def _env_bool(key: str, default: bool = False) -> bool:
    raw = (os.environ.get(key, "") or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def normalize_prompt_mode(raw: str | None) -> str:
    m = (raw or "auto").strip().lower()
    return m if m in PROMPT_MODES else "auto"


def normalize_prompt_variant(raw: str | None) -> str:
    v = (raw or "general").strip().lower()
    return v if v in PROMPT_VARIANTS else "general"


def prompt_mode_from_env() -> str:
    return normalize_prompt_mode(os.environ.get("JAVSTORY_TRANSLATION_PROMPT_MODE", "auto"))


def prompt_variant_from_env() -> str:
    return normalize_prompt_variant(os.environ.get("JAVSTORY_TRANSLATION_PROMPT_VARIANT", "general"))


def uses_custom_system_prompt_file() -> bool:
    return SYSTEM_PROMPT_PATH.is_file()


def builtin_system_prompt_template(variant: str) -> str:
    from javstory.translation.gemini_prompts import SYSTEM_TEMPLATE_GENERAL, SYSTEM_TEMPLATE_JAV

    v = normalize_prompt_variant(variant)
    return SYSTEM_TEMPLATE_JAV if v == "jav" else SYSTEM_TEMPLATE_GENERAL


def load_system_prompt_template(variant: str | None = None) -> str:
    """커스텀 파일 우선, 없으면 내장 variant."""
    try:
        if SYSTEM_PROMPT_PATH.is_file():
            return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        pass
    return builtin_system_prompt_template(variant or prompt_variant_from_env())


def save_system_prompt_template(text: str) -> None:
    """시스템 프롬프트 템플릿 저장. 내장과 동일하면 파일 삭제."""
    SYSTEM_PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    s = (text or "").rstrip()
    builtin = builtin_system_prompt_template(prompt_variant_from_env())
    if not s or s == builtin.rstrip():
        try:
            if SYSTEM_PROMPT_PATH.is_file():
                SYSTEM_PROMPT_PATH.unlink()
        except OSError:
            pass
        return
    SYSTEM_PROMPT_PATH.write_text(s + "\n", encoding="utf-8")


def format_system_prompt(template: str, note: str) -> str:
    """`{note}` / `{{note}}` 치환."""
    n = (note or "").strip()
    out = template.replace("{{note}}", n).replace("{note}", n)
    return out.strip()


def build_translation_system_prompt(
    note: str = "",
    *,
    variant: str | None = None,
) -> str:
    template = load_system_prompt_template(variant)
    return format_system_prompt(template, note)


def uses_html_translation_prompt(tier: dict[str, Any]) -> bool:
    mode = prompt_mode_from_env()
    if mode == "html":
        return True
    if mode == "json":
        return False
    return str(tier.get("provider") or "").lower() == "gemini"


def user_message_format_hint() -> str:
    return (
        '<main id="원문">\n'
        '<p id="0">日本語…</p>\n'
        "…\n"
        "</main>\n"
        '<main id="번역">'
    )


def translation_prompt_settings_snapshot() -> dict[str, Any]:
    variant = prompt_variant_from_env()
    template = load_system_prompt_template(variant)
    return {
        "prompt_mode": prompt_mode_from_env(),
        "prompt_variant": variant,
        "system_prompt_template": template,
        "uses_custom_template": uses_custom_system_prompt_file(),
        "global_note": load_global_note(),
        "builtin_templates": {
            "general": builtin_system_prompt_template("general"),
            "jav": builtin_system_prompt_template("jav"),
        },
        "prompt_mode_options": [
            {"id": mid, "label": PROMPT_MODE_LABELS.get(mid, mid)}
            for mid in PROMPT_MODES
        ],
        "prompt_variant_options": [
            {"id": vid, "label": PROMPT_VARIANT_LABELS.get(vid, vid)}
            for vid in PROMPT_VARIANTS
        ],
        "user_message_format": user_message_format_hint(),
        "placeholders": {
            "note": "시스템 프롬프트 내 {note} 또는 {{note}} — 전역·배우·작품 노트 + 작품 메타",
            "slot": "유저 메시지의 원문 HTML — 청크별 자동 생성 (수동 편집 불필요)",
        },
    }
