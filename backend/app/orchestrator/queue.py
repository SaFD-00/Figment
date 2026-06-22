"""In-process async job worker (single heavy worker — the VRAM ceiling forbids concurrent big
models) plus a per-job SSE pub/sub for progress streaming.

The worker no longer knows *how* a model runs: it resolves the model, picks a GenerationEngine
(local ComfyUI / cloud figure pipeline — cloud raster is added later), runs it, then does the
single shared post-processing (remove-bg → save → asset → done event)."""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import AsyncIterator, Optional

from app.comfy.client import ComfyUIClient, ServiceUnreachableError
from app.db import repo
from app.engines.base import EngineContext, EngineResult, GenerationEngine
from app.engines.figure import FigureEngine
from app.engines.local_comfy import LocalComfyEngine
from app.llm.ollama_client import OllamaClient
from app.models_catalog.registry import ModelDef, is_cloud, resolve, resolve_llm
from app.orchestrator.memory import MemoryOrchestrator
from app.schemas.genspec import GenSpec
from app.schemas.jobs import ProgressEvent
from app.services import rembg_service, storage

log = logging.getLogger("imggen.queue")


class JobWorker:
    def __init__(self, comfy: ComfyUIClient, ollama: OllamaClient, orch: MemoryOrchestrator):
        self.comfy = comfy
        self.ollama = ollama
        self.orch = orch
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._subs: dict[str, list[asyncio.Queue[ProgressEvent]]] = defaultdict(list)
        self._last: dict[str, ProgressEvent] = {}
        self._cancel: set[str] = set()
        self._task: Optional[asyncio.Task] = None
        # Engines are stateless; instantiate once. Cloud raster engine is wired in a later step.
        self._local_engine = LocalComfyEngine()
        self._figure_engine = FigureEngine()

    # ── lifecycle ──────────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def submit(self, job_id: str) -> None:
        await self._queue.put(job_id)
        self._publish(ProgressEvent(type="queued", job_id=job_id))

    def cancel(self, job_id: str) -> None:
        self._cancel.add(job_id)

    # ── pub/sub ────────────────────────────────────────────────────────────────
    def _publish(self, ev: ProgressEvent) -> None:
        self._last[ev.job_id] = ev
        for q in self._subs[ev.job_id]:
            q.put_nowait(ev)

    async def events(self, job_id: str) -> AsyncIterator[ProgressEvent]:
        q: asyncio.Queue[ProgressEvent] = asyncio.Queue()
        self._subs[job_id].append(q)
        # Replay the latest known state so a late subscriber isn't blank.
        if job_id in self._last:
            yield self._last[job_id]
        try:
            while True:
                ev = await q.get()
                yield ev
                if ev.type in ("done", "error"):
                    break
        finally:
            self._subs[job_id].remove(q)

    # ── main loop ──────────────────────────────────────────────────────────────
    async def _loop(self) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                await self._run(job_id)
            except ServiceUnreachableError as e:
                log.warning("job %s: %s", job_id, e)
                await repo.update_job(job_id, status="error", error=str(e))
                self._publish(ProgressEvent(type="error", job_id=job_id, message=str(e)))
            except Exception as e:  # noqa: BLE001
                log.exception("job %s failed", job_id)
                await repo.update_job(job_id, status="error", error=str(e))
                self._publish(ProgressEvent(type="error", job_id=job_id, message=str(e)))
            finally:
                self._cancel.discard(job_id)

    # ── run one job ──────────────────────────────────────────────────────────────
    def _select_engine(self, model: ModelDef, spec: GenSpec) -> GenerationEngine:
        """Pick the backend for a resolved (model, mode). Cloud → figure pipeline for now;
        a cloud raster engine is added in a later step."""
        if is_cloud(model):
            return self._figure_engine
        return self._local_engine

    async def _run(self, job_id: str) -> None:
        job = await repo.get_job(job_id)
        if not job:
            return
        spec = GenSpec.model_validate(job["genspec"])
        await repo.update_job(job_id, status="running", progress=0.0)
        self._publish(ProgressEvent(type="progress", job_id=job_id, progress=0.0, message="preparing"))

        model = resolve(spec.model, spec.mode)
        llm = resolve_llm(spec.llm_model)
        engine = self._select_engine(model, spec)
        ectx = EngineContext(
            job_id=job_id, project_id=job["project_id"], spec=spec, model=model, llm_model=llm,
            comfy=self.comfy, ollama=self.ollama, orch=self.orch,
            on_progress=self._publish, is_canceled=lambda: job_id in self._cancel,
        )
        result = await engine.run(ectx)
        await self._persist(job, spec, result)
        if not is_cloud(model):
            await self.orch.after_job()

    async def _persist(self, job: dict, spec: GenSpec, result: EngineResult) -> None:
        """The single result-persistence site for every engine: remove-bg (images), save the
        file + GenSpec sidecar, copy editable sidecars, create the asset, emit `done`."""
        job_id, project_id = job["id"], job["project_id"]
        if result.is_video:
            path, w, h = storage.save_video(project_id, result.video_bytes, "output",
                                            result.video_ext, spec.model_dump())
            meta = {"job": job_id, "video": True, **result.extra_meta}
        else:
            img = result.image_bytes
            if spec.remove_bg:
                img = await asyncio.to_thread(rembg_service.remove_bg, img, False)
            path, w, h = storage.save_image(project_id, img, "output", spec.model_dump())
            meta = {"job": job_id, **result.extra_meta}
            for role, src in result.sidecars.items():
                meta[role] = storage.save_named(project_id, src, role)
        asset = await repo.create_asset(project_id, "output", path, w, h,
                                        parent_id=spec.source_asset, meta=meta)
        await repo.touch_project(project_id, cover_asset=asset["id"])
        await repo.update_job(job_id, status="done", progress=1.0, result_asset=asset["id"])
        self._publish(ProgressEvent(type="done", job_id=job_id, progress=1.0, result_asset=asset["id"]))
