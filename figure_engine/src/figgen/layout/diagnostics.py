"""결정론적 레이아웃 문제 감지 — critic의 입력.

트리 형제 비겹침은 엔진이 보장하므로, 여기서는 Free 배치·아이콘 등 비형제 겹침과
박스 텍스트 잘림을 코드로 정확히 감지한다(VLM보다 픽셀 판정이 정확).
"""

from __future__ import annotations

from pydantic import BaseModel

from ..schema.figure_spec import FigureSpec
from .text_metrics import FontProvider
from .types import LayoutWarning, Rect, ResolvedLayout

_LEAF_TYPES = ("box", "text", "image", "chart")
_OVERLAP_RATIO = 0.05
_CLIP_TOL_MM = 0.5


def _leaves(spec: FigureSpec) -> list[BaseModel]:
    return [n for n, _ in spec.iter_elements() if getattr(n, "type", None) in _LEAF_TYPES]


def _intersection(a: Rect, b: Rect) -> float:
    ix = max(0.0, min(a.right, b.right) - max(a.x, b.x))
    iy = max(0.0, min(a.bottom, b.bottom) - max(a.y, b.y))
    return ix * iy


def detect_overlaps(layout: ResolvedLayout, spec: FigureSpec) -> list[LayoutWarning]:
    warns: list[LayoutWarning] = []
    leaves = [n for n in _leaves(spec) if n.id in layout.rects]  # type: ignore[attr-defined]
    for i in range(len(leaves)):
        for j in range(i + 1, len(leaves)):
            a, b = leaves[i], leaves[j]
            # 텍스트 라벨을 이미지 위에 얹는 것은 정상(장면/graphical_abstract 오버레이) — 제외
            if {getattr(a, "type", None), getattr(b, "type", None)} == {"image", "text"}:
                continue
            ra, rb = layout.rects[a.id], layout.rects[b.id]  # type: ignore[attr-defined]
            inter = _intersection(ra, rb)
            if inter <= 0:
                continue
            ratio = inter / max(1e-6, min(ra.w * ra.h, rb.w * rb.h))
            if ratio > _OVERLAP_RATIO:
                warns.append(
                    LayoutWarning(
                        kind="overlap",
                        element_ids=[a.id, b.id],  # type: ignore[attr-defined]
                        detail=f"겹침 {ratio * 100:.0f}%",
                        severity="major" if ratio > 0.2 else "minor",
                    )
                )
    return warns


def check_text_fit(
    layout: ResolvedLayout, spec: FigureSpec, fonts: FontProvider
) -> list[LayoutWarning]:
    from ..schema.style import StyleSheet, resolve_style

    ss = spec.stylesheet or StyleSheet(name="_default")
    warns: list[LayoutWarning] = []
    for node, _ in spec.iter_elements():
        t = getattr(node, "type", None)
        if t not in ("box", "text"):
            continue
        if node.id not in layout.rects:  # type: ignore[attr-defined]
            continue
        rect = layout.rects[node.id]  # type: ignore[attr-defined]
        text = node.label if t == "box" else node.text  # type: ignore[attr-defined]
        if not text:
            continue
        font = resolve_style(node, ss).font
        avail_w = rect.w - (8.0 if t == "box" else 0.0)
        tm = fonts.measure_text(text, font, max_width_mm=avail_w if avail_w > 0 else None)
        if tm.width_mm > rect.w + _CLIP_TOL_MM or tm.height_mm > rect.h + _CLIP_TOL_MM:
            warns.append(
                LayoutWarning(
                    kind="text_clipping",
                    element_ids=[node.id],  # type: ignore[attr-defined]
                    detail=f"텍스트 {tm.width_mm:.0f}×{tm.height_mm:.0f} > 박스 {rect.w:.0f}×{rect.h:.0f}",
                    severity="major",
                )
            )
    return warns


def check_connectors(layout: ResolvedLayout, spec: FigureSpec) -> list[LayoutWarning]:
    """라우팅에서 생략된(비정상 기하) 커넥터를 경고로 노출 — silent 붕괴 방지."""
    warns: list[LayoutWarning] = []
    drawn = set(layout.connector_paths)
    for c in spec.connectors:
        if c.id in drawn:
            continue
        if c.source in layout.rects and c.target in layout.rects:
            warns.append(
                LayoutWarning(
                    kind="connector_crossing",
                    element_ids=[c.source, c.target],
                    detail=f"커넥터 {c.id} 생략(과도한 길이/비정상 기하)",
                    severity="major",
                )
            )
    return warns


def check_content(spec: FigureSpec) -> list[LayoutWarning]:
    """그릴 콘텐츠 leaf(box/text/image/chart)가 전혀 없는 스펙을 경고.

    method_diagram/concept에서 box 대신 빈 free를 leaf로 남용하면 화면이 비어
    보이거나 깨진다 — 업스트림(planner) 문제를 표면화한다.
    """
    if spec.figure_type not in ("method_diagram", "concept"):
        return []
    leaves = [n for n, _ in spec.iter_elements() if getattr(n, "type", None) in _LEAF_TYPES]
    if leaves:
        return []
    return [
        LayoutWarning(
            kind="empty_content",
            element_ids=[spec.root.id],
            detail="콘텐츠 box/text가 없습니다(빈 free 남용 가능) — 스펙 확인 필요",
            severity="critical",
        )
    ]


def nudge_free_items(
    layout: ResolvedLayout, spec: FigureSpec, max_iters: int = 20
) -> ResolvedLayout:
    """Free 영역 내 겹침을 최소 침투 축 분리로 휴리스틱 해소(경계 클램프)."""
    free_ids: list[str] = []
    for node, _ in spec.iter_elements():
        if getattr(node, "type", None) == "free":
            free_ids.extend(it.node.id for it in node.items)  # type: ignore[attr-defined]
    movable = [i for i in free_ids if i in layout.rects]
    for _ in range(max_iters):
        moved = False
        for a in range(len(movable)):
            for b in range(a + 1, len(movable)):
                ra, rb = layout.rects[movable[a]], layout.rects[movable[b]]
                if _intersection(ra, rb) <= 0:
                    continue
                ox = min(ra.right, rb.right) - max(ra.x, rb.x)
                oy = min(ra.bottom, rb.bottom) - max(ra.y, rb.y)
                if ox < oy:  # x축으로 분리
                    shift = ox / 2 + 0.5
                    if ra.cx <= rb.cx:
                        ra.x -= shift
                        rb.x += shift
                    else:
                        ra.x += shift
                        rb.x -= shift
                else:
                    shift = oy / 2 + 0.5
                    if ra.cy <= rb.cy:
                        ra.y -= shift
                        rb.y += shift
                    else:
                        ra.y += shift
                        rb.y -= shift
                _clamp(ra, layout)
                _clamp(rb, layout)
                moved = True
        if not moved:
            break
    return layout


def _clamp(r: Rect, layout: ResolvedLayout) -> None:
    r.x = min(max(r.x, 0.0), max(0.0, layout.canvas_w_mm - r.w))
    r.y = min(max(r.y, 0.0), max(0.0, layout.canvas_h_mm - r.h))
