"""spec + ResolvedLayout + StyleSheet → ResolvedFigure (고정 계약 #2의 다리).

스타일 병합(resolve_style) + 사전 줄바꿈 lines[] 확정 + z-order 평탄화 + asset 바인딩.
텍스트 줄바꿈을 여기서 1회 확정해 PPTX/SVG 줄바꿈을 강제 일치시킨다.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..layout.engine import PAD_X
from ..layout.text_metrics import FontProvider
from ..layout.types import ConnectorPath, Rect, ResolvedLayout
from ..schema.figure_spec import Connector, FigureSpec
from ..schema.style import Font, StyleSheet, resolve_style
from .resolved import (
    ArrowKind,
    RChart,
    RConnector,
    RElement,
    ResolvedFigure,
    RGroup,
    RImage,
    RShape,
    RText,
    TextRun,
)

_DASH_BY_ROLE = {"flow": "solid", "feedback": "dash", "reference": "dot"}
_BOX_MIN_FONT_PT = 4.5


def _fit_box_font(fonts: FontProvider, font: Font, label: str, sublabel: str, maxw: float) -> Font:
    """가장 긴 단어가 박스 폭(maxw)에 안 들어가면 폰트를 비례 축소한다.

    레이아웃이 박스를 단어 폭 아래로 줄였을 때 문자 단위 줄바꿈을 방지하는 최후 방어선.
    골든 픽스처처럼 이미 들어맞는 경우엔 원본 폰트를 그대로 반환(무변경).
    """
    longest = fonts.longest_word_width_mm(label, font) if label else 0.0
    if sublabel:
        sub = font.model_copy(update={"size_pt": max(_BOX_MIN_FONT_PT, font.size_pt * 0.8)})
        longest = max(longest, fonts.longest_word_width_mm(sublabel, sub))
    if longest <= maxw or longest <= 0:
        return font
    new_pt = max(_BOX_MIN_FONT_PT, font.size_pt * (maxw / longest))
    return font.model_copy(update={"size_pt": new_pt})


def resolve(
    spec: FigureSpec,
    layout: ResolvedLayout,
    stylesheet: StyleSheet | None = None,
    *,
    fonts: FontProvider | None = None,
) -> ResolvedFigure:
    ss = stylesheet or spec.stylesheet or StyleSheet(name="_default")
    fonts = fonts or FontProvider()
    node_by_id = {n.id: n for n, _ in spec.iter_elements()}  # type: ignore[attr-defined]

    elements: list[RElement] = []

    # pass 1: 그룹 테두리 (뒤)
    for eid in layout.z_order:
        node = node_by_id.get(eid)
        if node is not None and node.type == "group" and eid in layout.rects:
            elements.append(_group(node, layout.rects[eid], ss, fonts))

    # pass 2: 커넥터 (중간)
    for c in spec.connectors:
        cp = layout.connector_paths.get(c.id)
        if cp is not None:
            elements.append(_connector(c, cp, ss, fonts))

    # pass 3: 리프 (앞)
    for eid in layout.z_order:
        node = node_by_id.get(eid)
        if node is None or eid not in layout.rects:
            continue
        rect = layout.rects[eid]
        t = node.type
        if t == "box":
            elements.append(_box(node, rect, ss, fonts))
        elif t == "text":
            elements.append(_text(node, rect, ss, fonts))
        elif t == "image":
            elements.append(_image(node, rect))
        elif t == "chart":
            elements.append(_chart(node, rect))

    return ResolvedFigure(
        width_mm=layout.canvas_w_mm,
        height_mm=layout.canvas_h_mm,
        background=ss.background,
        elements=elements,
    )


def _run_from_font(lines: list[str], font: Font, lh: float, *, h="center", v="middle") -> TextRun:
    return TextRun(
        lines=lines,
        family=font.family,
        size_pt=font.size_pt,
        weight=font.weight,
        italic=font.italic,
        color=font.color,
        h_align=h,
        v_align=v,
        line_height_mm=lh,
    )


def _box(node: BaseModel, rect: Rect, ss: StyleSheet, fonts: FontProvider) -> RShape:
    rs = resolve_style(node, ss)
    label = node.label or ""  # type: ignore[attr-defined]
    sublabel = getattr(node, "sublabel", None) or ""
    maxw = max(1.0, rect.w - 2 * PAD_X)
    # 박스 폭에 맞춰 폰트 자동 축소(문자 단위 줄바꿈 방지)
    font = _fit_box_font(fonts, rs.font, label, sublabel, maxw)
    lines: list[str] = []
    lh = font.size_pt * 0.3528 * 1.25
    if label:
        tm = fonts.measure_text(label, font, maxw)
        lines = tm.lines
        lh = tm.line_height_mm
    if sublabel:
        sub_font = font.model_copy(update={"size_pt": max(_BOX_MIN_FONT_PT, font.size_pt * 0.8)})
        lines = [*lines, *fonts.measure_text(sublabel, sub_font, maxw).lines]
    run = _run_from_font(lines, font, lh) if lines else None
    return RShape(
        id=node.id,  # type: ignore[attr-defined]
        kind="box",
        shape_kind=node.shape,  # type: ignore[attr-defined]
        x=rect.x,
        y=rect.y,
        w=rect.w,
        h=rect.h,
        fill=rs.fill or "#FFFFFF",
        fill_opacity=rs.fill_opacity,
        stroke_color=rs.stroke_color,
        stroke_width_pt=rs.stroke_width_pt,
        dash=rs.stroke_dash,
        corner_radius_mm=rs.corner_radius_mm,
        label=run,
        icon_asset=getattr(node, "icon_asset", None),
    )


def _text(node: BaseModel, rect: Rect, ss: StyleSheet, fonts: FontProvider) -> RText:
    rs = resolve_style(node, ss)
    maxw = node.max_width_mm or rect.w  # type: ignore[attr-defined]
    tm = fonts.measure_text(node.text, rs.font, maxw)  # type: ignore[attr-defined]
    run = _run_from_font(
        tm.lines, rs.font, tm.line_height_mm, h=node.h_align, v="top"  # type: ignore[attr-defined]
    )
    return RText(id=node.id, kind="text", x=rect.x, y=rect.y, w=rect.w, h=rect.h, run=run)  # type: ignore[attr-defined]


def _image(node: BaseModel, rect: Rect) -> RImage:
    return RImage(
        id=node.id,  # type: ignore[attr-defined]
        x=rect.x,
        y=rect.y,
        w=rect.w,
        h=rect.h,
        asset_id=getattr(node, "asset_id", None),
        svg_asset_id=getattr(node, "svg_asset_id", None),
        alt=getattr(node, "alt", ""),
        placeholder_label=getattr(node, "alt", "") or "image",
    )


def _chart(node: BaseModel, rect: Rect) -> RChart:
    return RChart(
        id=node.id,  # type: ignore[attr-defined]
        x=rect.x,
        y=rect.y,
        w=rect.w,
        h=rect.h,
        svg_asset_id=getattr(node, "svg_asset_id", None),
        placeholder_label=getattr(node, "brief", "") or "chart",
    )


def _group(node: BaseModel, rect: Rect, ss: StyleSheet, fonts: FontProvider) -> RGroup:
    label_run = None
    if getattr(node, "label", None):
        hf = ss.base_font(role="heading")
        tm = fonts.measure_text(node.label, hf)  # type: ignore[attr-defined]
        label_run = _run_from_font(tm.lines, hf, tm.line_height_mm, h="left", v="top")
    return RGroup(
        id=node.id,  # type: ignore[attr-defined]
        x=rect.x,
        y=rect.y,
        w=rect.w,
        h=rect.h,
        label=label_run,
        stroke_color="#9AA0A6",
        stroke_width_pt=max(0.75, ss.stroke_width_pt * 0.75),
        dash="solid",
        fill=None,
        corner_radius_mm=ss.corner_radius_mm + 1.0,
    )


def _arrow_kinds(arrow: str) -> tuple[ArrowKind, ArrowKind]:
    return {
        "end": ("triangle", "none"),
        "start": ("none", "triangle"),
        "both": ("triangle", "triangle"),
        "none": ("none", "none"),
    }[arrow]


def _connector(c: Connector, cp: ConnectorPath, ss: StyleSheet, fonts: FontProvider) -> RConnector:
    stroke = c.style or ss.connector
    head, tail = _arrow_kinds(c.arrow)
    dash = c.style.dash if c.style else _DASH_BY_ROLE.get(c.line_role, "solid")
    label_run = None
    if c.label:
        cf = ss.base_font(role="caption").model_copy(update={"size_pt": ss.base_font_pt * 0.85})
        tm = fonts.measure_text(c.label, cf)
        label_run = _run_from_font(tm.lines, cf, tm.line_height_mm, h="center", v="middle")
    return RConnector(
        id=c.id,
        points=list(cp.points),
        routing=cp.routing,
        head=head,
        tail=tail,
        stroke_color=stroke.color,
        stroke_width_pt=stroke.width_pt,
        dash=dash,
        from_id=c.source,
        to_id=c.target,
        src_side=cp.src_side,
        tgt_side=cp.tgt_side,
        label=label_run,
        label_anchor=cp.label_anchor,
    )
