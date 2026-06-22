# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What Figment is

Figment unifies two heritages into one product: the **FigGen** scientific-figure pipeline (cloud, structured → editable vector) and the **ImgGen** local image studio (ComfyUI/Ollama). It's a Next.js UI over a single FastAPI backend that drives **cloud models** (OpenRouter) and **local models** (ComfyUI + Ollama), with the model chosen **per generation in the UI** — not in config.

The local engine targets a **single NVIDIA H100 80GB (CUDA, GPU 0)**. The whole photoreal stack is sized to **co-reside at once** (~70GB under a 78GB budget); video (Wan 2.2) swaps in. The old Apple-Silicon/Metal constraints ("never fp8", "one big model at a time", GGUF-only) are gone — fp8/bf16 safetensors are first-class.

## Common commands

```bash
# Backend (FastAPI, Python 3.11+, uv)
cd backend && uv sync                                   # install (vendored figgen is an editable path dep)
uv run uvicorn app.main:app --reload --port 8000        # run API on :8000
uv run pytest                                           # hermetic test suite (mock provider; NO keys/GPU needed)
uv run pytest tests/test_builder.py                     # one file
uv run pytest tests/test_builder.py::test_video_wan_a14b_moe   # one test
uv run ruff check .                                     # lint (ruff is a dev dep)

# Frontend (Next.js 15 / React 19, pnpm@9.15.4)
cd frontend && pnpm install
pnpm dev          # http://localhost:3000
pnpm typecheck    # tsc --noEmit
pnpm build
```

One backend test (`test_figure_engine.py::test_figure_pipeline_generates_editable_artifacts`) makes a **live OpenAI/OpenRouter call** and fails without a key — this is environmental, not a regression. Everything else is hermetic.

### Running the full local stack (4 processes / 3 launchers)

`scripts/40_dev.sh` starts only the **backend (:8000) + frontend (:3000)** and assumes ComfyUI + Ollama are already up. So local end-to-end = **three launch commands**:

```bash
bash scripts/30_run_comfyui.sh    # ComfyUI diffusion engine  → :8188  (GPU 0, --highvram)
bash scripts/31_run_ollama.sh     # Ollama chat/planner LLM   → :11434 (idempotent)
bash scripts/40_dev.sh            # FastAPI backend :8000 + Next.js frontend :3000
```

First-time local setup, in order:
`00_bootstrap_dirs.sh` (runtime home + `/data` symlink) → `10_install_comfyui.sh` (clones ComfyUI, CUDA torch `cu124`) → `12_install_custom_nodes.sh` (IPAdapter/InstantID/PuLID/controlnet_aux/USDU/GGUF/RMBG + insightface) → `20_download_models.sh all` → `21_pull_ollama_models.sh`. Download stages: `base|sdxl|edit|ref|identity|video|all`.

## Architecture (the parts that span files)

### Two engines, one registry, UI-driven dispatch
`backend/app/models_catalog/registry.py` is the **single source of truth**. `MODELS` (image/video) and `LLM_MODELS` (chat) each carry an `engine` field: `local-comfy`, `local-ollama`, or `cloud-openrouter`. A request's `GenSpec.model` / `llm_model` (set by the UI) resolves through `registry.resolve()` / `resolve_llm()`; `DEFAULT_BY_MODE` fills in when null. **Removing or renaming a model id ripples** to `DEFAULT_BY_MODE`, `llm/prompts.py` heuristics, frontend fixed-model ids, and tests — grep before deleting.

### Job path vs chat path (two independent flows)
- **Generation jobs** run through the orchestrator queue (`backend/app/orchestrator/queue.py`, `JobWorker._run`) — a **single heavy in-process async worker**. It resolves the model, then forks:
  - `is_cloud(model)` → `engines/figure_pipeline.py` runs the vendored FigGen orchestrator on OpenRouter: structured **FigureSpec → editable SVG/PPTX** + preview PNG (this is the scientific-figure lineage; cloud image models do NOT just return a raster).
  - else → **local ComfyUI**: `orch.ensure_ready_for(model)`, upload inputs, `comfy/builder.build(spec, ctx)`, execute over ComfyUI `/prompt` + `/ws`, persist (video → animated webp, image → optional bg-removal).
