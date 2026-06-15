"""Upload source / reference / mask images. Stores them as assets so a GenSpec can reference them."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.db import repo
from app.services import image_ops, storage

router = APIRouter(prefix="/uploads", tags=["uploads"])

VALID_KINDS = {"source", "reference", "mask"}


@router.post("")
async def upload(project_id: str = Form(...), kind: str = Form("source"),
                 file: UploadFile = File(...)) -> dict:
    if kind not in VALID_KINDS:
        raise HTTPException(400, f"kind must be one of {VALID_KINDS}")
    if not await repo.get_project(project_id):
        raise HTTPException(404, "project not found")
    raw = await file.read()

    if kind == "mask":
        # store as-is (binarized later against the source at job build time)
        path, w, h = storage.save_image(project_id, raw, "mask")
    else:
        img = image_ops.fit_within(image_ops.load_rgb(raw))
        path, w, h = storage.save_image(project_id, image_ops.to_png_bytes(img), kind)
    asset = await repo.create_asset(project_id, kind, path, w, h)
    return asset
