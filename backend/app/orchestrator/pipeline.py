"""Standalone one-shot operations (upscale, white-bg) used by the toolbar — outside the
chat→GenSpec flow. Upscale runs a tiny ComfyUI graph and polls /history; white-bg is pure rembg."""
from __future__ import annotations

import asyncio

from app.comfy import builder as B
from app.comfy.client import ComfyUIClient, new_client_id
from app.services import rembg_service


async def upscale_image(comfy: ComfyUIClient, image_bytes: bytes) -> bytes:
    ref = await comfy.upload_image(image_bytes, f"up_{new_client_id()}.png")
    result = B.build_upscale(ref)
    client_id = new_client_id()
    prompt_id = await comfy.queue_prompt(result.graph, client_id)
    # poll /history until the prompt has outputs (upscale is a single fast node)
    for _ in range(120):  # up to ~60s
        hist = await comfy.history(prompt_id)
        entry = hist.get(prompt_id)
        if entry and entry.get("outputs"):
            outs = entry["outputs"]
            node_out = outs.get(result.save_node) or next((v for v in outs.values() if "images" in v), None)
            if node_out and node_out.get("images"):
                img = node_out["images"][0]
                return await comfy.view(img["filename"], img.get("subfolder", ""), img.get("type", "output"))
        await asyncio.sleep(0.5)
    raise RuntimeError("upscale timed out")


async def white_bg(image_bytes: bytes) -> bytes:
    return await asyncio.to_thread(rembg_service.remove_bg, image_bytes, True)


async def remove_bg(image_bytes: bytes) -> bytes:
    return await asyncio.to_thread(rembg_service.remove_bg, image_bytes, False)
