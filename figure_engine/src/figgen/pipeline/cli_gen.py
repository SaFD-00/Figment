"""`figgen gen "설명"` 핸들러 — planner → stylist → 렌더 (Phase 2, mock 구동 가능).

에셋 생성·critic은 Phase 3+ Orchestrator 범위 — 여기선 이미지가 placeholder로 렌더된다.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from ..assets.store import AssetStore
from ..config import get_settings
from ..layout.engine import LayoutEngine
from ..providers.registry import get_llm
from ..render.exporter import export_figure
from ..render.resolver import resolve
from ..schema.requests import GenerationRequest
from .planner import Planner
from .stylist import Stylist


async def _plan(planner: Planner, stylist: Stylist, req: GenerationRequest,
                asset_store: AssetStore, settings, provider: str | None):
    figure_type = await planner.classify(req)
    from .routing import is_image_first

    if is_image_first(figure_type):
        from .scene import generate_scene_spec

        spec = await generate_scene_spec(
            planner, req, asset_store, settings, provider, figure_type=figure_type)
        spec = stylist.apply(spec, req.style_preset)
        return figure_type, spec
    spec = await planner.plan(req, figure_type)
    spec = stylist.apply(spec, req.style_preset)
    if settings.diagram_box_icons and figure_type == "method_diagram":
        from .diagram_icons import generate_box_icons

        spec = await generate_box_icons(spec, req, asset_store, settings, provider)
    return figure_type, spec


def generate_cli(
    *,
    description: str,
    figure_type: str | None,
    style: str,
    provider: str | None,
    out: Path,
    box_icons: bool = False,
    dpi: int = 192,
    fmt: str = "png",
) -> int:
    settings = get_settings()
    if box_icons:
        settings.diagram_box_icons = True
    planner = Planner(
        get_llm("planner", settings, provider_override=provider),
        get_llm("classifier", settings, provider_override=provider),
    )
    stylist = Stylist()
    req = GenerationRequest(
        description=description,
        figure_type=figure_type,  # type: ignore[arg-type]
        style_preset=style,
        provider=provider or "auto",  # type: ignore[arg-type]
    )

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    asset_store = AssetStore(out / "assets")

    print(f"· provider(planner) = {planner.llm.name}")
    detected, spec = asyncio.run(_plan(planner, stylist, req, asset_store, settings, provider))
    print(f"· figure_type = {detected}  (요소 {len(spec.element_ids())}개)")

    layout = LayoutEngine().layout(spec)
    fig = resolve(spec, layout, spec.stylesheet)
    bundle = export_figure(fig, asset_store, preview_dpi=dpi)

    (out / "spec.json").write_text(
        json.dumps(spec.model_dump(mode="json", exclude_none=True), ensure_ascii=False, indent=2),
        encoding="utf-8")
    (out / "figure.svg").write_text(bundle.svg, encoding="utf-8")
    (out / "preview.svg").write_text(bundle.preview_svg, encoding="utf-8")
    (out / "figure.pptx").write_bytes(bundle.pptx)
    (out / "preview.png").write_bytes(bundle.preview_png)
    if fmt == "jpg":
        from ..render.preview import png_to_jpg

        (out / "figure.jpg").write_bytes(png_to_jpg(bundle.preview_png))

    print(f"✓ 생성 완료 → {out}")
    print(f"  캔버스 {fig.width_mm:.0f}×{fig.height_mm:.0f}mm, 요소 {len(fig.elements)}개")
    if layout.warnings:
        major = [w for w in layout.warnings if w.severity in ("critical", "major")]
        print(f"  ⚠ 경고 {len(layout.warnings)}건(주요 {len(major)}건): "
              + ", ".join(f"{w.kind}({','.join(w.element_ids)})" for w in layout.warnings[:5]))
        for w in major[:5]:
            print(f"    ! {w.severity} {w.kind}: {w.detail}")
    print("  파일: spec.json, figure.svg, preview.svg, figure.pptx, preview.png")
    return 0
