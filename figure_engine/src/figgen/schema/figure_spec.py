"""코어 FigureSpec — LLM 출력 타깃이자 렌더러 입력인 단일 진실 소스.

원칙: LLM에 절대좌표 금지. 레이아웃은 Row/Column/Grid/Group 중첩 트리 +
graphical abstract용 Free(0~1 비율 좌표) 노드만 허용. Connector는 트리 밖 flat 리스트
(id 참조). 스타일은 Planner 출력에서 제거(stylesheet=None 강제) — Stylist가 주입.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._types import MM, ElementId, HexColor
from .style import Stroke, StyleOverride, StyleSheet

FigureType = Literal[
    "method_diagram", "concept", "chart", "graphical_abstract", "scientific_illustration"
]
MAX_DEPTH = 6


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SizeHint(_Base):
    width_mm: MM | None = None
    height_mm: MM | None = None
    min_width_mm: MM | None = None
    min_height_mm: MM | None = None
    aspect: float | None = None  # w/h (이미지·차트)


class ElementBase(_Base):
    id: ElementId
    z: int = 0
    style: StyleOverride | None = None
    size_hint: SizeHint | None = None
    weight: float = 1.0  # 부모 main-axis 잔여 여백 분배 비율


# ── 리프 4종 ──────────────────────────────────────────────────────────────────
BoxShape = Literal["rect", "rounded", "ellipse", "diamond", "cylinder", "parallelogram", "hexagon"]
BoxRole = Literal["input", "output", "process", "model", "data", "decision", "loss", "note"]
TextRole = Literal["title", "heading", "body", "caption", "annotation"]
HAlign = Literal["left", "center", "right"]
ChartKind = Literal["line", "bar", "grouped_bar", "scatter", "heatmap", "box", "violin", "custom"]


class BoxElement(ElementBase):
    type: Literal["box"] = "box"
    label: str | None = None
    sublabel: str | None = None
    shape: BoxShape = "rounded"
    role: BoxRole | None = None
    icon_asset: str | None = None  # AssetStore id


class TextElement(ElementBase):
    type: Literal["text"] = "text"
    text: str
    text_role: TextRole = "body"
    h_align: HAlign = "left"
    max_width_mm: MM | None = None


class ImageElement(ElementBase):
    type: Literal["image"] = "image"
    alt: str  # 의미 설명 (critic용)
    gen_prompt: str | None = None
    asset_id: str | None = None  # 생성 후 채움 (래스터 PNG)
    svg_asset_id: str | None = None  # 벡터화 변형(편집 가능) — SVG 렌더 시 인라인
    needs_transparency: bool = True


class ChartElement(ElementBase):
    type: Literal["chart"] = "chart"
    chart_kind: ChartKind
    brief: str
    data_ref: str | None = None
    code_asset_id: str | None = None  # chart track이 채움
    svg_asset_id: str | None = None


# ── 컨테이너 ──────────────────────────────────────────────────────────────────
Align = Literal["start", "center", "end", "stretch"]
Justify = Literal["start", "center", "end", "space_between"]
GroupRole = Literal["module", "stage", "legend", "panel"]


class ContainerBase(ElementBase):
    gap_mm: MM = 4.0
    padding_mm: MM = 0.0
    align: Align = "center"  # cross축
    justify: Justify = "center"  # main축


class Row(ContainerBase):
    type: Literal["row"] = "row"
    children: list[Node]


class Column(ContainerBase):
    type: Literal["column"] = "column"
    children: list[Node]


class Grid(ContainerBase):
    type: Literal["grid"] = "grid"
    columns: int = Field(ge=1, le=8)
    children: list[Node]


class Group(ContainerBase):
    """시각적 테두리 + 라벨 컨테이너."""

    type: Literal["group"] = "group"
    label: str | None = None
    direction: Literal["row", "column"] = "column"
    role: GroupRole | None = None
    children: list[Node]


class FreeItem(_Base):
    node: Node
    x_frac: float = Field(ge=0, le=1)
    y_frac: float = Field(ge=0, le=1)
    w_frac: float | None = None
    h_frac: float | None = None
    anchor: Literal["top_left", "center"] = "center"


class Free(ElementBase):
    """0~1 비율 좌표 자유 배치 (graphical abstract 루트)."""

    type: Literal["free"] = "free"
    items: list[FreeItem]


Node = Annotated[
    Row | Column | Grid | Group | Free | BoxElement | TextElement | ImageElement | ChartElement,
    Field(discriminator="type"),
]

CONTAINER_TYPES = ("row", "column", "grid", "group")


# ── Connector (트리 밖 flat) ──────────────────────────────────────────────────
ConnSide = Literal["auto", "left", "right", "top", "bottom"]


class Connector(_Base):
    id: ElementId
    source: ElementId
    target: ElementId
    source_side: ConnSide = "auto"
    target_side: ConnSide = "auto"
    label: str | None = None
    arrow: Literal["end", "start", "both", "none"] = "end"
    routing: Literal["straight", "elbow", "curve"] = "elbow"
    line_role: Literal["flow", "feedback", "reference"] = "flow"
    style: Stroke | None = None


class Canvas(_Base):
    width_mm: MM = 180.0
    height_mm: MM | None = None  # None이면 레이아웃이 자동 산출
    background: HexColor = "#FFFFFF"


class FigureSpec(_Base):
    spec_version: Literal["1"] = "1"
    figure_type: FigureType
    title: str | None = None
    canvas: Canvas = Field(default_factory=Canvas)
    stylesheet: StyleSheet | None = None  # Planner 출력에선 항상 None, Stylist가 주입
    root: Node
    connectors: list[Connector] = Field(default_factory=list)

    # ── 순회 헬퍼 ─────────────────────────────────────────────────────────────
    def iter_elements(self) -> Iterator[tuple[BaseModel, list[str]]]:
        """(노드, 조상 id 경로) 를 깊이우선으로 순회."""
        yield from _iter(self.root, [])

    def find(self, element_id: str) -> BaseModel | None:
        for node, _ in self.iter_elements():
            if getattr(node, "id", None) == element_id:
                return node
        return None

    def element_ids(self) -> list[str]:
        return [n.id for n, _ in self.iter_elements()]

    def max_depth(self) -> int:
        return _depth(self.root)

    # ── 검증 ──────────────────────────────────────────────────────────────────
    @model_validator(mode="after")
    def _validate(self) -> FigureSpec:
        ids = self.element_ids()
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"중복 element id: {sorted(dupes)}")

        id_set = set(ids)
        conn_ids = [c.id for c in self.connectors]
        cdupes = {i for i in conn_ids if conn_ids.count(i) > 1}
        if cdupes:
            raise ValueError(f"중복 connector id: {sorted(cdupes)}")
        for c in self.connectors:
            if c.source not in id_set:
                raise ValueError(f"connector {c.id}: source '{c.source}' 미존재")
            if c.target not in id_set:
                raise ValueError(f"connector {c.id}: target '{c.target}' 미존재")

        depth = self.max_depth()
        if depth > MAX_DEPTH:
            raise ValueError(f"중첩 깊이 {depth} > {MAX_DEPTH}")
        return self


def _children_of(node: BaseModel) -> list[BaseModel]:
    t = getattr(node, "type", None)
    if t in CONTAINER_TYPES:
        return list(node.children)  # type: ignore[attr-defined]
    if t == "free":
        return [it.node for it in node.items]  # type: ignore[attr-defined]
    return []


def _iter(node: BaseModel, path: list[str]) -> Iterator[tuple[BaseModel, list[str]]]:
    yield node, path
    nid = getattr(node, "id", None)
    child_path = [*path, nid] if nid else path
    for child in _children_of(node):
        yield from _iter(child, child_path)


def _depth(node: BaseModel) -> int:
    children = _children_of(node)
    if not children:
        return 1
    return 1 + max(_depth(c) for c in children)


# 전방 참조(list[Node], FreeItem.node) 해소
for _m in (Row, Column, Grid, Group, Free, FreeItem):
    _m.model_rebuild()
FigureSpec.model_rebuild()
