"""저널 스타일 프리셋 — role → 스타일 결정론적 매핑 테이블.

Phase 1: nature_minimal, neurips_pastel 우선. ieee_classic/science_bold/grayscale_print는
Phase 4에서 보강한다. Stylist가 이 프리셋을 spec.stylesheet에 주입한다.
"""

from __future__ import annotations

from ..schema.style import Font, Stroke, StyleOverride, StyleSheet


def _box(fill: str, stroke: str = "#444444", width: float = 0.75) -> StyleOverride:
    return StyleOverride(fill=fill, stroke=Stroke(color=stroke, width_pt=width))


def _nature_minimal() -> StyleSheet:
    accent = "#E64B35"
    blue = "#3C5488"
    teal = "#00A087"
    return StyleSheet(
        name="nature_minimal",
        palette=["#3C5488", "#E64B35", "#4DBBD5", "#00A087", "#F39B7F", "#8491B4"],
        font_family="Arial",
        base_font_pt=7.0,
        title_font_pt=10.0,
        stroke_width_pt=0.75,
        corner_radius_mm=1.0,
        connector=Stroke(color="#555555", width_pt=0.75),
        background="#FFFFFF",
        role_styles={
            "box.input": _box("#EEF2F7", blue),
            "box.output": _box("#EEF2F7", blue),
            "box.process": _box("#FFFFFF", "#555555"),
            "box.model": _box("#FDECEA", accent),
            "box.data": _box("#E9F5F9", "#4DBBD5"),
            "box.decision": _box("#FFF7E6", "#D9A400"),
            "box.loss": _box("#FDECEA", accent),
            "box.note": _box("#F8F9FA", "#9AA0A6"),
            "text.title": StyleOverride(font=Font(family="Arial", size_pt=10.0, weight="bold", color="#1A1A1A")),
            "text.heading": StyleOverride(font=Font(family="Arial", size_pt=8.0, weight="bold", color="#333333")),
            "text.caption": StyleOverride(font=Font(family="Arial", size_pt=6.0, color="#666666")),
            "group.module": StyleOverride(stroke=Stroke(color=teal, width_pt=0.75)),
        },
        chart_rc={
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": False,
            "font.size": 7.0,
        },
    )


def _neurips_pastel() -> StyleSheet:
    return StyleSheet(
        name="neurips_pastel",
        palette=["#A1C9F4", "#FFB482", "#8DE5A1", "#FF9F9B", "#D0BBFF", "#FAB0E4"],
        font_family="Arial",
        base_font_pt=8.0,
        title_font_pt=11.0,
        stroke_width_pt=1.0,
        corner_radius_mm=2.0,
        connector=Stroke(color="#6C6C7A", width_pt=1.0),
        background="#FFFFFF",
        role_styles={
            "box.input": _box("#A1C9F4", "#4A7CB5", 1.0),
            "box.output": _box("#8DE5A1", "#3E9C5C", 1.0),
            "box.process": _box("#FFFFFF", "#6C6C7A", 1.0),
            "box.model": _box("#D0BBFF", "#7A5BC0", 1.0),
            "box.data": _box("#A1C9F4", "#4A7CB5", 1.0),
            "box.decision": _box("#FFB482", "#D17C3A", 1.0),
            "box.loss": _box("#FF9F9B", "#D05550", 1.0),
            "box.note": _box("#FAF7FF", "#B0A8C0", 1.0),
            "text.title": StyleOverride(font=Font(family="Arial", size_pt=11.0, weight="bold", color="#2A2A35")),
            "text.heading": StyleOverride(font=Font(family="Arial", size_pt=9.0, weight="bold", color="#3A3A45")),
            "group.module": StyleOverride(stroke=Stroke(color="#B0A8C0", width_pt=1.0)),
        },
        chart_rc={"axes.spines.top": False, "axes.spines.right": False, "font.size": 8.0},
    )


def _ieee_classic() -> StyleSheet:
    return StyleSheet(
        name="ieee_classic",
        palette=["#1F4E79", "#2E2E2E", "#7F7F7F", "#A6A6A6", "#404040", "#595959"],
        font_family="Times New Roman",
        base_font_pt=8.0,
        title_font_pt=10.0,
        stroke_width_pt=1.0,
        corner_radius_mm=0.0,  # 직각 모서리
        connector=Stroke(color="#2E2E2E", width_pt=1.0),
        background="#FFFFFF",
        role_styles={
            "box.input": _box("#FFFFFF", "#1F4E79", 1.0),
            "box.output": _box("#FFFFFF", "#1F4E79", 1.0),
            "box.process": _box("#FFFFFF", "#2E2E2E", 1.0),
            "box.model": _box("#EAEFF5", "#1F4E79", 1.0),
            "box.data": _box("#F2F2F2", "#7F7F7F", 1.0),
            "box.decision": _box("#FFFFFF", "#2E2E2E", 1.0),
            "box.loss": _box("#F2F2F2", "#2E2E2E", 1.0),
            "text.title": StyleOverride(font=Font(family="Times New Roman", size_pt=10.0, weight="bold", color="#000000")),
        },
        chart_rc={"axes.spines.top": True, "axes.spines.right": True, "font.size": 8.0},
    )


