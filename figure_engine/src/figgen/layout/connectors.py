"""rect 확정 후 connector 기하 라우팅.

PPTX는 동일 side 결정 로직을 공유하되 직선/elbow는 네이티브 커넥터(begin/end_connect)로,
curve는 freeform으로 렌더하도록 ``ConnectorPath``에 side 정보를 보존한다.
"""

from __future__ import annotations

from collections import defaultdict

from ..schema.figure_spec import Connector, FigureSpec
from .types import ConnectorPath, Rect, Side

_CURVE_PULL_MM = 12.0
# 한 변의 길이가 캔버스 해당 축의 이 비율을 넘으면 '과대'로 보고 부착점을 중앙 밴드로 클램프.
_OVERSIZE_FRAC = 0.6
_FRAC_BAND = (0.3, 0.7)
# 결과 코드 길이가 캔버스 대각선의 이 배수를 넘는 커넥터는 비정상으로 보고 생략.
_MAX_CHORD_FACTOR = 1.3


def route_connectors(spec: FigureSpec, rects: dict[str, Rect]) -> dict[str, ConnectorPath]:
    paths: dict[str, ConnectorPath] = {}

    root_rect = rects.get(spec.root.id)
    canvas_w = root_rect.w if root_rect else spec.canvas.width_mm
    canvas_h = root_rect.h if root_rect else (spec.canvas.height_mm or canvas_w)
    diag = (canvas_w**2 + canvas_h**2) ** 0.5 or 1.0

    # 1) side 결정
    resolved: dict[str, tuple[Side, Side]] = {}
    for c in spec.connectors:
        if c.source not in rects or c.target not in rects:
            continue
        resolved[c.id] = _resolve_sides(c, rects[c.source], rects[c.target])

    # 2) 동일 (node, side)에 붙는 커넥터 수 집계 → 균등 분산 인덱스
    side_occupancy: dict[tuple[str, Side], list[str]] = defaultdict(list)
    for c in spec.connectors:
        if c.id not in resolved:
            continue
        ss, ts = resolved[c.id]
        side_occupancy[(c.source, ss)].append(c.id)
        side_occupancy[(c.target, ts)].append(c.id)

    def _frac(node_id: str, side: Side, conn_id: str) -> float:
        members = side_occupancy[(node_id, side)]
        i = members.index(conn_id)
        return (i + 1) / (len(members) + 1)

    # 3) 경로 생성
    for c in spec.connectors:
        if c.id not in resolved:
            continue
        ss, ts = resolved[c.id]
        sr, tr = rects[c.source], rects[c.target]
        p_src = _side_point(sr, ss, _clamp_frac(_frac(c.source, ss, c.id), ss, sr, canvas_w, canvas_h))
        p_tgt = _side_point(tr, ts, _clamp_frac(_frac(c.target, ts, c.id), ts, tr, canvas_w, canvas_h))
        # degenerate: 캔버스 대각선을 크게 넘는 커넥터는 생략(diagnostics가 경고로 노출)
        chord = ((p_src[0] - p_tgt[0]) ** 2 + (p_src[1] - p_tgt[1]) ** 2) ** 0.5
        if chord > _MAX_CHORD_FACTOR * diag:
            continue
        pts = _build_path(c, ss, ts, p_src, p_tgt)
        paths[c.id] = ConnectorPath(
            points=pts,
            arrow_at=c.arrow,
            routing=c.routing,
            label_anchor=_longest_mid(pts) if c.label else None,
            src_side=ss,
            tgt_side=ts,
        )
    return paths


def _clamp_frac(frac: float, side: Side, r: Rect, canvas_w: float, canvas_h: float) -> float:
    """과대한 변에 붙는 부착점 비율을 중앙 밴드로 제한(전체 캔버스 세로/가로선 방지)."""
    lo, hi = _FRAC_BAND
    if side in ("left", "right") and r.h > _OVERSIZE_FRAC * canvas_h:
        return min(max(frac, lo), hi)
    if side in ("top", "bottom") and r.w > _OVERSIZE_FRAC * canvas_w:
        return min(max(frac, lo), hi)
    return frac


