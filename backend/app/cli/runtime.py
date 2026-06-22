"""In-process runtime for the CLI — no uvicorn, no Next.js.

`app_runtime()` replicates the FastAPI `lifespan` (minus the HTTP layer): it initializes the
SQLite DB, starts the same in-process `JobWorker` the web app uses, and tears both down on exit.
`run_genspec()` drives one generation job through that worker end-to-end, so the CLI exercises
the exact production path as the `/jobs` route — there is no parallel engine.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Union

from app import deps
from app.config import Settings, get_settings
from app.db import repo
from app.db.database import close_db, init_db
from app.cli.render import ProgressBar
from app.logging import setup_logging
from app.schemas.genspec import GenSpec
from app.services import image_ops, storage


class CliError(Exception):
    """A user-facing CLI failure (printed without a traceback)."""


@asynccontextmanager
async def app_runtime(*, verbose: bool = False) -> AsyncIterator[Settings]:
    """Boot the in-process backend (DB + job worker), yield Settings, tear down on exit.

    Mirrors `app.main.lifespan` but skips the ComfyUI node-validation probe (advisory, needs a
    live ComfyUI, and would slow every command) — `doctor` runs it on demand instead.
    """
    setup_logging()
    if not verbose:
        # Keep the console quiet (INFO logs go to AIStudio/logs/backend.log only); the CLI's own
        # output is the product. The file handler stays at INFO for debugging.
        for h in logging.getLogger().handlers:
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
                h.setLevel(logging.WARNING)
    s = get_settings()
    s.ensure_dirs()
    await init_db()
    deps.worker().start()
    try:
        yield s
    finally:
        await deps.shutdown()
        await close_db()


async def ensure_cli_project(title: str = "cli") -> str:
    """Reuse a project with this title (so CLI assets accumulate in one place), else create it."""
    for p in await repo.list_projects():
        if p["title"] == title:
            return p["id"]
    return (await repo.create_project(title))["id"]


async def stage_image_asset(project_id: str, src: Union[str, Path, bytes], kind: str) -> str:
    """Persist an input image as an asset (source/reference/mask), exactly like the /uploads route.

    Source/reference are fit-within + re-encoded to PNG; a mask is stored raw (binarized against
    the source at job-build time). Returns the new asset id for the GenSpec to reference.
    """
    raw = src if isinstance(src, (bytes, bytearray)) else Path(src).read_bytes()
    if kind == "mask":
        path, w, h = storage.save_image(project_id, bytes(raw), "mask")
    else:
        img = image_ops.fit_within(image_ops.load_rgb(bytes(raw)))
        path, w, h = storage.save_image(project_id, image_ops.to_png_bytes(img), kind)
    asset = await repo.create_asset(project_id, kind, path, w, h)
    return asset["id"]


async def run_genspec(spec: GenSpec, *, project_id: str, show_progress: bool = True,
                      label: str = "generate") -> dict:
    """Submit one GenSpec to the in-process worker and block until done; return the result asset.

    Raises CliError on a worker error event or a missing result. Note: the worker chains
    `remove_bg` itself when `spec.remove_bg` is set, but NOT upscale — callers chain that.
    """
    job = await repo.create_job(project_id, spec.mode.value, spec.model_dump(mode="json"))
    jid = job["id"]
    bar = ProgressBar(enabled=show_progress, label=label)
    await deps.worker().submit(jid)
    try:
        async for ev in deps.worker().events(jid):
            if ev.type == "progress":
                bar.update(ev.progress, ev.message or ev.node or "")
            elif ev.type == "error":
                raise CliError(ev.message or "job failed")
            elif ev.type == "done":
                bar.update(1.0, "done")
                break
    finally:
        bar.close()

    final = await repo.get_job(jid)
    if not final or not final.get("result_asset"):
        raise CliError("job finished without a result asset")
    asset = await repo.get_asset(final["result_asset"])
    if not asset:
        raise CliError("result asset row not found")
    return asset
