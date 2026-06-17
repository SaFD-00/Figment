"""Async Ollama client: streaming chat + explicit load/unload (keep_alive control)."""
from __future__ import annotations

import json
from typing import AsyncIterator, Optional

import httpx

from app.config import get_settings


def _to_ollama_messages(messages: list[dict]) -> list[dict]:
    """Adapt OpenAI-style messages to Ollama's native `/api/chat` shape.

    Provider-agnostic message builders (e.g. prompt-enhance) emit multimodal `content` as a parts
    list `[{type:text,...}, {type:image_url, image_url:{url}}]`. Ollama instead wants a plain string
    `content` plus a per-message `images` array of raw base64 (no `data:` prefix). Text-only string
    messages pass through untouched.
    """
    out: list[dict] = []
    for m in messages:
        content = m.get("content")
        if not isinstance(content, list):
            out.append(m)
            continue
        texts: list[str] = []
        images: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                texts.append(part.get("text", ""))
            elif part.get("type") == "image_url":
                url = (part.get("image_url") or {}).get("url", "")
                if url:
                    images.append(url.split(",", 1)[1] if url.startswith("data:") else url)
        msg = {**m, "content": "\n".join(texts)}
        if images:
            msg["images"] = images
        out.append(msg)
    return out


class OllamaClient:
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        s = get_settings()
        self.base = (base_url or s.ollama_url).rstrip("/")
        self.model = model or s.ollama_llm
        # Bounded timeouts (was timeout=None → infinite hang). A generous read window covers a
        # cold model load / slow first token, but a truly stuck Ollama now errors instead of
        # pinning the request forever. Streaming counts the first-byte wait as one read.
        self._http = httpx.AsyncClient(
            base_url=self.base,
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0),
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def version(self) -> Optional[str]:
        try:
            r = await self._http.get("/api/version")
            return r.json().get("version")
        except Exception:
            return None

    async def chat_stream(self, messages: list[dict], model: Optional[str] = None,
                          keep_alive: str | int = "5m") -> AsyncIterator[str]:
        """Yield assistant content deltas."""
        payload = {"model": model or self.model, "messages": _to_ollama_messages(messages),
                   "stream": True, "keep_alive": keep_alive}
        async with self._http.stream("POST", "/api/chat", json=payload) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "message" in obj and obj["message"].get("content"):
                    yield obj["message"]["content"]
                if obj.get("done"):
                    break

    async def unload(self, model: Optional[str] = None) -> None:
        """Evict the model from memory now (keep_alive: 0)."""
        try:
            await self._http.post("/api/chat", json={
                "model": model or self.model, "messages": [], "keep_alive": 0,
            })
        except Exception:
            pass

    async def warm(self, model: Optional[str] = None, keep_alive: str | int = "10m") -> None:
        try:
            await self._http.post("/api/chat", json={
                "model": model or self.model,
                "messages": [{"role": "user", "content": "ok"}],
                "stream": False, "keep_alive": keep_alive,
                "options": {"num_predict": 1},
            })
        except Exception:
            pass

    async def installed_models(self) -> list[str]:
        try:
            r = await self._http.get("/api/tags")
            return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            return []
