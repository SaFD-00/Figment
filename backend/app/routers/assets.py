"""Assets: fetch metadata, serve the file, one-shot toolbar ops (upscale, white-bg),
and export to editable formats (SVG / PPTX) — the Vectorize surface."""
from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from app import deps
from app.db import repo
from app.orchestrator import pipeline
from app.services import export_ops, storage

router = APIRouter(prefix="/assets", tags=["assets"])


def _require_file(a: dict) -> None:
    """404 (not 500) when the DB row survives but its file was removed from disk.

    Asset rows outlive their files (manual cleanup, a deleted project's leftover output dir,
    a moved AISTUDIO_HOME). Without this guard FileResponse/open() raises FileNotFoundError,
    which surfaces as a 500 — a stale thumbnail should degrade to a clean 404 instead.
    """
    if not os.path.exists(a["path"]):
        raise HTTPException(404, "asset file missing on disk")


@router.get("/{aid}")
async def get_asset(aid: str) -> dict:
    a = await repo.get_asset(aid)
    if not a:
        raise HTTPException(404, "not found")
    return a


@router.get("/{aid}/file")
async def get_file(aid: str):
    a = await repo.get_asset(aid)
    if not a:
        raise HTTPException(404, "not found")
    _require_file(a)
    return FileResponse(a["path"], media_type="image/png")


@router.post("/{aid}/upscale")
async def upscale(aid: str) -> dict:
    a = await repo.get_asset(aid)
    if not a:
        raise HTTPException(404, "not found")
    _require_file(a)
    data = open(a["path"], "rb").read()
    out = await pipeline.upscale_image(deps.comfy(), data)
    path, w, h = storage.save_image(a["project_id"], out, "upscaled")
    new = await repo.create_asset(a["project_id"], "upscaled", path, w, h, parent_id=aid)
    return new


@router.post("/{aid}/whitebg")
async def whitebg(aid: str) -> dict:
    a = await repo.get_asset(aid)
    if not a:
        raise HTTPException(404, "not found")
    _require_file(a)
    data = open(a["path"], "rb").read()
    out = await pipeline.white_bg(data)
    path, w, h = storage.save_image(a["project_id"], out, "nobg")
    new = await repo.create_asset(a["project_id"], "nobg", path, w, h, parent_id=aid)
    return new


@router.post("/{aid}/removebg")
async def removebg(aid: str) -> dict:
    a = await repo.get_asset(aid)
    if not a:
        raise HTTPException(404, "not found")
    _require_file(a)
    data = open(a["path"], "rb").read()
    out = await pipeline.remove_bg(data)
    path, w, h = storage.save_image(a["project_id"], out, "nobg")
    new = await repo.create_asset(a["project_id"], "nobg", path, w, h, parent_id=aid)
    return new


@router.get("/{aid}/export")
async def export(aid: str, fmt: str = "png"):
    """Download an asset as png | svg | pptx.

    Figure-engine assets serve their pre-rendered editable figure.svg / figure.pptx (from
    asset.meta). Plain raster assets are vectorized on the fly (vtracer → SVG; embed → PPTX).
    """
    a = await repo.get_asset(aid)
    if not a:
        raise HTTPException(404, "not found")
    meta = a.get("meta") or {}
    fmt = fmt.lower()

    if fmt == "png":
        _require_file(a)
        return FileResponse(a["path"], media_type="image/png",
                            filename=f"figment_{aid}.png")

    if fmt == "svg":
        sidecar = meta.get("svg")
        if sidecar and os.path.exists(sidecar):
            return FileResponse(sidecar, media_type=export_ops.SVG_MEDIA,
                                filename=f"figment_{aid}.svg")
        _require_file(a)
        png = open(a["path"], "rb").read()
        svg = await asyncio.to_thread(export_ops.png_to_svg, png)
        return Response(content=svg, media_type=export_ops.SVG_MEDIA,
                        headers={"Content-Disposition": f'attachment; filename="figment_{aid}.svg"'})

    if fmt == "pptx":
        sidecar = meta.get("pptx")
        if sidecar and os.path.exists(sidecar):
            return FileResponse(sidecar, media_type=export_ops.PPTX_MEDIA,
                                filename=f"figment_{aid}.pptx")
        _require_file(a)
        png = open(a["path"], "rb").read()
        pptx = await asyncio.to_thread(export_ops.png_to_pptx, png)
        return Response(content=pptx, media_type=export_ops.PPTX_MEDIA,
                        headers={"Content-Disposition": f'attachment; filename="figment_{aid}.pptx"'})

    raise HTTPException(400, f"unsupported format: {fmt}")


@router.get("/{aid}/formats")
async def formats(aid: str) -> dict:
    """Which export formats are available for this asset (drives the Export dropdown)."""
    a = await repo.get_asset(aid)
    if not a:
        raise HTTPException(404, "not found")
    meta = a.get("meta") or {}
    return {
        "png": True,
        "svg": True,  # always (figure sidecar or on-the-fly vectorize)
        "pptx": True,
        "is_figure": bool(meta.get("figure")),
    }
