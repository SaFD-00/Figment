# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) and other coding agents when working with code in this repository.

## What Figment is

Figment unifies two heritages into one product: the **FigGen** scientific-figure pipeline (cloud, structured → editable SVG/PPTX) and the **ImgGen** local image studio (ComfyUI/Ollama). Both run behind **one engine interface** (`engines/base.py`): cloud (OpenRouter) models now also produce plain **raster images** for the normal modes — interchangeable with local — while structured figures are an explicit opt-in (`Mode.figure`); local models run ComfyUI. It's a Next.js UI over a single FastAPI backend, with the model chosen **per generation mode in the UI** — not in config.

The local engine targets a **single NVIDIA H100 80GB (CUDA, GPU 0)**. The whole photoreal stack is sized to **co-reside at once** (~70GB under a 78GB budget); video (Wan 2.2) swaps in. The old Apple-Silicon/Metal constraints ("never fp8", "one big model at a time", GGUF-only) are gone — fp8/bf16 safetensors are first-class.

**Always consult the Obsidian vault for project context and decision history** — it holds the *why* behind changes that the repo alone doesn't record. The living project page is `~/Documents/Obsidian Vault/Projects/Figment.md` and dated update-log notes are under `~/Documents/Obsidian Vault/Projects/Figment/`. Read them before substantial work, and record significant updates back there (refresh the project page + add a dated detail note that links to it).

## Common commands

```bash
# Backend (FastAPI, Python 3.11+, uv)
cd backend && uv sync                                   # install (vendored figgen is an editable path dep)
uv run uvicorn app.main:app --reload --port 8000        # run API on :8000
uv run pytest                                           # hermetic test suite (mock provider; NO keys/GPU needed)
uv run pytest tests/test_builder.py                     # one file
uv run pytest tests/test_builder.py::test_video_wan_5b_ti2v   # one test
uv run ruff check .                                     # lint (ruff is a dev dep)

# Frontend (Next.js 15 / React 19, pnpm@9.15.4)
cd frontend && pnpm install
pnpm dev          # http://localhost:3000
pnpm typecheck    # tsc --noEmit
pnpm build
```

One backend test (`test_figure_engine.py::test_figure_pipeline_generates_editable_artifacts`) makes a **live OpenAI/OpenRouter call** and fails without a key — this is environmental, not a regression. Everything else is hermetic.

### CLI — the studio runs from the terminal too (no web app / server)

`scripts/figment` boots the backend **in-process** (`cli/runtime.py` replicates `main.py:lifespan`) and submits to the **same** `JobWorker`, registry, and DB as the web app — there is no parallel engine:

```bash
scripts/figment generate "a red fox in a snowy forest" --mode txt2img --out fox.png
scripts/figment generate "make it winter" --mode edit --source photo.png
scripts/figment enhance "창가의 고양이" --llm-model qwen3-vl-local   # short idea → rich English prompt
scripts/figment upscale fox.png        # also: removebg / whitebg (raw image files)
scripts/figment export <asset_id> --fmt pptx
scripts/figment chat "데이터센터 다이어그램 만들어줘"               # streams reply + GENSPEC
scripts/figment models | doctor        # catalog readiness ✓/✗ | service health
scripts/figment verify [--local-only|--cloud-only|--offline|--mode edit|--json]
```

`figment verify` **actually runs** every pipeline (local ComfyUI per model/mode, cloud raster images + the figure SVG/PPTX pipeline, Ollama + cloud chat/enhance, post-ops) and prints a PASS/SKIP/FAIL matrix; a missing weight / stopped service / absent key is a clean **SKIP with a reason**, never a false FAIL (exit code = number of FAILs). This is the real integration test — unit `pytest` is mock-only. Changes to the job/build/post-op path must keep **both** the HTTP and CLI entry points working (and `verify.py` exercising them).

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
`backend/app/models_catalog/registry.py` is the **single source of truth**. `MODELS` (image/video) and `LLM_MODELS` (chat/planner — **vision-capable only**, `vision=True`) each carry an `engine` field: `local-comfy`, `local-ollama`, or `cloud-openrouter`. A request's `GenSpec.model` / `llm_model` (set by the UI) resolves through `registry.resolve()` / `resolve_llm()`; `DEFAULT_BY_MODE` fills in when null. **Removing or renaming a model id ripples** to `DEFAULT_BY_MODE`, `llm/prompts.py` heuristics, frontend per-mode picks, and tests — grep before deleting.

### Job path vs chat path (two independent flows)
- **Generation jobs** run through the orchestrator queue (`backend/app/orchestrator/queue.py`, `JobWorker._run`) — a **single heavy in-process async worker**. It resolves the model, picks a **`GenerationEngine`** (`engines/base.py`) via `_select_engine`, runs it, then persists once in `_persist` (remove-bg for images → save → asset → `done` event) — so all three engines share post-processing:
  - **local** (`engines/local_comfy.py`): `orch.ensure_ready_for(model)`, upload inputs, `comfy/builder.build(spec, ctx)`, execute over ComfyUI `/prompt` + `/ws` (video → animated webp).
  - **cloud raster** (`engines/cloud_image.py`): OpenRouter image API → a plain raster PNG for the normal modes (txt2img/img2img/edit/inpaint/reference) — interchangeable with local. Mask inpaint / multi-ref degrade with a warning (the modalities path supports neither).
  - **cloud figure** (`engines/figure.py`, only for `Mode.figure`): the vendored FigGen orchestrator on OpenRouter → structured **FigureSpec → editable SVG/PPTX** + preview PNG (the scientific-figure lineage).
