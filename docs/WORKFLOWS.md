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
| edit (Qwen-Edit) | `build_edit_qwen` | UnetLoaderGGUF → CLIPLoaderGGUF type=qwen_image → TextEncodeQwenImageEdit **/ TextEncodeQwenImageEditPlus (≥2 imgs)** → LoraLoader(Lightning 4-step) | heavy (13GB) → LLM unloaded first; 1 img → single node, 2–3 imgs → Plus |
| reference (Qwen-Edit) | `build_edit_qwen` (via `build()` mode routing) | same graph as edit — 1 ref → `TextEncodeQwenImageEdit`, 2–3 refs → `TextEncodeQwenImageEditPlus` (`image1..image3`) | style/identity reference; positional Picture 1/2/3 |
| controlnet (SDXL) | `build_controlnet_sdxl` | preprocessor (Canny/Depth/Scribble/LineArt) → ControlNetLoader → ControlNetApplyAdvanced | **no openpose/DWPose/InstantID** (onnxruntime friction on arm64) |
| upscale | `build_upscale` | UpscaleModelLoader → ImageUpscaleWithModel | standalone; toolbar one-shot via `/assets/{id}/upscale` |
| bg-remove / white-bg | — (not ComfyUI) | rembg/BiRefNet on CPU | keeps the Metal GPU free |

## Reference images
`GenSpec.reference_images` accepts up to `MAX_REFERENCE_IMAGES` (= 6; `backend/app/schemas/genspec.py`,
mirrored in `frontend/lib/constants.ts`). `orchestrator/queue.py` uploads each to ComfyUI and fills
`ctx.comfy_refs`. Per-engine handling:
- **`qwen-edit` (edit + reference) — up to 3 (local):** 1 image → single-input `TextEncodeQwenImageEdit`;
  ≥2 images → `TextEncodeQwenImageEditPlus` (`image1..image3`, one `LoadImage` each, positional
  Picture 1/2/3). `build_edit_qwen` clamps to `LOCAL_QWEN_EDIT_MAX_REFS` (= 3); extra refs are dropped
  (the global 6 stays the outer bound, so a 6-ref local request degrades rather than 400s). The
  frontend caps the picker at 3 for local models (`refCap` / `LOCAL_MAX_REFERENCE_IMAGES`) and auto-trims
  on a cloud→local switch.
- **`controlnet` — first-ref-only (local):** single-input; uses the first reference, ignores the rest.
- **Cloud models — all refs:** passed through as `reference_image_ids` (up to 6).

Note: the Qwen edit encoder consumes images **positionally** (Picture 1/2/3) — there is no way to
address a reference by name/filename in the prompt.

## Execution
`orchestrator/queue.py`: connect `/ws` (waits for the `__connected__` sentinel) → `queue_prompt`
→ map `/ws` progress to SSE → on done, read `/history` + fetch via `/view` → save to
`<repo>/AIStudio/outputs/{project}/` with a `.json` sidecar (the GenSpec).

## Memory rule (24GB)
`orchestrator/memory.py`: one big model at a time — free ComfyUI on family switch, unload the
LLM (`keep_alive:0`) when model+LLM exceed budget, downshift to a lighter equivalent when one
exists. `LIGHTER_EQUIVALENT` is empty in the trimmed lineup, so an over-budget model runs as-is
(use a smaller Qwen GGUF quant + sequential offload on tight memory).

## CLI generation (in-process)
`scripts/figment generate --mode <m>` builds a `GenSpec` from flags and runs it through the **same**
`JobWorker`/builder path as `/jobs` (no parallel engine — see ARCHITECTURE.md → *CLI*). The `--mode`
maps 1:1 to the builder table above: `txt2img`/`img2img` → `build_txt2img_*`/`build_img2img`,
`inpaint` → `build_inpaint_sdxl` (`--source` + `--mask`), `edit`/`reference` → `build_edit_qwen`
(`--source` and/or `--ref` ×N, clamped to 3), `controlnet` → `build_controlnet_sdxl` (`--controlnet-type`).
`--upscale` is a post-step the CLI chains itself (the worker only chains `--remove-bg`).

## Verify matrix
`scripts/figment verify` (`backend/app/cli/verify.py`) exercises every builder above via `run_genspec`,
plus the LLM and post-op paths. Each case declares prerequisites and **SKIPs** with a precise reason when
one is unmet (never a false FAIL):

| Group | Cases | Builder / path exercised | Gated on |
|---|---|---|---|
| LOCAL | qwen-image txt2img/img2img · qwen-edit edit(1)/edit(multi)/reference · pony-v6 txt2img/controlnet · lustify-inpaint inpaint | `build_txt2img_qwen`/`build_img2img`/`build_edit_qwen`/`build_controlnet_sdxl`/`build_inpaint_sdxl` | ComfyUI up · weight file on disk · (net for source/ref) |
| CLOUD | seedream-4.5 txt2img/edit/reference | FigGen figure pipeline → preview PNG + SVG/PPTX sidecars | `OPENROUTER_API_KEY` (keyless ⇒ SKIP, never a mock pass) |
| LLM | qwen3-vl-local chat/enhance · gemma-4-31b chat/enhance | `llm/routing.chat_stream` + `build_enhance_messages` (vision) | Ollama tag pulled / OpenRouter key |
| POSTOP | upscale · removebg · whitebg · export svg/pptx | `pipeline.upscale_image` · `rembg` · `export_ops` | upscale: ComfyUI + Real-ESRGAN weight; rest: always (net for sample) |

Sample photos come from picsum.photos by fixed seed (cached under `AIStudio/testdata/`); the inpaint mask
is generated locally (PIL). Exit code = number of FAILs; SKIPs never fail the run.
