"""In-process async job worker (single heavy worker — the 24GB ceiling forbids concurrent big models)
plus a per-job SSE pub/sub for progress streaming."""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import AsyncIterator, Optional

from app.comfy import builder as B
from app.comfy.client import ComfyUIClient, new_client_id
from app.comfy.progress import is_prompt_done, parse_binary_preview, parse_text_message
from app.db import repo
from app.engines.figure_pipeline import StagedInput, run_figure_job
from app.llm.ollama_client import OllamaClient
from app.models_catalog.registry import is_cloud, resolve, resolve_llm
from app.orchestrator.memory import MemoryOrchestrator
from app.schemas.genspec import GenSpec, Mode
from app.schemas.jobs import ProgressEvent
from app.services import image_ops, rembg_service, storage

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
            except Exception as e:  # noqa: BLE001
                log.exception("job %s failed", job_id)
                await repo.update_job(job_id, status="error", error=str(e))
                self._publish(ProgressEvent(type="error", job_id=job_id, message=str(e)))
            finally:
                self._cancel.discard(job_id)

    async def _run(self, job_id: str) -> None:
        job = await repo.get_job(job_id)
        if not job:
            return
        spec = GenSpec.model_validate(job["genspec"])
        await repo.update_job(job_id, status="running", progress=0.0)
        self._publish(ProgressEvent(type="progress", job_id=job_id, progress=0.0, message="preparing"))

        # 1) resolve model — CLOUD models run the figure pipeline (editable SVG/PPTX),
        #    LOCAL models run the ComfyUI graph below.
        model = resolve(spec.model, spec.mode)
        if is_cloud(model):
            await self._run_figure(job_id, job, spec, model)
            return
        model = await self.orch.ensure_ready_for(model)

        # 2) prepare input images (upload to ComfyUI), build context
        ctx = await self._prepare_inputs(spec, model)

        # 3) build graph
        result = B.build(spec, ctx)

        # 4) execute over ws
        out_bytes = await self._execute(job_id, result, spec)

        # 5) optional post-steps (upscale, bg-remove) — light, in pipeline order
        if spec.remove_bg:
            out_bytes = await asyncio.to_thread(rembg_service.remove_bg, out_bytes, False)

        # 6) persist
        path, w, h = storage.save_image(job["project_id"], out_bytes, "output", spec.model_dump())
        asset = await repo.create_asset(job["project_id"], "output", path, w, h,
                                        parent_id=spec.source_asset, meta={"job": job_id})
        await repo.touch_project(job["project_id"], cover_asset=asset["id"])
        await repo.update_job(job_id, status="done", progress=1.0, result_asset=asset["id"])
        self._publish(ProgressEvent(type="done", job_id=job_id, progress=1.0, result_asset=asset["id"]))
        await self.orch.after_job()

    async def _run_figure(self, job_id: str, job: dict, spec: GenSpec, model) -> None:
        """Cloud path: drive the FigGen pipeline → save preview PNG + editable SVG/PPTX sidecars."""
        llm = resolve_llm(spec.llm_model)

        async def _staged(asset_id: str, prefix: str) -> Optional[StagedInput]:
            a = await repo.get_asset(asset_id)
            if not a:
                return None
            data = await asyncio.to_thread(lambda: open(a["path"], "rb").read())
            return StagedInput(data=data, name=f"{prefix}_{asset_id}.png")

        source = await _staged(spec.source_asset, "src") if spec.source_asset else None
        references: list[StagedInput] = []
        for ref in spec.reference_images:
            s = await _staged(ref.asset, "ref")
            if s:
                references.append(s)

        def on_progress(p: float, msg: str) -> None:
            self._publish(ProgressEvent(type="progress", job_id=job_id, progress=p, message=msg))

        result = await run_figure_job(
            spec=spec, project_id=job["project_id"], job_id=job_id,
            image_model=model, llm_model=llm, source=source, references=references,
            on_progress=on_progress,
        )

        png = result.preview_png
        if spec.remove_bg:
            png = await asyncio.to_thread(rembg_service.remove_bg, png, False)

        path, w, h = storage.save_image(job["project_id"], png, "output", spec.model_dump())
        svg = storage.save_named(job["project_id"], result.svg_path, "svg")
        pptx = storage.save_named(job["project_id"], result.pptx_path, "pptx")
        meta = {
            "job": job_id, "engine": model.engine, "figure": True,
            "svg": svg, "pptx": pptx, "spec": result.spec_path,
        }
        asset = await repo.create_asset(job["project_id"], "output", path, w, h,
                                        parent_id=spec.source_asset, meta=meta)
        await repo.touch_project(job["project_id"], cover_asset=asset["id"])
        await repo.update_job(job_id, status="done", progress=1.0, result_asset=asset["id"])
        self._publish(ProgressEvent(type="done", job_id=job_id, progress=1.0, result_asset=asset["id"]))

    async def _prepare_inputs(self, spec: GenSpec, model) -> B.BuildContext:
        width = image_ops.round_to_multiple(spec.width, 16)
        height = image_ops.round_to_multiple(spec.height, 16)
        ctx = B.BuildContext(model=model, width=width, height=height)

        source_img = None
        if spec.source_asset:
            a = await repo.get_asset(spec.source_asset)
            if a:
                data = open(a["path"], "rb").read()
                ctx.comfy_source = await self.comfy.upload_image(data, f"src_{spec.source_asset}.png")
                from PIL import Image
                import io as _io
                source_img = Image.open(_io.BytesIO(data))
                # keep source dims as the generation size for edits/inpaint
                ctx.width, ctx.height = source_img.size

        if spec.mask_asset:
            a = await repo.get_asset(spec.mask_asset)
            if a and source_img is not None:
                mdata = open(a["path"], "rb").read()
                mpng = image_ops.binarize_mask(mdata, source_img.size)
                ctx.comfy_mask = await self.comfy.upload_mask(mpng, f"mask_{spec.mask_asset}.png")

        for ref in spec.reference_images:
            a = await repo.get_asset(ref.asset)
            if a:
                data = open(a["path"], "rb").read()
                ctx.comfy_refs.append(await self.comfy.upload_image(data, f"ref_{ref.asset}.png"))
        return ctx

    async def _execute(self, job_id: str, result: B.BuildResult, spec: GenSpec) -> bytes:
        client_id = new_client_id()
        prompt_id: Optional[str] = None
        async for msg in self.comfy.ws_messages(client_id):
            if job_id in self._cancel:
                await self.comfy.interrupt()
                raise RuntimeError("canceled")
            if msg == "__connected__":
                prompt_id = await self.comfy.queue_prompt(result.graph, client_id)
                continue
            if isinstance(msg, bytes):
                ev = parse_binary_preview(job_id, msg)
                if ev:
                    self._publish(ev)
                continue
            # JSON message
            ev = parse_text_message(job_id, msg)
            if ev:
                if ev.type == "error":
                    raise RuntimeError(ev.message or "execution error")
                await repo.update_job(job_id, progress=ev.progress)
                self._publish(ev)
            if prompt_id and is_prompt_done(msg, prompt_id):
                break

        if not prompt_id:
            raise RuntimeError("prompt was never queued")
        return await self._fetch_result(prompt_id, result)

    async def _fetch_result(self, prompt_id: str, result: B.BuildResult) -> bytes:
        hist = await self.comfy.history(prompt_id)
        entry = hist.get(prompt_id, {})
        outputs = entry.get("outputs", {})
        node_out = outputs.get(result.save_node) or next(
            (v for v in outputs.values() if "images" in v), None
        )
        if not node_out or not node_out.get("images"):
            raise RuntimeError("no image in ComfyUI history output")
        img = node_out["images"][0]
        return await self.comfy.view(img["filename"], img.get("subfolder", ""), img.get("type", "output"))
