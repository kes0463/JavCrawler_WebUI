#!/usr/bin/env bash
# Linux/macOS — experimental launcher (Windows: start.bat)
set -euo pipefail
cd "$(dirname "$0")/.."
export JAVSTORY_DISABLE_MICA="${JAVSTORY_DISABLE_MICA:-1}"

if [[ ! -x venv/bin/python ]]; then
  echo "[ERROR] venv not found. Run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

exec venv/bin/python main.py "$@"
