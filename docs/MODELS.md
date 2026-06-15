# Models

All filenames are configured in `backend/app/models_catalog/registry.py`. Weights live under
`<repo>/AIStudio/models/<subdir>/` (the project-local runtime home). **Only GGUF / bf16 /
safetensors — never fp8 (corrupts on Metal).**

| Registry id | Role | Repo (HF) | File → subdir | ~VRAM | Verified |
|---|---|---|---|---|---|
| `pony-v6` | explicit-NSFW SDXL (txt2img/img2img/controlnet) | `AiAF/ponyDiffusionV6XL_v6StartWithThisOne.safetensors` | `…safetensors → checkpoints` | 7GB | ✅ single-file, standard SDXL path |
| `chroma-hd` | uncensored quality (txt2img) | `silveroxides/Chroma1-HD-GGUF` | `Chroma1-HD-Q5_K_M.gguf → unet` | 8-10GB | needs T5+CLIP-L+VAE |
| `z-image` | fast/light (txt2img) | `Comfy-Org/z_image_turbo` | `split_files/diffusion_models/z_image_turbo_bf16.safetensors → unet`; `qwen_3_4b.safetensors → clip`; `ae.safetensors → vae`; distill LoRA → loras | 4-6GB | ⚠ UNET+CLIP+VAE (not a single checkpoint) — builder path needs Z-Image-specific loaders |
| `flux-fill` | inpaint | `YarvixPA/FLUX.1-Fill-dev-GGUF` | `*Q5_K_M.gguf → unet` | 8GB | + T5+CLIP-L+VAE |
| `qwen-edit` | instruction edit | `unsloth/Qwen-Image-Edit-2511-GGUF` + `lightx2v/...Lightning` | `*Q4_K_M.gguf → unet`; lightning → loras | 13GB | heavy → LLM unloaded first |
| `kontext` | reference edit | `city96/FLUX.1-Kontext-dev-gguf` (verify) | `*Q4_K_M.gguf → unet` | 7GB | + T5+CLIP-L+VAE |
| `redux` | style reference | `black-forest-labs/FLUX.1-Redux-dev` + `Comfy-Org/sigclip_vision_384` | `→ style_models`, `→ clip_vision` | rides FLUX | uses StyleModelApply |

Shared FLUX-family encoders/VAE (for chroma/flux-fill/kontext/redux): `t5-v1_1-xxl-encoder-Q5_K_M.gguf`
(`city96/t5-v1_1-xxl-encoder-gguf` → `clip`), `clip_l.safetensors` (`comfyanonymous/flux_text_encoders` → `clip`), FLUX `ae.safetensors` (→ `vae`).

ControlNet (SDXL, `controlnet/`): `xinsir/controlnet-canny-sdxl-1.0`, `…-depth-sdxl-1.0`. Upscaler: Real-ESRGAN x4 (`upscale_models/`).

## Chat LLM (Ollama)
- Primary `hf.co/HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive:Q4_K_M` (~6.5GB) — installed.
- Fallback `…Qwen3.5-4B…:Q4_K_M` (~3.4GB) — installed.

## Download
`scripts/20_download_models.sh [base|sdxl|edit|ref|all]`. Repo ids marked **(VERIFY)** in the script
were confirmed during the first build for: Z-Image layout (diffusers/split), Chroma GGUF
(`silveroxides/Chroma1-HD-GGUF`, has Q4_K_M…Q5_K_M; pick by RAM), single-file Pony
(`AiAF/...safetensors`). Update `registry.py` filenames to match what you download.
