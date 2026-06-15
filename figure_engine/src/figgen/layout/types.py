"""레이아웃 공용 타입 — engine/connectors/diagnostics 순환 import 방지용 단일 소스."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

WarningKind = Literal[
    "overlap", "overflow", "text_clipping", "canvas_exceeded", "connector_crossing",
    "tiny_text", "empty_content"
]
Severity = Literal["critical", "major", "minor"]
ArrowAt = Literal["end", "start", "both", "none"]
Side = Literal["left", "right", "top", "bottom"]


class Rect(BaseModel):
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    def center(self) -> tuple[float, float]:
        return (self.cx, self.cy)


class ConnectorPath(BaseModel):
    points: list[tuple[float, float]]  # mm 폴리라인
    arrow_at: ArrowAt = "end"
    routing: Literal["straight", "elbow", "curve"] = "elbow"
    label_anchor: tuple[float, float] | None = None
    src_side: Side | None = None
    tgt_side: Side | None = None


class LayoutWarning(BaseModel):
    kind: WarningKind
    element_ids: list[str] = Field(default_factory=list)
    detail: str = ""
    severity: Severity = "major"


class ResolvedLayout(BaseModel):
    rects: dict[str, Rect] = Field(default_factory=dict)
    z_order: list[str] = Field(default_factory=list)
    connector_paths: dict[str, ConnectorPath] = Field(default_factory=dict)
    canvas_w_mm: float = 180.0
    canvas_h_mm: float = 120.0
    warnings: list[LayoutWarning] = Field(default_factory=list)
