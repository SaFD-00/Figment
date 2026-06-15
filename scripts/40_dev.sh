#!/usr/bin/env bash
# Dev launcher: backend (FastAPI :8000) + frontend (Next.js :3000). Assumes ComfyUI + Ollama already running.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cleanup() { echo; echo "Stopping dev servers..."; kill 0; }
trap cleanup EXIT INT TERM

( cd "$REPO/backend" && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port "${BACKEND_PORT:-8000}" ) &
( cd "$REPO/frontend" && pnpm dev ) &

wait
