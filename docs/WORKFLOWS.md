# Workflows (ComfyUI graph builder)

Graphs are built **programmatically** in `backend/app/comfy/builder.py` (not static JSON +
placeholders) so LoRA chains, reference-image fan-out, and per-mode branching stay type-safe.
Node availability is validated at startup against ComfyUI `/object_info`
(`backend/app/comfy/templates.py`). **Local target: single H100 80GB (CUDA)** — fp8/bf16 safetensors
are first-class; GGUF retained only for `flux-fill`.

`GenSpec.mode` + the resolved model's `family`/`template` (see `registry.py`) pick the builder:

| Mode / template | Builder fn | Key nodes | Notes |
|---|---|---|---|
| txt2img (SDXL) `txt2img_sdxl_lora` | `build_txt2img_sdxl` | CheckpointLoaderSimple → CLIPTextEncode×2 → EmptyLatentImage → KSampler → VAEDecode | LUSTIFY base; uses negative prompt; LoRA chain; universal adapter base |
| txt2img (Chroma) `txt2img_chroma` | `build_txt2img_flux` | **UNETLoader** (native fp8) → **CLIPLoader type=chroma** (single T5) → FluxGuidance → KSampler(cfg=1) | native loaders (not GGUF); Chroma ≠ FLUX dual-CLIP; **default** |
| txt2img (FLUX-family GGUF) | `build_txt2img_flux` | UnetLoaderGGUF → DualCLIPLoaderGGUF type=flux → FluxGuidance | GGUF path (`flux-fill` only) |
| img2img | `build_img2img` | LoadImage → VAEEncode → KSampler(denoise) | `denoise` = reference-fidelity dial; chroma→flux path, lustify→SDXL path |
| inpaint (FLUX Fill) `inpaint_flux_fill` | `build_inpaint_flux_fill` | LoadImage(src)+LoadImage(mask) → ImageToMask(red) → InpaintModelConditioning → KSampler | GGUF; mask: white=regen, black=keep, dims=source; **default inpaint** |
| edit (Qwen-Edit AIO) `edit_qwen_aio` | `build_edit_qwen_aio` | **CheckpointLoaderSimple** (fp8 AIO) → **TextEncodeQwenImageEdit** → KSampler(4-step) | all-in-one; **default edit**; also subject/face via a reference image |
| controlnet (SDXL) `controlnet` | `build_controlnet_sdxl` | preprocessor (Canny/Depth/Scribble/LineArt/**DWPose**) → ControlNetLoader (**union ProMax single file**) → ControlNetApplyAdvanced | one union file covers all types incl. pose; DWPose via `comfyui_controlnet_aux`; LUSTIFY base |
| reference / style (Redux) `redux_flux` | `build_redux_flux` | StyleModelLoader + CLIPVisionLoader → per ref: CLIPVisionEncode → **StyleModelApply** (chained) | rides Chroma fp8 base; blends multiple style refs; **default reference** |
| video (Wan 2.2 TI2V-5B) `video_wan` | `build_video_wan` | CLIPLoader(wan) + UNETLoader + wan2.2 VAE → **Wan22ImageToVideoLatent** (optional start_image) → KSampler → SaveAnimatedWEBP | native core nodes; one graph covers t2v + i2v; default & only video model |
| upscale | `build_upscale` | UpscaleModelLoader (RealESRGAN_x4plus) → ImageUpscaleWithModel / Ultimate SD Upscale | standalone; toolbar one-shot via `/assets/{id}/upscale` |
| bg-remove / white-bg | — (not ComfyUI) | rembg/BEN2 on CPU | keeps the GPU free |

## Reference images
`GenSpec.reference_images` accepts up to `MAX_REFERENCE_IMAGES` (= 6; `backend/app/schemas/genspec.py`,
mirrored in `frontend/lib/constants.ts`). The local engine (`engines/local_comfy.py`) uploads each to
ComfyUI and fills `ctx.comfy_refs`. **Multi-ref**: Redux (chained `StyleModelApply`) consumes all refs.
**First-ref-only**: `qwen-edit-aio` and `controlnet` are single-input — they use the first reference and
ignore the rest. Cloud **figure** passes all refs to FigGen; cloud **raster** (`engines/cloud_image.py`)
uses the first reference only (the OpenRouter modalities path is single-image).

## Execution
`orchestrator/queue.py`: connect `/ws` (waits for the `__connected__` sentinel) → `queue_prompt`
→ map `/ws` progress to SSE → on done, read `/history` + fetch via `/view` → save to
`<repo>/AIStudio/outputs/{project}/` with a `.json` sidecar (the GenSpec).

## Memory (H100 80GB · co-resident)
`orchestrator/memory.py`: the full photoreal image stack (~70GB) **co-resides** — no
one-big-model serialisation. The orchestrator only frees ComfyUI / unloads the LLM
(`keep_alive:0`) under the rarely-hit budget pressure (budget 78GB); `LIGHTER_EQUIVALENT` is
now empty. Wan 2.2 video swaps in (does not co-reside with the full image stack).
