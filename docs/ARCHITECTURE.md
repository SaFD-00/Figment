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
   Qwen3.5-9B uncensored      Qwen-Image/Pony/Chroma/Z-Image/FLUX-Fill/Qwen-Edit/Kontext/ControlNet/Redux/RealESRGAN
        └────────── shared 24GB unified memory (one big model at a time) ──────────┘
                                  ▼ writes
         <repo>/AIStudio/ (models, comfyui, outputs, db.sqlite, logs)  ← single runtime home (git-ignored)
           └ symlink → /data/<user>/Figment/AIStudio  (AGENTS.md: big artifacts live on /data, not root)
```

## Request flows
- **Chat → generate**: `POST /chat` streams the LLM reply; the GENSPEC block is withheld from the
  visible stream and emitted as a `genspec` SSE event. The user presses Generate → `POST /jobs`.
  The chat LLM follows the UI model pick (`ChatRequest.llm_model`): `chat.py:_resolve_chat` routes a
  **local** LLM to its Ollama tag and a **cloud** LLM to OpenRouter (`openrouter_client.py`), degrading
  to the default Ollama model when no key is set — so model choice lives in the picker, not `.env`.
- **Job execution** (`orchestrator/queue.py`): resolve model → `MemoryOrchestrator.ensure_ready_for`
  (free ComfyUI / unload LLM as needed) → upload input images to ComfyUI → `builder.build()` →
  connect `/ws` (sentinel) → `queue_prompt` → map progress to SSE → fetch result from `/history`+`/view`
  → save asset + sidecar → `done`.
- **Cloud path**: when the resolved image model is a cloud one, the job routes to the vendored
  FigGen pipeline on **OpenRouter** (`engines/figure_pipeline.py`) — structured FigureSpec → editable
  SVG/PPTX. Provider is unified on `OPENROUTER_API_KEY`; with no key it falls back to a mock provider.
- **Region Redraw**: frontend exports a white-on-black mask at exact source dims → `POST /uploads`
  (source + mask) → `POST /jobs {mode:inpaint}` → `build_inpaint_flux_fill` (or SDXL).
- **Toolbar one-shots**: `POST /assets/{id}/upscale|whitebg|removebg` (upscale via a tiny ComfyUI
  graph polled on `/history`; bg-removal via rembg on CPU).

## Why these choices
- **ComfyUI** as the single engine: one backend covers txt2img/img2img/inpaint/edit/controlnet/redux/
  upscale; programmatic `/prompt`+`/ws`; GGUF support (FP8 is broken on Metal).
- **Programmatic graph builder** (not JSON+placeholder): type-safe LoRA chains, ref-image fan-out,
  and per-mode branching; validated against live `/object_info` at startup.
- **SSE** (not WebSocket): generation progress is one-way server→client.
- **One-big-model rule**: 24GB unified memory can't hold two large models; the orchestrator serializes.
