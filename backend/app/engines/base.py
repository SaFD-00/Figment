"""Common generation-engine contract.

Every backend (local ComfyUI, cloud raster image, cloud figure pipeline) implements
`GenerationEngine.run(ctx) -> EngineResult`. The job worker builds one `EngineContext`
per job, dispatches to the right engine, then does the single shared post-processing
(remove-bg → save → asset → done event). This keeps the worker the sole owner of the
shared clients (ComfyUI/Ollama/memory) and the only place that persists results.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol, runtime_checkable

from app.comfy.client import ComfyUIClient
from app.llm.ollama_client import OllamaClient
from app.models_catalog.registry import ModelDef
from app.orchestrator.memory import MemoryOrchestrator
from app.schemas.genspec import GenSpec
from app.schemas.jobs import ProgressEvent


@dataclass
class EngineResult:
    """Normalized engine output. The worker turns this into a saved asset."""
    image_bytes: Optional[bytes] = None          # raster PNG (image modes)
    is_video: bool = False
    video_bytes: Optional[bytes] = None          # animated webp/mp4
    video_ext: str = "webp"
    sidecars: dict[str, str] = field(default_factory=dict)  # {role: src_path} copied into the project dir
    extra_meta: dict = field(default_factory=dict)          # merged into the asset meta as-is


@dataclass
class EngineContext:
    """Everything an engine needs for one job. Built by the worker; engines stay stateless."""
    job_id: str
    project_id: str
    spec: GenSpec
    model: ModelDef
    llm_model: Optional[ModelDef]
    comfy: ComfyUIClient
    ollama: OllamaClient
    orch: MemoryOrchestrator
    on_progress: Callable[[ProgressEvent], None]   # = worker._publish
    is_canceled: Callable[[], bool]                # = lambda: job_id in worker._cancel


@runtime_checkable
class GenerationEngine(Protocol):
    async def run(self, ctx: EngineContext) -> EngineResult: ...
