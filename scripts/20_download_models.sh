#!/usr/bin/env bash
# Download fp8/bf16/safetensors (+ retained GGUF) model weights into <repo>/AIStudio/models, in
# milestone order, each step guarded by the disk budget.
# Run a stage:  ./20_download_models.sh [base|sdxl|edit|ref|identity|video|all]
#
# LOCAL target is a single NVIDIA H100 80GB (CUDA): native fp8 is first-class; GGUF is kept only for
# flux-fill/kontext. ⚠ Repo IDs / filenames marked (VERIFY) — confirm on huggingface.co before a fresh
# machine run. All downloads use `hf download` (huggingface_hub CLI).
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

stage_base() {   # Chroma 1-HD native fp8 (default quality) + shared FLUX encoders/VAE + upscaler  (~17GB)
  # Shared FLUX-family native text encoders + VAE (Chroma/Redux/PuLID need these)
  dl comfyanonymous/flux_text_encoders    "t5xxl_fp8_e4m3fn.safetensors"     clip 5   # (VERIFY) single T5, type=chroma
  dl comfyanonymous/flux_text_encoders    "clip_l.safetensors"               clip 1
  dl black-forest-labs/FLUX.1-schnell     "ae.safetensors"                   vae  1
  # Chroma1-HD native fp8 single-file — PRIMARY uncensored photoreal (default txt2img/img2img)
  dl lodestones/Chroma1-HD                "Chroma1-HD-fp8.safetensors"       unet 9   # (VERIFY file)
  # RealESRGAN x4plus upscaler (Ultimate SD Upscale reuses your own NSFW base)
  dl ai-forever/Real-ESRGAN               "RealESRGAN_x4plus.pth"            upscale_models 0.1  # (VERIFY)
}

stage_sdxl() {   # LUSTIFY v4 (universal SDXL adapter base) + LUSTIFY SDXL Inpainting  (~16GB)
  dl TheImposterImposters/LUSTIFY-v4.0 \
     "lustifySDXLNSFW_v40.safetensors"  checkpoints 7   # (VERIFY) civitai 573152
  dl andro-flock/LUSTIFY-SDXL-NSFW-checkpoint-v2-0-INPAINTING \
     "lustifySDXL_inpainting.safetensors"  checkpoints 7   # (VERIFY)
  dl madebyollin/sdxl-vae-fp16-fix        "sdxl_vae.safetensors"             vae 1
}

stage_edit() {   # Instruction edit (Qwen-Edit Rapid AIO, default) + Kontext + FLUX Fill (GGUF kept)  (~49GB)
  dl Phr00t/Qwen-Image-Edit-Rapid-AIO     "Qwen-Image-Edit-Rapid-AIO.safetensors"  checkpoints 29   # (VERIFY) fp8 all-in-one
  dl YarvixPA/FLUX.1-Fill-dev-GGUF        "*Q5_K_M.gguf"                     unet 8
  dl city96/FLUX.1-Kontext-dev-gguf       "*Q4_K_M.gguf"                     unet 7   # (VERIFY repo)
}

stage_ref() {    # Reference: xinsir ControlNet-Union ProMax (single file) + FLUX Redux + CLIP-Vision  (~5GB)
  dl xinsir/controlnet-union-sdxl-1.0     "controlnet-union-sdxl-promax.safetensors" controlnet 2.5  # (VERIFY) covers canny/depth/scribble/lineart/pose
  dl black-forest-labs/FLUX.1-Redux-dev   "flux1-redux-dev.safetensors"      style_models 1   # (VERIFY)
  dl Comfy-Org/sigclip_vision_384         "sigclip_vision_patch14_384.safetensors"  clip_vision 1   # (VERIFY)
}

stage_identity() {  # Consent-gated face identity: PuLID-FLUX + InstantID + IP-Adapter FaceID + CLIP-Vision  (~6GB)
  dl guozinan/PuLID                       "pulid_flux_v0.9.1.safetensors"    pulid 1   # (VERIFY)
  dl InstantX/InstantID                   "ip-adapter.bin"                   instantid 1.5   # (VERIFY)
  dl InstantX/InstantID                   "ControlNetModel/diffusion_pytorch_model.safetensors" instantid 2.5  # (VERIFY) → instantid-diffusion_pytorch_model.safetensors
  dl h94/IP-Adapter-FaceID                "ip-adapter-faceid-plusv2_sdxl.bin"  ipadapter 1   # (VERIFY)
  dl h94/IP-Adapter                       "models/image_encoder/model.safetensors"  clip_vision 1   # (VERIFY) CLIP-ViT-H → CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors
}

stage_video() {  # NSFW video (Wan 2.2): TI2V-5B (default) + T2V/I2V-A14B + umt5/vae + lightx2v 4-step LoRA  (~84GB)
  # Shared Wan encoder + VAE
  dl Comfy-Org/Wan_2.2_ComfyUI_Repackaged "split_files/text_encoders/umt5_xxl_fp8_e4m3fn.safetensors"  clip 5   # (VERIFY)
  dl Comfy-Org/Wan_2.2_ComfyUI_Repackaged "split_files/vae/wan2.2_vae.safetensors"                     vae  1   # (VERIFY)
  # TI2V-5B (light, default video)
  dl Comfy-Org/Wan_2.2_ComfyUI_Repackaged "split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors" video 10  # (VERIFY) Wan-AI/Wan2.2-TI2V-5B
  # T2V-A14B (MoE: high+low noise UNETs)
  dl Comfy-Org/Wan_2.2_ComfyUI_Repackaged "split_files/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors" video 14  # (VERIFY) Wan-AI/Wan2.2-T2V-A14B
  dl Comfy-Org/Wan_2.2_ComfyUI_Repackaged "split_files/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors"  video 14  # (VERIFY)
  # I2V-A14B (MoE: high+low noise UNETs)
  dl Comfy-Org/Wan_2.2_ComfyUI_Repackaged "split_files/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors" video 14  # (VERIFY) Wan-AI/Wan2.2-I2V-A14B
  dl Comfy-Org/Wan_2.2_ComfyUI_Repackaged "split_files/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"  video 14  # (VERIFY)
  # lightx2v 4-step distill LoRAs (T2V + I2V)
  dl lightx2v/Wan2.2-Distill-Models       "wan2.2_t2v_lightx2v_4step.safetensors"  loras 1   # (VERIFY)
  dl lightx2v/Wan2.2-Distill-Models       "wan2.2_i2v_lightx2v_4step.safetensors"  loras 1   # (VERIFY)
}

case "$STAGE" in
  base)     stage_base ;;
  sdxl)     stage_sdxl ;;
  edit)     stage_edit ;;
  ref)      stage_ref ;;
  identity) stage_identity ;;
  video)    stage_video ;;
  all)      stage_base; stage_sdxl; stage_edit; stage_ref; stage_identity; stage_video ;;
  *) echo "usage: $0 [base|sdxl|edit|ref|identity|video|all]"; exit 1 ;;
esac
echo "✓ stage '$STAGE' done. Disk: $(free_gb) GB free on ${AISTUDIO_HOME:-$HOME}"
