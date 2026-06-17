# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) and other coding agents when working with code in this repository.

## What this is

Figment unifies a scientific-figure pipeline (FigGen, vendored as `figgen`) and a local image studio (ImgGen) into one product: a **Next.js** UI over a single **FastAPI** backend that drives **cloud** models (OpenRouter) and **local** models (ComfyUI / Ollama), selectable **per generation mode** in the UI. The local lineup is deliberately uncensored (abliterated text encoders + NSFW LoRAs) and tuned to run within **24GB unified memory on Apple Silicon**.

Deeper references live in `docs/`: `ARCHITECTURE.md` (request flows), `WORKFLOWS.md` (ComfyUI builder table, reference-image rules, verify matrix), `MODELS.md` (lineup). `README.md` is the user-facing overview. Read those before large changes — this file is the orientation, they are the detail.

## Commands

Backend (Python 3.11+, `uv`, run from `backend/`):
```bash
cd backend && uv sync                                  # install deps (figgen is editable from ../figure_engine)
uv run uvicorn app.main:app --reload --port 8000       # dev server
uv run pytest                                          # hermetic unit tests (mock provider; no keys/services needed)
uv run pytest tests/test_chat_routing.py -k handoff    # a single test / pattern
uv run ruff check . && uv run ruff format .            # lint + format
```

Frontend (Next.js 15 / React 19, `pnpm`, run from `frontend/`):
```bash
cd frontend && pnpm install
pnpm dev          # :3000, proxies /api/* → 127.0.0.1:8000 (see next.config.ts rewrites)
pnpm typecheck    # tsc --noEmit
pnpm build        # next build
```

Both servers at once (assumes ComfyUI + Ollama already running): `scripts/40_dev.sh`.

CLI — the **entire studio runs from the terminal, no web app or server** (`scripts/figment` → `python -m app.cli`, in-process):
```bash
scripts/figment generate "a red fox" --mode txt2img --out fox.png   # modes: txt2img|img2img|inpaint|edit|controlnet|reference
scripts/figment enhance "창가의 고양이" --llm-model gemma-4-local      # short idea → rich English prompt
scripts/figment chat "데이터센터 다이어그램"   # streams reply + GENSPEC
scripts/figment models | doctor                # catalog readiness ✓/✗ | service health
scripts/figment verify [--local-only|--cloud-only|--offline|--mode edit|--json]
```

`figment verify` **actually runs** every pipeline (local ComfyUI per model/mode, cloud figure pipeline, Ollama + cloud chat/enhance, post-ops) and prints a PASS/SKIP/FAIL matrix; a missing weight / stopped service / absent key is a clean **SKIP with a reason**, never a false FAIL. Exit code = number of FAILs. This is the real integration test — unit `pytest` is mock-only.

Local model provisioning (optional, 24GB+ Apple Silicon), in order: `scripts/10_install_comfyui.sh` → `11_install_custom_nodes.sh` → `20_download_models.sh all` (~60GB) → `21_pull_ollama_models.sh` → `30_run_comfyui.sh` (:8188) + `31_run_ollama.sh` (:11434).

## Architecture

```
frontend/  (Next.js)      app/{page,editor}  components/{home,editor,models,ui}  lib/{api,store(zustand),sse,canvas,types,constants}
backend/app/ (FastAPI)    routers: chat · jobs · projects · assets · uploads · models · prompt
  engines/                engine dispatch by ModelDef.engine → local-comfy | local-ollama | cloud-openrouter
  models_catalog/         registry.py — SINGLE source of truth: MODELS (image) + LLM_MODELS, local + cloud
  comfy/                  client (HTTP+WS) · builder (GenSpec→graph) · templates (node validation) · progress
  llm/                    routing (shared by chat + enhance) · ollama_client · openrouter_client · prompts · handoff
  orchestrator/           queue (JobWorker + SSE pub/sub) · memory (24GB rule) · pipeline (upscale/bg one-shots)
  services/ db/ schemas/  image_ops · rembg · storage · export_ops ; aiosqlite (WAL) ; GenSpec / job models
  cli/                    in-process terminal front-end (runtime replicates main.lifespan; verify.py)
figure_engine/            vendored FigGen (`figgen`): structured FigureSpec → editable SVG/PPTX (used by the cloud image path)
AIStudio/                 git-ignored runtime home: weights, ComfyUI, outputs, db.sqlite, logs (override via AISTUDIO_HOME)
```

