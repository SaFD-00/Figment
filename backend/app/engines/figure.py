"""Figure engine — drives the vendored FigGen pipeline (structured FigureSpec → editable
SVG/PPTX) for the explicit `Mode.figure` path on cloud models. Returns a preview PNG plus
svg/pptx sidecars; the worker persists them.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from app.db import repo
from app.engines.base import EngineContext, EngineResult
from app.engines.figure_pipeline import StagedInput, run_figure_job
from app.schemas.jobs import ProgressEvent


class FigureEngine:
    async def run(self, ctx: EngineContext) -> EngineResult:
        spec = ctx.spec

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
            ctx.on_progress(ProgressEvent(type="progress", job_id=ctx.job_id, progress=p, message=msg))

        result = await run_figure_job(
            spec=spec, project_id=ctx.project_id, job_id=ctx.job_id,
            image_model=ctx.model, llm_model=ctx.llm_model,
            source=source, references=references, on_progress=on_progress,
        )

        return EngineResult(
            image_bytes=result.preview_png,
            sidecars={"svg": result.svg_path, "pptx": result.pptx_path},
            extra_meta={"engine": ctx.model.engine, "figure": True, "spec": result.spec_path},
        )
