"""Sketch-to-Figure — 손그림/화이트보드 스케치 → 정제된 과학 일러스트.

흐름: 업로드 스케치를 gpt-image edit로 '깨끗한 글자 없는 장면'으로 정제(레이아웃 보존) →
plan_scene으로 편집 가능 라벨 제안 → build_overlay_spec(Free 루트 + 벡터화)로 표준 파이프라인
꼬리(STYLING→RENDERING→CRITIC)에 합류. scene.py(텍스트→장면)의 이미지-시드 변형.
"""

from __future__ import annotations

from pathlib import Path

from ..assets.prompts import build_scene_prompt
from ..assets.store import AssetStore
from ..config import Settings
from ..fullimage.composer import build_overlay_spec, canvas_mm_for_image
from ..providers.registry import get_image_client
from ..schema.figure_spec import FigureSpec
from ..schema.requests import GenerationRequest
from .planner import Planner, RefStyleReport


async def sketch_to_spec(
    planner: Planner,
    req: GenerationRequest,
    asset_store: AssetStore,
    settings: Settings,
    provider: str | None,
    *,
    research_ctx: str = "",
    style_ref: RefStyleReport | None = None,
) -> FigureSpec:
    sketch_path = req.reference_image_path
    if not sketch_path or not Path(sketch_path).exists():
        # 스케치 없음 → 텍스트 장면 생성으로 폴백
        from .scene import generate_scene_spec

        return await generate_scene_spec(
            planner, req, asset_store, settings, provider,
            research_ctx=research_ctx, style_ref=style_ref)

    sketch = Path(sketch_path).read_bytes()
    client = get_image_client(settings, transparent=False, provider_override=provider)
    intent = req.description or "a clean, publication-quality scientific diagram based on this sketch"
    palette = style_ref.palette_hex if style_ref else None
    scene_prompt = build_scene_prompt(intent, req.style_preset, palette=palette)
    cleaned = await client.edit(
        sketch,
        f"{scene_prompt}. Redraw the user's sketch as this clean illustration, preserving its "
        "layout and structure. Absolutely no text, no labels, no letters, no numbers.",
        background="opaque", input_fidelity="high")
    base_id = asset_store.put(cleaned.data, "image/png", kind="illustration")

    brief = await planner.plan_scene(req, research_ctx=research_ctx, style_ref=style_ref)

    svg_id: str | None = None
    if getattr(settings, "scene_vectorize", True):
        try:
            from ..fullimage.vectorize import vectorize_png

            svg_id = asset_store.put(vectorize_png(cleaned.data), "image/svg+xml",
                                     kind="illustration_svg")
        except Exception:  # noqa: BLE001
            svg_id = None

    return build_overlay_spec(
        base_id, brief.labels, canvas_mm=canvas_mm_for_image(cleaned.data), title=brief.title,
        figure_type="scientific_illustration", base_svg_asset_id=svg_id)
