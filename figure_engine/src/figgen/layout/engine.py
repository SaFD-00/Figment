"""FigureSpec → 절대좌표 ResolvedLayout 변환 (2-pass measure/arrange).

bottom-up measure(텍스트 PIL 실측 포함) → top-down arrange(weight 비례 shrink, justify/align).
트리 구조상 형제 겹침이 원천 차단된다. 캔버스 폭 고정, 높이 자동 산출.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..schema.figure_spec import FigureSpec
from ..schema.style import Font, StyleSheet, resolve_style
from ..units import BOX_ICON_MM
from .connectors import route_connectors
from .diagnostics import check_connectors, check_content, check_text_fit, detect_overlaps
from .text_metrics import FontProvider, Size
from .types import LayoutWarning, Rect, ResolvedLayout

# 박스 내부 여백 / 기본 최소 크기 (mm)
PAD_X = 4.0
PAD_Y = 3.0
BOX_MIN_W = 22.0
BOX_MIN_H = 10.0
IMAGE_DEFAULT = (24.0, 24.0)
CHART_DEFAULT = (60.0, 45.0)
CANVAS_MAX_H = 280.0
GROUP_LABEL_PAD = 2.0


class LayoutEngine:
    def __init__(self, fonts: FontProvider | None = None):
        self.fonts = fonts or FontProvider()

    def layout(self, spec: FigureSpec) -> ResolvedLayout:
        self._spec = spec
        self._ss: StyleSheet = spec.stylesheet or StyleSheet(name="_default")
        self._sizes: dict[str, Size] = {}
        self._rects: dict[str, Rect] = {}
        self._warnings: list[LayoutWarning] = []
        self._min_cache: dict[tuple[str, bool], float] = {}

        canvas_w = spec.canvas.width_mm
        root_size = self._measure(spec.root, canvas_w)
        if spec.canvas.height_mm is not None:
            canvas_h = spec.canvas.height_mm
            self._arrange(spec.root, Rect(x=0, y=0, w=canvas_w, h=canvas_h))
        elif root_size.h > CANVAS_MAX_H:
            # 자연 높이로 배치한 뒤 캔버스에 맞춰 모든 rect를 균일 축소한다.
            # (예전엔 canvas_h만 클램프 → 자식이 음수 좌표/캔버스 밖으로 튀어 렌더가 깨졌다.)
            self._arrange(spec.root, Rect(x=0, y=0, w=canvas_w, h=root_size.h))
            self._rescale_rects(CANVAS_MAX_H / root_size.h, canvas_w)
            canvas_h = CANVAS_MAX_H
            self._warnings.append(
                LayoutWarning(
                    kind="canvas_exceeded",
                    element_ids=[spec.root.id],
                    detail=f"root 높이 {root_size.h:.0f}mm > {CANVAS_MAX_H}mm 균일 축소",
                    severity="major",
                )
            )
        else:
            canvas_h = root_size.h
            self._arrange(spec.root, Rect(x=0, y=0, w=canvas_w, h=canvas_h))

        conn = route_connectors(spec, self._rects)
        layout = ResolvedLayout(
            rects=self._rects,
            z_order=self._z_order(spec),
            connector_paths=conn,
            canvas_w_mm=canvas_w,
            canvas_h_mm=canvas_h,
            warnings=self._warnings,
        )
        # 결정론적 진단 (Free 겹침 + 텍스트 잘림 + 커넥터 붕괴 + 빈 콘텐츠)
        layout.warnings.extend(detect_overlaps(layout, spec))
        layout.warnings.extend(check_text_fit(layout, spec, self.fonts))
        layout.warnings.extend(check_connectors(layout, spec))
        layout.warnings.extend(check_content(spec))
        return layout

    # ── 폰트 ──────────────────────────────────────────────────────────────────
    def _font(self, node: BaseModel) -> Font:
        return resolve_style(node, self._ss).font

    def _sub_font(self, node: BaseModel) -> Font:
        f = self._font(node)
        return f.model_copy(update={"size_pt": max(5.0, f.size_pt * 0.8), "color": "#666666"})

    # ── 최소 주축 크기 (문자 단위 줄바꿈 방지용 하한) ──────────────────────────────
    def _min_main(self, node: BaseModel, want_width: bool) -> float:
        key = (node.id, want_width)  # type: ignore[attr-defined]
        cached = self._min_cache.get(key)
        if cached is not None:
            return cached
        val = self._compute_min_main(node, want_width)
        self._min_cache[key] = val
        return val

    def _compute_min_main(self, node: BaseModel, want_width: bool) -> float:
        t = node.type  # type: ignore[attr-defined]
        s = self._sizes.get(node.id)  # type: ignore[attr-defined]
        if t == "box":
            return self._box_min_w(node) if want_width else (s.h if s else BOX_MIN_H)
        if t == "text":
            return self._text_min_w(node) if want_width else (s.h if s else 0.0)
        if t in ("image", "chart", "free", "grid"):
            if not s:
                return 0.0
            return s.w if want_width else s.h
        # row / column / group
        pad = node.padding_mm  # type: ignore[attr-defined]
        gap = node.gap_mm  # type: ignore[attr-defined]
        kids = node.children  # type: ignore[attr-defined]
        is_row = t == "row" or (t == "group" and node.direction == "row")  # type: ignore[attr-defined]
        mins = [self._min_main(c, want_width) for c in kids]
        along = (is_row and want_width) or (not is_row and not want_width)
        base = (sum(mins) + gap * max(0, len(kids) - 1)) if along else max(mins, default=0.0)
        extra = self._group_label_h(node) if (t == "group" and not want_width) else 0.0
        return base + 2 * pad + extra

    def _box_min_w(self, node: BaseModel) -> float:
        font = self._font(node)
        label = node.label or ""  # type: ignore[attr-defined]
        w = self.fonts.longest_word_width_mm(label, font) if label else 0.0
        if getattr(node, "sublabel", None):
            w = max(w, self.fonts.longest_word_width_mm(node.sublabel, self._sub_font(node)))  # type: ignore[attr-defined]
        s = self._sizes.get(node.id)  # type: ignore[attr-defined]
        cap = s.w if s else BOX_MIN_W
        return min(cap, w + 2 * PAD_X)

    def _text_min_w(self, node: BaseModel) -> float:
        font = self._font(node)
        w = self.fonts.longest_word_width_mm(node.text, font)  # type: ignore[attr-defined]
        s = self._sizes.get(node.id)  # type: ignore[attr-defined]
        return min(s.w if s else w, w)

    # ── measure (bottom-up) ────────────────────────────────────────────────────
    def _measure(self, node: BaseModel, avail_w: float) -> Size:
        t = node.type  # type: ignore[attr-defined]
        if t == "box":
            size = self._measure_box(node, avail_w)
        elif t == "text":
            size = self._measure_text(node, avail_w)
        elif t == "image":
            size = Size(w=IMAGE_DEFAULT[0], h=IMAGE_DEFAULT[1])
        elif t == "chart":
            size = Size(w=CHART_DEFAULT[0], h=CHART_DEFAULT[1])
        elif t == "grid":
            size = self._measure_grid(node, avail_w)
        elif t in ("row", "column", "group"):
            size = self._measure_linear(node, avail_w)
        elif t == "free":
            size = self._measure_free(node, avail_w)
        else:  # pragma: no cover
            size = Size(w=10, h=10)
        size = self._apply_size_hint(node, size)
        self._sizes[node.id] = size  # type: ignore[attr-defined]
        return size

    def _apply_size_hint(self, node: BaseModel, size: Size) -> Size:
        sh = getattr(node, "size_hint", None)
        if not sh:
            return size
        w, h = size.w, size.h
        if sh.width_mm is not None:
            w = sh.width_mm
        if sh.height_mm is not None:
            h = sh.height_mm
        if sh.aspect:
            if sh.width_mm is not None and sh.height_mm is None:
                h = w / sh.aspect
            elif sh.height_mm is not None and sh.width_mm is None:
                w = h * sh.aspect
        if sh.min_width_mm is not None:
            w = max(w, sh.min_width_mm)
        if sh.min_height_mm is not None:
            h = max(h, sh.min_height_mm)
        return Size(w=w, h=h)

    def _measure_box(self, node: BaseModel, avail_w: float) -> Size:
        font = self._font(node)
        label = node.label or ""  # type: ignore[attr-defined]
        maxw = None
        sh = node.size_hint  # type: ignore[attr-defined]
        if sh and sh.width_mm:
            maxw = max(1.0, sh.width_mm - 2 * PAD_X)
        tm = self.fonts.measure_text(label, font, maxw) if label else None
        tw = tm.width_mm if tm else 0.0
        th = tm.height_mm if tm else 0.0
        sw = sh_h = 0.0
        if getattr(node, "sublabel", None):
            sm = self.fonts.measure_text(node.sublabel, self._sub_font(node), maxw)  # type: ignore[attr-defined]
            sw, sh_h = sm.width_mm, sm.height_mm + 1.0
        w = max(tw, sw) + 2 * PAD_X
        h = th + sh_h + 2 * PAD_Y
        if getattr(node, "icon_asset", None):  # 상단 아이콘 영역 확보(M4.3)
            h += BOX_ICON_MM + 1.5
            w = max(w, BOX_ICON_MM + 2 * PAD_X)
        return Size(w=max(w, BOX_MIN_W), h=max(h, BOX_MIN_H))

    def _measure_text(self, node: BaseModel, avail_w: float) -> Size:
        font = self._font(node)
        maxw = node.max_width_mm or (avail_w if avail_w > 0 else None)  # type: ignore[attr-defined]
        tm = self.fonts.measure_text(node.text, font, maxw)  # type: ignore[attr-defined]
        return Size(w=tm.width_mm, h=tm.height_mm)

    def _measure_linear(self, node: BaseModel, avail_w: float) -> Size:
        is_row = node.type == "row" or (
            node.type == "group" and node.direction == "row"  # type: ignore[attr-defined]
        )
        pad = node.padding_mm  # type: ignore[attr-defined]
        gap = node.gap_mm  # type: ignore[attr-defined]
        inner_avail = max(1.0, avail_w - 2 * pad)
        children = node.children  # type: ignore[attr-defined]
        sizes = [self._measure(c, inner_avail) for c in children]
        n = len(sizes)
        if is_row:
            w = sum(s.w for s in sizes) + gap * max(0, n - 1)
            h = max((s.h for s in sizes), default=0.0)
        else:
            w = max((s.w for s in sizes), default=0.0)
            h = sum(s.h for s in sizes) + gap * max(0, n - 1)
        w += 2 * pad
        h += 2 * pad
        if node.type == "group":
            lab_h = self._group_label_h(node)
            h += lab_h
            if node.label:  # type: ignore[attr-defined]
                lw = self.fonts.measure_text(
                    node.label, self._ss.base_font(role="heading")  # type: ignore[attr-defined]
                ).width_mm
                w = max(w, lw + 2 * pad)
        return Size(w=w, h=h)

    def _group_label_h(self, node: BaseModel) -> float:
        if not getattr(node, "label", None):
            return 0.0
        tm = self.fonts.measure_text(node.label, self._ss.base_font(role="heading"))  # type: ignore[attr-defined]
        return tm.height_mm + GROUP_LABEL_PAD

    def _measure_grid(self, node: BaseModel, avail_w: float) -> Size:
        pad = node.padding_mm  # type: ignore[attr-defined]
        gap = node.gap_mm  # type: ignore[attr-defined]
        cols = node.columns  # type: ignore[attr-defined]
        children = node.children  # type: ignore[attr-defined]
        cell_avail = max(1.0, (avail_w - 2 * pad - gap * (cols - 1)) / cols)
        sizes = [self._measure(c, cell_avail) for c in children]
        rows = (len(sizes) + cols - 1) // cols
        col_w = [0.0] * cols
        row_h = [0.0] * rows
        for i, s in enumerate(sizes):
            r, c = divmod(i, cols)
            col_w[c] = max(col_w[c], s.w)
            row_h[r] = max(row_h[r], s.h)
        w = sum(col_w) + gap * (cols - 1) + 2 * pad
        h = sum(row_h) + gap * max(0, rows - 1) + 2 * pad
        self._grid_meta = getattr(self, "_grid_meta", {})
        self._grid_meta[node.id] = (col_w, row_h, cols)  # type: ignore[attr-defined]
        return Size(w=w, h=h)

    def _measure_free(self, node: BaseModel, avail_w: float) -> Size:
        items = node.items  # type: ignore[attr-defined]
        child_sizes = [self._measure(item.node, avail_w) for item in items]
        # 빈 Free, 또는 모든 자식이 0크기(빈 Free 중첩 등)면 0으로 붕괴한다.
        # method_diagram에서 box 대신 빈 free를 leaf로 남용한 스펙이 캔버스 폭/높이를
        # 통째로 차지해 음수 좌표·전체 캔버스 선으로 깨지는 것을 원천 차단한다.
        # graphical_abstract 루트는 실제 image/box item을 가지므로 avail 채움을 유지.
        has_content = any(cs.w > 0 or cs.h > 0 for cs in child_sizes)
        if not items or not has_content:
            return Size(w=0.0, h=0.0)
        sh = node.size_hint  # type: ignore[attr-defined]
        h = sh.height_mm if (sh and sh.height_mm) else avail_w * 0.6
        return Size(w=avail_w, h=h)

    # ── arrange (top-down) ──────────────────────────────────────────────────────
    def _arrange(self, node: BaseModel, rect: Rect) -> None:
        self._rects[node.id] = rect  # type: ignore[attr-defined]
        t = node.type  # type: ignore[attr-defined]
        if t in ("box", "text", "image", "chart"):
            return
        if t == "free":  # Free는 ContainerBase가 아님(padding/gap 없음) — 전체 rect 사용
            self._arrange_free(node, rect)
            return
        pad = node.padding_mm  # type: ignore[attr-defined]
        inner = Rect(x=rect.x + pad, y=rect.y + pad, w=rect.w - 2 * pad, h=rect.h - 2 * pad)
        if t == "group":
            lab_h = self._group_label_h(node)
            inner = Rect(x=inner.x, y=inner.y + lab_h, w=inner.w, h=max(1.0, inner.h - lab_h))
        if t == "grid":
            self._arrange_grid(node, inner)
        else:
            is_row = t == "row" or (t == "group" and node.direction == "row")  # type: ignore[attr-defined]
            self._arrange_linear(node, inner, main_x=is_row)

    def _arrange_linear(self, node: BaseModel, inner: Rect, *, main_x: bool) -> None:
        children = node.children  # type: ignore[attr-defined]
        gap = node.gap_mm  # type: ignore[attr-defined]
        justify = node.justify  # type: ignore[attr-defined]
        align = node.align  # type: ignore[attr-defined]
        n = len(children)
        if n == 0:
            return
        sizes = [self._sizes[c.id] for c in children]
        main_pref = [s.w if main_x else s.h for s in sizes]
        cross_pref = [s.h if main_x else s.w for s in sizes]
        inner_main = inner.w if main_x else inner.h
        inner_cross = inner.h if main_x else inner.w
        total = sum(main_pref) + gap * (n - 1)
        extra = inner_main - total

        main_size = list(main_pref)
        gap_eff = gap
        offset = 0.0
        if extra >= 0:
            if justify == "space_between" and n > 1:
                gap_eff = gap + extra / (n - 1)
            elif justify == "start":
                offset = 0.0
            elif justify == "end":
                offset = extra
            else:  # center
                offset = extra / 2
        else:
            # 폭 부족 — 우선순위: ① gap을 min_gap까지 압축, ② 박스 여유분(slack) 축소,
            # ③ 그래도 부족하면 최소폭(단어폭) 비례 축소. 박스는 가능한 한 '가장 긴 단어 폭'
            # 이상을 유지하고, 최종 가독성은 resolver의 폰트 자동 맞춤이 보장한다.
            deficit = -extra  # = total - inner_main (gap*(n-1) 포함)
            min_gap = min(gap, 3.0)
            gap_give = (gap - min_gap) * (n - 1) if n > 1 else 0.0
            if deficit <= gap_give:
                gap_eff = gap - deficit / (n - 1)
                severity = "minor"  # gap만으로 흡수 — 박스는 preferred 유지
            else:
                gap_eff = min_gap
                remaining = deficit - gap_give
                floors = [min(self._min_main(children[i], main_x), main_pref[i])
                          for i in range(n)]
                slack = [main_pref[i] - floors[i] for i in range(n)]
                total_slack = sum(slack)
                if remaining <= total_slack and total_slack > 1e-6:
                    for i in range(n):
                        main_size[i] = main_pref[i] - remaining * slack[i] / total_slack
                    severity = "minor"
                else:
                    rem2 = remaining - total_slack
                    ftot = sum(floors) or 1.0
                    for i in range(n):
                        main_size[i] = max(1.0, floors[i] - rem2 * floors[i] / ftot)
                    severity = "major"
            self._warnings.append(
                LayoutWarning(
                    kind="overflow",
                    element_ids=[node.id],  # type: ignore[attr-defined]
                    detail=f"내용 {total:.0f}mm > 가용 {inner_main:.0f}mm — 축소",
                    severity=severity,
                )
            )

        cur = (inner.x if main_x else inner.y) + offset
        for i, c in enumerate(children):
            ms = main_size[i]
            cs = inner_cross if align == "stretch" else cross_pref[i]
            if align == "start":
                co = 0.0
            elif align == "end":
                co = inner_cross - cs
            else:
                co = (inner_cross - cs) / 2
            if main_x:
                child_rect = Rect(x=cur, y=inner.y + co, w=ms, h=cs)
            else:
                child_rect = Rect(x=inner.x + co, y=cur, w=cs, h=ms)
            self._arrange(c, child_rect)
            cur += ms + gap_eff

    def _arrange_grid(self, node: BaseModel, inner: Rect) -> None:
        col_w, row_h, cols = self._grid_meta[node.id]  # type: ignore[attr-defined]
        gap = node.gap_mm  # type: ignore[attr-defined]
        align = node.align  # type: ignore[attr-defined]
        # 가용 폭에 맞춰 비례 스케일 (열 합이 inner.w를 넘으면 축소)
        total_w = sum(col_w) + gap * (cols - 1)
        scale = inner.w / total_w if total_w > inner.w else 1.0
        cw = [w * scale for w in col_w]
        y = inner.y
        children = node.children  # type: ignore[attr-defined]
        for r, rh in enumerate(row_h):
            x = inner.x
            for c in range(cols):
                idx = r * cols + c
                if idx >= len(children):
                    break
                child = children[idx]
                s = self._sizes[child.id]
                cell = Rect(x=x, y=y, w=cw[c], h=rh)
                # 셀 내 정렬 (center)
                w = min(s.w, cell.w) if align != "stretch" else cell.w
                h = min(s.h, cell.h) if align != "stretch" else cell.h
                rx = cell.x + (cell.w - w) / 2
                ry = cell.y + (cell.h - h) / 2
                self._arrange(child, Rect(x=rx, y=ry, w=w, h=h))
                x += cw[c] + gap
            y += rh + gap

    def _arrange_free(self, node: BaseModel, rect: Rect) -> None:
        for item in node.items:  # type: ignore[attr-defined]
            c = item.node
            s = self._sizes[c.id]
            w = item.w_frac * rect.w if item.w_frac else s.w
            h = item.h_frac * rect.h if item.h_frac else s.h
            px = rect.x + item.x_frac * rect.w
            py = rect.y + item.y_frac * rect.h
            if item.anchor == "center":
                px -= w / 2
                py -= h / 2
            px = min(max(px, rect.x), rect.right - w)
            py = min(max(py, rect.y), rect.bottom - h)
            self._arrange(c, Rect(x=px, y=py, w=w, h=h))

    def _rescale_rects(self, s: float, canvas_w: float) -> None:
        """모든 rect를 비율 s로 균일 축소하고 가로 중앙 정렬(오버플로 대응)."""
        x_off = (canvas_w - canvas_w * s) / 2.0
        for r in self._rects.values():
            r.x = r.x * s + x_off
            r.y = r.y * s
            r.w = r.w * s
            r.h = r.h * s

    # ── z-order ──────────────────────────────────────────────────────────────
    def _z_order(self, spec: FigureSpec) -> list[str]:
        order: list[tuple[int, int, str]] = []
        for i, (node, _) in enumerate(spec.iter_elements()):
            order.append((getattr(node, "z", 0), i, node.id))  # type: ignore[attr-defined]
        order.sort(key=lambda t: (t[0], t[1]))
        return [t[2] for t in order]
