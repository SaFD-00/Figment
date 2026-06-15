"""python-pptx 미지원 기능의 OOXML 직접 패치 (lxml 핵 격리 모듈).

화살촉(a:headEnd/tailEnd), 점선(a:prstDash), 채움 투명도(a:alpha), shape 이름을
shape._element(lxml)에 직접 주입한다. 모든 OOXML 핵을 한 파일에 모아 유지보수성 확보.

곡선 커넥터는 복잡한 custGeom 대신 python-pptx 네이티브 ``MSO_CONNECTOR.CURVE``로
렌더한다(편집 가능 + 견고). 정밀 베지어는 SVG 출력이 보존한다.
"""

from __future__ import annotations

from typing import Any

from pptx.oxml.ns import qn

_ARROW_OOXML = {"triangle": "triangle", "open": "arrow", "diamond": "diamond", "none": "none"}
_DASH_OOXML = {"solid": "solid", "dash": "dash", "dot": "sysDot"}


def _get_or_add_ln(shape: Any):
    spPr = shape._element.spPr
    ln = spPr.find(qn("a:ln"))
    if ln is None:
        ln = spPr.makeelement(qn("a:ln"), {})
        spPr.append(ln)
    return ln


def set_line_arrowheads(shape: Any, head: str = "none", tail: str = "none") -> None:
    """선의 끝(head=tailEnd)·시작(tail=headEnd) 화살촉 설정."""
    ln = _get_or_add_ln(shape)
    for tag, kind in (("a:tailEnd", head), ("a:headEnd", tail)):
        existing = ln.find(qn(tag))
        if existing is not None:
            ln.remove(existing)
        ooxml = _ARROW_OOXML.get(kind, "none")
        if ooxml == "none":
            continue
        ln.append(ln.makeelement(qn(tag), {"type": ooxml, "w": "med", "len": "med"}))


def set_dash(shape: Any, style: str) -> None:
    if style == "solid":
        return
    ln = _get_or_add_ln(shape)
    existing = ln.find(qn("a:prstDash"))
    if existing is not None:
        ln.remove(existing)
    ln.append(ln.makeelement(qn("a:prstDash"), {"val": _DASH_OOXML.get(style, "solid")}))


def set_fill_alpha(shape: Any, alpha: float) -> None:
    """solidFill srgbClr 아래 <a:alpha val=.../> 주입 (0..1 → 0..100000)."""
    if alpha >= 1.0:
        return
    spPr = shape._element.spPr
    solid = spPr.find(qn("a:solidFill"))
    if solid is None:
        return
    clr = solid.find(qn("a:srgbClr"))
    if clr is None:
        return
    for a in clr.findall(qn("a:alpha")):
        clr.remove(a)
    clr.append(clr.makeelement(qn("a:alpha"), {"val": str(int(max(0.0, min(1.0, alpha)) * 100000))}))


def set_shape_name(shape: Any, name: str) -> None:
    """shape.name = name (3중 키 fg-{id})."""
    try:
        shape.name = name
    except Exception:  # noqa: BLE001
        pass
