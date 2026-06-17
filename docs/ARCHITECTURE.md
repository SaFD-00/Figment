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
  orchestrator/  memory (24GB rules) · queue (job worker + SSE pub/sub) · pipeline (upscale/bg)
  db/       aiosqlite (WAL)  ·  services/ image_ops · rembg · storage
        │ HTTP /api/chat            │ HTTP /prompt + WS /ws
        ▼                           ▼
   Ollama (:11434)            ComfyUI (:8188, MPS, GGUF)
   Gemma 4 E4B abliterated    Qwen-Image/Qwen-Edit/Pony/LUSTIFY-Inpaint/ControlNet/RealESRGAN (all uncensored)
   (uncensored, multimodal)
        └────────── shared 24GB unified memory (one big model at a time) ──────────┘
                                  ▼ writes
         <repo>/AIStudio/ (models, comfyui, outputs, db.sqlite, logs)  ← single runtime home (git-ignored)
```

## Request flows
- **Chat → generate**: `POST /chat` streams the LLM reply; the GENSPEC block is withheld from the
  visible stream and emitted as a `genspec` SSE event. The user presses Generate → `POST /jobs`.
  The chat LLM follows the UI model pick (`ChatRequest.llm_model`): `llm/routing.py:resolve_chat` routes a
  **local** LLM to its Ollama tag and a **cloud** LLM to OpenRouter (`openrouter_client.py`), degrading
  to the default Ollama model when no key is set — so model choice lives in the picker, not `.env`.
- **Prompt enhance** (the composer's **Enhance** button): `POST /prompt/enhance` rewrites a short/vague
  idea into one rich **English** image prompt via the selected LLM, reusing the *same* routing
  (`llm/routing.py` — shared with chat). It returns a single JSON `{prompt}` (no streaming, no GENSPEC,
  no chat); `prompts.py:build_enhance_messages` tailors comma-tags vs natural language to the picked image
  model, and `routers/prompt.py:_clean` strips `<think>` reasoning / quotes / labels. The request also
  carries an optional **`instruction`** (the user's "how to enhance" note, woven into the user turn) and an
  optional **`image`** data URL: for **edit/reference** modes the home composer sends the first uploaded
  image, and `_enhance_image_url` attaches it as an OpenAI-style multimodal part whenever the **picked**
  model is a **vision** model — provider-agnostic, gated on `ModelDef.vision` alone (both the local
  `gemma-4-local` and the cloud `gemma-4-31b` qualify) — normalized to a ≤768px PNG via `image_ops`. The
  cloud route forwards those parts as-is; the local route is served by `ollama_client.py:_to_ollama_messages`,
  which converts them into Ollama's native per-message `images` array, so local vision enhance works too.
  The frontend drops the result into the prompt box with a one-step ↶ undo. (Distinct from the
  diagram's ComfyUI `/prompt`, which is the local image engine on :8188.)
  **Network resilience**: a local LLM's *first* enhance is a cold model load that can exceed the
  Next dev proxy's ~30s window → the proxy resets the socket (`ECONNRESET` / "socket hang up").
  The httpx clients use bounded timeouts (`ollama_client`/`openrouter_client`, not `timeout=None`)
  so a stuck call errors instead of hanging, and the frontend (`lib/api.ts:enhancePrompt`) retries
  **once** — the first attempt warms the model (Ollama `keep_alive`), so the retry lands warm.
  We deliberately do **not** pre-warm the LLM at boot: the pick may be a cloud API, so eagerly
  loading the local model would waste unified memory; the cold cost is paid lazily on first use.
- **Job execution** (`orchestrator/queue.py`): resolve model → `MemoryOrchestrator.ensure_ready_for`
  (free ComfyUI / unload LLM as needed) → upload input images to ComfyUI → `builder.build()` →
  connect `/ws` (sentinel) → `queue_prompt` → map progress to SSE → fetch result from `/history`+`/view`
  → save asset + sidecar → `done`.
- **Cloud path**: when the resolved image model is a cloud one, the job routes to the vendored
  FigGen pipeline on **OpenRouter** (`engines/figure_pipeline.py`) — structured FigureSpec → editable
  SVG/PPTX. Provider is unified on `OPENROUTER_API_KEY`; with no key it falls back to a mock provider.
- **Region Redraw**: frontend exports a white-on-black mask at exact source dims → `POST /uploads`
  (source + mask) → `POST /jobs {mode:inpaint}` → `build_inpaint_sdxl` (LUSTIFY 9-ch inpaint).
- **Toolbar one-shots**: `POST /assets/{id}/upscale|whitebg|removebg` (upscale via a tiny ComfyUI
  graph polled on `/history`; bg-removal via rembg on CPU).
- **Asset serving** (`routers/assets.py`): `GET /assets/{id}/file` and `…/export` stream the file
  off disk. Asset rows can outlive their files (manual cleanup, a deleted project's leftover output
  dir, a moved `AISTUDIO_HOME`), so every file-touching endpoint guards with `_require_file` →
  a clean **404** instead of a `FileNotFoundError` 500. The frontend hides such broken thumbnails
  (`lib/img.ts:hideBrokenImage`) rather than showing the browser's broken-image icon.
- **CLI (in-process)** (`backend/app/cli/`, run via `scripts/figment` → `python -m app.cli`): a terminal
  front-end that needs **no uvicorn and no Next.js**. `cli/runtime.py:app_runtime` replicates `main.py:lifespan`
  (init_db → `deps.worker().start()` → `deps.shutdown()` + close_db), skipping only the advisory ComfyUI
  node-validation probe (`doctor` runs that on demand). `cli/runtime.py:run_genspec` submits a GenSpec to the
  **same** `JobWorker` the `/jobs` route uses and streams its progress events to a terminal bar — so there is
  **no parallel engine**, the CLI exercises the identical production path. Input images are staged exactly like
  `/uploads` (`stage_image_asset` reuses `image_ops` + `storage`); post-ops/export/enhance/chat reuse
  `orchestrator/pipeline`, `services/export_ops`, and `llm/routing`. `cli/verify.py` drives that same
  `run_genspec` to exercise every pipeline (see WORKFLOWS.md → *Verify matrix*).

## Why these choices
- **ComfyUI** as the single engine: one backend covers txt2img/img2img/inpaint/edit/controlnet/reference/
  upscale; programmatic `/prompt`+`/ws`; GGUF support (FP8 is broken on Metal).
- **Programmatic graph builder** (not JSON+placeholder): type-safe LoRA chains, ref-image fan-out,
  and per-mode branching; validated against live `/object_info` at startup.
- **SSE** (not WebSocket): generation progress is one-way server→client.
- **One-big-model rule**: 24GB unified memory can't hold two large models; the orchestrator serializes.
