#!/usr/bin/env bash
# Pull the uncensored chat LLM (prompt-refinement) into Ollama.
set -euo pipefail

PRIMARY="${OLLAMA_LLM:-hf.co/HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive:Q4_K_M}"

echo "Pulling chat LLM: $PRIMARY (~5GB)"
ollama pull "$PRIMARY"

echo "✓ Ollama models:"; ollama list
