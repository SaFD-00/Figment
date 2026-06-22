"""Async OpenRouter streaming chat client.

Mirrors `OllamaClient.chat_stream` so the chat router can swap providers transparently when
the user picks a cloud LLM in the model picker. Key + base URL come from the vendored figgen
Settings (`app.engines.cloud.figure_settings`) — the same repo-root `.env` the cloud
image/LLM figure pipeline already reads, so there is one OpenRouter configuration surface.
"""
from __future__ import annotations

import json
from typing import AsyncIterator, Optional

import httpx

from app.engines.cloud import figure_settings


class OpenRouterChatClient:
    """Streams an OpenAI-style chat completion from OpenRouter.

    Opens (and closes) its own httpx client per `chat_stream` call — chat is one request per
    turn, so there is no long-lived connection to manage.
    """

    def __init__(self, model: str, *, base_url: Optional[str] = None, api_key: Optional[str] = None):
        s = figure_settings()
        self.model = model
        self.base = (base_url or s.openrouter_base_url).rstrip("/")
        if api_key is None and s.openrouter_api_key:
            api_key = s.openrouter_api_key.get_secret_value()
        self.api_key = api_key or ""

    async def chat_stream(self, messages: list[dict], model: Optional[str] = None,
                          **_: object) -> AsyncIterator[str]:
        """Yield assistant content deltas (OpenAI `chat/completions` SSE).

        `**_` absorbs the `keep_alive` kwarg the Ollama client accepts, so both clients share
        a call signature.
        """
        payload = {"model": model or self.model, "messages": messages, "stream": True}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # OpenRouter attribution headers (optional but recommended).
            "HTTP-Referer": "https://github.com/SaFD-00/Figment",
            "X-Title": "Figment",
        }
        timeout = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)
        async with httpx.AsyncClient(base_url=self.base, timeout=timeout) as http:
            async with http.stream("POST", "/chat/completions", json=payload, headers=headers) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    content = (choices[0].get("delta") or {}).get("content")
                    if content:
                        yield content
