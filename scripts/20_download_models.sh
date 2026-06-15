#!/usr/bin/env bash
# Download GGUF/safetensors model weights into <repo>/AIStudio/models, in milestone order,
# each step guarded by the disk budget. Run a stage:  ./20_download_models.sh [base|sdxl|edit|ref|all]
#
# ⚠ GGUF community repo IDs marked (VERIFY) — confirm on huggingface.co before a fresh machine run.
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
STAGE="${1:-base}"

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

dl() {  # dl <repo_id> <filename-glob> <dest-subdir> <approx_gb>
  local repo="$1" file="$2" sub="$3" gb="$4"
  diskguard "$gb" || { echo "Skipping $repo/$file (disk)"; return 0; }
  echo "⬇ $repo :: $file -> models/$sub"
  "$HF_BIN" download "$repo" "$file" --local-dir "$M/$sub"
}

stage_base() {   # Chroma (quality) + Z-Image (light) + shared encoders/vae  (~24GB)
  # Shared FLUX-family text encoders + VAE (Chroma/Flux-Fill/Kontext/Redux all need these)
  dl city96/t5-v1_1-xxl-encoder-gguf      "t5-v1_1-xxl-encoder-Q5_K_M.gguf"  clip 4
  dl comfyanonymous/flux_text_encoders    "clip_l.safetensors"               clip 1
  dl black-forest-labs/FLUX.1-schnell     "ae.safetensors"                   vae  1
  # Chroma1-HD (Q5_K_M GGUF) — PRIMARY quality/uncensored  (repo verified)
  dl silveroxides/Chroma1-HD-GGUF         "Chroma1-HD-Q5_K_M.gguf"           unet 8
  # Z-Image-Turbo (ComfyUI split files: UNET + Qwen text encoder + VAE + distill LoRA)
  dl Comfy-Org/z_image_turbo "split_files/diffusion_models/z_image_turbo_bf16.safetensors"      unet 6
  dl Comfy-Org/z_image_turbo "split_files/text_encoders/qwen_3_4b.safetensors"                  clip 4
  dl Comfy-Org/z_image_turbo "split_files/loras/z_image_turbo_distill_patch_lora_bf16.safetensors" loras 1
}

stage_sdxl() {   # Pony V6 (explicit NSFW, single-file) + SDXL inpaint  (~14GB)
  dl AiAF/ponyDiffusionV6XL_v6StartWithThisOne.safetensors \
     "ponyDiffusionV6XL_v6StartWithThisOne.safetensors"  checkpoints 7   # (verified single-file)
  dl diffusers/stable-diffusion-xl-1.0-inpainting-0.1 "*.safetensors"  checkpoints 7  # (VERIFY single-file)
  dl madebyollin/sdxl-vae-fp16-fix        "sdxl_vae.safetensors"             vae 1
}

stage_edit() {   # Inpaint (FLUX Fill) + instruction edit (Qwen-Edit + Lightning) + Kontext  (~30GB)
  dl YarvixPA/FLUX.1-Fill-dev-GGUF        "*Q5_K_M.gguf"                     unet 8
  dl unsloth/Qwen-Image-Edit-2511-GGUF    "*Q4_K_M.gguf"                     unet 13
  dl lightx2v/Qwen-Image-Edit-2511-Lightning "*.safetensors"                loras 1
  dl city96/FLUX.1-Kontext-dev-gguf       "*Q4_K_M.gguf"                     unet 7   # (VERIFY repo)
}

stage_ref() {    # Reference: SDXL ControlNet (canny+depth) + FLUX Redux + CLIP-Vision + upscaler  (~8GB)
  dl xinsir/controlnet-canny-sdxl-1.0     "diffusion_pytorch_model.safetensors" controlnet 2.5
  dl xinsir/controlnet-depth-sdxl-1.0     "diffusion_pytorch_model.safetensors" controlnet 2.5
  dl black-forest-labs/FLUX.1-Redux-dev   "*.safetensors"                    style_models 1
  dl Comfy-Org/sigclip_vision_384         "*.safetensors"                    clip_vision 1
  dl ai-forever/Real-ESRGAN               "RealESRGAN_x4.pth"                upscale_models 0.1  # (VERIFY)
}

case "$STAGE" in
  base) stage_base ;;
  sdxl) stage_sdxl ;;
  edit) stage_edit ;;
  ref)  stage_ref ;;
  all)  stage_base; stage_sdxl; stage_edit; stage_ref ;;
  *) echo "usage: $0 [base|sdxl|edit|ref|all]"; exit 1 ;;
esac
echo "✓ stage '$STAGE' done. Disk:"; df -g "$HOME" | awk 'NR==2{print $4" GB free"}'