### How a request becomes an image
1. **Chat → GenSpec**: `POST /chat` streams the LLM reply; the `GENSPEC` block is withheld from the visible stream and emitted as a separate `genspec` SSE event (`llm/handoff.py`). User presses Generate → `POST /jobs`.
2. **Engine dispatch**: `engines/engine_of(model)` routes by `ModelDef.engine`. **Local image** → `orchestrator/queue.py` (the `JobWorker`) builds a ComfyUI graph via `comfy/builder.py` and runs it. **Cloud image** → `engines/figure_pipeline.py` runs the vendored FigGen pipeline on OpenRouter → editable SVG/PPTX. **LLM** → `llm/routing.py`.
3. **Progress**: generation is one-way server→client, so it streams over **SSE** (not WebSocket); the worker maps ComfyUI `/ws` events to SSE and saves the output to `AIStudio/outputs/{project}/` with a `.json` GenSpec sidecar.

### Conventions that span files — get these right
- **Model selection lives in the UI, never in `.env`.** `.env` holds only API keys, service URLs, and a single fallback `OLLAMA_LLM`. The picker sends a model id; image models are remembered **per mode** (frontend store `selectedByMode`). Do not hard-code model ids in routers or the builder — resolve through `registry.py`.
- **`registry.py` is the single source of truth.** A `ModelDef` carries `engine`, `family`/`template` (which builder fn to use), `files` (local weight filenames that must match `scripts/20_download_models.sh`), `vision` (gates multimodal prompt-enhance), and for cloud/local-LLM a `cloud_model_id` (provider slug, or **Ollama tag** for local LLMs). Add a model here, not in the dispatch code.
- **LLM routing is shared.** `llm/routing.py:resolve_chat` powers both chat and `/prompt/enhance`: a cloud LLM with a configured key → OpenRouter, a local LLM → its Ollama tag, otherwise → the default Ollama model. Keep enhance and chat on this one path.
- **ComfyUI graphs are built programmatically** in `comfy/builder.py` (type-safe LoRA chains / ref fan-out / per-mode branching), not static JSON + placeholders. Nodes are validated at startup against live `/object_info` (`comfy/templates.py`). **GGUF / bf16 only — never fp8 (corrupts on Metal); no openpose/DWPose/InstantID (onnxruntime friction on arm64).**
- **One-big-model rule (24GB).** `orchestrator/memory.py` serializes large models: it frees ComfyUI on a family switch and unloads the LLM (`keep_alive:0`) when model+LLM exceed budget. Heavy local edit/reference inputs are downscaled (`LOCAL_QWEN_EDIT_MAX_SIDE` ≈1024px) and reference count is clamped (`qwen-edit` = **2** refs, not the node's 3, because a 3rd overflows the MPS attention buffer).
- **Reference-image caps are per engine**, enforced both server- and client-side: local Qwen-Edit = 2, controlnet = first ref only, cloud = up to `MAX_REFERENCE_IMAGES` (6, mirrored in `frontend/lib/constants.ts`). The UI auto-trims on a cloud→local switch.
- **Asset rows can outlive their files.** Every file-touching endpoint in `routers/assets.py` guards with `_require_file` → a clean **404** instead of a 500; the frontend hides broken thumbnails (`lib/img.ts:hideBrokenImage`). Preserve this when adding asset endpoints.
- **The CLI shares production code paths.** `cli/runtime.py` replicates `main.py:lifespan` and submits to the **same** `JobWorker` as `/jobs` — there is no parallel engine. Changes to the job/build/post-op path must keep both the HTTP and CLI entry points working (and `verify.py` exercising them).
- **Graceful degradation is a feature.** With no `OPENROUTER_API_KEY`, cloud options disable in the picker and the app falls back to local/mock so it runs fully offline. A cold-loading local LLM's first enhance can exceed the dev proxy window (`ECONNRESET`); clients use bounded httpx timeouts and the frontend retries enhance once. Don't add eager boot-time model warmup (the pick might be a cloud API).
