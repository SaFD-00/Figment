# Models

The unified catalog lives in `backend/app/models_catalog/registry.py` (`MODELS` = image generation,
`LLM_MODELS` = chat/planner). Local weights live under `<repo>/AIStudio/models/<subdir>/`. **Only GGUF /
bf16 / safetensors — never fp8 (corrupts on Metal).**

**Provider note:** the cloud engine is unified on **OpenRouter** (`OPENROUTER_API_KEY`). The OpenAI
provider path was removed — the OpenAI SDK class is retained only as the base `OpenRouterClient`
subclasses. With no key the cloud path falls back to a mock provider. Cloud slugs marked
**(VERIFY)** are best-guess preview names — overridable via env / `cloud_model_id`.

## Local image models (ComfyUI)

The lineup is **uncensored, one or two models per function**. Generation is Qwen + Pony only;
the FLUX/Chroma families were dropped entirely.

| Registry id | Role | Repo (HF) | File → subdir | ~VRAM | Notes |
|---|---|---|---|---|---|
| `qwen-image` | **default txt2img/img2img** · uncensored | `unsloth/Qwen-Image-2512-GGUF` (VERIFY) | `*Q4_K_M.gguf → unet` + abliterated Qwen2.5-VL clip + Qwen VAE | 13GB | + 8-step Lightning + NSFW LoRA; `build_txt2img_qwen` |
| `pony-v6` | explicit-NSFW SDXL (txt2img/img2img/controlnet) | `AiAF/ponyDiffusionV6XL_v6StartWithThisOne.safetensors` | `…safetensors → checkpoints` | 7GB | single-file SDXL; `score_*` prefix |
| `lustify-inpaint` | **inpaint** · nsfw | `andro-flock/LUSTIFY-SDXL-NSFW-checkpoint-v2-0-INPAINTING` (VERIFY) | `lustifySDXLNSFW_v20-inpainting.safetensors → checkpoints` | 7GB | genuine 9-ch SDXL inpaint, fp16; `build_inpaint_sdxl` |
| `qwen-edit` | **edit + reference** · uncensored | `unsloth/Qwen-Image-Edit-2511-GGUF` + `lightx2v/…Lightning` | `*Q4_K_M.gguf → unet`; lightning → loras | 13GB | shares abliterated clip/VAE with `qwen-image`; + NSFW LoRA |

**Uncensored Qwen stack** (qwen-image/qwen-edit): the refusal bias lives in the text encoder, not the
DiT — so the base Qwen DiT is paired with the **abliterated Qwen2.5-VL** TE
(`mradermacher/Qwen2.5-VL-7B-Instruct-abliterated-GGUF` Q4_K_M + mmproj → `clip`) plus a **NSFW LoRA**
(`goonsai/qwen-image-loras` → `loras`), sharing `qwen_image_vae.safetensors` (→ `vae`). All GGUF/fp16.

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
`scripts/20_download_models.sh [qwen|sdxl|edit|ref|all]`. Repo ids marked **(VERIFY)** are
best-guess — confirm on huggingface.co before a fresh-machine run, then update `registry.py` filenames
to match. Cloud models need no download (API only).
