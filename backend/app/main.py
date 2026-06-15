"""FastAPI app factory."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import deps
from app.comfy.templates import validate_required_nodes
from app.config import get_settings
from app.db.database import close_db, init_db
from app.logging import setup_logging
from app.routers import assets, chat, jobs, models, projects, uploads

log = logging.getLogger("imggen")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    s = get_settings()
    s.ensure_dirs()
    await init_db()
    deps.worker().start()

    # Probe ComfyUI (non-fatal if down — user may start it after the backend).
    try:
        if await deps.comfy().ping():
            report = await validate_required_nodes(deps.comfy())
            if not report.get("ok"):
                log.warning("ComfyUI core nodes missing: %s", report.get("missing"))
            if report.get("missing_optional"):
                log.info("Optional ComfyUI nodes not installed: %s", report["missing_optional"])
        else:
            log.warning("ComfyUI not reachable at %s — start it with scripts/30_run_comfyui.sh", s.comfy_url)
    except Exception as e:  # noqa: BLE001
        log.warning("ComfyUI probe failed: %s", e)

    ver = await deps.ollama().version()
    log.info("Ollama version: %s", ver or "unreachable")
    yield
    await deps.shutdown()
    await close_db()


def create_app() -> FastAPI:
    app = FastAPI(title="Figment", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["*"], allow_headers=["*"],
    )
    app.include_router(chat.router)
    app.include_router(jobs.router)
    app.include_router(projects.router)
    app.include_router(assets.router)
    app.include_router(uploads.router)
    app.include_router(models.router)

    @app.get("/health")
    async def health() -> dict:
        return {
            "ok": True,
            "comfy": await deps.comfy().ping(),
            "ollama": await deps.ollama().version() is not None,
        }

    return app


app = create_app()
