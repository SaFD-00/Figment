#!/usr/bin/env bash
# Download GGUF/safetensors model weights into <repo>/AIStudio/models, in milestone order,
# each step guarded by the disk budget. Run a stage:  ./20_download_models.sh [qwen|sdxl|edit|ref|all]
#
# Repo IDs + exact file paths below were verified against the HF API on 2026-06-16. `dl` takes an
# EXACT repo file path (not a glob) and renames/flattens it to the name registry.py expects.
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

stage_qwen() {   # Qwen-Image 2512 (txt2img/img2img) — uncensored stack: DiT GGUF + abliterated
                 # Qwen2.5-VL text encoder (+mmproj) + Qwen VAE + Lightning + NSFW LoRA  (~21GB)
  dl unsloth/Qwen-Image-2512-GGUF  "qwen-image-2512-Q4_K_M.gguf"  unet  Qwen-Image-2512-Q4_K_M.gguf  13
  # Abliterated Qwen2.5-VL text encoder lifts the refusal bias; mmproj is its vision projector.
  # Renamed (repo uses a dot before the quant; registry files["clip"] uses a dash).
  dl mradermacher/Qwen2.5-VL-7B-Instruct-abliterated-GGUF \
     "Qwen2.5-VL-7B-Instruct-abliterated.Q4_K_M.gguf"  clip  Qwen2.5-VL-7B-Instruct-abliterated-Q4_K_M.gguf  5
  dl mradermacher/Qwen2.5-VL-7B-Instruct-abliterated-GGUF \
     "Qwen2.5-VL-7B-Instruct-abliterated.mmproj-Q8_0.gguf"  clip  Qwen2.5-VL-7B-Instruct-abliterated.mmproj-Q8_0.gguf  1
  # Qwen VAE — shared with qwen-edit (flattened out of split_files/vae/).
  dl Comfy-Org/Qwen-Image_ComfyUI  "split_files/vae/qwen_image_vae.safetensors"  vae  qwen_image_vae.safetensors  1
  # 8-step distill LoRA (renamed to the registry's builtin_loras name).
  dl lightx2v/Qwen-Image-Lightning "Qwen-Image-Lightning-8steps-V2.0.safetensors"  loras  Qwen-Image-Lightning-8steps.safetensors  1
  dl goonsai/qwen-image-loras      "qwen_MCNL_v1.0.safetensors"  loras  qwen_MCNL_v1.0.safetensors  1   # NSFW LoRA
}

stage_sdxl() {   # Pony V6 (explicit NSFW) + LUSTIFY SDXL NSFW inpaint (genuine 9-ch UNet, fp16)  (~14GB)
  dl AiAF/ponyDiffusionV6XL_v6StartWithThisOne.safetensors \
     "ponyDiffusionV6XL_v6StartWithThisOne.safetensors"  checkpoints  ponyDiffusionV6XL_v6StartWithThisOne.safetensors  7
  dl andro-flock/LUSTIFY-SDXL-NSFW-checkpoint-v2-0-INPAINTING \
     "lustifySDXLNSFW_v20-inpainting.safetensors"  checkpoints  lustifySDXLNSFW_v20-inpainting.safetensors  7
  dl madebyollin/sdxl-vae-fp16-fix  "sdxl_vae.safetensors"  vae  sdxl_vae.safetensors  1
}

stage_edit() {   # Instruction + reference edit: Qwen-Image-Edit 2511 + shared TE/VAE + Lightning + NSFW LoRA
                 # Self-contained (~21GB) — running `edit` alone yields a fully working qwen-edit model.
  dl unsloth/Qwen-Image-Edit-2511-GGUF \
     "qwen-image-edit-2511-Q4_K_M.gguf"  unet  Qwen-Image-Edit-2511-Q4_K_M.gguf  13
  # Abliterated Qwen2.5-VL text encoder (+mmproj vision projector) + Qwen VAE. Also pulled by
  # stage_qwen; duplicated here so `edit` is standalone (dl is idempotent — skips if present).
  dl mradermacher/Qwen2.5-VL-7B-Instruct-abliterated-GGUF \
     "Qwen2.5-VL-7B-Instruct-abliterated.Q4_K_M.gguf"  clip  Qwen2.5-VL-7B-Instruct-abliterated-Q4_K_M.gguf  5
  dl mradermacher/Qwen2.5-VL-7B-Instruct-abliterated-GGUF \
     "Qwen2.5-VL-7B-Instruct-abliterated.mmproj-Q8_0.gguf"  clip  Qwen2.5-VL-7B-Instruct-abliterated.mmproj-Q8_0.gguf  1
  dl Comfy-Org/Qwen-Image_ComfyUI  "split_files/vae/qwen_image_vae.safetensors"  vae  qwen_image_vae.safetensors  1
  # 4-step Lightning (matches qwen-edit default steps=4); bf16 — fp8 corrupts on Metal.
  dl lightx2v/Qwen-Image-Edit-2511-Lightning \
     "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors"  loras  Qwen-Image-Edit-2511-Lightning.safetensors  1
  dl goonsai/qwen-image-loras  "qwen_MCNL_v1.0.safetensors"  loras  qwen_MCNL_v1.0.safetensors  1   # NSFW LoRA
}

stage_ref() {    # Structure control (SDXL ControlNet canny+depth) + Real-ESRGAN upscaler  (~5GB)
  # Both repos ship the file as diffusion_pytorch_model.safetensors — rename per-type to avoid a
  # collision in controlnet/ and to match registry CONTROLNET_FILES.
  # diskguard does integer arithmetic — keep these whole GB (rounded up).
  dl xinsir/controlnet-canny-sdxl-1.0 \
     "diffusion_pytorch_model.safetensors"  controlnet  controlnet-canny-sdxl-1.0.safetensors  3
  dl xinsir/controlnet-depth-sdxl-1.0 \
     "diffusion_pytorch_model.safetensors"  controlnet  controlnet-depth-sdxl-1.0.safetensors  3
  dl ai-forever/Real-ESRGAN  "RealESRGAN_x4.pth"  upscale_models  RealESRGAN_x4.pth  1
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
