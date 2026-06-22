"""Chat endpoint: stream the LLM reply (SSE), withhold the GENSPEC block, emit it as a
structured event when ready.

The chat LLM follows the user's pick in the model picker (GenSpec.llm_model): a cloud LLM
streams from OpenRouter, a local LLM from its Ollama tag, and an unknown/keyless pick falls
back to the default Ollama model — so model selection lives in the UI, not the .env."""
from __future__ import annotations

import json
from typing import Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, ValidationError
from sse_starlette.sse import EventSourceResponse

from app.db import repo
from app.llm.handoff import GenSpecExtractor
from app.llm.prompts import build_messages
# Provider routing lives in app.llm.routing (shared with the prompt-enhance endpoint).
# Re-exported here under the original private names for backward compatibility.
from app.llm.routing import chat_stream as _chat_stream
from app.llm.routing import resolve_chat as _resolve_chat  # noqa: F401  (re-export for callers/tests)
from app.schemas.genspec import GenSpec, Mode
from app.services import storage

router = APIRouter(prefix="/chat", tags=["chat"])

# Modes that consume a single base image vs. style/figure references. The home composer uploads
# every attachment as a neutral "reference" asset; the LLM picks the mode and we bind the ids here.
_SOURCE_MODES = {Mode.edit, Mode.img2img, Mode.inpaint, Mode.controlnet, Mode.video}
_REF_MODES = {Mode.reference, Mode.figure}


class Attachment(BaseModel):
    asset: str
    hint: Optional[Literal["source", "reference"]] = None  # advisory; routing decides binding


class ChatRequest(BaseModel):
    project_id: str
    message: str
    llm_model: Optional[str] = None  # picker id; None → default Ollama model
    attachments: Optional[list[Attachment]] = None  # images uploaded at the home composer


def _inject_attachments(
    spec: GenSpec, attachments: list[Attachment]
) -> tuple[Optional[GenSpec], Optional[str]]:
    """Bind uploaded asset ids onto the routed spec by mode, then re-validate.

    source_asset for image→image modes; reference_images for style/figure (and as a soft fallback
    when the LLM picked a text-only mode despite an upload). Re-validates so a mode/asset mismatch
    surfaces as a clean genspec_error rather than a 500 downstream."""
    if not attachments:
        return spec, None
    data = spec.model_dump(mode="json")
    ids = [a.asset for a in attachments]
    if spec.mode in _SOURCE_MODES:
        data["source_asset"] = data.get("source_asset") or ids[0]
    else:  # _REF_MODES, plus txt2img soft fallback
        existing = {r.get("asset") for r in data.get("reference_images", [])}
        for aid in ids:
            if aid not in existing:
                data["reference_images"].append({"asset": aid, "role": "style", "strength": 0.85})
    try:
        return GenSpec.model_validate(data), None
    except ValidationError as e:
        return None, f"attachment injection failed: {e}"


@router.post("")
async def chat(req: ChatRequest):
    history = await repo.list_messages(req.project_id)
    await repo.add_message(req.project_id, "user", req.message)

    attachments = req.attachments or []
    attachment_note: Optional[str] = None
    image_url: Optional[str] = None
    if attachments:
        n = len(attachments)
        attachment_note = (
            f"[{n} image{'s' if n != 1 else ''} attached by the user. Route to a mode that consumes "
            "an image (edit / img2img / reference / controlnet), or ask which one if it's ambiguous.]"
        )
        first = await repo.get_asset(attachments[0].asset)
        if first:
            image_url = storage.file_to_data_url(first["path"])

    messages = build_messages(
        history, req.message, attachment_note=attachment_note, image_url=image_url
    )
    stream = _chat_stream(messages, req.llm_model)

    async def gen():
        extractor = GenSpecExtractor()
        full_visible = ""
        try:
            async for tok in stream:
                visible = extractor.feed(tok)
                if visible:
                    full_visible += visible
                    yield {"event": "delta", "data": json.dumps({"text": visible})}
            # flush any trailing visible text (rare)
            tail = extractor.trailing_visible()
            if tail:
                full_visible += tail
                yield {"event": "delta", "data": json.dumps({"text": tail})}

            spec, raw, err = extractor.finish()
            # Bind home-composer uploads onto the routed spec (source vs reference, by mode).
            if spec and attachments:
                spec, inj_err = _inject_attachments(spec, attachments)
                if inj_err:
                    err = inj_err
            spec_dict = spec.model_dump(mode="json") if spec else None
            await repo.add_message(req.project_id, "assistant", full_visible.strip(), genspec=spec_dict)
            if spec_dict:
                yield {"event": "genspec", "data": json.dumps(spec_dict)}
            elif err:
                yield {"event": "genspec_error", "data": json.dumps({"error": err, "raw": raw})}
            yield {"event": "done", "data": "{}"}
        except Exception as e:  # noqa: BLE001
            yield {"event": "error", "data": json.dumps({"error": str(e)})}

    return EventSourceResponse(gen())
