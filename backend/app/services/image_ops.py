"""PIL helpers: dimension rounding, mask binarization/alignment, size assertions."""
from __future__ import annotations

import io

from PIL import Image, ImageOps


def load_rgb(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB")


def to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def round_to_multiple(v: int, m: int = 16) -> int:
    return max(m, (v // m) * m)


def fit_within(img: Image.Image, max_side: int = 1536) -> Image.Image:
    w, h = img.size
    if max(w, h) <= max_side:
        return img
    scale = max_side / max(w, h)
    return img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def binarize_mask(data: bytes, target_size: tuple[int, int]) -> bytes:
    """Return a white=regenerate / black=keep mask PNG at exactly target_size.
    Painted (non-transparent / bright) pixels -> white; everything else -> black."""
    img = Image.open(io.BytesIO(data))
    if img.mode in ("RGBA", "LA"):
        alpha = img.getchannel("A")
        mask = alpha.point(lambda p: 255 if p > 10 else 0)
    else:
        gray = img.convert("L")
        mask = gray.point(lambda p: 255 if p > 16 else 0)
    if mask.size != target_size:
        mask = mask.resize(target_size, Image.NEAREST)
    # ComfyUI ImageToMask(channel="red") expects an RGB image whose red channel is the mask.
    out = Image.merge("RGB", (mask, mask, mask))
    return to_png_bytes(out)


def assert_same_dims(a: tuple[int, int], b: tuple[int, int]) -> None:
    if a != b:
        raise ValueError(f"mask dims {b} must equal source dims {a}")
