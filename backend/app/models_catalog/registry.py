"""Unified model registry — the single source of truth for every model the user can pick,
spanning the LOCAL engine (ComfyUI diffusion + Ollama LLM) and the CLOUD engine
(OpenRouter for both image generation and LLM).

Two catalogs:
  • MODELS      — image-generation models (local ComfyUI + cloud OpenRouter), keyed by id.
  • LLM_MODELS  — chat/planner LLMs (local Ollama + cloud OpenRouter), keyed by id.

Local ComfyUI `files` names must match what scripts/20_download_models.sh places under
~/AIStudio/models/<dir>. FP8 files are never listed — they corrupt on Metal.
Cloud models carry a `cloud_model_id` (the provider slug) and `provider` instead of files.
Cloud slugs marked `# VERIFY` are best-guess preview names — overridable, confirm on OpenRouter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.schemas.genspec import Mode

# engine values
ENGINE_LOCAL_COMFY = "local-comfy"
ENGINE_LOCAL_OLLAMA = "local-ollama"
ENGINE_CLOUD_OPENROUTER = "cloud-openrouter"


@dataclass(frozen=True)
class ModelDef:
    id: str
    family: str                      # sdxl|cloud|ollama
    label: str
    vram_gb: float
    supports: tuple[Mode, ...]
    files: dict[str, str] = field(default_factory=dict)  # role -> filename (local only)
    uses_negative: bool = False
    nsfw: bool = False
    defaults: dict = field(default_factory=dict)   # steps,cfg,sampler,scheduler
    template: Optional[str] = None   # ComfyUI builder path key; defaults to family if None
    builtin_loras: tuple[tuple[str, float], ...] = ()
    # engine routing
    engine: str = ENGINE_LOCAL_COMFY
    kind: str = "image"              # "image" | "llm"
    provider: Optional[str] = None   # cloud: "openrouter"|"openai"; local llm: "ollama"
    cloud_model_id: Optional[str] = None  # provider slug for cloud / ollama tag for local llm
    vision: bool = False             # llm: accepts image input (multimodal) — gates image-enhance


# ── Image-generation models ────────────────────────────────────────────────
MODELS: dict[str, ModelDef] = {
    # ── Local generation — a single uncensored SDXL checkpoint (Juggernaut XL, NSFW build) that
    # serves every local mode. txt2img/img2img/inpaint(+SetLatentNoiseMask)/edit run on the
    # checkpoint directly; reference goes through IP-Adapter Plus (single image); controlnet reuses
    # the same checkpoint. No GGUF/Qwen stack — one big model keeps the 24GB budget simple. ──────
    "juggernaut-xl": ModelDef(
        id="juggernaut-xl", family="sdxl",
        label="Juggernaut XL (local · NSFW · all modes)",
        vram_gb=7.0,
        supports=(Mode.txt2img, Mode.img2img, Mode.inpaint, Mode.edit,
                  Mode.controlnet, Mode.reference),
        files={"checkpoint": "juggernautXL_v9.safetensors"},  # VERIFY repo/filename (CivitAI NSFW build)
        uses_negative=True, nsfw=True,
        defaults={"steps": 28, "cfg": 7.0, "sampler": "dpmpp_2m", "scheduler": "karras"},
        template="txt2img_sdxl_lora",
        # Optional NSFW LoRA (CivitAI, strength ~0.8) — add here once a file is chosen, e.g.
        # builtin_loras=(("juggernaut_nsfw.safetensors", 0.8),),  # VERIFY filename
        builtin_loras=(),
    ),
    # ── Cloud image models (all OpenRouter) ─────────────────────────────────
    "gpt-image-2": ModelDef(
        id="gpt-image-2", family="cloud", label="GPT Image 2 (cloud · OpenRouter)",
        vram_gb=0.0,
        supports=(Mode.txt2img, Mode.img2img, Mode.edit, Mode.inpaint, Mode.reference),
        engine=ENGINE_CLOUD_OPENROUTER, kind="image", provider="openrouter",
        cloud_model_id="openai/gpt-5.4-image-2",   # VERIFY slug (Elo T2I #1)
    ),
    "gpt-image-1": ModelDef(
        id="gpt-image-1", family="cloud", label="GPT Image 1 (cloud · OpenRouter)",
        vram_gb=0.0,
        supports=(Mode.txt2img, Mode.img2img, Mode.edit, Mode.inpaint, Mode.reference),
        engine=ENGINE_CLOUD_OPENROUTER, kind="image", provider="openrouter",
        cloud_model_id="openai/gpt-5-image",   # VERIFY slug (Elo Edit #1)
    ),
    "gemini-flash-image": ModelDef(
        id="gemini-flash-image", family="cloud", label="Gemini 3.1 Flash Image (cloud · OpenRouter)",
        vram_gb=0.0, supports=(Mode.txt2img, Mode.img2img, Mode.edit, Mode.reference),
        engine=ENGINE_CLOUD_OPENROUTER, kind="image", provider="openrouter",
        cloud_model_id="google/gemini-3.1-flash-image",   # VERIFY slug
    ),
    "gemini-pro-image": ModelDef(
        id="gemini-pro-image", family="cloud", label="Gemini 3 Pro Image (cloud · OpenRouter)",
        vram_gb=0.0, supports=(Mode.txt2img, Mode.img2img, Mode.edit, Mode.reference),
        engine=ENGINE_CLOUD_OPENROUTER, kind="image", provider="openrouter",
        cloud_model_id="google/gemini-3-pro-image",   # VERIFY slug
    ),
}

# ── Chat / planner LLM models — every entry is multimodal (vision=True) so prompt-enhance can
# read an uploaded edit/reference image on either route. The Ollama client converts OpenAI-style
# multimodal messages into Ollama's native per-message `images` array; cloud forwards as-is. ─────
LLM_MODELS: dict[str, ModelDef] = {
    # Single local VLM: an uncensored multimodal "thinking" model (Huihui Qwen3-VL 8B abliterated)
    # so local prompt-enhance / mask-region judgement can read images too.
    "qwen3-vl-local": ModelDef(
        id="qwen3-vl-local", family="ollama",
        label="Huihui Qwen3-VL 8B abliterated (local · Ollama, multimodal)",
        vram_gb=5.0, supports=(), engine=ENGINE_LOCAL_OLLAMA, kind="llm", provider="ollama",
        cloud_model_id="huihui_ai/qwen3-vl-abliterated:8b", vision=True,  # VERIFY Ollama tag
    ),
    # Cloud VLMs (OpenRouter). Any one serves chat + planner + vision-enhance.
    "gemini-2.5-flash": ModelDef(
        id="gemini-2.5-flash", family="cloud",
        label="Gemini 2.5 Flash (cloud · OpenRouter, multimodal)",
        vram_gb=0.0, supports=(), engine=ENGINE_CLOUD_OPENROUTER, kind="llm", provider="openrouter",
        cloud_model_id="google/gemini-2.5-flash", vision=True,
    ),
    "gpt-5.4-mini": ModelDef(
        id="gpt-5.4-mini", family="cloud",
        label="GPT-5.4 mini (cloud · OpenRouter, multimodal)",
        vram_gb=0.0, supports=(), engine=ENGINE_CLOUD_OPENROUTER, kind="llm", provider="openrouter",
        cloud_model_id="openai/gpt-5.4-mini", vision=True,   # VERIFY slug
    ),
    "qwen3-6-flash": ModelDef(
        id="qwen3-6-flash", family="cloud",
        label="Qwen3.6 Flash (cloud · OpenRouter, multimodal)",
        vram_gb=0.0, supports=(), engine=ENGINE_CLOUD_OPENROUTER, kind="llm", provider="openrouter",
        cloud_model_id="qwen/qwen3-6-flash", vision=True,   # VERIFY slug
    ),
}


# Default IMAGE model chosen per mode when GenSpec.model is null. The local lineup is now a single
# SDXL checkpoint, so every mode resolves to it (local-first; cloud is an explicit UI pick).
DEFAULT_BY_MODE: dict[Mode, str] = {
    Mode.txt2img: "juggernaut-xl",
    Mode.img2img: "juggernaut-xl",
    Mode.inpaint: "juggernaut-xl",
    Mode.edit: "juggernaut-xl",
    Mode.controlnet: "juggernaut-xl",
    Mode.reference: "juggernaut-xl",
}

# Lighter equivalents the orchestrator can downshift to under memory pressure.
# Empty: the trimmed uncensored lineup has no meaningful lighter uncensored stand-in
# (downshift() then safely returns the original model unchanged).
LIGHTER_EQUIVALENT: dict[str, str] = {}

# SDXL ControlNet model files keyed by control type.
CONTROLNET_FILES: dict[str, str] = {
    "canny": "controlnet-canny-sdxl-1.0.safetensors",
    "depth": "controlnet-depth-sdxl-1.0.safetensors",
    "scribble": "controlnet-scribble-sdxl-1.0.safetensors",
    "lineart": "controlnet-lineart-sdxl-1.0.safetensors",
}

# IP-Adapter Plus (SDXL) reference-image weights. The IP-Adapter model lives in models/ipadapter;
# the CLIP-ViT-H vision model lives in models/clip_vision. Both names must match what
# scripts/20_download_models.sh places on disk (and the ipadapter path in extra_model_paths.yaml).
IPADAPTER_FILES: dict[str, str] = {
    "ipadapter": "ip-adapter-plus_sdxl_vit-h.safetensors",         # VERIFY repo/filename
    "clip_vision": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors",  # VERIFY repo/filename
}

UPSCALE_MODEL = "RealESRGAN_x4.pth"


def resolve(model_id: Optional[str], mode: Mode) -> ModelDef:
    """Resolve an image-generation model id (falling back to the per-mode default)."""
    if model_id and model_id in MODELS:
        return MODELS[model_id]
    return MODELS[DEFAULT_BY_MODE[mode]]


def resolve_llm(model_id: Optional[str]) -> Optional[ModelDef]:
    """Resolve a chat/planner LLM model id (None if unknown)."""
    if model_id and model_id in LLM_MODELS:
        return LLM_MODELS[model_id]
    return None


def is_cloud(m: ModelDef) -> bool:
    return m.engine == ENGINE_CLOUD_OPENROUTER
