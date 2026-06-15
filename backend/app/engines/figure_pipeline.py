"""Figure engine adapter — runs the vendored FigGen pipeline (structured FigureSpec →
editable SVG/PPTX) for CLOUD image models, behind Figment's unified job queue.

A Figment GenSpec (mode + cloud model) is translated into a FigGen JobRequest:
    • txt2img   → task="generate"  (Text-to-Figure)
    • reference → task="generate"  with the reference as the style image (Reference-to-Figure)
    • img2img   → task="sketch"    with the source as the sketch (Image-to-Figure)

The chosen cloud image/LLM model ids drive a per-job FigGen Settings override so the user's
model selection flows through. With no API key configured the FigGen registry safely falls
back to the mock provider (offline-friendly), still emitting real SVG/PPTX artifacts.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

from figgen.jobs.models import JobRecord, JobRequest, ModelPrefs, Stage, StageEvent
from figgen.jobs.store import FileStore
from figgen.pipeline.orchestrator import Orchestrator

from app.config import get_settings
from app.engines.cloud import figure_settings
from app.models_catalog.registry import ModelDef
from app.schemas.genspec import GenSpec, Mode

# Coarse 0..1 progress per FigGen stage completion (queue maps these to SSE events).
_STAGE_PROGRESS: dict[Stage, float] = {
    Stage.PLANNING: 0.20,
    Stage.STYLING: 0.35,
    Stage.ASSETS: 0.55,
    Stage.RENDERING: 0.78,
    Stage.CRITIC: 0.90,
    Stage.FINALIZING: 0.98,
}


@dataclass
class StagedInput:
    data: bytes
    name: str


@dataclass
class FigureResult:
    preview_png: bytes
    svg_path: str
    pptx_path: str
    preview_svg_path: str
    spec_path: str
    job_dir: str
    artifacts: dict[str, str] = field(default_factory=dict)


@lru_cache
def figure_store() -> FileStore:
    """FileStore rooted under AIStudio/outputs/_figure_engine (self-contained runtime home)."""
    root = get_settings().outputs_dir / "_figure_engine"
    root.mkdir(parents=True, exist_ok=True)
    return FileStore(root)


def _job_settings(image_model: ModelDef, llm_model: Optional[ModelDef]):
    """Per-job FigGen Settings: provider + model ids from the user's selection."""
    base = figure_settings()
    provider = image_model.provider or "auto"   # "openrouter" | "openai"
    overrides: dict = {"provider_default": provider}
    if image_model.cloud_model_id:
        overrides["image_model"] = image_model.cloud_model_id
    # Apply the chosen LLM only when it shares the image model's provider (FigGen uses a
    # single provider per job for both LLM and image calls).
    if llm_model and llm_model.cloud_model_id and llm_model.provider == provider:
        slug = llm_model.cloud_model_id
        overrides.update(
            planner_model=slug, classifier_model=slug,
            vision_model=slug, chart_coder_model=slug, research_model=slug,
        )
    return base.model_copy(update=overrides)


def _mode_to_task(mode: Mode) -> str:
    if mode == Mode.img2img:
        return "sketch"
    return "generate"


async def run_figure_job(
    *,
    spec: GenSpec,
    project_id: str,
    job_id: str,
    image_model: ModelDef,
    llm_model: Optional[ModelDef],
    source: Optional[StagedInput] = None,
    references: Optional[list[StagedInput]] = None,
    on_progress: Callable[[float, str], None] = lambda p, m: None,
) -> FigureResult:
    """Run a single figure-generation job through the FigGen orchestrator."""
    store = figure_store()
    settings = _job_settings(image_model, llm_model)
    task = _mode_to_task(spec.mode)

    # Stage input images into the FigGen store (order matters: sketch=[source, *style refs]).
    ordered: list[StagedInput] = []
    if source is not None:
        ordered.append(source)
    ordered.extend(references or [])
    ref_ids: list[str] = []
    for inp in ordered:
        up = store.save_upload(project_id, inp.name, inp.data, kind="reference")
        ref_ids.append(up.file_id)

    req = JobRequest(
        task=task,
        prompt=spec.prompt,
        model_prefs=ModelPrefs(
            provider=settings.provider_default,  # type: ignore[arg-type]
            imager=image_model.cloud_model_id,
            max_critic_rounds=settings.max_critic_iters,
        ),
        research=settings.research_enabled_default,
        reference_image_ids=ref_ids,
    )
    record = JobRecord(job_id=job_id, project_id=project_id, request=req)
    store.create_job_dir(project_id, job_id)

    def progress_cb(ev: StageEvent) -> None:
        if ev.stage is not None:
            p = _STAGE_PROGRESS.get(ev.stage, 0.5)
            on_progress(p, ev.message or ev.stage.value)

    orch = Orchestrator(settings, store, critic_enabled=settings.critic_enabled)
    # FigGen rendering (cairosvg/vtracer) is sync CPU work; the LLM/image calls are async.
    # Running it directly is acceptable under the single heavy-worker model.
    artifacts = await orch.run(record, progress_cb)

    jd = store.job_dir(project_id, job_id)
    preview_png_path = jd / artifacts.get("preview.png", "preview.png")
    return FigureResult(
        preview_png=Path(preview_png_path).read_bytes(),
        svg_path=str(jd / artifacts.get("figure.svg", "figure.svg")),
        pptx_path=str(jd / artifacts.get("figure.pptx", "figure.pptx")),
        preview_svg_path=str(jd / artifacts.get("preview.svg", "preview.svg")),
        spec_path=str(jd / artifacts.get("spec.json", "spec.json")),
        job_dir=str(jd),
        artifacts=artifacts,
    )
