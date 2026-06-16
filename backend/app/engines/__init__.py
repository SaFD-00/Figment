"""Engine abstraction — routes a resolved model to the right execution backend.

Engines:
  • local-comfy   → ComfyUI diffusion graphs (app.comfy.*) — existing ImgGen path.
  • local-ollama  → Ollama chat LLM (app.llm.ollama_client).
  • cloud-openrouter → vendored FigGen providers on OpenRouter (figure pipeline + image/LLM).

This module centralizes which engine handles a given model so routers/queue can dispatch
without hard-coding provider checks.
"""
from __future__ import annotations

from app.config import get_settings
from app.engines.cloud import cloud_key_present, figure_settings
from app.models_catalog.registry import (
    ENGINE_CLOUD_OPENROUTER,
    ENGINE_LOCAL_COMFY,
    ENGINE_LOCAL_OLLAMA,
    ModelDef,
    is_cloud,
)

__all__ = [
    "engine_of",
    "model_ready",
    "cloud_key_present",
    "figure_settings",
]


def engine_of(model: ModelDef) -> str:
    return model.engine


def _local_file_ready(model: ModelDef) -> bool:
    """A local ComfyUI model is ready when its primary weight file is on disk."""
    s = get_settings()
    primary = model.files.get("unet") or model.files.get("checkpoint")
    if not primary:
        return False
    for sub in ("unet", "checkpoints"):
        if (s.models_dir / sub / primary).exists():
            return True
    return False


def model_ready(model: ModelDef) -> bool:
    """Whether a model can actually be used right now.

    • cloud      → the provider API key is configured.
    • local-comfy→ the weight file exists under AIStudio/models.
    • local-ollama→ assumed installed via scripts (best-effort; verified at job time).
    """
    if is_cloud(model):
        return cloud_key_present(model.provider or "")
    if model.engine == ENGINE_LOCAL_COMFY:
        return _local_file_ready(model)
    if model.engine == ENGINE_LOCAL_OLLAMA:
        return True
    return False
