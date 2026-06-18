# Workflows (ComfyUI graph builder)

Graphs are built **programmatically** in `backend/app/comfy/builder.py` (not static JSON +
placeholders) so LoRA chains, reference-image fan-out, and per-mode branching stay type-safe.
Node availability is validated at startup against ComfyUI `/object_info`
(`backend/app/comfy/templates.py`). **safetensors/bf16/fp16 only — never fp8 (corrupts on Metal).**

Every local mode runs on the single SDXL checkpoint (`juggernaut-xl`); `GenSpec.mode` picks the builder
(see `comfy/builder.py:build()`):

| Mode | Builder fn | Key nodes | Notes |
|---|---|---|---|
| txt2img | `build_txt2img_sdxl` | CheckpointLoaderSimple → CLIPTextEncode×2 → EmptyLatentImage → KSampler → VAEDecode | uses negative prompt |
| img2img | `build_img2img` | LoadImage → VAEEncode → KSampler(denoise) | `_sdxl_base`; `denoise` = fidelity dial |
| inpaint | `build_inpaint_sdxl` | LoadImage(src)+LoadImage(mask) → ImageToMask(red) → VAEEncodeForInpaint(grow_mask_by) → **SetLatentNoiseMask** → KSampler(denoise≥0.9) | standard 4-ch checkpoint → `SetLatentNoiseMask` re-asserts the mask; white=regen, black=keep |
| edit | `build_edit_juggernaut` | routes to `build_inpaint_sdxl` (mask) or `build_img2img` (no mask, denoise≥0.75) | planner decides if a mask exists; no mask generation in the builder |
| reference | `build_reference_ipadapter` | IPAdapterModelLoader + CLIPVisionLoader → **IPAdapterAdvanced** (weight 0.6–0.8) → EmptyLatentImage → KSampler | IP-Adapter Plus, **single** reference image |
| controlnet | `build_controlnet_sdxl` | preprocessor (Canny/Depth/Scribble/LineArt) → ControlNetLoader → ControlNetApplyAdvanced | **no openpose/DWPose/InstantID** (onnxruntime friction on arm64) |
| upscale | `build_upscale` | UpscaleModelLoader → ImageUpscaleWithModel | standalone; toolbar one-shot via `/assets/{id}/upscale` |
| bg-remove / white-bg | — (not ComfyUI) | rembg/BiRefNet on CPU | keeps the Metal GPU free |

## Reference images
`GenSpec.reference_images` accepts up to `MAX_REFERENCE_IMAGES` (= 6; `backend/app/schemas/genspec.py`,
mirrored in `frontend/lib/constants.ts`). `orchestrator/queue.py` uploads each to ComfyUI and fills
`ctx.comfy_refs`. Per-engine handling:
- **local `reference` (IP-Adapter Plus) — single image:** `build_reference_ipadapter` conditions on
  `ctx.comfy_refs[0]` (or the source if none). IP-Adapter Plus takes one reference image, so the local
  cap is `LOCAL_MAX_REFS` (= 1); the global 6 stays the outer bound. `queue.py` downscales each
  source/reference upload to `LOCAL_MAX_SIDE` (= 1024px longest side) as an MPS memory guard (SDXL is
  1024-native; the CLIP-Vision encoder resizes internally). The frontend caps the picker at 1 for local
  models (`refCap` / `LOCAL_MAX_REFERENCE_IMAGES`) and auto-trims on a cloud→local switch.
- **`controlnet` — first-ref-only (local):** single-input; uses the first reference, ignores the rest.
- **Cloud models — all refs:** passed through as `reference_image_ids` (up to 6).

## Execution
`orchestrator/queue.py`: connect `/ws` (waits for the `__connected__` sentinel) → `queue_prompt`
→ map `/ws` progress to SSE → on done, read `/history` + fetch via `/view` → save to
`<repo>/AIStudio/outputs/{project}/` with a `.json` sidecar (the GenSpec).

## Memory rule (24GB)
`orchestrator/memory.py`: one big model at a time — free ComfyUI on family switch, unload the
LLM (`keep_alive:0`) when model+LLM exceed budget, downshift to a lighter equivalent when one
exists. `LIGHTER_EQUIVALENT` is empty (the single 7GB SDXL checkpoint + 5GB VLM co-fit under 19GB),
so an over-budget model runs as-is.

## CLI generation (in-process)
`scripts/figment generate --mode <m>` builds a `GenSpec` from flags and runs it through the **same**
`JobWorker`/builder path as `/jobs` (no parallel engine — see ARCHITECTURE.md → *CLI*). The `--mode`
maps 1:1 to the builder table above: `txt2img`/`img2img` → `build_txt2img_sdxl`/`build_img2img`,
`inpaint` → `build_inpaint_sdxl` (`--source` + `--mask`), `edit` → `build_edit_juggernaut`
(`--source`, optional `--mask`), `reference` → `build_reference_ipadapter` (`--ref`, single image),
`controlnet` → `build_controlnet_sdxl` (`--controlnet-type`).
`--upscale` is a post-step the CLI chains itself (the worker only chains `--remove-bg`).

## Verify matrix
`scripts/figment verify` (`backend/app/cli/verify.py`) exercises every builder above via `run_genspec`,
plus the LLM and post-op paths. Each case declares prerequisites and **SKIPs** with a precise reason when
one is unmet (never a false FAIL):

| Group | Cases | Builder / path exercised | Gated on |
|---|---|---|---|
| LOCAL | juggernaut-xl txt2img/img2img/edit(img2img)/edit(mask→inpaint)/reference/controlnet/inpaint | `build_txt2img_sdxl`/`build_img2img`/`build_edit_juggernaut`/`build_reference_ipadapter`/`build_controlnet_sdxl`/`build_inpaint_sdxl` | ComfyUI up · weight file on disk · IP-Adapter weights+nodes (reference) · (net for source/ref) |
| CLOUD | gpt-image-2 txt2img/edit · gemini-pro-image reference | FigGen figure pipeline → preview PNG + SVG/PPTX sidecars | `OPENROUTER_API_KEY` (keyless ⇒ SKIP, never a mock pass) |
| LLM | qwen3-vl-local chat/enhance · gemini-2.5-flash chat/enhance | `llm/routing.chat_stream` + `build_enhance_messages` (vision) | Ollama tag pulled / OpenRouter key |
| POSTOP | upscale · removebg · whitebg · export svg/pptx | `pipeline.upscale_image` · `rembg` · `export_ops` | upscale: ComfyUI + Real-ESRGAN weight; rest: always (net for sample) |

Sample photos come from picsum.photos by fixed seed (cached under `AIStudio/testdata/`); the inpaint mask
is generated locally (PIL). Exit code = number of FAILs; SKIPs never fail the run.
