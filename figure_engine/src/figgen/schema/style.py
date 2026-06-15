"""스타일 타입 + 저널 프리셋 스타일시트 모델 + 스타일 해석.

스타일은 Planner 출력에서 제거되고(Planner는 role만 태깅), Stylist가 프리셋의
``role_styles`` 테이블로 결정론적 변환한다. 우선순위:
**element.style override > role_styles[f'{type}.{role}'] > stylesheet 기본값.**
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ._types import HexColor

Dash = Literal["solid", "dash", "dot"]
FontWeight = Literal["regular", "medium", "bold"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Stroke(_Base):
    color: HexColor = "#333333"
    width_pt: float = 1.0
    dash: Dash = "solid"


class Font(_Base):
    family: str = "Arial"
    size_pt: float = 8.0
    weight: FontWeight = "regular"
    italic: bool = False
    color: HexColor = "#222222"


class StyleOverride(_Base):
    """요소별 부분 오버라이드 — 전 필드 Optional."""

    fill: HexColor | None = None
    fill_opacity: float | None = None
    stroke: Stroke | None = None
    font: Font | None = None
    corner_radius_mm: float | None = None


class StyleSheet(_Base):
    name: str
    palette: list[HexColor] = Field(default_factory=lambda: ["#4C72B0", "#DD8452", "#55A868"])
    role_styles: dict[str, StyleOverride] = Field(default_factory=dict)
    font_family: str = "Arial"
    base_font_pt: float = 8.0
    title_font_pt: float = 11.0
    stroke_width_pt: float = 1.0
    corner_radius_mm: float = 1.5
    connector: Stroke = Field(default_factory=lambda: Stroke(color="#555555", width_pt=1.0))
    arrowhead_scale: float = 1.0
    background: HexColor = "#FFFFFF"
    # matplotlib rcParams (차트 트랙 주입; svg.fonttype='none' 등)
    chart_rc: dict[str, Any] = Field(default_factory=dict)

    def base_font(self, *, role: str = "body") -> Font:
        size = self.title_font_pt if role in ("title", "heading") else self.base_font_pt
        return Font(family=self.font_family, size_pt=size)

    def chart_rcparams(self) -> dict[str, Any]:
        """차트 트랙용 rcParams — figure 본체와 폰트/배색 통일."""
        rc: dict[str, Any] = {
            "svg.fonttype": "none",  # SVG 텍스트를 <text>로 유지 (Illustrator 편집 가능)
            "font.family": self.font_family,
            "font.size": self.base_font_pt,
            "axes.edgecolor": "#333333",
            "axes.prop_cycle": _color_cycle(self.palette),
            "figure.facecolor": self.background,
            "axes.facecolor": self.background,
            "savefig.facecolor": self.background,
        }
        rc.update(self.chart_rc)
        return rc


def _color_cycle(palette: list[str]) -> str:
    # matplotlib cycler 문자열 표현 (runner에서 eval 없이 재구성)
    return "+".join(palette)


class ResolvedStyle(_Base):
    """렌더러가 소비하는 최종 해석 스타일 (요소 1개분)."""

    fill: HexColor | None = None
    fill_opacity: float = 1.0
    stroke_color: HexColor | None = "#333333"
    stroke_width_pt: float = 1.0
    stroke_dash: Dash = "solid"
    font: Font = Field(default_factory=Font)
    corner_radius_mm: float = 1.5


def resolve_style(element: Any, stylesheet: StyleSheet, *, text_role: str = "body") -> ResolvedStyle:
    """element.style > role_styles[type.role] > stylesheet 기본값 순으로 병합.

    figure_spec import 없이 duck-typing(getattr)으로 동작(순환 방지).
    """
    etype = getattr(element, "type", "")
    erole = getattr(element, "role", None)
    etext_role = getattr(element, "text_role", None) or text_role

    # 기본값 (stylesheet)
    rs = ResolvedStyle(
        fill=None,
        fill_opacity=1.0,
        stroke_color=stylesheet.connector.color if etype == "connector" else "#333333",
        stroke_width_pt=stylesheet.stroke_width_pt,
        stroke_dash="solid",
        font=stylesheet.base_font(role=etext_role if etype == "text" else "body"),
        corner_radius_mm=stylesheet.corner_radius_mm,
    )

    # role_styles 적용
    role_key = None
    if etype == "text":
        role_key = f"text.{etext_role}"
    elif erole:
        role_key = f"{etype}.{erole}"
    if role_key and role_key in stylesheet.role_styles:
        _apply_override(rs, stylesheet.role_styles[role_key])

    # element.style override (최우선)
    el_style = getattr(element, "style", None)
    if el_style is not None:
        _apply_override(rs, el_style)

    return rs


def _apply_override(rs: ResolvedStyle, ov: StyleOverride) -> None:
    if ov.fill is not None:
        rs.fill = ov.fill
    if ov.fill_opacity is not None:
        rs.fill_opacity = ov.fill_opacity
    if ov.stroke is not None:
        rs.stroke_color = ov.stroke.color
        rs.stroke_width_pt = ov.stroke.width_pt
        rs.stroke_dash = ov.stroke.dash
    if ov.font is not None:
        rs.font = ov.font
    if ov.corner_radius_mm is not None:
        rs.corner_radius_mm = ov.corner_radius_mm
