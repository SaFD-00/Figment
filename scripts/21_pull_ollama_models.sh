#!/usr/bin/env bash
# Pull the uncensored, vision-capable chat/planner LLM (prompt-refinement) into Ollama.
# Blobs land on the /data volume via OLLAMA_MODELS — the *running server's* env governs storage,
# so we (re)ensure the server is up and pointed at /data via 31_run_ollama.sh before pulling.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure the server is running with OLLAMA_MODELS pointed at /data (idempotent).
"$HERE/31_run_ollama.sh"

# The chat/planner LLM lineup is vision-capable only — the local default is the multimodal qwen3-vl.
PRIMARY="${OLLAMA_LLM:-huihui_ai/qwen3-vl-abliterated:8b}"

echo "Pulling chat/planner LLM: $PRIMARY (~5GB)"
ollama pull "$PRIMARY"

echo "✓ Ollama models:"; ollama list
