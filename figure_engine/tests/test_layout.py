"""레이아웃 엔진 불변식 + 텍스트 줄바꿈 결정성."""

from __future__ import annotations

from figgen.layout import FontProvider, LayoutEngine
from figgen.schema import FigureSpec
from figgen.schema.style import Font

CONTAINER = ("row", "column", "grid", "group")


def _layout(spec_dict):
    return LayoutEngine().layout(FigureSpec.model_validate(spec_dict))


def _overlap_area(a, b):
    ix = max(0.0, min(a.right, b.right) - max(a.x, b.x))
    iy = max(0.0, min(a.bottom, b.bottom) - max(a.y, b.y))
    return ix * iy


def _assert_siblings_disjoint(spec: FigureSpec, lay):
    """모든 컨테이너(Free 제외)의 직속 자식 rect는 서로 겹치지 않아야 한다."""
    for node, _ in spec.iter_elements():
        if getattr(node, "type", None) not in CONTAINER:
            continue
        kids = [c.id for c in node.children if c.id in lay.rects]
        for i in range(len(kids)):
            for j in range(i + 1, len(kids)):
                area = _overlap_area(lay.rects[kids[i]], lay.rects[kids[j]])
                assert area < 0.5, f"{kids[i]}↔{kids[j]} 겹침 {area:.2f}㎟ in {node.id}"


def test_row_siblings_disjoint():
    d = {
        "figure_type": "method_diagram",
        "root": {"type": "row", "id": "root", "gap_mm": 6, "children": [
            {"type": "box", "id": "a", "label": "Alpha"},
            {"type": "box", "id": "b", "label": "Beta module name"},
            {"type": "box", "id": "c", "label": "Gamma"},
        ]},
    }
    spec = FigureSpec.model_validate(d)
    _assert_siblings_disjoint(spec, LayoutEngine().layout(spec))


def test_nested_grid_column_disjoint():
    d = {
        "figure_type": "concept",
        "root": {"type": "column", "id": "root", "gap_mm": 5, "children": [
            {"type": "text", "id": "t", "text": "Title", "text_role": "title"},
            {"type": "grid", "id": "g", "columns": 3, "gap_mm": 4, "children": [
                {"type": "box", "id": f"b{i}", "label": f"Cell {i}"} for i in range(6)
            ]},
        ]},
    }
    spec = FigureSpec.model_validate(d)
    _assert_siblings_disjoint(spec, LayoutEngine().layout(spec))


def test_canvas_width_fixed_height_auto():
    lay = _layout({
        "figure_type": "concept", "canvas": {"width_mm": 120},
        "root": {"type": "box", "id": "a", "label": "x"},
    })
    assert lay.canvas_w_mm == 120
    assert lay.canvas_h_mm > 0


def test_overflow_warning_emitted():
    # 좁은 캔버스에 넓은 내용 → overflow 경고
    d = {
        "figure_type": "method_diagram", "canvas": {"width_mm": 60},
        "root": {"type": "row", "id": "root", "gap_mm": 4, "children": [
            {"type": "box", "id": f"b{i}", "label": f"Long label block {i}"} for i in range(5)
        ]},
    }
    lay = _layout(d)
    assert any(w.kind == "overflow" for w in lay.warnings)


def test_wrap_determinism():
    fp = FontProvider()
    font = Font(family="Arial", size_pt=8)
    a = fp.measure_text("The quick brown fox jumps over", font, max_width_mm=25)
    b = fp.measure_text("The quick brown fox jumps over", font, max_width_mm=25)
    assert a.lines == b.lines
    assert len(a.lines) > 1  # 줄바꿈 발생
    assert a.width_mm == b.width_mm


def test_free_layout_positions_within_canvas():
    d = {
        "figure_type": "graphical_abstract",
        "canvas": {"width_mm": 160, "height_mm": 90},
        "root": {"type": "free", "id": "root", "items": [
            {"node": {"type": "box", "id": "p1", "label": "Problem"}, "x_frac": 0.2, "y_frac": 0.3},
            {"node": {"type": "box", "id": "p2", "label": "Method"}, "x_frac": 0.5, "y_frac": 0.5},
            {"node": {"type": "box", "id": "p3", "label": "Result"}, "x_frac": 0.8, "y_frac": 0.3},
        ]},
        "connectors": [{"id": "a1", "source": "p1", "target": "p2"}],
    }
    lay = _layout(d)
    for pid in ("p1", "p2", "p3"):
        r = lay.rects[pid]
        assert 0 <= r.x and r.right <= 160.01
        assert 0 <= r.y and r.bottom <= 90.01


def _all_within_canvas(lay, tol=0.5):
    for nid, r in lay.rects.items():
        assert r.x >= -tol, f"{nid} x={r.x} < 0"
        assert r.y >= -tol, f"{nid} y={r.y} < 0"
        assert r.right <= lay.canvas_w_mm + tol, f"{nid} right={r.right} > {lay.canvas_w_mm}"
        assert r.bottom <= lay.canvas_h_mm + tol, f"{nid} bottom={r.bottom} > {lay.canvas_h_mm}"


def test_empty_free_leaves_collapse_no_offcanvas():
    # MobileGPT-V2 회귀: box 대신 빈 free를 leaf로 남용한 method_diagram.
    # 예전엔 빈 free가 캔버스 폭/높이를 통째로 차지해 음수 좌표·전체 캔버스 선으로 깨졌다.
    def free_leaf(i):
        return {"type": "free", "id": f"f{i}", "items": [
            {"node": {"type": "free", "id": f"f{i}_n", "items": []},
             "x_frac": 0.5, "y_frac": 0.5}]}

    d = {
        "figure_type": "method_diagram",
        "root": {"type": "row", "id": "root", "gap_mm": 10, "padding_mm": 8,
                 "children": [free_leaf(i) for i in range(8)]},
        "connectors": [
            {"id": f"c{i}", "source": f"f{i}", "target": f"f{i+1}", "routing": "straight"}
            for i in range(7)
        ],
    }
    lay = _layout(d)
    _all_within_canvas(lay)
    assert lay.canvas_h_mm < 280.0  # CANVAS_MAX_H 미만 (예전엔 280 클램프 + 넘침)
    # 빈 free는 0크기로 붕괴
    assert lay.rects["f0"].w < 1.0 and lay.rects["f0"].h < 1.0
    # 콘텐츠 leaf가 없음을 critical로 경고
    assert any(w.kind == "empty_content" and w.severity == "critical" for w in lay.warnings)
    # 모든 커넥터가 정상 길이로 그려짐(생략 없음)
    assert len(lay.connector_paths) == 7


def test_tall_overflow_rescales_within_canvas():
    # 자연 높이가 CANVAS_MAX_H를 넘는 세로 스택 → 균일 축소로 캔버스 안에 수용.
    d = {
        "figure_type": "method_diagram",
        "root": {"type": "column", "id": "root", "gap_mm": 6, "children": [
            {"type": "box", "id": f"b{i}", "label": f"Stage {i}",
             "size_hint": {"height_mm": 40}} for i in range(10)
        ]},
    }
    lay = _layout(d)
    assert lay.canvas_h_mm <= 280.0 + 0.01
    _all_within_canvas(lay)
    assert any(w.kind == "canvas_exceeded" for w in lay.warnings)


def test_fit_font_size_shrinks():
    fp = FontProvider()
    from figgen.layout.text_metrics import Size

    big = Font(family="Arial", size_pt=20)
    fitted = fp.fit_font_size("A long-ish label", Size(w=20, h=8), big, min_pt=4)
    assert 4 <= fitted <= 20
