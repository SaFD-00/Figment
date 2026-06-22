"""Filesystem storage for assets under ~/AIStudio/outputs/{project}/. Writes a JSON sidecar
with the GenSpec for reproducibility."""
from __future__ import annotations

import io
import json
import uuid
from pathlib import Path

from PIL import Image

from app.config import get_settings


def _project_dir(project_id: str) -> Path:
    d = get_settings().outputs_dir / project_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_image(project_id: str, data: bytes, kind: str, genspec: dict | None = None) -> tuple[str, int, int]:
    """Write PNG + optional sidecar. Returns (abs_path, width, height)."""
    name = f"{kind}_{uuid.uuid4().hex[:10]}.png"
    path = _project_dir(project_id) / name
    path.write_bytes(data)
    if genspec is not None:
        path.with_suffix(".json").write_text(json.dumps(genspec, ensure_ascii=False, indent=2))
    with Image.open(io.BytesIO(data)) as im:
        w, h = im.size
    return str(path), w, h


def save_video(project_id: str, data: bytes, kind: str, ext: str = "webp",
               genspec: dict | None = None) -> tuple[str, int, int]:
    """Write an animated video (webp/mp4) + optional sidecar. Returns (abs_path, width, height).

    Dims are best-effort (first frame via PIL); falls back to (0, 0) for containers PIL can't open.
    """
    name = f"{kind}_{uuid.uuid4().hex[:10]}.{ext.lstrip('.')}"
    path = _project_dir(project_id) / name
    path.write_bytes(data)
    if genspec is not None:
        path.with_suffix(".json").write_text(json.dumps(genspec, ensure_ascii=False, indent=2))
    w, h = 0, 0
    try:
        with Image.open(io.BytesIO(data)) as im:
            w, h = im.size
    except Exception:  # mp4 / unsupported container — dims unknown, not fatal
        pass
    return str(path), w, h


def save_named(project_id: str, src_path: str, ext: str) -> str:
    """Copy a sidecar artifact (e.g. figure.svg / figure.pptx) into the project dir.

    Returns the new absolute path. Skips silently (returns "") if the source is missing.
    """
    src = Path(src_path)
    if not src.exists():
        return ""
    dest = _project_dir(project_id) / f"figure_{uuid.uuid4().hex[:10]}.{ext.lstrip('.')}"
    dest.write_bytes(src.read_bytes())
    return str(dest)
