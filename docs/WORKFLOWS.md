# Workflows (ComfyUI graph builder)

Graphs are built **programmatically** in `backend/app/comfy/builder.py` (not static JSON +
placeholders) so LoRA chains, reference-image fan-out, and per-mode branching stay type-safe.
Node availability is validated at startup against ComfyUI `/object_info`
(`backend/app/comfy/templates.py`). **GGUF/bf16 only — never fp8 (corrupts on Metal).**

`GenSpec.mode` + the resolved model's `family`/`template` (see `registry.py`) pick the builder:

| Mode / template | Builder fn | Key nodes | Notes |
|---|---|---|---|
| txt2img (SDXL/Pony) | `build_txt2img_sdxl` | CheckpointLoaderSimple → CLIPTextEncode×2 → EmptyLatentImage → KSampler → VAEDecode | uses negative prompt; Pony gets `score_9,…` prefix |
| txt2img (Chroma) | `build_txt2img_flux` | UnetLoaderGGUF → **CLIPLoaderGGUF type=chroma** (single T5) → FluxGuidance → KSampler(cfg=1) | Chroma ≠ FLUX dual-CLIP |
| txt2img (FLUX-family) | `build_txt2img_flux` | UnetLoaderGGUF → DualCLIPLoaderGGUF type=flux → FluxGuidance | |
| txt2img (Z-Image) | `build_txt2img_zimage` | ⚠ currently CheckpointLoaderSimple — Z-Image ships as UNET + Qwen-3-4B text encoder + VAE (`Comfy-Org/z_image_turbo` split files); path needs UNETLoader+CLIPLoader(qwen)+VAELoader rewrite before use |
| img2img | `build_img2img` | LoadImage → VAEEncode → KSampler(denoise) | `denoise` = reference-fidelity dial |
| inpaint (FLUX Fill) | `build_inpaint_flux_fill` | LoadImage(src)+LoadImage(mask) → ImageToMask(red) → InpaintModelConditioning → KSampler | mask: white=regen, black=keep, dims=source |
| inpaint (SDXL) | `build_inpaint_sdxl` | VAEEncodeForInpaint(grow_mask_by) → KSampler | fast fallback |
| edit (Kontext) | `build_edit_kontext` | per ref: LoadImage→VAEEncode→ReferenceLatent (chained) → KSampler | single + multi reference |
| edit (Qwen-Edit) | `build_edit_qwen` | UnetLoaderGGUF → CLIPLoaderGGUF type=qwen_image → TextEncodeQwenImageEdit → LoraLoader(Lightning 4-step) | heavy (13GB) → LLM unloaded first |
| controlnet (SDXL) | `build_controlnet_sdxl` | preprocessor (Canny/Depth/Scribble/LineArt) → ControlNetLoader → ControlNetApplyAdvanced | **no openpose/DWPose/InstantID** (onnxruntime friction on arm64) |
| reference / style (Redux) | `build_redux_flux` | StyleModelLoader + CLIPVisionLoader → CLIPVisionEncode → **StyleModelApply** (strength, strength_type) | |
| upscale | `build_upscale` | UpscaleModelLoader → ImageUpscaleWithModel | standalone; toolbar one-shot via `/assets/{id}/upscale` |
| bg-remove / white-bg | — (not ComfyUI) | rembg/BiRefNet on CPU | keeps the Metal GPU free |

## Execution
`orchestrator/queue.py`: connect `/ws` (waits for the `__connected__` sentinel) → `queue_prompt`
→ map `/ws` progress to SSE → on done, read `/history` + fetch via `/view` → save to
`<repo>/AIStudio/outputs/{project}/` with a `.json` sidecar (the GenSpec).

## Memory rule (24GB)
`orchestrator/memory.py`: one big model at a time — free ComfyUI on family switch, unload the
LLM (`keep_alive:0`) when model+LLM exceed budget, downshift to a lighter equivalent if a single
model exceeds budget (chroma→z-image, qwen-edit→kontext, flux-fill→sdxl-inpaint).