def _science_bold() -> StyleSheet:
    return StyleSheet(
        name="science_bold",
        palette=["#D7263D", "#1B998B", "#2E294E", "#F46036", "#E2C044", "#0B6E4F"],
        font_family="Arial",
        base_font_pt=8.0,
        title_font_pt=12.0,
        stroke_width_pt=1.25,
        corner_radius_mm=1.5,
        connector=Stroke(color="#2E294E", width_pt=1.25),
        background="#FFFFFF",
        role_styles={
            "box.input": _box("#FDE2E5", "#D7263D", 1.25),
            "box.output": _box("#D7F2EE", "#1B998B", 1.25),
            "box.process": _box("#FFFFFF", "#2E294E", 1.25),
            "box.model": _box("#E7E5F0", "#2E294E", 1.5),
            "box.data": _box("#FCEFD6", "#E2C044", 1.25),
            "box.loss": _box("#FDE2E5", "#D7263D", 1.25),
            "text.title": StyleOverride(font=Font(family="Arial", size_pt=12.0, weight="bold", color="#2E294E")),
        },
        chart_rc={"axes.spines.top": False, "axes.spines.right": False, "font.size": 8.0,
                  "lines.linewidth": 2.0},
    )


def _grayscale_print() -> StyleSheet:
    # connector role를 대시 패턴으로 구분 (흑백 인쇄 안전)
    return StyleSheet(
        name="grayscale_print",
        palette=["#FFFFFF", "#E6E6E6", "#CCCCCC", "#B3B3B3", "#999999", "#808080"],
        font_family="Arial",
        base_font_pt=8.0,
        title_font_pt=10.0,
        stroke_width_pt=1.0,
        corner_radius_mm=1.0,
        connector=Stroke(color="#333333", width_pt=1.0),
        background="#FFFFFF",
        role_styles={
            "box.input": _box("#F2F2F2", "#333333", 1.0),
            "box.output": _box("#E0E0E0", "#333333", 1.0),
            "box.process": _box("#FFFFFF", "#333333", 1.0),
            "box.model": _box("#D9D9D9", "#1A1A1A", 1.25),
            "box.data": _box("#ECECEC", "#555555", 1.0),
            "box.loss": _box("#D9D9D9", "#1A1A1A", 1.0),
            "connector.feedback": StyleOverride(stroke=Stroke(color="#333333", width_pt=1.0, dash="dash")),
            "connector.reference": StyleOverride(stroke=Stroke(color="#333333", width_pt=1.0, dash="dot")),
            "text.title": StyleOverride(font=Font(family="Arial", size_pt=10.0, weight="bold", color="#000000")),
        },
        chart_rc={"axes.spines.top": False, "axes.spines.right": False, "font.size": 8.0,
                  "image.cmap": "Greys"},
    )


def _flat() -> StyleSheet:
    """figurelabs 'Flat' 프리셋 — 굵은 솔리드 면, 그라데이션/그림자 없음, 둥근 모서리, sans."""
    blue, green, amber = "#3B82F6", "#22C55E", "#F59E0B"
    red, purple, teal = "#EF4444", "#8B5CF6", "#14B8A6"
    return StyleSheet(
        name="flat",
        palette=[blue, green, amber, red, purple, teal],
        font_family="Arial",
        base_font_pt=8.0,
        title_font_pt=12.0,
        stroke_width_pt=0.0,  # 외곽선 없이 솔리드 면
        corner_radius_mm=2.5,
        connector=Stroke(color="#94A3B8", width_pt=1.25),
        background="#FFFFFF",
        role_styles={
            "box.input": _box("#DBEAFE", blue, 0.0),
            "box.output": _box("#DCFCE7", green, 0.0),
            "box.process": _box("#F1F5F9", "#94A3B8", 0.0),
            "box.model": _box("#EDE9FE", purple, 0.0),
            "box.data": _box("#CCFBF1", teal, 0.0),
            "box.decision": _box("#FEF3C7", amber, 0.0),
            "box.loss": _box("#FEE2E2", red, 0.0),
            "box.note": _box("#F8FAFC", "#CBD5E1", 0.0),
            "text.title": StyleOverride(font=Font(family="Arial", size_pt=12.0, weight="bold", color="#0F172A")),
            "text.heading": StyleOverride(font=Font(family="Arial", size_pt=9.0, weight="bold", color="#1E293B")),
            "text.caption": StyleOverride(font=Font(family="Arial", size_pt=6.5, color="#64748B")),
            "group.module": StyleOverride(stroke=Stroke(color="#CBD5E1", width_pt=1.0)),
        },
        chart_rc={
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": False,
            "font.size": 8.0,
        },
    )


_PRESETS: dict[str, StyleSheet] = {
    "nature_minimal": _nature_minimal(),
    "neurips_pastel": _neurips_pastel(),
    "ieee_classic": _ieee_classic(),
    "science_bold": _science_bold(),
    "grayscale_print": _grayscale_print(),
    "flat": _flat(),
}


def get_preset(name: str) -> StyleSheet:
    if name not in _PRESETS:
        raise KeyError(f"알 수 없는 프리셋: {name} (가용: {sorted(_PRESETS)})")
    return _PRESETS[name].model_copy(deep=True)


def list_presets() -> list[dict]:
    """meta API용 — id/이름/팔레트 스와치."""
    return [
        {"id": name, "name": ss.name, "palette": ss.palette[:6]}
        for name, ss in _PRESETS.items()
    ]


def has_preset(name: str) -> bool:
    return name in _PRESETS
