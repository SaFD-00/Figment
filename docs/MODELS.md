# Models

The unified catalog lives in `backend/app/models_catalog/registry.py` (`MODELS` = image generation,
`LLM_MODELS` = chat/planner). Local weights live under `<repo>/AIStudio/models/<subdir>/`. **Local target
is a single NVIDIA H100 80GB (CUDA)** — bf16/fp16/fp8 safetensors are all first-class (the old "never
fp8 — corrupts on Metal" rule is gone); GGUF is retained only for FLUX-Fill/Kontext. The whole photoreal
image stack (~70GB) is sized to **co-reside** at once; video swaps in.

**Provider note:** the cloud engine is unified on **OpenRouter** (`OPENROUTER_API_KEY`). The OpenAI
provider path was removed — the OpenAI SDK class is retained only as the base `OpenRouterClient`
subclasses. With no key the cloud path falls back to a mock provider. Cloud slugs marked
**(VERIFY)** are best-guess preview names — overridable via env / `cloud_model_id`.

## Local image models (ComfyUI)

| Registry id | Role | Repo (HF / civitai) | File → subdir | ~VRAM (H100 bf16/fp8) | Notes |
|---|---|---|---|---|---|
| `chroma-hd` | **default txt2img/img2img** · uncensored photoreal · nsfw | `lodestones/Chroma1-HD` | `Chroma1-HD-fp8.safetensors → unet` | 15GB | native fp8; single T5 (type=chroma) + CLIP-L + FLUX VAE; Apache-2.0; `txt2img_chroma` |
| `lustify` | fast explicit photoreal SDXL (txt2img/img2img/controlnet) · nsfw | `TheImposterImposters/LUSTIFY-v4.0` (civitai 573152) | `lustifySDXLNSFW_v40.safetensors → checkpoints` | 8GB | universal SDXL adapter base; `txt2img_sdxl_lora` |
| `flux-fill` | inpaint | `YarvixPA/FLUX.1-Fill-dev-GGUF` | `*Q5_K_M.gguf → unet` | 12GB | GGUF kept (non-default); + T5+CLIP-L+VAE; needs NSFW LoRA |
| `sdxl-inpaint` | inpaint · nsfw | `andro-flock/LUSTIFY-SDXL-NSFW-checkpoint-v2-0-INPAINTING` | `lustifySDXL_inpainting.safetensors → checkpoints` | 8GB | LUSTIFY SDXL Inpainting; `inpaint_sdxl` |
| `qwen-edit-aio` | **default edit** · NSFW instruction edit | `Phr00t/Qwen-Image-Edit-Rapid-AIO` | `Qwen-Image-Edit-Rapid-AIO.safetensors → checkpoints` | 29GB | fp8 all-in-one (CheckpointLoaderSimple); 4-step; `edit_qwen_aio` |
| `kontext` | reference edit (multi-ref) | `city96/FLUX.1-Kontext-dev-gguf` (VERIFY) | `*Q4_K_M.gguf → unet` | 12GB | GGUF kept; + T5+CLIP-L+VAE; needs NSFW Kontext LoRA |
| `redux` | **default reference** · style reference (multi-ref) | `black-forest-labs/FLUX.1-Redux-dev` + `Comfy-Org/sigclip_vision_384` | `flux1-redux-dev.safetensors → style_models`, `sigclip_vision_patch14_384.safetensors → clip_vision` | 15GB | rides the Chroma fp8 base (shares unet/clip/vae); chained StyleModelApply |

### Identity / face (consent-gated)
Synthetic faces or consenting adults only. All three ride an existing base (shared weights, low extra VRAM).

| Registry id | Role | Repo (HF) | File → subdir | ~VRAM (H100) | Notes |
|---|---|---|---|---|---|
| `instantid` | face identity over LUSTIFY SDXL | `InstantX/InstantID` | `ip-adapter.bin → instantid` (VERIFY), `instantid-diffusion_pytorch_model.safetensors → controlnet` | 12GB | over `lustify`; needs DWPose; `identity_instantid` |
| `ip-adapter` | identity/style over LUSTIFY SDXL | `h94/IP-Adapter-FaceID` | `ip-adapter-faceid-plusv2_sdxl.bin → ipadapter` (VERIFY), CLIP-ViT-H → clip_vision | 9GB | over `lustify`; `identity_ipadapter` |
| `pulid-flux` | face identity over Chroma/FLUX | `guozinan/PuLID` | `pulid_flux_v0.9.1.safetensors → pulid` (VERIFY) | 20GB | over `chroma-hd`; `identity_pulid` |

### Local video models (Wan 2.2)
New `Mode.video`. Default video = `wan22-ti2v`. Video swaps in (does **not** co-reside with the full image stack).
Shared: `umt5_xxl_fp8_e4m3fn.safetensors → clip`, `wan2.2_vae.safetensors → vae`.

| Registry id | Role | Repo (HF) | File → subdir | ~VRAM (H100) | Notes |
|---|---|---|---|---|---|
| `wan22-ti2v` | **default** · text+image→video (light) | `Wan-AI/Wan2.2-TI2V-5B` | `wan2.2_ti2v_5B_fp16.safetensors → unet` (VERIFY) | 16GB | `video_wan` |
| `wan22-t2v` | text→video (MoE quality) | `Wan-AI/Wan2.2-T2V-A14B` + `lightx2v/Wan2.2-Distill-Models` | high+low-noise `*_fp8_scaled.safetensors → unet`; `wan2.2_t2v_lightx2v_4step.safetensors → loras` | 34GB | dual UNET + 4-step distill LoRA |
| `wan22-i2v` | image→video (MoE quality) | `Wan-AI/Wan2.2-I2V-A14B` + `lightx2v/Wan2.2-Distill-Models` | high+low-noise `*_fp8_scaled.safetensors → unet`; `wan2.2_i2v_lightx2v_4step.safetensors → loras` | 34GB | dual UNET + 4-step distill LoRA |

Shared FLUX/Chroma encoders/VAE (native safetensors) for `chroma-hd`/`redux`/`pulid-flux`:
`t5xxl_fp8_e4m3fn.safetensors` (`comfyanonymous/flux_text_encoders` → `clip`, VERIFY; single T5,
type=chroma), `clip_l.safetensors` (→ `clip`), FLUX `ae.safetensors` (→ `vae`). The GGUF-kept
`flux-fill`/`kontext` use FLUX **GGUF** encoders: `t5-v1_1-xxl-encoder-Q5_K_M.gguf`
(`city96/t5-v1_1-xxl-encoder-gguf` → `clip`) + `clip_l.safetensors` + FLUX `ae.safetensors`.

ControlNet (SDXL, `controlnet/`): a SINGLE xinsir **ControlNet-Union ProMax** file
`controlnet-union-sdxl-promax.safetensors` (`xinsir/controlnet-union-sdxl-1.0`) covers
canny/depth/scribble/lineart/**pose**; pose preprocessor = **DWPose** (`comfyui_controlnet_aux`).
Upscaler: `RealESRGAN_x4plus.pth` (`upscale_models/`) + **Ultimate SD Upscale**
(`ssitu/ComfyUI_UltimateSDUpscale`, reuses your own NSFW base). bg-remove: rembg (CPU) / BEN2
(`PramaLLC/BEN2`) optional.

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
`scripts/20_download_models.sh [base|sdxl|edit|ref|identity|video|all]`. Repo ids/filenames marked
**(VERIFY)** are best-guess — confirm on huggingface.co before a fresh-machine run, then update
`registry.py` filenames to match. Custom nodes via `scripts/12_install_custom_nodes.sh`. Cloud models
need no download (API only).
