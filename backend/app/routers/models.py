"""Model catalog: the unified list the frontend picker reads — local ComfyUI/Ollama models
plus cloud OpenRouter models, for both image generation and chat/planner LLMs.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.engines import model_ready
from app.models_catalog.registry import LLM_MODELS, MODELS, ModelDef

router = APIRouter(prefix="/models", tags=["models"])


def _serialize(m: ModelDef) -> dict:
    return {
        "id": m.id,
        "label": m.label,
        "family": m.family,
        "kind": m.kind,                 # "image" | "llm"
        "engine": m.engine,             # local-comfy | local-ollama | cloud-openrouter
        "provider": m.provider,
        "vram_gb": m.vram_gb,
        "modes": [mode.value for mode in m.supports],
        "nsfw": m.nsfw,
        "uses_negative": m.uses_negative,
        "cloud_model_id": m.cloud_model_id,
        "vision": m.vision,             # llm: accepts image input (multimodal)
        "ready": model_ready(m),
    }


@router.get("")
async def list_models() -> list[dict]:
    """All image-generation models (backward-compatible: image models only)."""
    return [_serialize(m) for m in MODELS.values()]


@router.get("/all")
async def list_all_models() -> dict:
    """Both catalogs, grouped by kind — used by the unified model picker."""
    return {
        "image": [_serialize(m) for m in MODELS.values()],
        "llm": [_serialize(m) for m in LLM_MODELS.values()],
    }


@router.get("/llm")
async def list_llm_models() -> list[dict]:
    return [_serialize(m) for m in LLM_MODELS.values()]