- **Chat** is separate (`routers/chat.py`, not the queue). `_resolve_chat(llm_model)` streams from **Ollama** (local pick) or **OpenRouter** (cloud pick) — the chat LLM follows the UI's LLM pick independently of the image model. `llm/handoff.py` extracts a `GenSpec` from the conversation.

### ComfyUI graph builder
`backend/app/comfy/builder.py` builds graphs **programmatically** (the `_G` helper; links are `[node_id, output_index]` pairs), one builder per template keyed off `ModelDef.template`. `comfy/templates.py` validates that the custom-node `class_type`s each builder needs are present by querying ComfyUI `/object_info` at startup (fail-fast). Wan 2.2 uses ComfyUI **native core** video nodes (no WanVideoWrapper). The Wan 2.2 A14B models are a true **MoE**: two `UNETLoader` experts (high/low noise) + per-expert lightx2v 4-step LoRA + two chained `KSamplerAdvanced` stages (high `[0,split)` hands leftover noise to low `[split,steps)`); the 5B TI2V is a single dense sampler with `Wan22ImageToVideoLatent`. See `test_builder.py` for the canonical assertions.

### Config & runtime home
`backend/app/config.py` (`Settings`, pydantic-settings, reads repo-root `.env`) holds local + service settings; cloud/OpenRouter settings live in the vendored `figure_engine/src/figgen/config.py`, bound to the same `.env` via `engines/cloud.py`. Everything runtime — weights, ComfyUI, `db.sqlite`, outputs, logs — lives under a **single `AISTUDIO_HOME`** (default `<repo>/AIStudio`). Note the env var is `COMFY_URL` (not `COMFYUI_URL`).

### Frontend wiring
`frontend/lib/api.ts` / `sse.ts` hit a hardcoded `/api` base; `frontend/next.config.ts` rewrites `/api/*` → `http://127.0.0.1:8000/*` (backend host is hardcoded, no `NEXT_PUBLIC_API_URL`). The model picker is **backend-sourced** (`GET /api/models/all` → `lib/models.ts` store), grouped Local/Cloud by `engine`; nothing is hardcoded in the picker. The canvas is **react-konva**, dynamically imported `ssr:false` (Konva touches `window`); `next.config.ts` aliases the `canvas` module to `false`. Region-redraw is pinned to `flux-fill` (inpaint), text-edit to `qwen-edit-aio` (edit).

## Conventions & constraints

- **Storage rule (`~/AGENTS.md`):** large/regenerable artifacts go on the big `/data` volume, never the small root volume. `<repo>/AIStudio` is a **symlink → `/data/<user>/Figment/AIStudio`** (created by `00_bootstrap_dirs.sh`) and is git-ignored. Don't write multi-GB outputs under the repo root.
- **`.env` is keys + service URLs + fallback defaults only** — there is **no model selection in `.env`**; models are picked in the UI. The model ids in `.env`/`.env.example` are fallbacks used when nothing is selected (and for FigGen sub-roles). With no `OPENROUTER_API_KEY`, the cloud engine falls back to a safe `mock` provider (offline-safe) and cloud options disable in the picker.
- **GPU pinning:** local ComfyUI runs on GPU 0 (`CUDA_VISIBLE_DEVICES=0`, `--highvram`) so the multi-model stack co-resides on one H100.
- **Content scope:** legal adult consensual NSFW only. Identity/face tooling (InstantID / IP-Adapter FaceID / PuLID-FLUX) is **consent-gated** ("consenting adults / synthetic faces only"). Exclude anything enabling CSAM or non-consensual deepfakes of real, identifiable people.
- `Mode` enum (`schemas/genspec.py`): `txt2img, img2img, inpaint, edit, controlnet, reference, video`. Up to `MAX_REFERENCE_IMAGES = 6` reference images.

## Docs
`docs/ARCHITECTURE.md` (system/engine dispatch), `docs/MODELS.md` (local model table), `docs/WORKFLOWS.md` (builder/memory rules). `README.md` for the user-facing overview and quickstart.
