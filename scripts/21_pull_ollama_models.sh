#!/usr/bin/env bash
# Pull the uncensored chat LLM (prompt-refinement) into Ollama.
set -euo pipefail

PRIMARY="${OLLAMA_LLM:-hf.co/HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive:Q4_K_M}"
FALLBACK="hf.co/HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive:Q4_K_M"

echo "Pulling primary LLM: $PRIMARY (~5GB)"
ollama pull "$PRIMARY"

echo "Pulling fallback LLM: $FALLBACK (~2.6GB)"
ollama pull "$FALLBACK" || echo "⚠ fallback pull failed (non-fatal)"

echo "✓ Ollama models:"; ollama list
