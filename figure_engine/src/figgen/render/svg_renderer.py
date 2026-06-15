"""ResolvedFigure → SVG 문자열. stdlib ElementTree 직접 생성, Illustrator 편집성 최적화.

좌표계는 mm 단일 단위(width/height='{W}mm', viewBox='0 0 W H'). 선굵기·폰트는 pt→mm 변환.
요소마다 <g id='fg-{id}' data-fg-id data-fg-kind> 래핑(3중 키). 텍스트는 <text>+<tspan> 벡터.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from ..units import BOX_ICON_MM, pt_to_mm
from .resolved import (
    RChart,
    RConnector,
    ResolvedFigure,
    RGroup,
    RImage,
    RShape,
    RText,
    TextRun,
)

_DASH_MM = {"solid": None, "dash": "3 2", "dot": "0.8 1.6"}


def _wrap_label(text: str, max_chars: int, max_lines: int = 3) -> list[str]:
    """폰트 글리프에 의존하지 않는 단순 단어 단위 줄바꿈(placeholder 라벨용)."""
    max_chars = max(4, max_chars)
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if len(trial) <= max_chars or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
            if len(lines) >= max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and (len(cur) > max_chars or words):
        last = lines[-1]
        if len(last) > max_chars - 1:
            lines[-1] = last[: max_chars - 1] + "…"
    return lines or [text[:max_chars]]


class SvgRenderer:
    def __init__(
        self,
        asset_store: Any | None = None,
        embed_images: bool = True,
        asset_href_base: str = "assets/",
    ):
        self.asset_store = asset_store
        self.embed_images = embed_images
        self.asset_href_base = asset_href_base

    def render(self, fig: ResolvedFigure, *, debug: bool = False) -> str:
        W, H = fig.width_mm, fig.height_mm
        svg = ET.Element(
            "svg",
            {
                "xmlns": "http://www.w3.org/2000/svg",
                "xmlns:xlink": "http://www.w3.org/1999/xlink",
                "width": f"{W:.3f}mm",
                "height": f"{H:.3f}mm",
                "viewBox": f"0 0 {W:.3f} {H:.3f}",
                "font-family": "Arial, Helvetica, sans-serif",
            },
        )
        self._markers_needed: dict[tuple[str, str], None] = {}
        defs = ET.SubElement(svg, "defs")

        # 배경
        ET.SubElement(
            svg, "rect", {"x": "0", "y": "0", "width": f"{W:.3f}", "height": f"{H:.3f}",
                          "fill": fig.background}
        )

        content = ET.SubElement(svg, "g", {"id": "fg-content"})
        for el in fig.elements:
            self._render_element(content, el, debug=debug)

        # 사용된 (kind,color) marker 사전 생성 (marker는 stroke 상속 불가)
        for kind, color in self._markers_needed:
            self._add_marker(defs, kind, color)

        if debug:
            self._render_debug_overlay(svg, fig)

        return _serialize(svg)

    def render_debug(self, fig: ResolvedFigure) -> str:
        return self.render(fig, debug=True)

    # ── 요소 ──────────────────────────────────────────────────────────────────
    def _wrap(self, parent: ET.Element, el: Any) -> ET.Element:
        return ET.SubElement(
            parent,
            "g",
            {"id": f"fg-{el.id}", "data-fg-id": el.id, "data-fg-kind": el.kind},
        )

    def _render_element(self, parent: ET.Element, el: Any, *, debug: bool) -> None:
        if isinstance(el, RShape):
            self._shape(parent, el)
        elif isinstance(el, RGroup):
            self._group(parent, el)
        elif isinstance(el, RText):
            self._text(parent, el)
        elif isinstance(el, RImage):
            self._image(parent, el)
        elif isinstance(el, RChart):
            self._chart(parent, el)
        elif isinstance(el, RConnector):
            self._connector(parent, el)

    def _stroke_attrs(self, color: str | None, width_pt: float, dash: str) -> dict[str, str]:
        if not color:
            return {"stroke": "none"}
        a = {"stroke": color, "stroke-width": f"{pt_to_mm(width_pt):.3f}"}
        d = _DASH_MM.get(dash)
        if d:
            a["stroke-dasharray"] = d
        return a

    def _shape(self, parent: ET.Element, el: RShape) -> None:
        g = self._wrap(parent, el)
        fill = el.fill or "none"
        attrs = {"fill": fill, **self._stroke_attrs(el.stroke_color, el.stroke_width_pt, el.dash)}
        if el.fill and el.fill_opacity < 1.0:
            attrs["fill-opacity"] = f"{el.fill_opacity:.3f}"
        self._shape_geometry(g, el, attrs)
        icon_h = 0.0
        if getattr(el, "icon_asset", None) and self.asset_store is not None:  # M4.3
            href = self._image_href(el.icon_asset)
            if href:
                iw = min(BOX_ICON_MM, el.w - 2.0, max(4.0, el.h * 0.5))
                ix = el.x + (el.w - iw) / 2
                iy = el.y + 1.5
                ET.SubElement(g, "image", {
                    "x": f"{ix:.3f}", "y": f"{iy:.3f}", "width": f"{iw:.3f}",
                    "height": f"{iw:.3f}", "href": href,
                    "preserveAspectRatio": "xMidYMid meet"})
                icon_h = iw + 1.5
        if el.label:
            self._draw_run(g, el.label, el.x, el.y + icon_h, el.w, el.h - icon_h)

    def _shape_geometry(self, g: ET.Element, el: RShape, attrs: dict[str, str]) -> None:
        x, y, w, h = el.x, el.y, el.w, el.h
        sk = el.shape_kind
        if sk in ("rect", "rounded"):
            r = {"x": f"{x:.3f}", "y": f"{y:.3f}", "width": f"{w:.3f}", "height": f"{h:.3f}", **attrs}
            if sk == "rounded":
                r["rx"] = f"{el.corner_radius_mm:.3f}"
            ET.SubElement(g, "rect", r)
        elif sk == "ellipse":
            ET.SubElement(g, "ellipse", {"cx": f"{x + w / 2:.3f}", "cy": f"{y + h / 2:.3f}",
                                         "rx": f"{w / 2:.3f}", "ry": f"{h / 2:.3f}", **attrs})
        elif sk == "diamond":
            pts = [(x + w / 2, y), (x + w, y + h / 2), (x + w / 2, y + h), (x, y + h / 2)]
            ET.SubElement(g, "polygon", {"points": _pts(pts), **attrs})
        elif sk == "parallelogram":
            o = w * 0.18
            pts = [(x + o, y), (x + w, y), (x + w - o, y + h), (x, y + h)]
            ET.SubElement(g, "polygon", {"points": _pts(pts), **attrs})
        elif sk == "hexagon":
            o = w * 0.2
            pts = [(x + o, y), (x + w - o, y), (x + w, y + h / 2), (x + w - o, y + h),
                   (x + o, y + h), (x, y + h / 2)]
            ET.SubElement(g, "polygon", {"points": _pts(pts), **attrs})
        elif sk == "cylinder":
            ry = min(h * 0.12, w * 0.18)
            d = (
                f"M {x:.3f} {y + ry:.3f} A {w / 2:.3f} {ry:.3f} 0 0 1 {x + w:.3f} {y + ry:.3f} "
                f"L {x + w:.3f} {y + h - ry:.3f} A {w / 2:.3f} {ry:.3f} 0 0 1 {x:.3f} {y + h - ry:.3f} Z"
            )
            ET.SubElement(g, "path", {"d": d, **attrs})
            ET.SubElement(g, "path", {
                "d": f"M {x:.3f} {y + ry:.3f} A {w / 2:.3f} {ry:.3f} 0 0 0 {x + w:.3f} {y + ry:.3f}",
                "fill": "none", "stroke": attrs.get("stroke", "none"),
                "stroke-width": attrs.get("stroke-width", "0.3")})
        else:  # fallback rect
            ET.SubElement(g, "rect", {"x": f"{x:.3f}", "y": f"{y:.3f}", "width": f"{w:.3f}",
                                      "height": f"{h:.3f}", **attrs})

    def _group(self, parent: ET.Element, el: RGroup) -> None:
        g = self._wrap(parent, el)
        attrs = {"fill": el.fill or "none",
                 **self._stroke_attrs(el.stroke_color, el.stroke_width_pt, el.dash)}
        ET.SubElement(g, "rect", {"x": f"{el.x:.3f}", "y": f"{el.y:.3f}", "width": f"{el.w:.3f}",
                                  "height": f"{el.h:.3f}", "rx": f"{el.corner_radius_mm:.3f}",
                                  **attrs})
        if el.label:
            # 좌상단 라벨
            self._draw_run(g, el.label, el.x + 2.0, el.y + 0.5, el.w - 4.0, el.label.line_height_mm)

    def _text(self, parent: ET.Element, el: RText) -> None:
        g = self._wrap(parent, el)
        self._draw_run(g, el.run, el.x, el.y, el.w, el.h)

    def _image(self, parent: ET.Element, el: RImage) -> None:
        g = self._wrap(parent, el)
        # 벡터화된 변형이 있으면 차트와 동일 경로로 인라인(편집 가능 <path>) — 실패 시 래스터 폴백
        if getattr(el, "svg_asset_id", None) and self.asset_store is not None:
            svg_text = _try_get_chart_svg(self.asset_store, el.svg_asset_id)
            if svg_text:
                before = len(list(g))
                _inline_chart_svg(g, svg_text, el)
                if len(list(g)) > before:
                    return
        href = self._image_href(el.asset_id) if el.asset_id else None
        if href:
            ET.SubElement(g, "image", {"x": f"{el.x:.3f}", "y": f"{el.y:.3f}",
                                       "width": f"{el.w:.3f}", "height": f"{el.h:.3f}",
                                       "href": href, "preserveAspectRatio": "xMidYMid meet"})
        else:
            self._placeholder(g, el.x, el.y, el.w, el.h, el.placeholder_label or "image")

    def _chart(self, parent: ET.Element, el: RChart) -> None:
        g = self._wrap(parent, el)
        svg_text = None
        if el.svg_asset_id and self.asset_store is not None:
            svg_text = _try_get_chart_svg(self.asset_store, el.svg_asset_id)
        if svg_text:
            _inline_chart_svg(g, svg_text, el)
        else:
            self._placeholder(g, el.x, el.y, el.w, el.h, el.placeholder_label or "chart", chart=True)

    def _connector(self, parent: ET.Element, el: RConnector) -> None:
        g = self._wrap(parent, el)
        d = _path_d(el.points, el.routing)
        attrs = {"d": d, "fill": "none",
                 **self._stroke_attrs(el.stroke_color, el.stroke_width_pt, el.dash)}
        if el.head in ("triangle", "open", "diamond"):
            self._markers_needed[(el.head, el.stroke_color)] = None
            attrs["marker-end"] = f"url(#arrow-{el.head}-{_cid(el.stroke_color)})"
        if el.tail in ("triangle", "open", "diamond"):
            self._markers_needed[(el.tail, el.stroke_color)] = None
            attrs["marker-start"] = f"url(#arrow-{el.tail}-{_cid(el.stroke_color)})"
        ET.SubElement(g, "path", attrs)
        if el.label and el.label_anchor:
            ax, ay = el.label_anchor
            self._draw_run(g, el.label, ax - 12, ay - el.label.line_height_mm / 2, 24,
                           el.label.line_height_mm, bg=True)

    # ── 텍스트 그리기 ──────────────────────────────────────────────────────────
    def _draw_run(self, parent: ET.Element, run: TextRun, x: float, y: float, w: float, h: float,
                  *, bg: bool = False) -> None:
        if not run.lines or all(not s for s in run.lines):
            return
        size_mm = pt_to_mm(run.size_pt)
        lh = run.line_height_mm
        n = len(run.lines)
        # 수평 정렬
        if run.h_align == "left":
            tx, anchor = x, "start"
        elif run.h_align == "right":
            tx, anchor = x + w, "end"
        else:
            tx, anchor = x + w / 2, "middle"
        # 수직: 첫 baseline
        ascent = size_mm * 0.8
        if run.v_align == "top":
            first = y + ascent
        elif run.v_align == "bottom":
            first = y + h - (n - 1) * lh - (lh - ascent)
        else:  # middle
            first = y + h / 2 - (n - 1) * lh / 2 + size_mm * 0.32
        if bg:
            tw = max(len(s) for s in run.lines) * size_mm * 0.55
            ET.SubElement(parent, "rect", {
                "x": f"{tx - (tw / 2 if anchor == 'middle' else 0):.3f}",
                "y": f"{first - ascent:.3f}", "width": f"{tw:.3f}",
                "height": f"{n * lh:.3f}", "fill": "#FFFFFF", "fill-opacity": "0.75"})
        text = ET.SubElement(parent, "text", {
            "x": f"{tx:.3f}", "y": f"{first:.3f}", "font-size": f"{size_mm:.3f}",
            "fill": run.color, "text-anchor": anchor,
            "font-weight": "bold" if run.weight == "bold" else "normal",
        })
        if run.italic:
            text.set("font-style", "italic")
        for i, line in enumerate(run.lines):
            ts = ET.SubElement(text, "tspan", {"x": f"{tx:.3f}", "y": f"{first + i * lh:.3f}"})
            ts.text = line

    def _placeholder(self, g: ET.Element, x: float, y: float, w: float, h: float, label: str,
                     *, chart: bool = False) -> None:
        ET.SubElement(g, "rect", {"x": f"{x:.3f}", "y": f"{y:.3f}", "width": f"{w:.3f}",
                                  "height": f"{h:.3f}", "fill": "#F1F3F4", "stroke": "#BDC1C6",
                                  "stroke-width": "0.3", "stroke-dasharray": "1.5 1.5", "rx": "1"})
        # 박스 폭에 맞춰 단어 단위 줄바꿈(글리프 미존재 tofu·중간 절단 방지)
        size_pt = 7.0
        size_mm = pt_to_mm(size_pt)
        max_chars = int(max(4.0, (w - 2.0) / (size_mm * 0.55)))
        kind = "chart" if chart else "figure"
        lines = _wrap_label(f"{label} ({kind})", max_chars)
        run = TextRun(lines=lines, size_pt=size_pt, color="#80868B",
                      h_align="center", v_align="middle", line_height_mm=size_mm * 1.25)
        self._draw_run(g, run, x, y, w, h)

    # ── markers / assets ───────────────────────────────────────────────────────
    def _add_marker(self, defs: ET.Element, kind: str, color: str) -> None:
        m = ET.SubElement(defs, "marker", {
            "id": f"arrow-{kind}-{_cid(color)}", "viewBox": "0 0 10 10",
            "refX": "8.5", "refY": "5", "markerWidth": "7", "markerHeight": "7",
            "orient": "auto-start-reverse", "markerUnits": "strokeWidth"})
        if kind == "triangle":
            ET.SubElement(m, "path", {"d": "M 0 1 L 9 5 L 0 9 z", "fill": color})
        elif kind == "open":
            ET.SubElement(m, "path", {"d": "M 0 1 L 9 5 L 0 9", "fill": "none",
                                      "stroke": color, "stroke-width": "1.4"})
        elif kind == "diamond":
            ET.SubElement(m, "path", {"d": "M 0 5 L 5 1 L 10 5 L 5 9 z", "fill": color})

    def _image_href(self, asset_id: str) -> str | None:
        if self.asset_store is None:
            return None
        if self.embed_images:
            data = _try_get_asset_png(self.asset_store, asset_id)
            if data:
                import base64

                b64 = base64.b64encode(data).decode("ascii")
                return f"data:image/png;base64,{b64}"
            return None
        return f"{self.asset_href_base}{asset_id}.png"

    def _render_debug_overlay(self, svg: ET.Element, fig: ResolvedFigure) -> None:
        g = ET.SubElement(svg, "g", {"id": "fg-debug", "font-family": "monospace"})
        for el in fig.elements:
            x = getattr(el, "x", None)
            y = getattr(el, "y", None)
            if x is None or y is None:
                continue
            t = ET.SubElement(g, "text", {"x": f"{x + 0.5:.3f}", "y": f"{y + 2.6:.3f}",
                                          "font-size": "2.2", "fill": "#D93025"})
            t.text = el.id


# ── 모듈 헬퍼 ──────────────────────────────────────────────────────────────────
def _pts(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.3f},{y:.3f}" for x, y in points)


def _path_d(points: list[tuple[float, float]], routing: str) -> str:
    if not points:
        return ""
    if routing == "curve" and len(points) == 4:
        p0, c1, c2, p3 = points
        return (f"M {p0[0]:.3f} {p0[1]:.3f} C {c1[0]:.3f} {c1[1]:.3f} "
                f"{c2[0]:.3f} {c2[1]:.3f} {p3[0]:.3f} {p3[1]:.3f}")
    d = f"M {points[0][0]:.3f} {points[0][1]:.3f}"
    for x, y in points[1:]:
        d += f" L {x:.3f} {y:.3f}"
    return d


def _cid(color: str) -> str:
    return color.lstrip("#").lower()


def _serialize(svg: ET.Element) -> str:
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(svg, encoding="unicode")


def _try_get_asset_png(store: Any, asset_id: str) -> bytes | None:
    for meth in ("get_png", "get_bytes"):
        fn = getattr(store, meth, None)
        if fn:
            try:
                return fn(asset_id)
            except Exception:  # noqa: BLE001
                return None
    return None


def _try_get_chart_svg(store: Any, asset_id: str) -> str | None:
    fn = getattr(store, "get_svg", None)
    if fn:
        try:
            return fn(asset_id)
        except Exception:  # noqa: BLE001
            return None
    return None


def _strip_ns(el: ET.Element) -> None:
    """요소 태그에서 {namespace} 접두사 제거 → <ns0:path> 대신 깨끗한 <path>로 직렬화.

    figure.svg가 기본 svg 네임스페이스를 쓰므로(루트에 리터럴 xmlns), 인라인되는 차트/벡터
    자식도 동일 네임스페이스로 보이게 한다(Illustrator/Inkscape 편집성).
    """
    for e in el.iter():
        if isinstance(e.tag, str) and "}" in e.tag:
            e.tag = e.tag.split("}", 1)[1]


def _inline_chart_svg(g: ET.Element, svg_text: str, el: RChart) -> None:
    """차트/벡터 SVG 루트를 <g transform>으로 el 영역에 fit-인라인(편집 유지)."""
    try:
        inner = ET.fromstring(svg_text.encode("utf-8") if isinstance(svg_text, str) else svg_text)
    except Exception:  # noqa: BLE001
        return
    vb_w, vb_h = _chart_dims(inner)
    if not vb_w or not vb_h:
        return
    _strip_ns(inner)  # <ns0:path> → <path>
    scale = min(el.w / vb_w, el.h / vb_h)  # 균일 스케일 fit
    ox = el.x + (el.w - vb_w * scale) / 2
    oy = el.y + (el.h - vb_h * scale) / 2
    holder = ET.SubElement(g, "g", {
        "transform": f"translate({ox:.3f} {oy:.3f}) scale({scale:.5f})"})
    for child in list(inner):
        holder.append(child)


def _chart_dims(inner: ET.Element) -> tuple[float, float]:
    vb = inner.get("viewBox")
    if vb:
        parts = [float(p) for p in vb.replace(",", " ").split()]
        if len(parts) == 4 and parts[2] and parts[3]:
            return parts[2], parts[3]
    w, h = inner.get("width", ""), inner.get("height", "")

    def _num(s: str) -> float:
        m = re.match(r"[-+]?[\d.]+", s)
        return float(m.group()) if m else 0.0

    return _num(w), _num(h)
