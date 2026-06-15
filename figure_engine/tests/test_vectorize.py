"""Phase D — vtracer 벡터화 단위 검증 (오프라인, 결정론)."""

from __future__ import annotations

import io

from figgen.fullimage.vectorize import vectorize_png


def _png(w: int = 48, h: int = 48) -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (w, h), (240, 240, 245))
    d = ImageDraw.Draw(img)
    d.ellipse([8, 8, w - 8, h - 8], fill=(80, 120, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_vectorize_png_returns_valid_svg():
    svg = vectorize_png(_png())
    assert "<svg" in svg and "</svg>" in svg
    assert "path" in svg  # 컬러 영역 path 레이어


def test_vectorize_png_deterministic():
    png = _png()
    assert vectorize_png(png) == vectorize_png(png)  # 동일 입력 → 동일 SVG
