#!/usr/bin/env bash
# Download fp8/bf16/safetensors (+ retained GGUF) model weights into <repo>/AIStudio/models, in
# milestone order, each step guarded by the disk budget.
# Run a stage:  ./20_download_models.sh [base|sdxl|edit|ref|identity|video|all]
#
# LOCAL target is a single NVIDIA H100 80GB (CUDA): native fp8 is first-class; GGUF is kept only for
# flux-fill/kontext. Repo IDs / filenames below were VERIFIED against the HuggingFace API (2026-06):
# each `dl` line is <repo> <repo-file> <dest-subdir> <approx_gb> [rename_to]. Where the HF basename
# differs from the on-disk name the backend registry expects, the 5th arg renames it after download,
# so the registry/builder stay untouched. All downloads use `hf download` (huggingface_hub CLI).
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
# Xet high-performance transfer can stall on throttled/unauthenticated connections; enable only with a token.
if [ -n "${HF_TOKEN:-}" ]; then export HF_XET_HIGH_PERFORMANCE=1; else export HF_XET_HIGH_PERFORMANCE=0; fi

dl() {  # dl <repo_id> <repo_file> <dest-subdir> <approx_gb> [rename_to]
  local repo="$1" file="$2" sub="$3" gb="$4" rename="${5:-}"
  local destdir="$M/$sub"
  local target="${rename:-$(basename "$file")}"
  if [ -s "$destdir/$target" ]; then echo "✓ exists: $sub/$target — skip"; return 0; fi
  diskguard "$gb" || { echo "Skipping $repo/$file (disk)"; return 0; }
  echo "⬇ $repo :: $file  ->  models/$sub/$target  (~${gb}GB)"
  mkdir -p "$destdir"
  local stage="$M/.hfstage"; rm -rf "$stage"
  "$HF_BIN" download "$repo" "$file" --local-dir "$stage"
  mv -f "$stage/$file" "$destdir/$target"
  rm -rf "$stage"
}

stage_base() {   # Chroma1-HD native fp8 (default quality) + shared FLUX encoders/VAE + upscaler  (~15GB)
  # Shared FLUX-family native text encoders + VAE (Chroma/Redux/PuLID need these)
  dl comfyanonymous/flux_text_encoders  "t5xxl_fp8_e4m3fn.safetensors"  clip 5     # single T5, type=chroma
  dl comfyanonymous/flux_text_encoders  "clip_l.safetensors"            clip 0.25
  dl black-forest-labs/FLUX.1-schnell   "ae.safetensors"                vae  0.3   # FLUX VAE (Apache, un-gated)
  # Chroma1-HD native fp8 single-file — PRIMARY uncensored photoreal (default txt2img/img2img)
  dl Comfy-Org/Chroma1-HD_repackaged    "split_files/diffusion_models/Chroma1-HD-fp8mixed.safetensors" \
     unet 9.2 "Chroma1-HD-fp8.safetensors"
  # RealESRGAN x4plus upscaler (Ultimate SD Upscale reuses your own NSFW base for the diffusion tier)
  dl lllyasviel/Annotators              "RealESRGAN_x4plus.pth"         upscale_models 0.07
}

stage_sdxl() {   # LUSTIFY v4 (universal SDXL adapter base) + LUSTIFY SDXL Inpainting  (~14GB)
  dl xxxpo13/LUSTIFY_SDXL  "lustifySDXLNSFWSFW_v40.safetensors"  checkpoints 6.5 "lustifySDXLNSFW_v40.safetensors"
  dl andro-flock/LUSTIFY-SDXL-NSFW-checkpoint-v2-0-INPAINTING \
     "lustifySDXLNSFW_v20-inpainting.safetensors"  checkpoints 6.9 "lustifySDXL_inpainting.safetensors"
  dl madebyollin/sdxl-vae-fp16-fix  "sdxl_vae.safetensors"  vae 0.3
}

stage_edit() {   # Instruction edit (Qwen-Edit Rapid AIO, default) + Kontext + FLUX Fill (GGUF) + GGUF T5  (~44GB)
  dl Phr00t/Qwen-Image-Edit-Rapid-AIO  "v16/Qwen-Rapid-AIO-NSFW-v16.safetensors" \
     checkpoints 26.5 "Qwen-Image-Edit-Rapid-AIO.safetensors"   # fp8 all-in-one (latest NSFW)
  dl YarvixPA/FLUX.1-Fill-dev-GGUF  "flux1-fill-dev-Q5_K_S.gguf"  unet 7.72 "FLUX.1-Fill-dev-Q5_K_M.gguf"
  dl QuantStack/FLUX.1-Kontext-dev-GGUF  "flux1-kontext-dev-Q4_K_M.gguf"  unet 6.93
  dl city96/t5-v1_1-xxl-encoder-gguf  "t5-v1_1-xxl-encoder-Q5_K_M.gguf"  clip 3.15   # GGUF T5 for flux-fill/kontext
}

