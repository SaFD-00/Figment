"""Cloud raster-image engine — generates plain raster images via OpenRouter, so a cloud model
is interchangeable with the local ComfyUI backend for the normal image modes (txt2img/img2img/
edit/inpaint/reference). The structured figure (SVG/PPTX) pipeline lives in FigureEngine and is
reached only through Mode.figure.

Mask inpaint and multi-reference are not supported by the OpenRouter `/chat/completions`
modalities path — masks are ignored (whole-image edit) and only the first reference is used.
Both degrade with a logged warning rather than failing.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
from typing import Optional

from app.comfy.client import ServiceUnreachableError
from app.db import repo
from app.engines.base import EngineContext, EngineResult
from app.engines.cloud import cloud_key_present, figure_settings
from app.schemas.genspec import Mode

from figgen.providers.openrouter_client import OpenRouterImageClient

log = logging.getLogger("imggen.cloud")


def _mock_png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 200, 200)).save(buf, format="PNG")
    return buf.getvalue()


class CloudImageEngine:
    async def run(self, ctx: EngineContext) -> EngineResult:
        model, spec = ctx.model, ctx.spec
        provider = model.provider or "openrouter"

        if not cloud_key_present(provider):
            if os.getenv("FIGMENT_CLOUD_MOCK"):
                log.warning("FIGMENT_CLOUD_MOCK set — returning a placeholder image (no API key)")
                return EngineResult(image_bytes=_mock_png(),
                                    extra_meta={"engine": model.engine, "cloud_image": True, "mock": True})
            raise ServiceUnreachableError(
                f"{provider} API key not configured — set OPENROUTER_API_KEY to use cloud models"
            )

        settings = figure_settings()
        client = OpenRouterImageClient(
            settings.openrouter_api_key.get_secret_value(),
            model.cloud_model_id or settings.image_model,
            base_url=settings.openrouter_base_url,
        )

        image = await self._input_image(spec)

        if spec.mode == Mode.inpaint and spec.mask_asset:
            log.warning("cloud %s: mask inpaint unsupported on this path — whole-image edit", model.id)
        if len(spec.reference_images) > 1:
            log.warning("cloud %s: multiple references unsupported — using the first only", model.id)

        if image is None or spec.mode == Mode.txt2img:
            result = await client.generate(spec.prompt, width_px=spec.width, height_px=spec.height)
        else:
            # img2img exposes the denoise dial as the input-fidelity strength; edit/reference keep
            # the conservative default.
            strength = spec.denoise if spec.mode == Mode.img2img else None
            result = await client.edit(image, spec.prompt, strength=strength)

        return EngineResult(image_bytes=result.data,
                            extra_meta={"engine": model.engine, "cloud_image": True})

    async def _input_image(self, spec) -> Optional[bytes]:
        """Source image (or the first reference) as bytes, for the edit/img2img path."""
        asset_id = spec.source_asset or (spec.reference_images[0].asset if spec.reference_images else None)
        if not asset_id:
            return None
        a = await repo.get_asset(asset_id)
        if not a:
            return None
        return await asyncio.to_thread(lambda: open(a["path"], "rb").read())
