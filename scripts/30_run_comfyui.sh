#!/usr/bin/env bash
# Launch ComfyUI with Mac/MPS-tuned flags. Reads weights from <repo>/AIStudio/models via extra_model_paths.yaml.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AISTUDIO_HOME="${AISTUDIO_HOME:-$REPO_ROOT/AIStudio}"
COMFY_DIR="$AISTUDIO_HOME/comfyui"
cd "$COMFY_DIR"

# Use the venv interpreter directly (robust even if the venv was relocated/copied).
PY="$COMFY_DIR/.venv/bin/python"

# PYTORCH_ENABLE_MPS_FALLBACK lets unsupported ops fall back to CPU instead of crashing.
export PYTORCH_ENABLE_MPS_FALLBACK=1

exec "$PY" main.py \
  --listen 127.0.0.1 --port "${COMFY_PORT:-8188}" \
  --use-pytorch-cross-attention \
  --reserve-vram 2.0 \
  --preview-method auto \
  --extra-model-paths-config "$AISTUDIO_HOME/extra_model_paths.yaml"