stage_ref() {    # Reference: xinsir ControlNet-Union ProMax (single file) + FLUX Redux + CLIP-Vision  (~4GB)
  dl xinsir/controlnet-union-sdxl-1.0  "diffusion_pytorch_model_promax.safetensors" \
     controlnet 2.5 "controlnet-union-sdxl-promax.safetensors"   # covers canny/depth/scribble/lineart/pose
  dl black-forest-labs/FLUX.1-Redux-dev  "flux1-redux-dev.safetensors"  style_models 0.66
  dl Comfy-Org/sigclip_vision_384  "sigclip_vision_patch14_384.safetensors"  clip_vision 0.86
}

stage_identity() {  # Consent-gated face identity: PuLID-FLUX + InstantID + IP-Adapter FaceID + CLIP-Vision  (~9GB)
  dl guozinan/PuLID  "pulid_flux_v0.9.1.safetensors"  pulid 1.1
  dl InstantX/InstantID  "ip-adapter.bin"  instantid 1.6
  dl InstantX/InstantID  "ControlNetModel/diffusion_pytorch_model.safetensors" \
     instantid 2.33 "instantid-diffusion_pytorch_model.safetensors"
  dl h94/IP-Adapter-FaceID  "ip-adapter-faceid-plusv2_sdxl.bin"  ipadapter 1.0
  dl h94/IP-Adapter  "models/image_encoder/model.safetensors" \
     clip_vision 2.35 "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"
}

stage_video() {  # NSFW video (Wan 2.2): TI2V-5B (default) + T2V/I2V-A14B + umt5/vae + lightx2v 4-step LoRAs  (~88GB)
  # Shared Wan encoder + VAE
  dl Comfy-Org/Wan_2.2_ComfyUI_Repackaged  "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" \
     clip 5 "umt5_xxl_fp8_e4m3fn.safetensors"
  dl Comfy-Org/Wan_2.2_ComfyUI_Repackaged  "split_files/vae/wan2.2_vae.safetensors"  vae 0.5
  # TI2V-5B (light, default video)
  dl Comfy-Org/Wan_2.2_ComfyUI_Repackaged  "split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors"  video 10
  # T2V-A14B (MoE: high+low noise UNETs)
  dl Comfy-Org/Wan_2.2_ComfyUI_Repackaged  "split_files/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors" video 14
  dl Comfy-Org/Wan_2.2_ComfyUI_Repackaged  "split_files/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors"  video 14
  # I2V-A14B (MoE: high+low noise UNETs)
  dl Comfy-Org/Wan_2.2_ComfyUI_Repackaged  "split_files/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors" video 14
  dl Comfy-Org/Wan_2.2_ComfyUI_Repackaged  "split_files/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"  video 14
  # lightx2v / Lightning 4-step distill LoRAs — A14B is a MoE, so a high- AND low-noise LoRA per task.
  dl Kijai/WanVideo_comfy  "LoRAs/Wan22_Lightx2v/Wan_2_2_I2V_A14B_HIGH_lightx2v_4step_lora_260412_rank_64_fp16.safetensors" \
     loras 0.63 "wan2.2_i2v_lightx2v_4step.safetensors"
  dl Kijai/WanVideo_comfy  "LoRAs/Wan22_Lightx2v/Wan_2_2_I2V_A14B_LOW_lightx2v_4step_lora_260412_rank_64_fp16.safetensors" \
     loras 0.63 "wan2.2_i2v_lightx2v_4step_low.safetensors"
  dl Kijai/WanVideo_comfy  "LoRAs/Wan22-Lightning/Wan22_A14B_T2V_HIGH_Lightning_4steps_lora_250928_rank128_fp16.safetensors" \
     loras 1.23 "wan2.2_t2v_lightx2v_4step.safetensors"
  dl Kijai/WanVideo_comfy  "LoRAs/Wan22-Lightning/Wan22_A14B_T2V_LOW_Lightning_4steps_lora_250928_rank64_fp16.safetensors" \
     loras 0.61 "wan2.2_t2v_lightx2v_4step_low.safetensors"
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
