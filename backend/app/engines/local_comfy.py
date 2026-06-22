"""Local engine — runs a GenSpec as a ComfyUI diffusion graph on the H100.

Lifted almost verbatim from the old JobWorker local path: ensure ComfyUI is reachable,
let the memory orchestrator make room, upload inputs, build the graph, drive it over the
websocket, then fetch the rendered bytes. Progress/cancel come from the EngineContext so
the worker stays the single pub/sub owner.
"""
from __future__ import annotations

import io
from typing import Optional

from PIL import Image

from app.comfy import builder as B
from app.comfy.client import ServiceUnreachableError, new_client_id
from app.comfy.progress import is_prompt_done, parse_binary_preview, parse_text_message
from app.config import get_settings
from app.db import repo
from app.engines.base import EngineContext, EngineResult
from app.schemas.genspec import LOCAL_MAX_SIDE, Mode
from app.services import image_ops


class LocalComfyEngine:
    async def run(self, ctx: EngineContext) -> EngineResult:
        # ComfyUI is needed for both uploads and the ws run — probe once for a clear message.
        if not await ctx.comfy.ping():
            url = get_settings().comfy_url
            raise ServiceUnreachableError(
                f"ComfyUI not reachable at {url} — start it with scripts/30_run_comfyui.sh"
            )
        model = await ctx.orch.ensure_ready_for(ctx.model)

        build_ctx = await self._prepare_inputs(ctx, model)
        result = B.build(ctx.spec, build_ctx)
        out_bytes = await self._execute(ctx, result)

        if result.is_video:
            return EngineResult(is_video=True, video_bytes=out_bytes, video_ext="webp")
        return EngineResult(image_bytes=out_bytes)

    async def _prepare_inputs(self, ctx: EngineContext, model) -> B.BuildContext:
        spec = ctx.spec
        width = image_ops.round_to_multiple(spec.width, 16)
        height = image_ops.round_to_multiple(spec.height, 16)
        build_ctx = B.BuildContext(model=model, width=width, height=height)

        # Edit/reference uploads run on SDXL (img2img/inpaint) or a CLIP-Vision encoder; downscale
        # them to the working-size cap (SDXL is 1024-native). This path is always local.
        clamp_side = LOCAL_MAX_SIDE if spec.mode in (Mode.edit, Mode.reference) else None

        source_img: Optional[Image.Image] = None
        if spec.source_asset:
            a = await repo.get_asset(spec.source_asset)
            if a:
                data = open(a["path"], "rb").read()
                if clamp_side:
                    data = image_ops.downscale_to_png(data, clamp_side)
                build_ctx.comfy_source = await ctx.comfy.upload_image(data, f"src_{spec.source_asset}.png")
                source_img = Image.open(io.BytesIO(data))
                # keep source dims as the generation size for edits/inpaint
                build_ctx.width, build_ctx.height = source_img.size

        if spec.mask_asset:
            a = await repo.get_asset(spec.mask_asset)
            if a and source_img is not None:
                mdata = open(a["path"], "rb").read()
                mpng = image_ops.binarize_mask(mdata, source_img.size)
                build_ctx.comfy_mask = await ctx.comfy.upload_mask(mpng, f"mask_{spec.mask_asset}.png")

        for ref in spec.reference_images:
            a = await repo.get_asset(ref.asset)
            if a:
                data = open(a["path"], "rb").read()
                if clamp_side:
                    data = image_ops.downscale_to_png(data, clamp_side)
                build_ctx.comfy_refs.append(await ctx.comfy.upload_image(data, f"ref_{ref.asset}.png"))
        return build_ctx

    async def _execute(self, ctx: EngineContext, result: B.BuildResult) -> bytes:
        job_id = ctx.job_id
        client_id = new_client_id()
        prompt_id: Optional[str] = None
        async for msg in ctx.comfy.ws_messages(client_id):
            if ctx.is_canceled():
                await ctx.comfy.interrupt()
                raise RuntimeError("canceled")
            if msg == "__connected__":
                prompt_id = await ctx.comfy.queue_prompt(result.graph, client_id)
                continue
            if isinstance(msg, bytes):
                ev = parse_binary_preview(job_id, msg)
                if ev:
                    ctx.on_progress(ev)
                continue
            # JSON message
            ev = parse_text_message(job_id, msg)
            if ev:
                if ev.type == "error":
                    raise RuntimeError(ev.message or "execution error")
                await repo.update_job(job_id, progress=ev.progress)
                ctx.on_progress(ev)
            if prompt_id and is_prompt_done(msg, prompt_id):
                break

        if not prompt_id:
            raise RuntimeError("prompt was never queued")
        return await self._fetch_result(ctx, prompt_id, result)

    async def _fetch_result(self, ctx: EngineContext, prompt_id: str, result: B.BuildResult) -> bytes:
        hist = await ctx.comfy.history(prompt_id)
        entry = hist.get(prompt_id, {})
        outputs = entry.get("outputs", {})
        node_out = outputs.get(result.save_node) or next(
            (v for v in outputs.values() if "images" in v), None
        )
        if not node_out or not node_out.get("images"):
            raise RuntimeError("no image in ComfyUI history output")
        img = node_out["images"][0]
        return await ctx.comfy.view(img["filename"], img.get("subfolder", ""), img.get("type", "output"))
