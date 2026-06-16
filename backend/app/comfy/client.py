"""Async ComfyUI client: upload images, queue prompts, stream /ws progress, fetch outputs, free memory."""
from __future__ import annotations

import json
import uuid
from typing import AsyncIterator, Optional

import httpx
import websockets

from app.config import get_settings


class ServiceUnreachableError(RuntimeError):
    """필수 외부 서비스(예: ComfyUI)가 도달 불가. 버그가 아닌 운영 상태 —
    WARNING으로 한 줄 로깅하고 사용자에게 메시지를 그대로 노출한다."""


class ComfyUIClient:
    def __init__(self, base_url: Optional[str] = None):
        self.base = (base_url or get_settings().comfy_url).rstrip("/")
        self.ws_base = self.base.replace("http://", "ws://").replace("https://", "wss://")
        self._http = httpx.AsyncClient(base_url=self.base, timeout=60.0)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def ping(self) -> bool:
        try:
            r = await self._http.get("/system_stats")
            return r.status_code == 200
        except Exception:
            return False

    async def object_info(self) -> dict:
        r = await self._http.get("/object_info")
        r.raise_for_status()
        return r.json()

    async def upload_image(self, data: bytes, filename: str, subfolder: str = "imggen",
                           overwrite: bool = True) -> str:
        """Upload an input image; returns the server-side reference (e.g. 'imggen/foo.png')."""
        files = {"image": (filename, data, "image/png")}
        form = {"subfolder": subfolder, "type": "input", "overwrite": "true" if overwrite else "false"}
        r = await self._http.post("/upload/image", files=files, data=form)
        r.raise_for_status()
        j = r.json()
        name = j["name"]
        sub = j.get("subfolder", "")
        return f"{sub}/{name}" if sub else name

    async def upload_mask(self, data: bytes, filename: str, subfolder: str = "imggen") -> str:
        files = {"image": (filename, data, "image/png")}
        form = {"subfolder": subfolder, "type": "input", "overwrite": "true"}
        r = await self._http.post("/upload/image", files=files, data=form)
        r.raise_for_status()
        j = r.json()
        sub = j.get("subfolder", "")
        return f"{sub}/{j['name']}" if sub else j["name"]

    async def queue_prompt(self, graph: dict, client_id: str) -> str:
        r = await self._http.post("/prompt", json={"prompt": graph, "client_id": client_id})
        if r.status_code != 200:
            raise RuntimeError(f"ComfyUI /prompt rejected the graph: {r.status_code} {r.text}")
        return r.json()["prompt_id"]

    async def view(self, filename: str, subfolder: str = "", type_: str = "output") -> bytes:
        r = await self._http.get("/view", params={"filename": filename, "subfolder": subfolder, "type": type_})
        r.raise_for_status()
        return r.content

    async def history(self, prompt_id: str) -> dict:
        r = await self._http.get(f"/history/{prompt_id}")
        r.raise_for_status()
        return r.json()

    async def free(self, unload_models: bool = True, free_memory: bool = True) -> None:
        try:
            await self._http.post("/free", json={"unload_models": unload_models, "free_memory": free_memory})
        except Exception:
            pass  # best-effort

    async def interrupt(self) -> None:
        try:
            await self._http.post("/interrupt")
        except Exception:
            pass

    async def ws_messages(self, client_id: str) -> AsyncIterator[dict | bytes | str]:
        """Yield decoded JSON dicts (and raw bytes for binary preview frames) from /ws.
        Yields the sentinel string "__connected__" once, immediately after the socket opens,
        so the caller can safely queue the prompt without missing early messages."""
        url = f"{self.ws_base}/ws?clientId={client_id}"
        async with websockets.connect(url, max_size=16 * 1024 * 1024) as ws:
            yield "__connected__"
            async for msg in ws:
                if isinstance(msg, bytes):
                    yield msg
                else:
                    try:
                        yield json.loads(msg)
                    except json.JSONDecodeError:
                        continue


def new_client_id() -> str:
    return uuid.uuid4().hex
