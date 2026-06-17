# Figment

**Figures & images, made effortless.** Figment unifies the FigGen scientific-figure pipeline
and the ImgGen local image studio into one product — a clean Next.js UI over a single FastAPI
backend that can drive **cloud models** (OpenRouter) and **local models**
(ComfyUI / Ollama), selectable per generation.

## Features

**Generate** — Turn ideas into figures instantly
- **Text-to-Figure** — schematics from text or PDFs
- **Image-to-Figure** — sketches or photos into illustrations
- **Reference-to-Figure** — match the style/layout of one or more references (up to **3** images on local Qwen-Edit, **6** on cloud)
- **Prompt Enhance** — one click turns a short idea (any language) into a rich, detailed **English**
  prompt; your selected LLM does the rewrite (comma-tags for SDXL/Pony, natural language otherwise) and
  **↶ undo** restores the original. Add an optional **"how to enhance"** note to steer the rewrite, and
  in **edit/reference** modes a **multimodal LLM** reads your uploaded image to ground the prompt.
  With a **local** LLM the *first* enhance may lag while the model cold-loads (the model isn't
  pre-loaded at boot, since your pick could be a cloud API); the UI auto-retries once on the warmed
  model, so just wait or click again — cloud LLMs have no such warmup.
  Available in both the home composer and the editor chat.

**Edit** — Refine without starting over
- **Text Edit** — fix labels/legends on the image
- **Region Redraw** — redraw only selected parts (mask inpaint)
- **BG Remove** — clean white/transparent background

**Vectorize** — Export to fully editable formats
- **Editable PPTX**, **SVG**, and a **built-in canvas** (Konva raster + mask)

## Models

Pick the **image** model **per function** (each generation mode remembers its own pick) and a
**chat/planner LLM** right in the UI — an inline **pill picker** in the composer (home prompt box,
editor chat, and reference panel), grouped Local / Cloud. **There is no model config in `.env`** —
it only holds API keys, service URLs, and fallback defaults.
- **Cloud image** (OpenRouter): GPT Image 2, Nano Banana 2, SeeDream 4.5, FLUX.2 Max/Pro/Flex
- **Cloud LLM** (OpenRouter): Gemma 4 31B — a free **multimodal** model
- **Local** (ComfyUI/Ollama, uncensored): Qwen-Image 2512, Qwen-Edit (edit + reference), Pony V6, LUSTIFY SDXL inpaint, Qwen3-VL 8B abliterated (chat/planner, **multimodal**)

The selected model drives the whole pipeline: image generation, and the **chat/planner LLM follows
your pick too** — a local LLM streams from **Ollama**, a cloud LLM from **OpenRouter** (the same LLM
also powers **Prompt Enhance** in the composer). Both the local Qwen3-VL and the cloud Gemma are
**multimodal**, so Prompt Enhance can read an uploaded edit/reference image on either route. Cloud image
models route through the **figure pipeline** (structured FigureSpec → editable SVG/PPTX); local image
models route through **ComfyUI**. With no API key, cloud options are disabled in the picker and the
app falls back to local/mock so it runs fully offline.

## Architecture

```
frontend/        Next.js 15 + React 19 + Tailwind + Zustand + react-konva
backend/app/     FastAPI host: routers (chat·jobs·projects·assets·uploads·models)
  engines/       engine dispatch: local-comfy · cloud (figure pipeline) · ollama
  models_catalog/ unified registry (image + llm, local + cloud)
  comfy/ llm/ orchestrator/ services/ db/   (local engine + queue + storage)
figure_engine/   vendored FigGen package (`figgen`): pipeline, schema, layout, render, vectorize
AIStudio/        local runtime home (weights, ComfyUI, sqlite, outputs) — git-ignored
```

## Quickstart

```bash
cp .env.example .env          # add OPENROUTER_API_KEY for cloud, or run local services

# Backend
cd backend && uv sync && uv run uvicorn app.main:app --port 8000

# Frontend
cd frontend && pnpm install && pnpm dev    # http://localhost:3000
```

Local models (optional, 24GB+ Apple Silicon) — provisioning order:

```bash
scripts/10_install_comfyui.sh        # ComfyUI + its venv (MPS torch)
scripts/11_install_custom_nodes.sh   # ComfyUI-GGUF + controlnet_aux preprocessors
scripts/20_download_models.sh all    # all weights → AIStudio/models (~60GB)
scripts/21_pull_ollama_models.sh     # the local chat/planner LLM (~6GB)
scripts/30_run_comfyui.sh            # start ComfyUI (:8188)
scripts/31_run_ollama.sh             # start Ollama (:11434)
scripts/figment verify               # confirm every pipeline (PASS/SKIP/FAIL matrix)
```

## CLI

The whole studio runs from the terminal too — **no web app, no server**. `scripts/figment` boots the
backend **in-process** (same job worker, registry, and DB as the web app) and reuses every pipeline:

```bash
scripts/figment generate "a red fox in a snowy forest" --mode txt2img --out fox.png
scripts/figment generate "make it winter" --mode edit --source photo.png
scripts/figment enhance "창가의 고양이" --llm-model qwen3-vl-local   # rich English prompt → stdout
scripts/figment upscale fox.png        # also: removebg / whitebg (raw image files)
scripts/figment export <asset_id> --fmt pptx
scripts/figment chat "데이터센터 다이어그램 만들어줘"               # streams reply + GENSPEC
scripts/figment models                 # catalog + per-model readiness (✓/✗)
scripts/figment doctor                 # ComfyUI/Ollama/key/weights health report
```

`generate` mirrors all six modes (`--mode txt2img|img2img|inpaint|edit|controlnet|reference`) with
`--model/--source/--mask/--ref/--seed/--steps/...`; `--upscale`/`--remove-bg` chain post-steps. Run
`scripts/figment <cmd> --help` for the full flag set.

## Verify

```bash
cd backend && uv run pytest          # hermetic unit tests (mock provider; no keys needed)
cd frontend && pnpm typecheck && pnpm build

scripts/figment verify               # end-to-end: actually run every pipeline, local + cloud
scripts/figment verify --local-only  # or --cloud-only / --offline / --mode edit / --json
```

`figment verify` downloads small sample images, then **really runs** each feature (local ComfyUI
generation per model/mode, cloud figure pipeline, Ollama + cloud chat/enhance, upscale/bg-remove/export).
A missing model weight, stopped service, or absent API key is a clean **SKIP** with the exact reason —
never a false failure. It prints a PASS/SKIP/FAIL matrix and exits with the number of FAILs.
