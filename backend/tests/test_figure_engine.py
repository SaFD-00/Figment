"""Hermetic tests for the cloud figure engine + export helpers.

With no API key configured the FigGen registry falls back to the mock provider, so the full
pipeline (classify → plan → style → assets → render → finalize) runs offline and still emits
real editable SVG/PPTX artifacts.
"""
from __future__ import annotations

import io

from PIL import Image

from app.engines.figure_pipeline import run_figure_job
from app.models_catalog.registry import LLM_MODELS, MODELS
from app.schemas.genspec import GenSpec, Mode
from app.services import export_ops


async def test_figure_pipeline_generates_editable_artifacts(tmp_path, monkeypatch):
    # Route the figure store under a temp AIStudio so the test is hermetic.
    import app.config as cfg
    import app.engines.figure_pipeline as fp

    settings = cfg.get_settings()
    monkeypatch.setattr(settings, "aistudio_home", tmp_path, raising=False)
    fp.figure_store.cache_clear()

    spec = GenSpec(
        mode=Mode.txt2img, model="seedream-4.5", llm_model="minimax-m3",
        prompt="A method diagram of a three-step assay",
    )
    result = await run_figure_job(
        spec=spec, project_id="p_test", job_id="j_test",
        image_model=MODELS["seedream-4.5"], llm_model=LLM_MODELS["minimax-m3"],
    )

    assert len(result.preview_png) > 0
    import os
    assert os.path.exists(result.svg_path) and os.path.getsize(result.svg_path) > 0
    assert os.path.exists(result.pptx_path) and os.path.getsize(result.pptx_path) > 0
    assert result.artifacts.get("figure.svg") == "figure.svg"
    fp.figure_store.cache_clear()


def _png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (40, 120, 200)).save(buf, "PNG")
    return buf.getvalue()


def test_png_to_svg_is_svg():
    svg = export_ops.png_to_svg(_png(48, 48))
    assert "<svg" in svg.lower()


def test_png_to_pptx_handles_small_and_large():
    for dims in [(32, 32), (1024, 768), (1536, 512)]:
        pptx = export_ops.png_to_pptx(_png(*dims))
        assert pptx[:2] == b"PK"  # valid zip/OOXML
