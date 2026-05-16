"""API 키: keyring 우선 저장 + .env 동기화 및 os.environ 반영."""
from __future__ import annotations

import os
from typing import Optional

import keyring
from dotenv import load_dotenv

from javstory.config.app_config import (
    ENV_FILE_PATH,
    ENV_OPENROUTER_API_KEY,
    KEYRING_ACCOUNT_OPENROUTER,
    KEYRING_SERVICE_NAME,
    ENV_GEMINI_API_KEY,
    KEYRING_ACCOUNT_GEMINI,
)

# 프로젝트 .env 로드 (이미 설정된 OS 환경변수는 덮어쓰지 않음 — dotenv 기본)
load_dotenv(ENV_FILE_PATH, override=False)


def get_openrouter_api_key() -> Optional[str]:
    """환경변수 → keyring 순으로 조회. 공백만 있으면 None 취급."""
    key = os.getenv(ENV_OPENROUTER_API_KEY)
    if key and key.strip():
        return key.strip()
    stored = keyring.get_password(KEYRING_SERVICE_NAME, KEYRING_ACCOUNT_OPENROUTER)
    if stored and stored.strip():
        return stored.strip()
    return None


def set_openrouter_api_key(value: str, *, write_env_file: bool = True) -> None:
    """keyring 저장, os.environ 반영, 옵션으로 .env 파일 기록."""
    v = (value or "").strip()
    if not v:
        raise ValueError("API 키가 비어 있습니다.")

    keyring.set_password(KEYRING_SERVICE_NAME, KEYRING_ACCOUNT_OPENROUTER, v)
    os.environ[ENV_OPENROUTER_API_KEY] = v

    if write_env_file:
        set_env_runtime_value(ENV_OPENROUTER_API_KEY, v)


def _escape_env_value(value: str) -> str:
    """double-quoted .env 값에 쓸 수 있도록 특수문자를 이스케이프한다.

    처리 순서: 백슬래시 → 큰따옴표 → 개행 → 캐리지리턴
    순서를 바꾸면 이중 이스케이프가 발생하므로 변경하지 말 것.
    """
    return (
        value
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )


def set_env_runtime_value(key: str, value: str) -> None:
    """임의의 환경변수 키-값을 .env 파일에 안전하게 반영하고 os.environ에도 즉시 적용."""
    os.environ[key] = str(value)

    escaped = _escape_env_value(str(value))
    entry = f'{key}="{escaped}"'

    lines: list[str] = []
    if ENV_FILE_PATH.is_file():
        raw = ENV_FILE_PATH.read_text(encoding="utf-8")
        lines = raw.splitlines()

    out: list[str] = []
    replaced = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            out.append(line)
            continue

        name = line.split("=", 1)[0].strip()
        if name == key:
            out.append(entry)
            replaced = True
        else:
            out.append(line)

    if not replaced:
        if out and out[-1].strip():
            out.append("")
        out.append(entry)

    ENV_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ENV_FILE_PATH.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def clear_openrouter_api_key_from_keyring() -> None:
    """keyring 항목만 제거(.env는 사용자가 직접 지우거나 다음 저장 시 덮어쓰기)."""
    try:
        keyring.delete_password(KEYRING_SERVICE_NAME, KEYRING_ACCOUNT_OPENROUTER)
    except Exception:
        pass


def get_gemini_api_key() -> Optional[str]:
    """환경변수 → keyring 순으로 조회. 공백만 있으면 None 취급."""
    key = os.getenv(ENV_GEMINI_API_KEY)
    if key and key.strip():
        return key.strip()
    stored = keyring.get_password(KEYRING_SERVICE_NAME, KEYRING_ACCOUNT_GEMINI)
    if stored and stored.strip():
        return stored.strip()
    return None


def set_gemini_api_key(value: str, *, write_env_file: bool = True) -> None:
    """keyring 저장, os.environ 반영, 옵션으로 .env 파일 기록."""
    v = (value or "").strip()
    if not v:
        raise ValueError("Gemini API 키가 비어 있습니다.")
    keyring.set_password(KEYRING_SERVICE_NAME, KEYRING_ACCOUNT_GEMINI, v)
    os.environ[ENV_GEMINI_API_KEY] = v
    if write_env_file:
        set_env_runtime_value(ENV_GEMINI_API_KEY, v)


def clear_gemini_api_key_from_keyring() -> None:
    try:
        keyring.delete_password(KEYRING_SERVICE_NAME, KEYRING_ACCOUNT_GEMINI)
    except Exception:
        pass


def apply_env_to_os() -> None:
    """저장소에서 읽은 키를 subprocess/라이브러리용으로 os.environ에 맞춤."""
    k = get_openrouter_api_key()
    if k:
        os.environ[ENV_OPENROUTER_API_KEY] = k
    gk = get_gemini_api_key()
    if gk:
        os.environ[ENV_GEMINI_API_KEY] = gk
