"""figurelabs 인-캔버스/refiner 이미지 연산 — image client edit 위에 구축.

각 연산은 AssetStore의 기존 asset을 입력으로 받아 편집 결과를 ``parent_id``로 버전 체인에
이어 저장하고 새 asset_id를 반환한다(비파괴·undo 가능). mask 인페인트는 region_redraw 전용.
"""

from __future__ import annotations

import io

from ..assets.store import AssetStore
from ..providers.base import ImageClient

_REFINE_PROMPT = {
    "upscale": "upscale to higher resolution and sharpen fine detail",
    "denoise": "remove noise, grain, and compression artifacts while keeping edges crisp",
    "color_correct": "correct color balance, white point, and contrast for print",
    "white_bg": "replace the background with a clean solid white background",
}


def build_region_mask(size: tuple[int, int], region: list[float] | None) -> bytes | None:
    """region([x,y,w,h] 0..1) 안을 투명(=재생성 영역), 밖을 불투명(=보존)으로 둔 마스크 PNG.

    region이 없으면 None(전체 편집).
    """
    if not region or len(region) != 4:
        return None
    from PIL import Image, ImageDraw

    w, h = size
    mask = Image.new("RGBA", (w, h), (0, 0, 0, 255))  # 불투명 = 보존
    x, y, rw, rh = region
    box = (int(x * w), int(y * h), int((x + rw) * w), int((y + rh) * h))
    ImageDraw.Draw(mask).rectangle(box, fill=(0, 0, 0, 0))  # 투명 = 편집
    buf = io.BytesIO()
    mask.save(buf, format="PNG")
    return buf.getvalue()


def _size_of(png: bytes) -> tuple[int, int]:
    from PIL import Image

    return Image.open(io.BytesIO(png)).size


async def region_redraw(
    client: ImageClient, store: AssetStore, asset_id: str, instruction: str,
    region: list[float] | None,
) -> str:
    src = store.get_png(asset_id)
    if src is None:
        return asset_id
    mask = build_region_mask(_size_of(src), region)
    prompt = instruction.strip() or "redraw this region cohesively, matching the surrounding style"
    res = await client.edit(src, prompt, mask=mask, background="opaque", input_fidelity="high")
    return store.put(res.data, "image/png", kind="illustration", parent_id=asset_id)


async def white_background(client: ImageClient, store: AssetStore, asset_id: str) -> str:
    src = store.get_png(asset_id)
    if src is None:
        return asset_id
    res = await client.edit(
        src, "replace the background with a clean solid white background, keep the subject unchanged",
        background="opaque", input_fidelity="high")
    return store.put(res.data, "image/png", kind="illustration", parent_id=asset_id)


async def refine_asset(
    client: ImageClient, store: AssetStore, asset_id: str, modes: list[str],
) -> str:
    src = store.get_png(asset_id)
    if src is None:
        return asset_id
    modes = modes or ["upscale"]
    detail = "; ".join(_REFINE_PROMPT.get(m, m) for m in modes)
    prompt = f"Improve this scientific figure for publication quality: {detail}. Preserve all content."
    res = await client.edit(src, prompt, background="opaque", input_fidelity="high")
    return store.put(res.data, "image/png", kind="illustration", parent_id=asset_id)
