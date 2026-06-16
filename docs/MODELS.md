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
the **local** FLUX/Chroma families were dropped entirely (cloud FLUX.2 remains — see below).

| Registry id | Role | Repo (HF) | File → subdir | ~VRAM | Notes |
|---|---|---|---|---|---|
| `qwen-image` | **default txt2img/img2img** · uncensored | `unsloth/Qwen-Image-2512-GGUF` (VERIFY) | `*Q4_K_M.gguf → unet` + abliterated Qwen2.5-VL clip + Qwen VAE | 13GB | + 8-step Lightning + NSFW LoRA; `build_txt2img_qwen` |
| `pony-v6` | explicit-NSFW SDXL (txt2img/img2img/controlnet) | `AiAF/ponyDiffusionV6XL_v6StartWithThisOne.safetensors` | `…safetensors → checkpoints` | 7GB | single-file SDXL; `score_*` prefix |
| `lustify-inpaint` | **inpaint** · nsfw | `andro-flock/LUSTIFY-SDXL-NSFW-checkpoint-v2-0-INPAINTING` (VERIFY) | `lustifySDXLNSFW_v20-inpainting.safetensors → checkpoints` | 7GB | genuine 9-ch SDXL inpaint, fp16; `build_inpaint_sdxl` |
| `qwen-edit` | **edit + reference** · uncensored | `unsloth/Qwen-Image-Edit-2511-GGUF` + `lightx2v/…Lightning` | `*Q4_K_M.gguf → unet`; lightning → loras | 13GB | shares abliterated clip/VAE with `qwen-image`; + NSFW LoRA; **multi-ref up to 3** (`TextEncodeQwenImageEditPlus`, positional Picture 1/2/3) |

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
- `qwen3-vl-local` — `huihui_ai/qwen3-vl-abliterated:8b` (~6.1GB) — the single local chat/planner LLM,
  an uncensored **multimodal** (`vision=True`) Qwen3-VL so local Prompt Enhance can read images too.

**Cloud (OpenRouter):** `gemma-4-31b` (`google/gemma-4-31b-it:free`) — a single free **multimodal**
(`vision=True`) model.

Prompt Enhance attaches an uploaded edit/reference image whenever the **picked** model is vision-capable,
regardless of provider (`routers/prompt.py:_enhance_image_url` gates on `ModelDef.vision` alone). The cloud
route forwards OpenAI-style multimodal parts as-is; the local route is served by `OllamaClient`, which
converts those parts into Ollama's native per-message `images` array (`llm/ollama_client.py:_to_ollama_messages`).
A non-vision/unknown pick degrades to text-only enhance.
The FigGen pipeline keeps its own per-feature defaults (`FIGGEN_*_MODEL`) independent of this catalog.

## Download
`scripts/20_download_models.sh [qwen|sdxl|edit|ref|all]`. Repo ids marked **(VERIFY)** are
best-guess — confirm on huggingface.co before a fresh-machine run, then update `registry.py` filenames
to match. Cloud models need no download (API only).
