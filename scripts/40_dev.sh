#!/usr/bin/env bash
# Dev launcher: backend (FastAPI) + frontend (Next.js :3000). Assumes ComfyUI + Ollama already running.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Ensure pnpm is on PATH (installed by corepack/standalone at ~/.local/share/pnpm/bin).
export PATH="$HOME/.local/share/pnpm/bin:$PATH"

# Pin to GPU 0 only.
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

# Load backend/.env so BACKEND_PORT (and other settings) are available to both processes.
if [[ -f "$REPO/backend/.env" ]]; then
  set -o allexport
  # shellcheck source=/dev/null
  source "$REPO/backend/.env"
  set +o allexport
fi

cleanup() {
  trap - EXIT INT TERM
  echo
  echo "Stopping dev servers..."
  kill 0
}
trap cleanup EXIT INT TERM

( cd "$REPO/backend" && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port "${BACKEND_PORT:-8000}" ) &
( cd "$REPO/frontend" && BACKEND_PORT="${BACKEND_PORT:-8000}" pnpm dev ) &

wait
