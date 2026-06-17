"""Sample test data for `figment verify` — deterministic photos fetched from the internet,
plus a locally-generated inpaint mask (no extra download).

Photos come from picsum.photos by fixed seed, so every run uses the same images, and they're
cached under AISTUDIO_HOME/testdata (re-encoded to PNG). Once cached, verify runs fully offline.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import httpx

from app.config import get_settings
from app.services import image_ops

# Stable seeds → reproducible sample photos.
SEED_SOURCE = "figment-a"
SEED_REF1 = "figment-b"
SEED_REF2 = "figment-c"


def _cache_dir() -> Path:
    d = get_settings().aistudio_home / "testdata"
    d.mkdir(parents=True, exist_ok=True)
    return d


async def fetch_sample(seed: str, w: int = 768, h: int = 768, *, offline: bool = False) -> Optional[Path]:
    """Return a cached PNG sample for `seed`, fetching from picsum.photos if absent.

    Returns None when offline (or after retries fail) so net-gated verify cases can SKIP cleanly.
    """
    dest = _cache_dir() / f"{seed}_{w}x{h}.png"
    if dest.exists():
        return dest
    if offline:
        return None
    url = f"https://picsum.photos/seed/{seed}/{w}/{h}"
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=30.0)) as client:
                r = await client.get(url, follow_redirects=True)
                r.raise_for_status()
                png = image_ops.to_png_bytes(image_ops.load_rgb(r.content))
                dest.write_bytes(png)
                return dest
        except Exception:  # noqa: BLE001 — transient network errors → retry, then SKIP
            if attempt < 2:
                await asyncio.sleep(1.5 * (attempt + 1))
    return None


def make_mask(size: tuple[int, int]) -> bytes:
    """A simple inpaint mask: a white filled ellipse (regen region) on black, at `size`.

    The job pipeline re-binarizes this against the source (white=regen, black=keep), so an
    approximate shape is enough to exercise the inpaint path.
    """
    from PIL import Image, ImageDraw

    w, h = size
    img = Image.new("RGB", (w, h), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([w * 0.3, h * 0.3, w * 0.7, h * 0.7], fill=(255, 255, 255))
    return image_ops.to_png_bytes(img)
