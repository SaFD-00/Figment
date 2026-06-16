"""Chat-LLM provider routing, shared by the chat and prompt-enhance endpoints.

The picker's llm_model id selects the backend: a cloud LLM with a configured key streams
from OpenRouter, a local LLM from its Ollama tag, and an unknown/keyless pick falls back to
the default Ollama model — so model selection lives in the UI, not the .env."""
from __future__ import annotations

from typing import AsyncIterator, Optional

from app import deps
from app.engines import figure_settings
from app.llm.openrouter_client import OpenRouterChatClient
from app.models_catalog.registry import (
    ENGINE_CLOUD_OPENROUTER,
    ENGINE_LOCAL_OLLAMA,
    resolve_llm,
)


def resolve_chat(llm_model: Optional[str]) -> tuple[str, Optional[str]]:
    """Pick (provider, model) for an LLM turn from the selected LLM id.

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


def chat_stream(messages: list[dict], llm_model: Optional[str]) -> AsyncIterator[str]:
    """Token async-iterator for the chosen provider (no network until iterated)."""
    provider, model = resolve_chat(llm_model)
    if provider == "openrouter":
        return OpenRouterChatClient(model=model).chat_stream(messages)  # type: ignore[arg-type]
    return deps.ollama().chat_stream(messages, model=model)
