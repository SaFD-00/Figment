#!/usr/bin/env bash
# Ensure the Ollama server is running (it usually runs as a background service already).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AISTUDIO_HOME="${AISTUDIO_HOME:-$REPO_ROOT/AIStudio}"
mkdir -p "$AISTUDIO_HOME/logs"
if curl -fsS "http://127.0.0.1:11434/api/version" >/dev/null 2>&1; then
  echo "✓ Ollama already serving on :11434"
else
  echo "Starting ollama serve ..."
  nohup ollama serve >"$AISTUDIO_HOME/logs/ollama.log" 2>&1 &
  sleep 2
  curl -fsS "http://127.0.0.1:11434/api/version" && echo "  ✓ up"
fi
