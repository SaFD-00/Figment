#!/usr/bin/env bash
# Ensure the Ollama server is running (it usually runs as a background service already).
# Pulled LLM blobs are stored on the big /data volume via OLLAMA_MODELS, NOT the small root volume.
# The *server* process's env decides where weights land, so OLLAMA_MODELS must be exported BEFORE
# `ollama serve` — a server started without it falls back to ~/.ollama/models on root.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Load OLLAMA_MODELS / overrides from repo .env if present.
ENV_FILE="$REPO_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
fi

AISTUDIO_HOME="${AISTUDIO_HOME:-$REPO_ROOT/AIStudio}"
# AISTUDIO_HOME is normally a symlink to /data/<user>/Figment/AIStudio (see AGENTS.md /
# scripts/00_bootstrap_dirs.sh), so this keeps the Ollama blob store on /data.
export OLLAMA_MODELS="${OLLAMA_MODELS:-$AISTUDIO_HOME/ollama}"
mkdir -p "$AISTUDIO_HOME/logs" "$OLLAMA_MODELS"

if curl -fsS "http://127.0.0.1:11434/api/version" >/dev/null 2>&1; then
  echo "✓ Ollama already serving on :11434 — leaving it as-is."
  echo "  ⚠ A running server keeps the store path it was started with; this script only sets"
  echo "    OLLAMA_MODELS ($OLLAMA_MODELS) for a server it starts. Restart it to relocate the store."
else
  echo "Starting ollama serve  (OLLAMA_MODELS=$OLLAMA_MODELS) ..."
  nohup ollama serve >"$AISTUDIO_HOME/logs/ollama.log" 2>&1 &
  sleep 2
  curl -fsS "http://127.0.0.1:11434/api/version" && echo "  ✓ up"
fi
