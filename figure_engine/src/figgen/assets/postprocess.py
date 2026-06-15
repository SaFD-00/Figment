"""에셋 후처리 — 크로마키, 트림, 패딩, 리사이즈 (numpy + PIL)."""

from __future__ import annotations

import io

import numpy as np
from PIL import Image


def _load(png: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png)).convert("RGBA")


def _dump(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def chroma_key(
    png: bytes,
    key_rgb: tuple[int, int, int] = (0, 255, 0),
    tolerance: float = 0.35,
    despill: bool = True,
    feather_px: int = 2,
) -> bytes:
    """그린스크린 → 알파. 키 색상 거리 기반 soft alpha + 그린 스필 제거."""
    img = _load(png)
    arr = np.asarray(img).astype(np.float32)
    rgb = arr[..., :3]
    key = np.array(key_rgb, dtype=np.float32)
    dist = np.linalg.norm(rgb - key, axis=-1) / (np.sqrt(3) * 255.0)
    alpha = np.clip((dist - tolerance * 0.5) / max(1e-6, tolerance), 0.0, 1.0)
    if despill:
        r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
        mask = g > np.maximum(r, b)
        g_new = np.where(mask, np.maximum(r, b), g)
        rgb[..., 1] = g_new
    out = np.dstack([rgb, alpha * 255.0]).astype(np.uint8)
    result = Image.fromarray(out, "RGBA")
    if feather_px > 0:
        from PIL import ImageFilter

        a = result.split()[3].filter(ImageFilter.GaussianBlur(feather_px))
        result.putalpha(a)
    return _dump(result)


def trim_transparent(png: bytes, alpha_threshold: int = 8) -> bytes:
    img = _load(png)
    alpha = np.asarray(img.split()[3])
    ys, xs = np.where(alpha > alpha_threshold)
    if len(xs) == 0:
        return png
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    return _dump(img.crop(box))


def pad_to_aspect(png: bytes, aspect: float, pad_pct: float = 0.05) -> bytes:
    """투명 패딩으로 종횡비(aspect=w/h) 맞춤 + 여백."""
    img = _load(png)
    w, h = img.size
    pad = int(max(w, h) * pad_pct)
    w2, h2 = w + 2 * pad, h + 2 * pad
    target_w, target_h = w2, h2
    if w2 / h2 < aspect:
        target_w = int(h2 * aspect)
    else:
        target_h = int(w2 / aspect)
    canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    canvas.paste(img, ((target_w - w) // 2, (target_h - h) // 2), img)
    return _dump(canvas)


def resize_for_placement(
    png: bytes,
    target_size_pt: tuple[float, float],
    oversample: float = 2.0,
    dpi: float = 96.0,
) -> bytes:
    """배치 크기의 oversample배 픽셀로 LANCZOS 다운스케일(파일 크기 통제, 인쇄 화질 유지)."""
    img = _load(png)
    tw = max(1, int(target_size_pt[0] / 72.0 * dpi * oversample))
    th = max(1, int(target_size_pt[1] / 72.0 * dpi * oversample))
    return _dump(img.resize((tw, th), Image.LANCZOS))
