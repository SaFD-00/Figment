#!/usr/bin/env bash
# Install ComfyUI into <repo>/AIStudio/comfyui with its own uv venv (MPS torch on arm64 macOS).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AISTUDIO_HOME="${AISTUDIO_HOME:-$REPO_ROOT/AIStudio}"
COMFY_DIR="$AISTUDIO_HOME/comfyui"

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

# PyTorch nightly/stable with MPS comes from the default index on macOS arm64.
uv pip install --upgrade pip
uv pip install torch torchvision torchaudio
uv pip install -r requirements.txt

echo "✓ ComfyUI installed. Python: $(python --version), torch MPS check:"
python - <<'PY'
import torch
print("torch", torch.__version__, "mps available:", torch.backends.mps.is_available())
PY
