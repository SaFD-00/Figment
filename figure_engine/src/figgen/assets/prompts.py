"""과학 일러스트 스타일 일관성 프롬프트 템플릿.

PRESET_VERSION을 캐시 키에 넣어 프롬프트 개선 시 캐시를 자동 무효화한다.
"""

from __future__ import annotations

PRESET_VERSION = "v1"

_STYLE_PROMPTS = {
    "nature_minimal": "flat vector scientific illustration, thin uniform outlines, muted palette, "
                      "no gradients, no shadows",
    "neurips_pastel": "soft pastel flat design, rounded shapes, gentle colors, no gradients",
    "ieee_classic": "clean line-art, high contrast, minimal color",
    "science_bold": "bold flat vector, high saturation accent, strong outlines",
    "grayscale_print": "monochrome flat line-art, grayscale, print-safe",
    "flat": "flat design illustration, bold solid fills, no gradients, no shadows, "
            "clean rounded shapes, vivid modern palette",
}
_DEFAULT = _STYLE_PROMPTS["nature_minimal"]
_COMMON_SUFFIX = "single isolated subject, centered, no text, no letters, no watermark, no border"


def build_icon_prompt(desc: str, preset: str, transparent: bool) -> str:
    style = _STYLE_PROMPTS.get(preset, _DEFAULT)
    return f"{desc}, {style}, {_COMMON_SUFFIX}"


def build_scene_prompt(desc: str, preset: str, palette: list[str] | None = None) -> str:
    """풍부한 단일 장면(scientific_illustration)용 프롬프트.

    아이콘용 ``_COMMON_SUFFIX``("single isolated subject, centered")는 고의로 생략한다 —
    그 문구가 여러 주체가 공간적으로 배치된 '장면'을 단일 객체로 망가뜨리기 때문.
    이미지 모델이 글자를 흐리게 박지 않도록 'no text'만 유지(라벨은 벡터 오버레이가 담당).
    """
    style = _STYLE_PROMPTS.get(preset, _DEFAULT)
    pal = f", palette: {', '.join(palette[:4])}" if palette else ""
    return (f"{desc}, {style}{pal}, cohesive multi-region scientific scene, "
            "neutral or white background, no text, no labels")
