# Models

The unified catalog lives in `backend/app/models_catalog/registry.py` (`MODELS` = image generation,
`LLM_MODELS` = chat/planner). Local weights live under `<repo>/AIStudio/models/<subdir>/`. **Only
safetensors / bf16 / fp16 — never fp8 (corrupts on Metal).**

**Provider note:** the cloud engine is unified on **OpenRouter** (`OPENROUTER_API_KEY`). The OpenAI
provider path was removed — the OpenAI SDK class is retained only as the base `OpenRouterClient`
subclasses. With no key the cloud path falls back to a mock provider. Cloud slugs marked
**(VERIFY)** are best-guess preview names — overridable via env / `cloud_model_id`.

## Local image models (ComfyUI)

The local lineup is **a single uncensored SDXL checkpoint** that serves every mode. There is no Qwen
GGUF stack and no dedicated inpaint checkpoint — one big model keeps the 24GB budget simple.

| Registry id | Role | Repo (HF) | File → subdir | ~VRAM | Notes |
|---|---|---|---|---|---|
| `juggernaut-xl` | **all modes** · NSFW photoreal SDXL | `RunDiffusion/Juggernaut-XL-v9` (VERIFY) | `…safetensors → checkpoints` | 7GB | txt2img/img2img/edit via `build_txt2img_sdxl`/`build_img2img`; inpaint via `build_inpaint_sdxl` (+`SetLatentNoiseMask`, standard 4-ch checkpoint); reference via `build_reference_ipadapter` (IP-Adapter Plus); controlnet via `build_controlnet_sdxl`. Optional NSFW LoRA (strength ~0.8) in `builtin_loras` |

**Per-mode routing on one checkpoint** (`comfy/builder.py:build()`):
- **txt2img / img2img** → SDXL KSampler (img2img via `VAEEncode`, `denoise` = fidelity dial).
- **inpaint** → `VAEEncodeForInpaint` + **`SetLatentNoiseMask`** (Juggernaut is a standard 4-ch checkpoint,
  not a 9-ch inpaint UNet, so the mask must be re-asserted on the latent), denoise ≥ 0.9.
- **edit** → mask present ⇒ inpaint with the edit instruction as prompt; no mask ⇒ high-denoise img2img.
  The LLM/GENSPEC planner decides whether a mask exists — the builder does not generate masks.
- **reference** → **IP-Adapter Plus**, single reference image: `IPAdapterModelLoader` + `CLIPVisionLoader`
  → `IPAdapterAdvanced` patches the MODEL (weight 0.6–0.8), then a normal txt2img KSampler.
- **controlnet** → SDXL ControlNet adapter on the same checkpoint (first reference only).

**Reference / structure weights:** IP-Adapter Plus (`h94/IP-Adapter` → `ipadapter/`) + CLIP-ViT-H
(`→ clip_vision/`), both in `IPADAPTER_FILES`. ControlNet (SDXL, `controlnet/`):
`xinsir/controlnet-canny-sdxl-1.0`, `…-depth-sdxl-1.0`. Upscaler: Real-ESRGAN x4 (`upscale_models/`).

## Cloud image models (OpenRouter)

| Registry id | Slug (`cloud_model_id`) | Modes |
|---|---|---|
| `gpt-image-2` | `openai/gpt-5.4-image-2` (VERIFY) | txt2img, img2img, edit, inpaint, reference |
| `gpt-image-1` | `openai/gpt-5-image` (VERIFY) | txt2img, img2img, edit, inpaint, reference |
| `gemini-flash-image` | `google/gemini-3.1-flash-image` (VERIFY) | txt2img, img2img, edit, reference |
| `gemini-pro-image` | `google/gemini-3-pro-image` (VERIFY) | txt2img, img2img, edit, reference |

## Chat / planner LLMs (all multimodal VLMs)

**Local (Ollama):**
- `qwen3-vl-local` — `huihui_ai/qwen3-vl-abliterated:8b` (~5GB, VERIFY tag) — the single local
  chat/planner VLM, an uncensored **multimodal** (`vision=True`) Qwen3-VL so local Prompt Enhance can
  read images too. Mirrors `config.ollama_llm` / `.env` `OLLAMA_LLM`.

**Cloud (OpenRouter):** all **multimodal** (`vision=True`):
- `gemini-2.5-flash` (`google/gemini-2.5-flash`)
- `gpt-5.4-mini` (`openai/gpt-5.4-mini`, VERIFY)
- `qwen3-6-flash` (`qwen/qwen3-6-flash`, VERIFY)

Prompt Enhance attaches an uploaded edit/reference image whenever the **picked** model is vision-capable,
regardless of provider (`routers/prompt.py:_enhance_image_url` gates on `ModelDef.vision` alone). The cloud
route forwards OpenAI-style multimodal parts as-is; the local route is served by `OllamaClient`, which
converts those parts into Ollama's native per-message `images` array (`llm/ollama_client.py:_to_ollama_messages`).
A non-vision/unknown pick degrades to text-only enhance.
The FigGen pipeline keeps its own per-feature defaults (`FIGGEN_*_MODEL`) independent of this catalog.

## Download
`scripts/20_download_models.sh [sdxl|ref|all]` (`sdxl` = Juggernaut XL + VAE; `ref` = IP-Adapter Plus
+ CLIP-ViT-H + ControlNet + Real-ESRGAN). Repo ids marked **(VERIFY)** are
best-guess — confirm on huggingface.co before a fresh-machine run, then update `registry.py` filenames
to match. Cloud models need no download (API only).

## Readiness & verify
`engines/model_ready(m)` reports whether a catalog entry can run **right now**: a local-comfy model is
ready when its primary weight file exists under `AIStudio/models/`, a cloud model when its provider key
is set, and the local-ollama LLM is assumed installed (verified at job time). `scripts/figment models`
and `scripts/figment doctor` surface this per model.

`scripts/figment verify` goes further — it **actually runs** each entry's real pipeline (local generation,
cloud figure pipeline, chat/enhance, post-ops) and asserts a plausible result. An unready entry is a clean
**SKIP** with the exact missing weight file / service / key, so the matrix is honest on a partially-provisioned
machine (a keyless cloud model SKIPs rather than passing on the mock provider). See WORKFLOWS.md → *Verify matrix*.
