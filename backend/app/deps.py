"""Process-wide singletons (single-user local app)."""
from __future__ import annotations

from typing import Optional

from app.comfy.client import ComfyUIClient
from app.llm.ollama_client import OllamaClient
from app.orchestrator.memory import MemoryOrchestrator
from app.orchestrator.queue import JobWorker

_comfy: Optional[ComfyUIClient] = None
_ollama: Optional[OllamaClient] = None
_orch: Optional[MemoryOrchestrator] = None
_worker: Optional[JobWorker] = None


def comfy() -> ComfyUIClient:
    global _comfy
    if _comfy is None:
        _comfy = ComfyUIClient()
    return _comfy


def ollama() -> OllamaClient:
    global _ollama
    if _ollama is None:
        _ollama = OllamaClient()
    return _ollama


def orchestrator() -> MemoryOrchestrator:
    global _orch
    if _orch is None:
        _orch = MemoryOrchestrator(comfy(), ollama())
    return _orch


def worker() -> JobWorker:
    global _worker
    if _worker is None:
        _worker = JobWorker(comfy(), ollama(), orchestrator())
    return _worker


async def shutdown() -> None:
    if _worker:
        await _worker.stop()
    if _comfy:
        await _comfy.aclose()
    if _ollama:
        await _ollama.aclose()
