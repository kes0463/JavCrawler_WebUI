#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
MODEL="${JAVSTORY_OLLAMA_MODEL:-javstory-ko-av}"
FILE="config/ollama/Modelfile"
if [[ ! -f "$FILE" ]]; then
  echo "[ERROR] Modelfile not found: $FILE" >&2
  exit 1
fi
echo "Creating Ollama model '${MODEL}' from ${FILE} ..."
ollama create "${MODEL}" -f "${FILE}"
echo "Done. Use model name '${MODEL}' in JAVSTORY Settings (Ollama)."
