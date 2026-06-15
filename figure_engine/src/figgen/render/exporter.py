"""최종 산출물 패키징 단일 진입점.

웹 앱 다운로드 핸들러와 Critic 루프가 공유한다.
- figure.svg: 에셋 base64 임베드 (Illustrator 단일 파일)
- preview.svg: 에셋 href 참조 (브라우저 미리보기 — 빠른 로드)
- figure.pptx / preview.png
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from .pptx_renderer import PptxRenderer
from .preview import svg_to_png
from .resolved import ResolvedFigure
from .svg_renderer import SvgRenderer


class ExportBundle(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    pptx: bytes
    svg: str  # 임베드판 (다운로드)
    preview_svg: str  # href판 (미리보기)
    preview_png: bytes
    chart_svgs: dict[str, str] = {}


def export_figure(
    fig: ResolvedFigure,
    asset_store: Any | None = None,
    *,
    preview_dpi: int = 192,
    asset_href_base: str = "assets/",
) -> ExportBundle:
    svg_embed = SvgRenderer(asset_store, embed_images=True).render(fig)
    svg_href = SvgRenderer(asset_store, embed_images=False, asset_href_base=asset_href_base).render(fig)
    pptx = PptxRenderer(asset_store).render(fig)
    png = svg_to_png(svg_embed, dpi=preview_dpi)
    return ExportBundle(pptx=pptx, svg=svg_embed, preview_svg=svg_href, preview_png=png)
