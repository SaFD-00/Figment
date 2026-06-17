#!/usr/bin/env bash
# Pull the uncensored multimodal chat LLM (prompt-refinement + vision enhance) into Ollama.
set -euo pipefail

PRIMARY="${OLLAMA_LLM:-huihui_ai/gemma-4-abliterated:e4b}"

echo "Pulling chat LLM: $PRIMARY (~9.6GB)"
ollama pull "$PRIMARY"

echo "✓ Ollama models:"; ollama list
