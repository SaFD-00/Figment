"""Map ComfyUI /ws messages to our ProgressEvent stream."""
from __future__ import annotations

import base64
import struct
from typing import Optional

from app.schemas.jobs import ProgressEvent


def parse_text_message(job_id: str, msg: dict) -> Optional[ProgressEvent]:
    t = msg.get("type")
    data = msg.get("data", {})
    if t == "progress":
        value, mx = data.get("value", 0), data.get("max", 1) or 1
        return ProgressEvent(type="progress", job_id=job_id, progress=value / mx, step=value, total=mx)
    if t == "executing":
        node = data.get("node")
        if node is None:
            return None  # null node => the prompt finished executing
        return ProgressEvent(type="progress", job_id=job_id, node=str(node))
    if t == "execution_error":
        return ProgressEvent(type="error", job_id=job_id, message=str(data.get("exception_message", "execution error")))
    return None


def parse_binary_preview(job_id: str, raw: bytes) -> Optional[ProgressEvent]:
    """ComfyUI binary preview frame: first 4 bytes = event type, next 4 = image format, rest = image bytes."""
    if len(raw) < 8:
        return None
    try:
        _event, _fmt = struct.unpack(">II", raw[:8])
        img = raw[8:]
        b64 = base64.b64encode(img).decode("ascii")
        return ProgressEvent(type="preview", job_id=job_id, preview_b64=f"data:image/jpeg;base64,{b64}")
    except Exception:
        return None


def is_prompt_done(msg: dict, prompt_id: str) -> bool:
    """True when ComfyUI signals this prompt finished (executing with node=null for our prompt)."""
    if msg.get("type") == "executing":
        data = msg.get("data", {})
        return data.get("node") is None and data.get("prompt_id") == prompt_id
    return False
