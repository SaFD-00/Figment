"""저널 스타일 프리셋 적용 (순수 함수, LLM 미사용) + 참조 이미지 스타일 매칭.

spec.stylesheet에 프리셋 주입 + role 없는 박스에 팔레트 순환 색 + 이미지 gen_prompt에
일관성 서픽스 추가. 프리셋 교체(restyle)는 spec 재생성 없이 즉시.
"""

from __future__ import annotations

from ..schema.figure_spec import CONTAINER_TYPES, FigureSpec
from ..schema.style import StyleSheet
from ..styles.presets import get_preset


class Stylist:
    def apply(
        self, spec: FigureSpec, preset_name: str = "nature_minimal", custom: StyleSheet | None = None
    ) -> FigureSpec:
        ss = custom or get_preset(preset_name)
        data = spec.model_dump()
        suffix = self._style_suffix(ss)
        counter = {"i": 0}
        _walk(data["root"], ss, suffix, counter)
        data["stylesheet"] = ss.model_dump()
        return FigureSpec.model_validate(data)

    def restyle(self, spec: FigureSpec, new_preset: str) -> FigureSpec:
        """재생성 없이 프리셋 교체(이미지 gen_prompt 서픽스만 갱신)."""
        return self.apply(spec, new_preset)

    def from_reference(self, spec: FigureSpec, palette_hex: list[str]) -> FigureSpec:
        """참조 이미지 팔레트로 최근접 프리셋의 색만 치환한 파생 스타일(하위호환)."""
        ss = get_preset("nature_minimal")
        if palette_hex:
            ss = ss.model_copy(update={"palette": palette_hex[:6] or ss.palette})
        return self.apply(spec, "nature_minimal", custom=ss)

    def from_report(self, spec: FigureSpec, report, *, base_preset: str = "nature_minimal") -> FigureSpec:
        """RefStyleReport(palette/density/font_feel)를 실제 StyleSheet로 반영한 파생 스타일.

        프롬프트 텍스트 가이드를 넘어 렌더 스타일시트(색/폰트/선두께)에 결정론적으로 적용한다.
        """
        ss = get_preset(base_preset)
        updates: dict = {}
        palette = getattr(report, "palette_hex", None)
        if palette:
            updates["palette"] = palette[:6]
        fam = _font_family_for(getattr(report, "font_feel", ""))
        if fam:
            updates["font_family"] = fam
        density = getattr(report, "density", "medium")
        if density == "dense":
            updates["stroke_width_pt"] = max(0.5, ss.stroke_width_pt * 0.8)
        elif density == "sparse":
            updates["stroke_width_pt"] = ss.stroke_width_pt * 1.2
        if updates:
            ss = ss.model_copy(update=updates)
        return self.apply(spec, base_preset, custom=ss)

    @staticmethod
    def _style_suffix(ss: StyleSheet) -> str:
        pal = ", ".join(ss.palette[:3])
        return f"flat minimal vector style, consistent line weight, palette: {pal}, white background"


def _font_family_for(font_feel: str) -> str | None:
    """참조 폰트 느낌(font_feel) → 시스템 폰트 패밀리(없으면 None=프리셋 유지)."""
    f = (font_feel or "").lower()
    if "mono" in f:
        return "Courier New"
    if "serif" in f and "sans" not in f:
        return "Times New Roman"
    if any(k in f for k in ("sans", "modern", "clean", "geometric", "grotesk")):
        return "Arial"
    return None


def _walk(node: dict, ss: StyleSheet, suffix: str, counter: dict) -> None:
    t = node.get("type")
    if t == "box" and not node.get("role"):
        style = node.get("style") or {}
        if not style.get("fill"):
            style["fill"] = ss.palette[counter["i"] % len(ss.palette)]
            counter["i"] += 1
            node["style"] = style
    if t == "image" and node.get("gen_prompt"):
        if suffix.split(",")[0] not in node["gen_prompt"]:
            node["gen_prompt"] = f"{node['gen_prompt']}. {suffix}"
    if t in CONTAINER_TYPES:
        for c in node.get("children", []):
            _walk(c, ss, suffix, counter)
    elif t == "free":
        for it in node.get("items", []):
            _walk(it["node"], ss, suffix, counter)
