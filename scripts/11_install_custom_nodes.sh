#!/usr/bin/env bash
# Install ComfyUI custom nodes needed by our workflow templates.
# Deliberately AVOIDS onnxruntime-dependent nodes (DWPose/openpose/InstantID) — arm64 install friction.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AISTUDIO_HOME="${AISTUDIO_HOME:-$REPO_ROOT/AIStudio}"
COMFY_DIR="$AISTUDIO_HOME/comfyui"
NODES_DIR="$COMFY_DIR/custom_nodes"
mkdir -p "$NODES_DIR"
cd "$NODES_DIR"

# shellcheck disable=SC1091
source "$COMFY_DIR/.venv/bin/activate"

clone() {  # clone <url> <dir>
  local url="$1" dir="$2"
  if [ ! -d "$dir/.git" ]; then
    echo "── clone $dir"
    git clone --depth 1 "$url" "$dir"
  else
    echo "── update $dir"; git -C "$dir" pull --ff-only || true
  fi
  if [ -f "$dir/requirements.txt" ]; then
    # Strip onnxruntime lines to avoid arm64 build pain; we don't use those nodes.
    grep -viE 'onnxruntime|insightface|mediapipe|dwpose' "$dir/requirements.txt" > /tmp/req_clean.txt || true
    uv pip install -r /tmp/req_clean.txt || echo "⚠ some deps for $dir failed (non-fatal)"
  fi
}

# GGUF unet/clip loaders — required by every FLUX/Chroma/Qwen template
clone https://github.com/city96/ComfyUI-GGUF                       ComfyUI-GGUF
# ControlNet preprocessors (we use only canny/depth/scribble/lineart — torch-only)
clone https://github.com/Fannovel16/comfyui_controlnet_aux         comfyui_controlnet_aux
# Multi-reference latent injection (1-4 images, per-image strength) — Kontext/Flux/Qwen
clone https://github.com/shootthesound/comfyui-ReferenceLatentPlus  comfyui-ReferenceLatentPlus
# FLUX Redux strength control (base Redux is built into ComfyUI core StyleModel nodes)
clone https://github.com/kaibioinfo/ComfyUI_AdvancedRefluxControl   ComfyUI_AdvancedRefluxControl

echo "✓ Custom nodes installed (onnxruntime-dependent nodes intentionally skipped)."
echo "  Note: FLUX.1-Kontext is supported natively by recent ComfyUI core; no extra node needed."
