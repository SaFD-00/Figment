"""Chat endpoint: stream the LLM reply (SSE), withhold the GENSPEC block, emit it as a
structured event when ready.

The chat LLM follows the user's pick in the model picker (GenSpec.llm_model): a cloud LLM
streams from OpenRouter, a local LLM from its Ollama tag, and an unknown/keyless pick falls
back to the default Ollama model — so model selection lives in the UI, not the .env."""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.db import repo
from app.llm.handoff import GenSpecExtractor
from app.llm.prompts import build_messages
# Provider routing lives in app.llm.routing (shared with the prompt-enhance endpoint).
# Re-exported here under the original private names for backward compatibility.
from app.llm.routing import chat_stream as _chat_stream
from app.llm.routing import resolve_chat as _resolve_chat  # noqa: F401  (re-export for callers/tests)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    project_id: str
    message: str
    llm_model: Optional[str] = None  # picker id; None → default Ollama model


@router.post("")
async def chat(req: ChatRequest):
    history = await repo.list_messages(req.project_id)
    await repo.add_message(req.project_id, "user", req.message)
    messages = build_messages(history, req.message)
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
