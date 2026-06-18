#!/usr/bin/env bash
# Pull the uncensored multimodal chat LLM (prompt-refinement + vision enhance) into Ollama.
set -euo pipefail

PRIMARY="${OLLAMA_LLM:-huihui_ai/qwen3-vl-abliterated:8b}"   # VERIFY Ollama tag

echo "Pulling chat LLM: $PRIMARY (~5GB)"
ollama pull "$PRIMARY"

echo "✓ Ollama models:"; ollama list
