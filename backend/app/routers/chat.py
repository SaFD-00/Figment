"""Chat endpoint: stream the LLM reply (SSE), withhold the GENSPEC block, emit it as a
structured event when ready."""
from __future__ import annotations

import json

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app import deps
from app.db import repo
from app.llm.handoff import GenSpecExtractor
from app.llm.prompts import build_messages

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    project_id: str
    message: str


@router.post("")
async def chat(req: ChatRequest):
    history = await repo.list_messages(req.project_id)
    await repo.add_message(req.project_id, "user", req.message)
    messages = build_messages(history, req.message)
    llm = deps.ollama()

    async def gen():
        extractor = GenSpecExtractor()
        full_visible = ""
        try:
            async for tok in llm.chat_stream(messages):
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
