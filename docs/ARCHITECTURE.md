# Architecture

```
Browser (Next.js :3000)
  ChatPanel ── SSE ──┐         CanvasStage (react-konva: image + mask layers)
  PromptBox/Gallery  │         EditToolbar (Region Redraw / Text Edit / Upscale / White BG / Add Ref / Export)
        │  /api/* proxy
        ▼
FastAPI backend (:8000)
  routers/  chat · jobs · projects · assets · uploads · models
  llm/      ollama_client · openrouter_client · prompts · handoff (GENSPEC extractor)
  comfy/    client (HTTP+WS) · builder (GenSpec→graph) · progress · templates(validate)
  orchestrator/  memory (H100 80GB co-resident) · queue (job worker + SSE pub/sub) · pipeline (upscale/bg)
  db/       aiosqlite (WAL)  ·  services/ image_ops · rembg · storage
        │ HTTP /api/chat            │ HTTP /prompt + WS /ws
        ▼                           ▼
   Ollama (:11434)            ComfyUI (:8188, CUDA, fp8/safetensors)
   Qwen3-VL 8b (multimodal)   Chroma·LUSTIFY·FLUX-Fill·Qwen-Edit-AIO·Redux·Wan2.2-TI2V·ControlNet-Union·RealESRGAN
        └────────── H100 80GB VRAM (full photoreal stack co-resident) ──────────┘
                                  ▼ writes
         <repo>/AIStudio/ (models, comfyui, outputs, db.sqlite, logs)  ← single runtime home (git-ignored)
           └ symlink → /data/<user>/Figment/AIStudio  (AGENTS.md: big artifacts live on /data, not root)
```

## Request flows
- **Home → chat (single entry, no mode tabs)**: the home composer (`PromptBox`) no longer picks a
  mode. It creates a project, stages any uploads as `reference` assets, and hands `{prompt,
  attachments}` to the editor via the zustand `pendingStart` field. `ChatPanel` auto-sends that as the
  **first chat turn**, so the originating prompt becomes the first message in the conversation (it is
  no longer a card pinned to the canvas).
- **Chat → route → generate**: `POST /chat` streams the LLM reply; the GENSPEC block is withheld from
  the visible stream and emitted as a `genspec` SSE event. The chat LLM is the **router** — its system
  prompt (`llm/prompts.py`) chooses `GenSpec.mode` from the prompt and any attached image, and asks one
  short clarifying question (no GENSPEC) when the intent is ambiguous (edit vs. reference, raster vs.
  figure). With attachments, `chat.py` notes them to the (vision) LLM and, after routing, injects the
  asset ids into the spec by mode (`source_asset` for image→image, `reference_images` for style/figure)
  then re-validates. A confident **first-turn** route auto-runs the job; later turns surface a "Generate
  this" confirm button → `POST /jobs`. The chat LLM follows the UI model pick (`ChatRequest.llm_model`):
  `chat.py:_resolve_chat` routes a **local** LLM to its Ollama tag and a **cloud** LLM to OpenRouter
  (`openrouter_client.py`), degrading to the default Ollama model when no key is set — so model choice
  lives in the picker, not `.env`.
- **Job execution** (`orchestrator/queue.py`, `JobWorker._run`): resolve model → pick a
  `GenerationEngine` (`engines/base.py`) via `_select_engine` → `engine.run(EngineContext)` →
  `_persist` (one shared site: remove-bg for images → save asset + sidecars → `done`). The three engines:
  - **local** (`engines/local_comfy.py`): `MemoryOrchestrator.ensure_ready_for` (the image stack
    co-resides; frees ComfyUI / unloads LLM only under rare budget pressure) → upload inputs →
    `builder.build()` → `/ws` (sentinel) → `queue_prompt` → progress→SSE → result from `/history`+`/view`.
  - **cloud raster** (`engines/cloud_image.py`): OpenRouter image API → a plain PNG, for the normal
    modes — interchangeable with local.
  - **cloud figure** (`engines/figure.py`, `Mode.figure` only): the vendored FigGen pipeline →
    structured FigureSpec → editable SVG/PPTX + preview PNG.
  Provider is unified on `OPENROUTER_API_KEY`; no key → raster raises a clear error, figure falls back
  to a mock provider.
- **Region Redraw**: frontend exports a white-on-black mask at exact source dims → `POST /uploads`
  (source + mask) → `POST /jobs {mode:inpaint}` → `build_inpaint_flux_fill`.
- **Toolbar one-shots**: `POST /assets/{id}/upscale|whitebg|removebg` (upscale via a tiny ComfyUI
  graph polled on `/history`; bg-removal via rembg on CPU).

## Why these choices
- **One engine interface, three backends** (`engines/`): local ComfyUI, cloud raster (OpenRouter),
  cloud figure (FigGen). The job worker selects by `(engine, mode)` and shares one persistence path —
  so a cloud model is interchangeable with local for raster work, and figures are an explicit mode.
- **ComfyUI** for local: one backend covers txt2img/img2img/inpaint/edit/controlnet/redux/video/
  upscale; programmatic `/prompt`+`/ws`; CUDA fp8/bf16 safetensors are first-class (GGUF retained
  only for FLUX-Fill).
- **Programmatic graph builder** (not JSON+placeholder): type-safe LoRA chains, ref-image fan-out,
  and per-mode branching; validated against live `/object_info` at startup.
- **SSE** (not WebSocket): generation progress is one-way server→client.
- **Co-residency** (not one-big-model): the H100's 80GB holds the whole photoreal stack (~70GB) at
  once, so the orchestrator no longer serialises — it only frees under rare budget pressure (78GB).
