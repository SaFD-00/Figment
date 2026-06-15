"""ResolvedFigure — 렌더러가 소비하는 해석 완료 스펙(고정 계약 #3).

mm 좌표 + 사전 줄바꿈된 ``lines[]`` + 해석된 색/폰트만 담는다. PPTX/SVG 렌더러는
이 모델을 좌표·스타일·줄바꿈 계산 없이 결정론적으로 그리기만 한다.
각 요소는 3중 키(spec id / SVG data-fg-id / PPTX shape.name)를 위해 ``id``/``kind``를 보존한다.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

ArrowKind = Literal["none", "triangle", "open", "diamond"]
ResolvedShapeKind = Literal[
    "rect", "rounded", "ellipse", "diamond", "cylinder", "parallelogram", "hexagon"
]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TextRun(_Base):
    """인라인 텍스트(박스 내부 라벨, 커넥터 라벨, 독립 텍스트 공통)."""

    lines: list[str]
    family: str = "Arial"
    size_pt: float = 8.0
    weight: Literal["regular", "medium", "bold"] = "regular"
    italic: bool = False
    color: str = "#222222"
    h_align: Literal["left", "center", "right"] = "center"
    v_align: Literal["top", "middle", "bottom"] = "middle"
    line_height_mm: float = 3.5


class RShape(_Base):
    rkind: Literal["shape"] = "shape"
    id: str
    kind: str = "box"
    shape_kind: ResolvedShapeKind = "rounded"
    x: float
    y: float
    w: float
    h: float
    fill: str | None = None
    fill_opacity: float = 1.0
    stroke_color: str | None = "#333333"
    stroke_width_pt: float = 1.0
    dash: Literal["solid", "dash", "dot"] = "solid"
    corner_radius_mm: float = 1.5
    label: TextRun | None = None
    icon_asset: str | None = None  # 있으면 박스 상단에 작은 일러스트(M4.3)


class RText(_Base):
    rkind: Literal["text"] = "text"
    id: str
    kind: str = "text"
    x: float
    y: float
    w: float
    h: float
    run: TextRun


class RImage(_Base):
    rkind: Literal["image"] = "image"
    id: str
    kind: str = "image"
    x: float
    y: float
    w: float
    h: float
    asset_id: str | None = None
    svg_asset_id: str | None = None  # 있으면 SVG에 벡터 path로 인라인(편집 가능)
    alt: str = ""
    placeholder_label: str = ""


class RChart(_Base):
    rkind: Literal["chart"] = "chart"
    id: str
    kind: str = "chart"
    x: float
    y: float
    w: float
    h: float
    svg_asset_id: str | None = None
    placeholder_label: str = ""


class RGroup(_Base):
    rkind: Literal["group"] = "group"
    id: str
    kind: str = "group"
    x: float
    y: float
    w: float
    h: float
    label: TextRun | None = None
    stroke_color: str | None = "#999999"
    stroke_width_pt: float = 1.0
    dash: Literal["solid", "dash", "dot"] = "solid"
    fill: str | None = None
    fill_opacity: float = 1.0
    corner_radius_mm: float = 2.0


class RConnector(_Base):
    rkind: Literal["connector"] = "connector"
    id: str
    kind: str = "connector"
    points: list[tuple[float, float]]
    routing: Literal["straight", "elbow", "curve"] = "elbow"
    head: ArrowKind = "triangle"
    tail: ArrowKind = "none"
    stroke_color: str = "#555555"
    stroke_width_pt: float = 1.0
    dash: Literal["solid", "dash", "dot"] = "solid"
    from_id: str | None = None
    to_id: str | None = None
    src_side: str | None = None
    tgt_side: str | None = None
    label: TextRun | None = None
    label_anchor: tuple[float, float] | None = None


RElement = Annotated[
    RShape | RText | RImage | RChart | RGroup | RConnector,
    Field(discriminator="rkind"),
]


class ResolvedFigure(_Base):
    width_mm: float
    height_mm: float
    background: str = "#FFFFFF"
    elements: list[RElement] = Field(default_factory=list)  # 그리기 순서(뒤→앞)
