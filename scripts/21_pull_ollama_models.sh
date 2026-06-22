#!/usr/bin/env bash
# Pull the uncensored chat LLM (prompt-refinement) into Ollama.
# Blobs land on the /data volume via OLLAMA_MODELS — the *running server's* env governs storage,
# so we (re)ensure the server is up and pointed at /data via 31_run_ollama.sh before pulling.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure the server is running with OLLAMA_MODELS pointed at /data (idempotent).
"$HERE/31_run_ollama.sh"

PRIMARY="${OLLAMA_LLM:-hf.co/HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive:Q4_K_M}"
FALLBACK="hf.co/HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive:Q4_K_M"

echo "Pulling primary LLM: $PRIMARY (~5GB)"
ollama pull "$PRIMARY"

echo "Pulling fallback LLM: $FALLBACK (~2.6GB)"
ollama pull "$FALLBACK" || echo "⚠ fallback pull failed (non-fatal)"

echo "✓ Ollama models:"; ollama list
