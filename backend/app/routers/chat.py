"""Chat endpoint: stream the LLM reply (SSE), withhold the GENSPEC block, emit it as a
structured event when ready.

The chat LLM follows the user's pick in the model picker (GenSpec.llm_model): a cloud LLM
streams from OpenRouter, a local LLM from its Ollama tag, and an unknown/keyless pick falls
back to the default Ollama model — so model selection lives in the UI, not the .env."""
from __future__ import annotations

import json
from typing import AsyncIterator, Optional

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app import deps
from app.db import repo
from app.engines import figure_settings
from app.llm.handoff import GenSpecExtractor
from app.llm.openrouter_client import OpenRouterChatClient
from app.llm.prompts import build_messages
from app.models_catalog.registry import (
    ENGINE_CLOUD_OPENROUTER,
    ENGINE_LOCAL_OLLAMA,
    resolve_llm,
)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    project_id: str
    message: str
    llm_model: Optional[str] = None  # picker id; None → default Ollama model


def _resolve_chat(llm_model: Optional[str]) -> tuple[str, Optional[str]]:
    """Pick (provider, model) for a chat turn from the selected LLM id.

    Returns provider in {"openrouter", "ollama"}; model is the slug/tag, or None for the
    Ollama default. A cloud LLM without a configured key degrades to the local default.
    """
    m = resolve_llm(llm_model)
    if (
        m
        and m.engine == ENGINE_CLOUD_OPENROUTER
        and m.cloud_model_id
        and figure_settings().has_key(m.provider or "openrouter")
    ):
        return "openrouter", m.cloud_model_id
    if m and m.engine == ENGINE_LOCAL_OLLAMA and m.cloud_model_id:
        return "ollama", m.cloud_model_id  # local LLMs carry their Ollama tag in cloud_model_id
    return "ollama", None


def _chat_stream(messages: list[dict], llm_model: Optional[str]) -> AsyncIterator[str]:
    """Token async-iterator for the chosen provider (no network until iterated)."""
    provider, model = _resolve_chat(llm_model)
    if provider == "openrouter":
        return OpenRouterChatClient(model=model).chat_stream(messages)  # type: ignore[arg-type]
    return deps.ollama().chat_stream(messages, model=model)


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
