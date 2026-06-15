# Figment

**Figures & images, made effortless.** Figment unifies the FigGen scientific-figure pipeline
and the ImgGen local image studio into one product — a clean Next.js UI over a single FastAPI
backend that can drive **cloud models** (OpenRouter / OpenAI) and **local models**
(ComfyUI / Ollama), selectable per generation.

## Features

**Generate** — Turn ideas into figures instantly
- **Text-to-Figure** — schematics from text or PDFs
- **Image-to-Figure** — sketches or photos into illustrations
- **Reference-to-Figure** — match the style/layout of a reference

**Edit** — Refine without starting over
- **Text Edit** — fix labels/legends on the image
- **Region Redraw** — redraw only selected parts (mask inpaint)
- **BG Remove** — clean white/transparent background

**Vectorize** — Export to fully editable formats
- **Editable PPTX**, **SVG**, and a **built-in canvas** (Konva raster + mask)

## Models

Pick any **image** model and any **chat/planner LLM** from a unified picker:
- **Cloud** (OpenRouter/OpenAI): SeeDream 4.5, GPT-Image 1.5, MiniMax M3, Claude, GPT-5.x …
- **Local** (ComfyUI/Ollama): Chroma, Z-Image, Pony, FLUX Fill/Kontext/Redux, Qwen-Edit, Qwen3.5 …

Cloud models route through the **figure pipeline** (structured FigureSpec → editable SVG/PPTX);
local models route through **ComfyUI**. With no API key configured, the cloud path falls back to
a mock provider so the app runs fully offline.

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
