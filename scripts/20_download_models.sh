#!/usr/bin/env bash
# Download GGUF/safetensors model weights into <repo>/AIStudio/models, in milestone order,
# each step guarded by the disk budget. Run a stage:  ./20_download_models.sh [qwen|sdxl|edit|ref|all]
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
STAGE="${1:-qwen}"

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

stage_qwen() {   # Qwen-Image 2512 (txt2img/img2img) — uncensored stack: DiT GGUF + abliterated
                 # Qwen2.5-VL text encoder (+mmproj) + Qwen VAE + Lightning + NSFW LoRA  (~21GB)
  dl unsloth/Qwen-Image-2512-GGUF  "*Q4_K_M.gguf"  unet 13   # (VERIFY repo/file)
  # Abliterated Qwen2.5-VL text encoder lifts the refusal bias; mmproj is its vision projector.
  # The resulting .gguf filename must match registry files["clip"] — rename if it differs. (VERIFY)
  dl mradermacher/Qwen2.5-VL-7B-Instruct-abliterated-GGUF "*Q4_K_M.gguf"  clip 5
  dl mradermacher/Qwen2.5-VL-7B-Instruct-abliterated-GGUF "*mmproj*"      clip 1
  # Qwen VAE — shared with qwen-edit.
  dl Comfy-Org/Qwen-Image_ComfyUI  "split_files/vae/qwen_image_vae.safetensors"  vae 1   # (VERIFY)
  dl lightx2v/Qwen-Image-Lightning "*8steps*.safetensors"  loras 1   # (VERIFY) 8-step distill LoRA
  dl goonsai/qwen-image-loras      "qwen_MCNL_v1.0.safetensors"  loras 1   # (VERIFY) NSFW LoRA
}

stage_sdxl() {   # Pony V6 (explicit NSFW) + LUSTIFY SDXL NSFW inpaint (genuine 9-ch UNet, fp16)  (~14GB)
  dl AiAF/ponyDiffusionV6XL_v6StartWithThisOne.safetensors \
     "ponyDiffusionV6XL_v6StartWithThisOne.safetensors"  checkpoints 7   # (verified single-file)
  dl andro-flock/LUSTIFY-SDXL-NSFW-checkpoint-v2-0-INPAINTING \
     "lustifySDXLNSFW_v20-inpainting.safetensors"  checkpoints 7   # (VERIFY 9-ch inpaint)
  dl madebyollin/sdxl-vae-fp16-fix        "sdxl_vae.safetensors"             vae 1
}

stage_edit() {   # Instruction + reference edit: Qwen-Image-Edit 2511 + Lightning + NSFW LoRA  (~14GB)
  # Shares the abliterated Qwen2.5-VL text encoder + Qwen VAE pulled by `stage_qwen`.
  dl unsloth/Qwen-Image-Edit-2511-GGUF    "*Q4_K_M.gguf"                     unet 13
  dl lightx2v/Qwen-Image-Edit-2511-Lightning "*.safetensors"                loras 1
  dl goonsai/qwen-image-loras             "qwen_MCNL_v1.0.safetensors"       loras 1   # (VERIFY) NSFW LoRA
}

stage_ref() {    # Structure control (SDXL ControlNet canny+depth) + Real-ESRGAN upscaler  (~5GB)
  dl xinsir/controlnet-canny-sdxl-1.0     "diffusion_pytorch_model.safetensors" controlnet 2.5
  dl xinsir/controlnet-depth-sdxl-1.0     "diffusion_pytorch_model.safetensors" controlnet 2.5
  dl ai-forever/Real-ESRGAN               "RealESRGAN_x4.pth"                upscale_models 0.1  # (VERIFY)
}

case "$STAGE" in
  qwen) stage_qwen ;;
  sdxl) stage_sdxl ;;
  edit) stage_edit ;;
  ref)  stage_ref ;;
  all)  stage_qwen; stage_sdxl; stage_edit; stage_ref ;;
  *) echo "usage: $0 [qwen|sdxl|edit|ref|all]"; exit 1 ;;
esac
echo "✓ stage '$STAGE' done. Disk:"; df -g "$HOME" | awk 'NR==2{print $4" GB free"}'
