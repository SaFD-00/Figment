"""Background removal via rembg (BiRefNet). Runs in-process on CPU so it never competes with
the Metal GPU. Heavy import is lazy so the app starts without onnx warm-up cost."""
from __future__ import annotations

import io

from PIL import Image

_session = None


def _get_session():
    global _session
    if _session is None:
        from rembg import new_session  # lazy
        # BiRefNet = best edges; CPU provider is the reliable path on Apple Silicon.
        try:
            _session = new_session("birefnet-general", providers=["CPUExecutionProvider"])
        except Exception:
            _session = new_session("u2net", providers=["CPUExecutionProvider"])
    return _session


def remove_bg(data: bytes, white_bg: bool = False) -> bytes:
    from rembg import remove  # lazy
    cut = remove(data, session=_get_session())
    img = Image.open(io.BytesIO(cut)).convert("RGBA")
    if white_bg:
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.alpha_composite(img)
        img = bg.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
