#!/usr/bin/env bash
# Download safetensors model weights into <repo>/AIStudio/models, each step guarded by the disk
# budget. Run a stage:  ./20_download_models.sh [sdxl|ref|all]
#
# The local lineup is a single SDXL checkpoint (Juggernaut XL) that serves every mode, plus
# IP-Adapter Plus (reference), SDXL ControlNet (structure) and Real-ESRGAN (upscale). Repo IDs +
# file paths marked VERIFY are best-guess preview names — confirm on HF before a fresh run. `dl`
# takes an EXACT repo file path (not a glob) and renames/flattens it to the name registry.py expects.
# All downloads use `hf download` (huggingface_hub CLI). FP8 files are intentionally never fetched (Metal-incompatible).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/lib_diskguard.sh"

# Load HF_TOKEN (+ other vars) from repo .env if present — enables fast, un-throttled downloads.
ENV_FILE="$HERE/../.env"
if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
fi
if [ -n "${HF_TOKEN:-}" ]; then
  export HF_TOKEN HUGGING_FACE_HUB_TOKEN="$HF_TOKEN"
  echo "✓ Using HF_TOKEN (authenticated, fast downloads)."
else
  echo "⚠ No HF_TOKEN in .env — downloads will be throttled (~640KB/s). Add one to .env for speed."
fi

AISTUDIO_HOME="${AISTUDIO_HOME:-$HERE/../AIStudio}"
M="$AISTUDIO_HOME/models"
STAGE="${1:-sdxl}"

# Resolve an `hf` CLI binary (prefer PATH, then uv-tool, then the ComfyUI venv).
HF_BIN=""
for cand in hf "$HOME/.local/bin/hf" "$AISTUDIO_HOME/comfyui/.venv/bin/hf"; do
  if command -v "$cand" >/dev/null 2>&1 || [ -x "$cand" ]; then HF_BIN="$cand"; break; fi
done
if [ -z "$HF_BIN" ]; then
  echo "Installing huggingface_hub CLI via uv tool..."
  uv tool install "huggingface_hub[cli,hf_transfer]" >/dev/null 2>&1 || true
  HF_BIN="$HOME/.local/bin/hf"
fi
# xet/hf_transfer can stall on throttled/unauthenticated connections; keep it off unless a token is set.
if [ -n "${HF_TOKEN:-}" ]; then export HF_HUB_ENABLE_HF_TRANSFER=1; else export HF_HUB_ENABLE_HF_TRANSFER=0; fi

dl() {  # dl <repo_id> <src_file_path> <dest-subdir> <dest-filename> <approx_gb>
  # `hf download` takes an EXACT repo file path (globs are NOT expanded as positionals — they
  # get URL-encoded into a literal name and 404). We download the exact file into a staging dir,
  # then move it to models/<sub>/<dest-filename> — flattening any repo subdir and renaming to the
  # name the registry (backend/app/models_catalog/registry.py) expects.
  local repo="$1" src="$2" sub="$3" dst="$4" gb="$5"
  local dest="$M/$sub/$dst"
  if [ -f "$dest" ]; then echo "✓ have models/$sub/$dst"; return 0; fi
  diskguard "$gb" || { echo "Skipping $repo/$src (disk)"; return 0; }
  echo "⬇ $repo :: $src -> models/$sub/$dst"
  mkdir -p "$M/$sub"
  local tmp; tmp="$(mktemp -d "$M/$sub/.dl.XXXXXX")"
  if "$HF_BIN" download "$repo" "$src" --local-dir "$tmp"; then
    mv -f "$tmp/$src" "$dest"
  else
    echo "⚠ download failed: $repo/$src (skipping, non-fatal)"
  fi
  rm -rf "$tmp"
}

stage_sdxl() {   # Juggernaut XL (single uncensored SDXL checkpoint, NSFW build) + SDXL VAE  (~8GB)
  # The destination filename MUST match registry MODELS["juggernaut-xl"].files["checkpoint"].
  dl RunDiffusion/Juggernaut-XL-v9 \
     "Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors"  checkpoints  juggernautXL_v9.safetensors  7   # VERIFY repo/src
  dl madebyollin/sdxl-vae-fp16-fix  "sdxl_vae.safetensors"  vae  sdxl_vae.safetensors  1
  # Optional NSFW LoRA (CivitAI, strength ~0.8) — uncomment + match registry builtin_loras name.
  # dl <repo> "<src>.safetensors"  loras  juggernaut_nsfw.safetensors  1   # VERIFY
}

stage_ref() {    # Reference (IP-Adapter Plus + CLIP-ViT-H) + ControlNet (canny/depth) + Real-ESRGAN  (~8GB)
  # IP-Adapter Plus model → models/ipadapter ; CLIP-ViT-H vision model → models/clip_vision.
  # Filenames MUST match registry IPADAPTER_FILES.
  dl h94/IP-Adapter \
     "sdxl_models/ip-adapter-plus_sdxl_vit-h.safetensors"  ipadapter  ip-adapter-plus_sdxl_vit-h.safetensors  1   # VERIFY repo path
  dl h94/IP-Adapter \
     "models/image_encoder/model.safetensors"  clip_vision  CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors  3   # VERIFY repo path + dest name
  # Both ControlNet repos ship the file as diffusion_pytorch_model.safetensors — rename per-type to
  # avoid a collision in controlnet/ and to match registry CONTROLNET_FILES.
  # diskguard does integer arithmetic — keep these whole GB (rounded up).
  dl xinsir/controlnet-canny-sdxl-1.0 \
     "diffusion_pytorch_model.safetensors"  controlnet  controlnet-canny-sdxl-1.0.safetensors  3
  dl xinsir/controlnet-depth-sdxl-1.0 \
     "diffusion_pytorch_model.safetensors"  controlnet  controlnet-depth-sdxl-1.0.safetensors  3
  dl ai-forever/Real-ESRGAN  "RealESRGAN_x4.pth"  upscale_models  RealESRGAN_x4.pth  1
}

case "$STAGE" in
  sdxl) stage_sdxl ;;
  ref)  stage_ref ;;
  all)  stage_sdxl; stage_ref ;;
  *) echo "usage: $0 [sdxl|ref|all]"; exit 1 ;;
esac
echo "✓ stage '$STAGE' done. Disk:"; df -g "$HOME" | awk 'NR==2{print $4" GB free"}'
