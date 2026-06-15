"""`figgen render <spec.json>` 핸들러 — API 불필요한 결정론 렌더 경로."""

from __future__ import annotations

import json
from pathlib import Path

from ..layout.engine import LayoutEngine
from ..schema.figure_spec import FigureSpec
from ..styles.presets import get_preset
from .exporter import export_figure
from .resolver import resolve


def render_spec_file(
    spec_path: Path,
    out_dir: Path,
    *,
    style: str | None = None,
    want_pptx: bool = True,
    want_png: bool = True,
    dpi: int = 192,
    fmt: str = "png",
) -> int:
    spec_path = Path(spec_path)
    if not spec_path.exists():
        print(f"오류: spec 파일 없음 — {spec_path}")
        return 1
    spec = FigureSpec.model_validate_json(spec_path.read_text(encoding="utf-8"))
    if style:
        spec = spec.model_copy(update={"stylesheet": get_preset(style)})

    layout = LayoutEngine().layout(spec)
    fig = resolve(spec, layout, spec.stylesheet)
    bundle = export_figure(fig, preview_dpi=dpi)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "spec.json").write_text(
        json.dumps(spec.model_dump(mode="json", exclude_none=True), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "figure.svg").write_text(bundle.svg, encoding="utf-8")
    (out_dir / "preview.svg").write_text(bundle.preview_svg, encoding="utf-8")
    if want_pptx:
        (out_dir / "figure.pptx").write_bytes(bundle.pptx)
    if want_png:
        (out_dir / "preview.png").write_bytes(bundle.preview_png)
        if fmt == "jpg":
            from .preview import png_to_jpg

            (out_dir / "figure.jpg").write_bytes(png_to_jpg(bundle.preview_png))

    print(f"✓ 렌더 완료 → {out_dir}")
    print(f"  요소 {len(fig.elements)}개, 캔버스 {fig.width_mm:.0f}×{fig.height_mm:.0f}mm")
    if layout.warnings:
        print(f"  ⚠ 경고 {len(layout.warnings)}건:")
        for w in layout.warnings[:8]:
            print(f"    - [{w.severity}] {w.kind}: {','.join(w.element_ids)} {w.detail}")
    files = ["spec.json", "figure.svg", "preview.svg"]
    if want_pptx:
        files.append("figure.pptx")
    if want_png:
        files.append("preview.png")
    print("  파일:", ", ".join(files))
    return 0
