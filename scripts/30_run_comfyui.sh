#!/usr/bin/env bash
# Launch ComfyUI on a single NVIDIA H100 80GB (CUDA). Reads weights from <repo>/AIStudio/models
# via extra_model_paths.yaml. The full photoreal stack co-resides on GPU 0 (--highvram).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AISTUDIO_HOME="${AISTUDIO_HOME:-$REPO_ROOT/AIStudio}"
COMFY_DIR="$AISTUDIO_HOME/comfyui"
cd "$COMFY_DIR"

# Use the venv interpreter directly (robust even if the venv was relocated/copied).
PY="$COMFY_DIR/.venv/bin/python"

# Pin to GPU 0 so the multi-model stack co-resides on one H100.
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

exec "$PY" main.py \
  --listen 127.0.0.1 --port "${COMFY_PORT:-8188}" \
  --highvram \
  --use-pytorch-cross-attention \
  --preview-method auto \
  --extra-model-paths-config "$AISTUDIO_HOME/extra_model_paths.yaml"
