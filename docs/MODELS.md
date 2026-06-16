# Models

The unified catalog lives in `backend/app/models_catalog/registry.py` (`MODELS` = image generation,
`LLM_MODELS` = chat/planner). Local weights live under `<repo>/AIStudio/models/<subdir>/`. **Only GGUF /
bf16 / safetensors — never fp8 (corrupts on Metal).**

**Provider note:** the cloud engine is unified on **OpenRouter** (`OPENROUTER_API_KEY`). The OpenAI
provider path was removed — the OpenAI SDK class is retained only as the base `OpenRouterClient`
subclasses. With no key the cloud path falls back to a mock provider. Cloud slugs marked
**(VERIFY)** are best-guess preview names — overridable via env / `cloud_model_id`.

## Local image models (ComfyUI)

| Registry id | Role | Repo (HF) | File → subdir | ~VRAM | Notes |
|---|---|---|---|---|---|
| `qwen-image` | **default txt2img/img2img** | `unsloth/Qwen-Image-2512-GGUF` (VERIFY) | `*Q4_K_M.gguf → unet` + Qwen2.5-VL clip + Qwen VAE | 13GB | + optional 8-step Lightning LoRA; `build_txt2img_qwen` |
| `chroma-hd` | uncensored quality (txt2img) · nsfw | `silveroxides/Chroma1-HD-GGUF` | `Chroma1-HD-Q5_K_M.gguf → unet` | 8-10GB | needs T5+CLIP-L+VAE |
| `z-image` | fast/light (txt2img) · nsfw | `Comfy-Org/z_image_turbo` | UNET + Qwen-3-4B clip + VAE (split files) | 4-6GB | distill LoRA |
| `pony-v6` | explicit-NSFW SDXL (txt2img/img2img/controlnet) | `AiAF/ponyDiffusionV6XL_v6StartWithThisOne.safetensors` | `…safetensors → checkpoints` | 7GB | single-file SDXL; `score_*` prefix |
| `flux-fill` | inpaint | `YarvixPA/FLUX.1-Fill-dev-GGUF` | `*Q5_K_M.gguf → unet` | 8GB | + T5+CLIP-L+VAE |
| `sdxl-inpaint` | inpaint (fast fallback) | `diffusers/stable-diffusion-xl-1.0-inpainting-0.1` | `→ checkpoints` | 7GB | |
| `qwen-edit` | instruction edit | `unsloth/Qwen-Image-Edit-2511-GGUF` + `lightx2v/…Lightning` | `*Q4_K_M.gguf → unet`; lightning → loras | 13GB | shares Qwen clip/VAE with `qwen-image` |
| `kontext` | reference edit (multi-ref) | `city96/FLUX.1-Kontext-dev-gguf` (VERIFY) | `*Q4_K_M.gguf → unet` | 7GB | + T5+CLIP-L+VAE |
| `redux` | style reference (multi-ref) | `black-forest-labs/FLUX.1-Redux-dev` + `Comfy-Org/sigclip_vision_384` | `→ style_models`, `→ clip_vision` | rides FLUX | chained StyleModelApply |

Shared FLUX-family encoders/VAE (chroma/flux-fill/kontext/redux): `t5-v1_1-xxl-encoder-Q5_K_M.gguf`
(`city96/t5-v1_1-xxl-encoder-gguf` → `clip`), `clip_l.safetensors` (`comfyanonymous/flux_text_encoders` →
`clip`), FLUX `ae.safetensors` (→ `vae`). Qwen-family (qwen-image/qwen-edit): `qwen_2.5_vl_7b.safetensors`
(→ `clip`), `qwen_image_vae.safetensors` (→ `vae`).

ControlNet (SDXL, `controlnet/`): `xinsir/controlnet-canny-sdxl-1.0`, `…-depth-sdxl-1.0`. Upscaler: Real-ESRGAN x4 (`upscale_models/`).

## Cloud image models (OpenRouter)

| Registry id | Slug (`cloud_model_id`) | Modes |
|---|---|---|
| `gpt-image-2` | `openai/gpt-image-2` (VERIFY) | txt2img, img2img, edit, inpaint |
| `nano-banana-2` | `google/nano-banana-2` (VERIFY) | txt2img, img2img, edit, reference |
| `seedream-4.5` | `bytedance-seed/seedream-4.5` | txt2img, img2img, edit, reference |
| `flux2-max` | `black-forest-labs/flux.2-max` | txt2img, img2img, edit, reference |
| `flux2-pro` | `black-forest-labs/flux.2-pro` | txt2img, img2img, edit, reference |
| `flux2-flex` | `black-forest-labs/flux.2-flex` | txt2img, img2img, edit, reference |

## Chat / planner LLMs

**Local (Ollama):**
- `qwen-9b-local` — `hf.co/HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive:Q4_K_M` (~6.5GB, primary).
- `qwen-4b-local` — `…Qwen3.5-4B…:Q4_K_M` (~3.4GB, light fallback).

**Cloud (OpenRouter):** `gpt-oss-20b` (`openai/gpt-oss-20b:free`), `gpt-oss-120b` (`:free`),
`qwen3-plus` (`qwen/qwen3.7-plus`), `qwen3-flash` (`qwen/qwen3.6-flash`), `qwen3-35b-a3b`
(`qwen/qwen3.6-35b-a3b`). The FigGen pipeline's per-feature defaults (`FIGGEN_*_MODEL`) point at these;
`FIGGEN_VISION_MODEL` must be a VL-capable slug (the gpt-oss models are text-only).

## Download
`scripts/20_download_models.sh [base|qwen|sdxl|edit|ref|all]`. Repo ids marked **(VERIFY)** are
best-guess — confirm on huggingface.co before a fresh-machine run, then update `registry.py` filenames
to match. Cloud models need no download (API only).
