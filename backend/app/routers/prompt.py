"""Prompt-enhance endpoint: an LLM rewrites a short idea into a rich English image prompt.

Single JSON response (no streaming, no GENSPEC block) — the result fills the composer prompt box.
The LLM follows the user's pick in the model picker (same routing as the chat endpoint), so a cloud
LLM streams from OpenRouter, a local one from its Ollama tag, and a keyless/unknown pick falls back
to the default Ollama model."""
from __future__ import annotations

import base64
import re
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.llm.prompts import build_enhance_messages
from app.llm.routing import chat_stream, resolve_chat
from app.models_catalog.registry import resolve_llm
from app.services import image_ops

router = APIRouter(prefix="/prompt", tags=["prompt"])


class EnhanceRequest(BaseModel):
    prompt: str
    llm_model: Optional[str] = None    # picker LLM id; None → default Ollama model
    image_model: Optional[str] = None  # picker image id → tags-vs-natural-language style hint
    instruction: Optional[str] = None  # optional "how to enhance" guidance from the user
    image: Optional[str] = None        # first source/reference image as a data URL (vision enhance)


class EnhanceResponse(BaseModel):
    prompt: str


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_LABEL_RE = re.compile(r"^\s*(enhanced|improved|rewritten|final)?\s*prompt\s*:\s*", re.IGNORECASE)


def _clean(text: str) -> str:
    """Strip artifacts small/reasoning LLMs leak despite the system rules.

    Drops <think>…</think> reasoning, a leading "Enhanced prompt:" label, and wrapping
    quotes/backticks so the result is ready to drop straight into the prompt box.
    """
    # Remove paired reasoning blocks, then anything before a stray closing </think>.
    text = _THINK_RE.sub("", text)
    if "</think>" in text.lower():
        idx = text.lower().rfind("</think>")
        text = text[idx + len("</think>"):]
    text = text.strip()
    text = _LABEL_RE.sub("", text).strip()
    # Strip a single layer of wrapping quotes/backticks if the whole thing is wrapped.
    for q in ('"', "'", "`"):
        if len(text) >= 2 and text[0] == q and text[-1] == q:
            text = text[1:-1].strip()
            break
    return text.strip()


def _prepare_image_data_url(s: str) -> str:
    """Normalize a client data URL / base64 image into a size-capped PNG data URL.

    Strips the `data:<mime>;base64,` prefix, decodes, then reuses the upload path's image
    helpers (load → fit_within → png) so the payload sent to the LLM is bounded and EXIF-safe.
    """
    b64 = s.split(",", 1)[1] if s.startswith("data:") else s
    raw = base64.b64decode(b64)
    # 768px is plenty for the LLM to read subject/composition/style; keeps the payload small.
    png = image_ops.to_png_bytes(image_ops.fit_within(image_ops.load_rgb(raw), max_side=768))
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _enhance_image_url(req: EnhanceRequest) -> Optional[str]:
    """Image data URL to attach — only for a cloud vision LLM the route will actually use."""
    if not req.image:
        return None
    provider, _ = resolve_chat(req.llm_model)
    m = resolve_llm(req.llm_model)
    if provider != "openrouter" or not (m and m.vision):
        return None  # local/non-vision route ignores the image (text-only enhance)
    try:
        return _prepare_image_data_url(req.image)
    except Exception:  # noqa: BLE001 — a malformed image must not break text enhance
        return None


@router.post("/enhance", response_model=EnhanceResponse)
async def enhance(req: EnhanceRequest) -> EnhanceResponse:
    text = req.prompt.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Prompt is empty.")
    messages = build_enhance_messages(
        text, req.image_model, instruction=req.instruction, image_url=_enhance_image_url(req),
    )
    try:
        chunks: list[str] = []
        async for tok in chat_stream(messages, req.llm_model):
            chunks.append(tok)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Enhance failed: {e}") from e
    enhanced = _clean("".join(chunks))
    if not enhanced:
        raise HTTPException(status_code=502, detail="The LLM returned an empty result.")
    return EnhanceResponse(prompt=enhanced)
