"""미리보기/Critic용 PNG 생성 (SVG 경유, LibreOffice 비의존).

SvgRenderer 출력 → cairosvg 래스터가 critic VLM 입력·브라우저 미리보기·썸네일 공용 경로다
("critic이 보는 것 = 사용자가 받는 SVG"). cairosvg 폰트 품질 한계 시 resvg 백엔드로 교체.
"""

from __future__ import annotations

from typing import Protocol

from .. import _native  # noqa: F401  (libcairo dlopen 경로 보강 보장)
from .resolved import ResolvedFigure
from .svg_renderer import SvgRenderer


class PreviewBackend(Protocol):
    def to_png(self, svg: str, dpi: int) -> bytes: ...


class CairoSvgBackend:
    def to_png(self, svg: str, dpi: int) -> bytes:
        import cairosvg

        return cairosvg.svg2png(bytestring=svg.encode("utf-8"), dpi=dpi)


class ResvgBackend:  # pragma: no cover - 선택 백엔드
    def to_png(self, svg: str, dpi: int) -> bytes:
        import resvg_py  # type: ignore

        return bytes(resvg_py.svg_to_bytes(svg_string=svg, dpi=dpi))


_DEFAULT_BACKEND: PreviewBackend = CairoSvgBackend()


def svg_to_png(svg: str, dpi: int = 192, backend: PreviewBackend | None = None) -> bytes:
    return (backend or _DEFAULT_BACKEND).to_png(svg, dpi)


def png_to_jpg(png: bytes, quality: int = 92) -> bytes:
    """PNG → JPEG. 알파는 흰 배경에 평탄화(JPEG는 투명 미지원)."""
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(png))
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def render_preview(
    fig: ResolvedFigure,
    renderer: SvgRenderer | None = None,
    dpi: int = 192,
    *,
    debug: bool = False,
    backend: PreviewBackend | None = None,
) -> bytes:
    renderer = renderer or SvgRenderer(embed_images=True)
    svg = renderer.render(fig, debug=debug)
    return svg_to_png(svg, dpi=dpi, backend=backend)


def downsample_png(png: bytes, max_edge: int = 1024) -> bytes:
    """critic 비용 가드 — 긴 변 max_edge로 다운샘플."""
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(png))
    if max(img.size) <= max_edge:
        return png
    ratio = max_edge / max(img.size)
    new = (round(img.size[0] * ratio), round(img.size[1] * ratio))
    img = img.resize(new, Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
