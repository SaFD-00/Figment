# Models

The unified catalog lives in `backend/app/models_catalog/registry.py` (`MODELS` = image generation,
`LLM_MODELS` = chat/planner). Local weights live under `<repo>/AIStudio/models/<subdir>/`. **Local target
is a single NVIDIA H100 80GB (CUDA)** — bf16/fp16/fp8 safetensors are all first-class (the old "never
fp8 — corrupts on Metal" rule is gone); GGUF is retained only for FLUX-Fill. The whole photoreal
image stack (~70GB) is sized to **co-reside** at once; video swaps in.

The catalog is **consolidated to one model per feature** (or one model covering several), chosen for
performance + native NSFW. All required weights are already on disk — **no new downloads are needed**.

**Provider note:** the cloud engine is unified on **OpenRouter** (`OPENROUTER_API_KEY`). Cloud models
now produce **raster images** (interchangeable with local) for the normal modes and **editable
SVG/PPTX figures** for `Mode.figure`. With no key the cloud path raises a clear error (raster) or
falls back to a mock provider (figure). Cloud slugs marked **(VERIFY)** are best-guess preview names.

## Local image models (ComfyUI)

| Registry id | Role | Repo (HF / civitai) | File → subdir | ~VRAM (H100 bf16/fp8) | Notes |
|---|---|---|---|---|---|
| `chroma-hd` | **default txt2img/img2img** · uncensored photoreal · nsfw | `lodestones/Chroma1-HD` | `Chroma1-HD-fp8.safetensors → unet` | 15GB | native fp8; single T5 (type=chroma) + CLIP-L + FLUX VAE; Apache-2.0; `txt2img_chroma` |
| `lustify` | fast explicit photoreal SDXL (txt2img/img2img/**controlnet** base) · nsfw | `TheImposterImposters/LUSTIFY-v4.0` (civitai 573152) | `lustifySDXLNSFW_v40.safetensors → checkpoints` | 8GB | universal SDXL base; `txt2img_sdxl_lora` |
| `flux-fill` | **default inpaint** · nsfw | `YarvixPA/FLUX.1-Fill-dev-GGUF` | `*Q5_K_M.gguf → unet` | 12GB | GGUF; + T5+CLIP-L+VAE; prompt-faithful; `inpaint_flux_fill` |
| `qwen-edit-aio` | **default edit** (incl. subject/face via a reference image) · NSFW | `Phr00t/Qwen-Image-Edit-Rapid-AIO` | `Qwen-Image-Edit-Rapid-AIO.safetensors → checkpoints` | 29GB | fp8 all-in-one (CheckpointLoaderSimple); 4-step; `edit_qwen_aio` |
| `redux` | **default reference** · style reference (multi-ref) · nsfw | `black-forest-labs/FLUX.1-Redux-dev` + `Comfy-Org/sigclip_vision_384` | `flux1-redux-dev.safetensors → style_models`, `sigclip_vision_patch14_384.safetensors → clip_vision` | 15GB | rides the Chroma fp8 base (shares unet/clip/vae); chained StyleModelApply |

**Face / subject identity** has no dedicated model. It is done through `edit` (qwen-edit-aio) with a
reference image, or `reference` (redux) for style — **consent-gated** (consenting adults / synthetic
faces only). The old `instantid` / `ip-adapter` / `pulid-flux` entries were removed; `pulid-flux` was
also structurally broken (it loaded the Chroma unet, which `ApplyPulidFlux` rejects — FLUX-only).

### Local video model (Wan 2.2)
`Mode.video`, default `wan22-ti2v`. Video swaps in (does **not** co-reside with the full image stack).

| Registry id | Role | Repo (HF) | File → subdir | ~VRAM (H100) | Notes |
|---|---|---|---|---|---|
| `wan22-ti2v` | text+image→video (5B, dense) | `Wan-AI/Wan2.2-TI2V-5B` | `wan2.2_ti2v_5B_fp16.safetensors → unet` (VERIFY), `umt5_xxl_fp8_e4m3fn.safetensors → clip`, `wan2.2_vae.safetensors → vae` | 16GB | `video_wan`; one graph covers t2v **and** i2v via `Wan22ImageToVideoLatent`'s optional `start_image` |

The Wan 2.2 A14B MoE models (`wan22-t2v` / `wan22-i2v`) were consolidated out — the 5B TI2V covers
both directions.

Shared FLUX/Chroma encoders/VAE (native safetensors) for `chroma-hd`/`redux`:
`t5xxl_fp8_e4m3fn.safetensors` (`comfyanonymous/flux_text_encoders` → `clip`, VERIFY; single T5,
type=chroma), `clip_l.safetensors` (→ `clip`), FLUX `ae.safetensors` (→ `vae`). The GGUF-based
`flux-fill` uses FLUX **GGUF** encoders: `t5-v1_1-xxl-encoder-Q5_K_M.gguf`
(`city96/t5-v1_1-xxl-encoder-gguf` → `clip`) + `clip_l.safetensors` + FLUX `ae.safetensors`.

ControlNet (SDXL, `controlnet/`): a SINGLE xinsir **ControlNet-Union ProMax** file
`controlnet-union-sdxl-promax.safetensors` (`xinsir/controlnet-union-sdxl-1.0`) covers
canny/depth/scribble/lineart/**pose**; pose preprocessor = **DWPose** (`comfyui_controlnet_aux`).
Upscaler: `RealESRGAN_x4plus.pth` (`upscale_models/`) + **Ultimate SD Upscale**
(`ssitu/ComfyUI_UltimateSDUpscale`, reuses your own NSFW base). bg-remove: rembg (CPU).

## Cloud image models (OpenRouter)

Each does raster images (CloudImageEngine) for the normal modes **and** structured figures
(FigureEngine) for `Mode.figure`.

| Registry id | Slug (`cloud_model_id`) | Modes |
|---|---|---|
| `gpt-image-2` | `openai/gpt-image-2` (VERIFY) | txt2img, img2img, edit, inpaint, reference, figure |
| `nano-banana-2` | `google/nano-banana-2` (VERIFY) | txt2img, img2img, edit, inpaint, reference, figure |

## Chat / planner LLMs

The chat/planner LLM lineup is **vision-capable only** (every entry is multimodal, `vision=True`), so
prompt-enhance can always ground the rewrite in an uploaded edit/reference image.

**Local (Ollama):**
- `qwen3-vl-local` — `huihui_ai/qwen3-vl-abliterated:8b` (~5GB, uncensored multimodal; the local default).

**Cloud (OpenRouter):** `gemini-2.5-flash` (`google/gemini-2.5-flash`), `gpt-5.4-mini`
(`openai/gpt-5.4-mini`), `qwen3-6-flash` (`qwen/qwen3-6-flash`). The FigGen pipeline's per-feature
defaults (`FIGGEN_*_MODEL`) point at a multimodal slug; `FIGGEN_VISION_MODEL` must be VL-capable
(all of these are).

## Download
All weights for the consolidated catalog are already present — no new downloads required.
`scripts/20_download_models.sh [base|sdxl|edit|ref|video|all]` remains for a fresh machine (the
`identity` stage still exists but its weights are no longer wired into the catalog). Repo ids/filenames
marked **(VERIFY)** are best-guess — confirm on huggingface.co before a fresh-machine run. Custom nodes
via `scripts/12_install_custom_nodes.sh`. Cloud models need no download (API only).
