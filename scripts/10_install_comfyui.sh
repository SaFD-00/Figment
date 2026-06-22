#!/usr/bin/env bash
# Install ComfyUI into <repo>/AIStudio/comfyui with its own uv venv (CUDA torch for the H100).
# TARGET: single NVIDIA H100 80GB (CUDA, GPU 0). The torch CUDA wheels bundle their own runtime, so
# the host only needs a recent driver (>=525); the system nvcc/CUDA version is irrelevant. Override
# the wheel channel with TORCH_CUDA=cu126|cu128 if you want newer cuDNN/cuBLAS.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AISTUDIO_HOME="${AISTUDIO_HOME:-$REPO_ROOT/AIStudio}"
COMFY_DIR="$AISTUDIO_HOME/comfyui"
TORCH_CUDA="${TORCH_CUDA:-cu124}"   # cu124 covers Hopper/H100 (sm_90); newer driver (595) accepts cu126/cu128 too

if [ ! -d "$COMFY_DIR/.git" ]; then
  echo "Cloning ComfyUI -> $COMFY_DIR"
  git clone --depth 1 https://github.com/comfyanonymous/ComfyUI "$COMFY_DIR"
else
  echo "ComfyUI already cloned; pulling latest"
  git -C "$COMFY_DIR" pull --ff-only || true
fi

cd "$COMFY_DIR"
if [ ! -d ".venv" ]; then
  uv venv --python 3.12 .venv   # 3.12 is the most wheel-complete for the ML stack
fi
# shellcheck disable=SC1091
source .venv/bin/activate

uv pip install --upgrade pip
# CUDA PyTorch from the pinned channel (wheels carry the CUDA runtime; host driver 525+ suffices).
uv pip install torch torchvision torchaudio --index-url "https://download.pytorch.org/whl/${TORCH_CUDA}"
uv pip install -r requirements.txt

echo "✓ ComfyUI installed. Python: $(python --version), torch CUDA check:"
python - <<'PY'
import torch
print("torch", torch.__version__,
      "| cuda available:", torch.cuda.is_available(),
      "| device:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu")
PY