- **Chat & prompt-enhance** are separate from the queue. `llm/routing.py:resolve_chat` powers **both** `routers/chat.py` and `routers/prompt.py` (`POST /prompt/enhance`): a cloud LLM (with a configured key) streams from **OpenRouter**, a local LLM from its **Ollama** tag, otherwise the default Ollama model — independently of the image model. The lineup is **vision-capable only** (local `qwen3-vl-local` + the cloud multimodal LLMs, all `vision=True`), so enhance can always ground the rewrite in an uploaded edit/reference image on either route. `llm/handoff.py` extracts a `GenSpec` from the conversation.

### ComfyUI graph builder
`backend/app/comfy/builder.py` builds graphs **programmatically** (the `_G` helper; links are `[node_id, output_index]` pairs), one builder per template keyed off `ModelDef.template`. `comfy/templates.py` validates that the custom-node `class_type`s each builder needs are present by querying ComfyUI `/object_info` at startup (fail-fast). Wan 2.2 uses ComfyUI **native core** video nodes (no WanVideoWrapper). The local video model is **Wan 2.2 TI2V-5B**: a single dense sampler whose `Wan22ImageToVideoLatent` takes an optional `start_image`, so one graph covers both text→video and image→video. See `test_builder.py` for the canonical assertions.

### Config & runtime home
`backend/app/config.py` (`Settings`, pydantic-settings, reads repo-root `.env`) holds local + service settings; cloud/OpenRouter settings live in the vendored `figure_engine/src/figgen/config.py`, bound to the same `.env` via `engines/cloud.py`. Everything runtime — weights, ComfyUI, `db.sqlite`, outputs, logs — lives under a **single `AISTUDIO_HOME`** (default `<repo>/AIStudio`). Note the env var is `COMFY_URL` (not `COMFYUI_URL`).

### Frontend wiring
`frontend/lib/api.ts` / `sse.ts` hit a hardcoded `/api` base; `frontend/next.config.ts` rewrites `/api/*` → `http://127.0.0.1:8000/*` (backend host is hardcoded, no `NEXT_PUBLIC_API_URL`). The model picker is **backend-sourced** (`GET /api/models/all` → `lib/models.ts` store), grouped Local/Cloud by `engine`; nothing is hardcoded in the picker. Image/video models are remembered **per mode** (store `selectedByMode` over all `GEN_MODES` incl. `video` and `figure`; `getImageModelForMode(mode)`), so each generation mode keeps its own pick — composer (home prompt box), editor chat, and reference panel all use the inline `ModelPill`. The canvas is **react-konva**, dynamically imported `ssr:false` (Konva touches `window`); `next.config.ts` aliases the `canvas` module to `false`. Region-redraw and text-edit resolve their model through the per-mode pick (defaulting via `DEFAULT_BY_MODE` to `flux-fill` for inpaint and `qwen-edit-aio` for edit).

## Conventions & constraints

- **Storage rule (`~/AGENTS.md`):** large/regenerable artifacts go on the big `/data` volume, never the small root volume. `<repo>/AIStudio` is a **symlink → `/data/<user>/Figment/AIStudio`** (created by `00_bootstrap_dirs.sh`) and is git-ignored. Don't write multi-GB outputs under the repo root.
- **Model selection lives in the UI, never in `.env`.** `.env` holds only API keys, service URLs, and fallback defaults (the `OLLAMA_LLM` used when nothing is selected, plus FigGen sub-role fallbacks). The picker sends a model id; do not hard-code model ids in routers or the builder — resolve through `registry.py`. With no `OPENROUTER_API_KEY`, the cloud engine falls back to a safe `mock` provider (offline-safe) and cloud options disable in the picker.
- **GPU pinning:** local ComfyUI runs on GPU 0 (`CUDA_VISIBLE_DEVICES=0`, `--highvram`) so the multi-model stack co-resides on one H100.
- **Reference-image caps:** up to `MAX_REFERENCE_IMAGES = 6` references per request (mirrored in `frontend/lib/constants.ts`). The multi-ref builder (Redux style) consumes all of them; ControlNet uses the first. Subject/face consistency is done through `edit` with a reference image (qwen-edit-aio). Heavy local edit/reference inputs are downscaled to `LOCAL_MAX_SIDE` (1024px longest side) before reaching ComfyUI.
- **Asset rows can outlive their files.** Every file-touching endpoint in `routers/assets.py` guards with `_require_file` → a clean **404** instead of a 500; the frontend hides broken thumbnails (`lib/img.ts:hideBrokenImage`). Preserve this when adding asset endpoints.
- **Graceful degradation is a feature.** A cold-loading local LLM's first enhance can exceed the dev proxy window (`ECONNRESET`); clients use bounded httpx timeouts and the frontend retries enhance once. Don't add eager boot-time model warmup (the pick might be a cloud API).
- **Content scope:** legal adult consensual NSFW only. Face/subject work (via `edit` with a reference image) is **consent-gated** ("consenting adults / synthetic faces only"). Exclude anything enabling CSAM or non-consensual deepfakes of real, identifiable people.
- `Mode` enum (`schemas/genspec.py`): `txt2img, img2img, inpaint, edit, controlnet, reference, video, figure` (`figure` is cloud-only — structured SVG/PPTX).

## Docs
`docs/ARCHITECTURE.md` (system/engine dispatch), `docs/MODELS.md` (local model table), `docs/WORKFLOWS.md` (builder/memory rules). `README.md` for the user-facing overview and quickstart.
