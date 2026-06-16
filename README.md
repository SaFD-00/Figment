# Figment

**Figures & images, made effortless.** Figment unifies the FigGen scientific-figure pipeline
and the ImgGen local image studio into one product — a clean Next.js UI over a single FastAPI
backend that can drive **cloud models** (OpenRouter) and **local models**
(ComfyUI / Ollama), selectable per generation.

## Features

**Generate** — Turn ideas into figures instantly
- **Text-to-Figure** — schematics from text or PDFs
- **Image-to-Figure** — sketches or photos into illustrations
- **Reference-to-Figure** — match the style/layout of a reference
- **✨ Prompt Enhance** — one click turns a short idea (any language) into a rich, detailed **English**
  prompt; your selected LLM does the rewrite (comma-tags for SDXL/Pony, natural language otherwise) and
  **↶ undo** restores the original. Available in both the home composer and the editor chat.

**Edit** — Refine without starting over
- **Text Edit** — fix labels/legends on the image
- **Region Redraw** — redraw only selected parts (mask inpaint)
- **BG Remove** — clean white/transparent background

**Vectorize** — Export to fully editable formats
- **Editable PPTX**, **SVG**, and a **built-in canvas** (Konva raster + mask)

## Models

Pick any **image** model and any **chat/planner LLM** right in the UI — an inline **pill picker**
in the composer (home prompt box and the editor chat), grouped Local / Cloud. **There is no model
config in `.env`** — it only holds API keys, service URLs, and fallback defaults.
- **Cloud image** (OpenRouter): GPT Image 2, Nano Banana 2, SeeDream 4.5, FLUX.2 Max/Pro/Flex
- **Cloud LLM** (OpenRouter): GPT-OSS 20B/120B (free), Qwen3.7 Plus, Qwen3.6 Flash, Qwen3.6 35B-A3B
- **Local** (ComfyUI/Ollama): Qwen-Image 2512, Chroma, Z-Image, Pony, FLUX Fill/Kontext/Redux, Qwen-Edit, Qwen3.5 …

The selected model drives the whole pipeline: image generation, and the **chat/planner LLM follows
your pick too** — a local LLM streams from **Ollama**, a cloud LLM from **OpenRouter** (the same LLM
also powers **✨ Prompt Enhance** in the composer). Cloud image
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

Local models (optional, 24GB+ Apple Silicon): `scripts/10_install_comfyui.sh`,
`scripts/20_download_models.sh`, `scripts/30_run_comfyui.sh`, `scripts/31_run_ollama.sh`.

## Verify

```bash
cd backend && uv run pytest          # hermetic (mock provider; no keys needed)
cd frontend && pnpm typecheck && pnpm build
```