def _resolve_sides(c: Connector, sr: Rect, tr: Rect) -> tuple[Side, Side]:
    if c.source_side != "auto" and c.target_side != "auto":
        return c.source_side, c.target_side  # type: ignore[return-value]
    dx = tr.cx - sr.cx
    dy = tr.cy - sr.cy
    if abs(dx) >= abs(dy):
        ss, ts = ("right", "left") if dx >= 0 else ("left", "right")
    else:
        ss, ts = ("bottom", "top") if dy >= 0 else ("top", "bottom")
    if c.source_side != "auto":
        ss = c.source_side  # type: ignore[assignment]
    if c.target_side != "auto":
        ts = c.target_side  # type: ignore[assignment]
    return ss, ts  # type: ignore[return-value]


def _side_point(r: Rect, side: Side, frac: float) -> tuple[float, float]:
    if side == "left":
        return (r.x, r.y + frac * r.h)
    if side == "right":
        return (r.right, r.y + frac * r.h)
    if side == "top":
        return (r.x + frac * r.w, r.y)
    return (r.x + frac * r.w, r.bottom)  # bottom


def _is_horizontal(side: Side) -> bool:
    return side in ("left", "right")


def _build_path(
    c: Connector,
    ss: Side,
    ts: Side,
    p_src: tuple[float, float],
    p_tgt: tuple[float, float],
) -> list[tuple[float, float]]:
    if c.routing == "straight":
        return [p_src, p_tgt]
    if c.routing == "curve":
        return _bezier(ss, ts, p_src, p_tgt)
    return _elbow(ss, ts, p_src, p_tgt)


def _elbow(
    ss: Side, ts: Side, p_src: tuple[float, float], p_tgt: tuple[float, float]
) -> list[tuple[float, float]]:
    sx, sy = p_src
    tx, ty = p_tgt
    sh, th = _is_horizontal(ss), _is_horizontal(ts)
    if sh and th:  # 수평-수평 → 수직 중간선
        midx = (sx + tx) / 2
        return [p_src, (midx, sy), (midx, ty), p_tgt]
    if not sh and not th:  # 수직-수직 → 수평 중간선
        midy = (sy + ty) / 2
        return [p_src, (sx, midy), (tx, midy), p_tgt]
    # 혼합 → 단일 코너
    if sh:  # source 수평, target 수직
        return [p_src, (tx, sy), p_tgt]
    return [p_src, (sx, ty), p_tgt]  # source 수직, target 수평


def _bezier(
    ss: Side, ts: Side, p_src: tuple[float, float], p_tgt: tuple[float, float]
) -> list[tuple[float, float]]:
    sx, sy = p_src
    tx, ty = p_tgt
    c1 = _offset_along_normal(p_src, ss, _CURVE_PULL_MM)
    c2 = _offset_along_normal(p_tgt, ts, _CURVE_PULL_MM)
    return [p_src, c1, c2, p_tgt]  # [p0, c1, c2, p3]


def _offset_along_normal(p: tuple[float, float], side: Side, d: float) -> tuple[float, float]:
    x, y = p
    if side == "left":
        return (x - d, y)
    if side == "right":
        return (x + d, y)
    if side == "top":
        return (x, y - d)
    return (x, y + d)


def _longest_mid(pts: list[tuple[float, float]]) -> tuple[float, float]:
    if len(pts) < 2:
        return pts[0]
    best = (pts[0], pts[1])
    best_len = -1.0
    for a, b in zip(pts, pts[1:], strict=False):
        d = (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
        if d > best_len:
            best_len = d
            best = (a, b)
    return ((best[0][0] + best[1][0]) / 2, (best[0][1] + best[1][1]) / 2)
