# Workflows (ComfyUI graph builder)

Graphs are built **programmatically** in `backend/app/comfy/builder.py` (not static JSON +
placeholders) so LoRA chains, reference-image fan-out, and per-mode branching stay type-safe.
Node availability is validated at startup against ComfyUI `/object_info`
(`backend/app/comfy/templates.py`). **GGUF/bf16 only — never fp8 (corrupts on Metal).**

`GenSpec.mode` + the resolved model's `family`/`template` (see `registry.py`) pick the builder:

| Mode / template | Builder fn | Key nodes | Notes |
|---|---|---|---|
| txt2img (SDXL/Pony) | `build_txt2img_sdxl` | CheckpointLoaderSimple → CLIPTextEncode×2 → EmptyLatentImage → KSampler → VAEDecode | uses negative prompt; Pony gets `score_9,…` prefix |
| txt2img (Qwen-Image) | `build_txt2img_qwen` | UnetLoaderGGUF → **CLIPLoaderGGUF type=qwen_image** (abliterated TE) → VAELoader → EmptySD3LatentImage → KSampler | default txt2img/img2img + 8-step Lightning + NSFW LoRA; `_qwen_base` shared with img2img |
| img2img | `build_img2img` | LoadImage → VAEEncode → KSampler(denoise) | qwen-image → `_qwen_base`, else SDXL → `_sdxl_base`; `denoise` = fidelity dial |
| inpaint (SDXL) | `build_inpaint_sdxl` | LoadImage(src)+LoadImage(mask) → ImageToMask(red) → VAEEncodeForInpaint(grow_mask_by) → KSampler | LUSTIFY genuine 9-ch inpaint; mask: white=regen, black=keep, dims=source |
| edit (Qwen-Edit) | `build_edit_qwen` | UnetLoaderGGUF → CLIPLoaderGGUF type=qwen_image → TextEncodeQwenImageEdit → LoraLoader(Lightning 4-step) | heavy (13GB) → LLM unloaded first |
| reference (Qwen-Edit) | `build_edit_qwen` (via `build()` mode routing) | same graph as edit — uses the first reference image | style/identity reference; multi-ref is a follow-up |
| controlnet (SDXL) | `build_controlnet_sdxl` | preprocessor (Canny/Depth/Scribble/LineArt) → ControlNetLoader → ControlNetApplyAdvanced | **no openpose/DWPose/InstantID** (onnxruntime friction on arm64) |
| upscale | `build_upscale` | UpscaleModelLoader → ImageUpscaleWithModel | standalone; toolbar one-shot via `/assets/{id}/upscale` |
| bg-remove / white-bg | — (not ComfyUI) | rembg/BiRefNet on CPU | keeps the Metal GPU free |

## Reference images
`GenSpec.reference_images` accepts up to `MAX_REFERENCE_IMAGES` (= 6; `backend/app/schemas/genspec.py`,
mirrored in `frontend/lib/constants.ts`). `orchestrator/queue.py` uploads each to ComfyUI and fills
`ctx.comfy_refs`. **First-ref-only (local)**: `qwen-edit` (edit + reference) and `controlnet` are
single-input — they use the first reference and ignore the rest. Multi-reference for `qwen-edit`
(up to 4 via `TextEncodeQwenImageEditPlus`) is a planned follow-up. Cloud models pass all refs as
`reference_image_ids`.

## Execution
`orchestrator/queue.py`: connect `/ws` (waits for the `__connected__` sentinel) → `queue_prompt`
→ map `/ws` progress to SSE → on done, read `/history` + fetch via `/view` → save to
`<repo>/AIStudio/outputs/{project}/` with a `.json` sidecar (the GenSpec).

## Memory rule (24GB)
`orchestrator/memory.py`: one big model at a time — free ComfyUI on family switch, unload the
LLM (`keep_alive:0`) when model+LLM exceed budget, downshift to a lighter equivalent when one
exists. `LIGHTER_EQUIVALENT` is empty in the trimmed lineup, so an over-budget model runs as-is
(use a smaller Qwen GGUF quant + sequential offload on tight memory).
