#!/usr/bin/env bash
# Install the CUDA ComfyUI custom nodes for the H100 photoreal stack — identity / pose / upscale /
# bg-remove — plus the GGUF loaders and controlnet preprocessors. This is the single custom-node
# installer (no separate arm64 script). Wan 2.2 video uses ComfyUI's NATIVE core nodes
# (WanImageToVideo / EmptyHunyuanLatentVideo / SaveAnimatedWEBP), so no WanVideoWrapper is required.
# Run AFTER 10_install_comfyui.sh.
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
    uv pip install -r "$dir/requirements.txt" || echo "⚠ some deps for $dir failed (non-fatal)"
  fi
}

# GGUF unet/clip loaders — retained for flux-fill/kontext (re-clone is a no-op if already present)
clone https://github.com/city96/ComfyUI-GGUF                       ComfyUI-GGUF
# Face/identity adapters over LUSTIFY SDXL / Chroma
clone https://github.com/cubiq/ComfyUI_IPAdapter_plus              ComfyUI_IPAdapter_plus
clone https://github.com/cubiq/ComfyUI_InstantID                   ComfyUI_InstantID
clone https://github.com/balazik/ComfyUI-PuLID-Flux                ComfyUI-PuLID-Flux
# ControlNet preprocessors incl. DWPose (pose) — now usable on CUDA
clone https://github.com/Fannovel16/comfyui_controlnet_aux         comfyui_controlnet_aux
# Ultimate SD Upscale (reuses our own NSFW base)
clone https://github.com/ssitu/ComfyUI_UltimateSDUpscale           ComfyUI_UltimateSDUpscale
# Wan 2.2 video uses ComfyUI's native core nodes — no WanVideoWrapper needed.
# Background removal (BEN2/RMBG)
clone https://github.com/1038lab/ComfyUI-RMBG                      ComfyUI-RMBG

# Face detect + pose deps — arm64-blocked, fine on CUDA (InstantID / PuLID / DWPose).
echo "── pip install onnxruntime-gpu insightface (CUDA face+pose deps)"
uv pip install onnxruntime-gpu insightface || echo "⚠ onnxruntime-gpu/insightface install failed (non-fatal)"

echo "✓ CUDA custom nodes installed (identity / DWPose / USDU / RMBG / GGUF). Wan 2.2 = native core nodes."
