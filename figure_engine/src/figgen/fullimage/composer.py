"""풀 이미지 모드(graphical abstract): 통짜 AI 이미지 + 편집 가능 라벨 오버레이.

베이스 이미지는 'no text, no labels'로 생성하고 모든 텍스트는 정규화 좌표(0..1) 오버레이
TextElement로 둔다(이미지 모델 오타/저해상도 텍스트 차단, 라벨은 항상 후편집 가능).
표준 파이프라인에 합류하도록 **root=Free FigureSpec**을 생성한다(critic이 x_frac/y_frac 패치 가능).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from ..providers.base import ImageClient
from ..schema.figure_spec import FigureSpec


class LabelProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    nx: float = Field(ge=0, le=1)
    ny: float = Field(ge=0, le=1)
    anchor: str = "center"  # 'center' | 'top_left'
    font_role: str = "body"  # 'title'|'heading'|'body'|'caption'


_TEXT_ROLES = {"title", "heading", "body", "caption", "annotation"}


def _slug(text: str, i: int) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:24]
    return s if s and s[0].isalpha() else f"label_{i}"


def _clamp01(v: float) -> float:
    return min(1.0, max(0.0, v))


def canvas_mm_for_image(png: bytes, *, max_w: float = 170.0, max_h: float = 140.0) -> tuple[float, float]:
    """이미지 종횡비에 맞춘 캔버스(mm) — refine/vectorize/sketch의 풀블리드 spec용."""
    import io

    from PIL import Image

    w, h = Image.open(io.BytesIO(png)).size
    if w <= 0 or h <= 0:
        return (max_w, round(max_w * 2 / 3, 1))
    ar = w / h
    cw, ch = max_w, max_w / ar
    if ch > max_h:
        ch, cw = max_h, max_h * ar
    return (round(cw, 1), round(ch, 1))


async def generate_base_image(
    prompt: str, image_client: ImageClient, *, width_px: int = 1536, height_px: int = 1024
) -> bytes:
    """텍스트 없는 베이스 이미지 생성."""
    full = (f"{prompt}. A scientific graphical abstract illustration, "
            "absolutely no text, no labels, no letters, no numbers, no captions.")
    result = await image_client.generate(full, width_px=width_px, height_px=height_px,
                                         transparent=False)
    return result.data


def build_overlay_spec(
    base_asset_id: str,
    labels: list[LabelProposal],
    *,
    canvas_mm: tuple[float, float] = (170.0, 95.0),
    title: str | None = None,
    figure_type: str = "graphical_abstract",
    base_svg_asset_id: str | None = None,
) -> FigureSpec:
    """베이스 이미지(풀블리드) + 편집 가능 라벨 오버레이로 Free 루트 FigureSpec 생성.

    base_svg_asset_id가 주어지면 베이스 이미지가 SVG에서 편집 가능한 벡터 path로 인라인된다.
    """
    base_node = {"type": "image", "id": "base_image", "alt": "graphical abstract base",
                 "asset_id": base_asset_id, "needs_transparency": False}
    if base_svg_asset_id:
        base_node["svg_asset_id"] = base_svg_asset_id
    items: list[dict] = [{
        "node": base_node,
        "x_frac": 0.5, "y_frac": 0.5, "w_frac": 1.0, "h_frac": 1.0, "anchor": "center",
    }]
    used = {"base_image"}
    for i, lab in enumerate(labels):
        lid = _slug(lab.text, i)
        while lid in used:
            lid = f"{lid}_{i}"
        used.add(lid)
        # 라이브 LLM이 비표준값(예: anchor="middle", font_role="label")을 줄 수 있어 정규화한다.
        role = lab.font_role if lab.font_role in _TEXT_ROLES else "body"
        anchor = "top_left" if lab.anchor == "top_left" else "center"
        items.append({
            "node": {"type": "text", "id": lid, "text": lab.text, "text_role": role,
                     "h_align": "center"},
            "x_frac": _clamp01(lab.nx), "y_frac": _clamp01(lab.ny), "anchor": anchor,
        })
    if title:
        items.append({
            "node": {"type": "text", "id": "ga_title", "text": title, "text_role": "title",
                     "h_align": "center"},
            "x_frac": 0.5, "y_frac": 0.06, "anchor": "center",
        })
    return FigureSpec.model_validate({
        "figure_type": figure_type,
        "canvas": {"width_mm": canvas_mm[0], "height_mm": canvas_mm[1]},
        "root": {"type": "free", "id": "root", "items": items},
    })
