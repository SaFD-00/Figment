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
    family: str                      # qwen-image|sdxl|qwen-edit|cloud|ollama
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


# ── Image-generation models ────────────────────────────────────────────────
MODELS: dict[str, ModelDef] = {
    # ── Local generation (uncensored: abliterated Qwen2.5-VL TE + NSFW LoRA) ─
    "qwen-image": ModelDef(
        id="qwen-image", family="qwen-image", label="Qwen-Image 2512 (local · uncensored txt2img)",
        vram_gb=13.0, supports=(Mode.txt2img, Mode.img2img),
        files={"unet": "Qwen-Image-2512-Q4_K_M.gguf",   # VERIFY repo/filename
               # abliterated Qwen2.5-VL text encoder lifts the refusal bias (base Qwen has no active
               # censorship — only the TE's refusal lean + missing safety training).
               "clip": "Qwen2.5-VL-7B-Instruct-abliterated-Q4_K_M.gguf",  # VERIFY repo/filename
               "vae": "qwen_image_vae.safetensors"},
        uses_negative=False, nsfw=True,
        defaults={"steps": 8, "cfg": 1.0, "sampler": "euler", "scheduler": "simple"},
        template="txt2img_qwen",
        builtin_loras=(
            ("Qwen-Image-Lightning-8steps.safetensors", 1.0),  # VERIFY 8-step distill LoRA
            ("qwen_MCNL_v1.0.safetensors", 1.0),               # VERIFY NSFW LoRA (goonsai)
        ),
    ),
    "pony-v6": ModelDef(
        id="pony-v6", family="sdxl", label="Pony Diffusion V6 XL (local · explicit NSFW)",
        vram_gb=7.0, supports=(Mode.txt2img, Mode.img2img, Mode.controlnet),
        files={"checkpoint": "ponyDiffusionV6XL_v6StartWithThisOne.safetensors"},
        uses_negative=True, nsfw=True,
        defaults={"steps": 28, "cfg": 7.0, "sampler": "dpmpp_2m_sde", "scheduler": "karras"},
        template="txt2img_sdxl_lora",
    ),
    # ── Local inpaint (masked region redraw) ────────────────────────────────
    "lustify-inpaint": ModelDef(
        id="lustify-inpaint", family="sdxl", label="LUSTIFY SDXL NSFW (local · inpaint)",
        vram_gb=7.0, supports=(Mode.inpaint,),
        files={"checkpoint": "lustifySDXLNSFW_v20-inpainting.safetensors"},  # VERIFY genuine 9-ch inpaint UNet
        uses_negative=True, nsfw=True,
        defaults={"steps": 30, "cfg": 6.0, "sampler": "dpmpp_2m", "scheduler": "karras"},
        template="inpaint_sdxl",
    ),
    # ── Local instruction + reference edit (shared abliterated TE + NSFW LoRA) ─
    "qwen-edit": ModelDef(
        id="qwen-edit", family="qwen-edit", label="Qwen-Image-Edit 2511 (local · edit + reference)",
        vram_gb=13.0, supports=(Mode.edit, Mode.reference),
        files={"unet": "Qwen-Image-Edit-2511-Q4_K_M.gguf",
               "clip": "Qwen2.5-VL-7B-Instruct-abliterated-Q4_K_M.gguf",  # shared abliterated TE
               "vae": "qwen_image_vae.safetensors"},
        uses_negative=False, nsfw=True,
        defaults={"steps": 4, "cfg": 1.0, "sampler": "euler", "scheduler": "simple"},
        template="edit_qwen_lightning",
        builtin_loras=(
            ("Qwen-Image-Edit-2511-Lightning.safetensors", 1.0),
            ("qwen_MCNL_v1.0.safetensors", 1.0),  # VERIFY NSFW LoRA (goonsai; edit-compatible)
        ),
    ),
    # ── Cloud image models (all OpenRouter) ─────────────────────────────────
    "gpt-image-2": ModelDef(
        id="gpt-image-2", family="cloud", label="GPT Image 2 (cloud · OpenRouter)",
        vram_gb=0.0, supports=(Mode.txt2img, Mode.img2img, Mode.edit, Mode.inpaint),
        engine=ENGINE_CLOUD_OPENROUTER, kind="image", provider="openrouter",
        cloud_model_id="openai/gpt-image-2",   # VERIFY slug
    ),
    "nano-banana-2": ModelDef(
        id="nano-banana-2", family="cloud", label="Nano Banana 2 (cloud · OpenRouter)",
        vram_gb=0.0, supports=(Mode.txt2img, Mode.img2img, Mode.edit, Mode.reference),
        engine=ENGINE_CLOUD_OPENROUTER, kind="image", provider="openrouter",
        cloud_model_id="google/nano-banana-2",   # VERIFY slug
    ),
    "seedream-4.5": ModelDef(
        id="seedream-4.5", family="cloud", label="SeeDream 4.5 (cloud · BioRender-grade)",
        vram_gb=0.0, supports=(Mode.txt2img, Mode.img2img, Mode.edit, Mode.reference),
        engine=ENGINE_CLOUD_OPENROUTER, kind="image", provider="openrouter",
        cloud_model_id="bytedance-seed/seedream-4.5",
        defaults={"aspect_ratio": "1:1", "image_size": "2K"},
    ),
    "flux2-max": ModelDef(
        id="flux2-max", family="cloud", label="FLUX.2 Max (cloud · OpenRouter)",
        vram_gb=0.0, supports=(Mode.txt2img, Mode.img2img, Mode.edit, Mode.reference),
        engine=ENGINE_CLOUD_OPENROUTER, kind="image", provider="openrouter",
        cloud_model_id="black-forest-labs/flux.2-max",
    ),
    "flux2-pro": ModelDef(
        id="flux2-pro", family="cloud", label="FLUX.2 Pro (cloud · OpenRouter)",
        vram_gb=0.0, supports=(Mode.txt2img, Mode.img2img, Mode.edit, Mode.reference),
        engine=ENGINE_CLOUD_OPENROUTER, kind="image", provider="openrouter",
        cloud_model_id="black-forest-labs/flux.2-pro",
    ),
    "flux2-flex": ModelDef(
        id="flux2-flex", family="cloud", label="FLUX.2 Flex (cloud · OpenRouter)",
        vram_gb=0.0, supports=(Mode.txt2img, Mode.img2img, Mode.edit, Mode.reference),
        engine=ENGINE_CLOUD_OPENROUTER, kind="image", provider="openrouter",
        cloud_model_id="black-forest-labs/flux.2-flex",
    ),
}

# ── Chat / planner LLM models ───────────────────────────────────────────────
LLM_MODELS: dict[str, ModelDef] = {
    "qwen-9b-local": ModelDef(
        id="qwen-9b-local", family="ollama", label="Qwen3.5-9B Uncensored (local · Ollama)",
        vram_gb=6.5, supports=(), engine=ENGINE_LOCAL_OLLAMA, kind="llm", provider="ollama",
        cloud_model_id="hf.co/HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive:Q4_K_M",
    ),
    "qwen-4b-local": ModelDef(
        id="qwen-4b-local", family="ollama", label="Qwen3.5-4B Uncensored (local · Ollama, light)",
        vram_gb=3.4, supports=(), engine=ENGINE_LOCAL_OLLAMA, kind="llm", provider="ollama",
        cloud_model_id="hf.co/HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive:Q4_K_M",
    ),
    "gpt-oss-20b": ModelDef(
        id="gpt-oss-20b", family="cloud", label="GPT-OSS 20B (cloud · OpenRouter, free)",
        vram_gb=0.0, supports=(), engine=ENGINE_CLOUD_OPENROUTER, kind="llm", provider="openrouter",
        cloud_model_id="openai/gpt-oss-20b:free",
    ),
    "gpt-oss-120b": ModelDef(
        id="gpt-oss-120b", family="cloud", label="GPT-OSS 120B (cloud · OpenRouter, free)",
        vram_gb=0.0, supports=(), engine=ENGINE_CLOUD_OPENROUTER, kind="llm", provider="openrouter",
        cloud_model_id="openai/gpt-oss-120b:free",
    ),
    "qwen3-plus": ModelDef(
        id="qwen3-plus", family="cloud", label="Qwen3.7 Plus (cloud · OpenRouter)",
        vram_gb=0.0, supports=(), engine=ENGINE_CLOUD_OPENROUTER, kind="llm", provider="openrouter",
        cloud_model_id="qwen/qwen3.7-plus",
    ),
    "qwen3-flash": ModelDef(
        id="qwen3-flash", family="cloud", label="Qwen3.6 Flash (cloud · OpenRouter)",
        vram_gb=0.0, supports=(), engine=ENGINE_CLOUD_OPENROUTER, kind="llm", provider="openrouter",
        cloud_model_id="qwen/qwen3.6-flash",
    ),
    "qwen3-35b-a3b": ModelDef(
        id="qwen3-35b-a3b", family="cloud", label="Qwen3.6 35B-A3B (cloud · OpenRouter)",
        vram_gb=0.0, supports=(), engine=ENGINE_CLOUD_OPENROUTER, kind="llm", provider="openrouter",
        cloud_model_id="qwen/qwen3.6-35b-a3b",
    ),
}


# Default IMAGE model chosen per mode when GenSpec.model is null (local-first; cloud fallback).
DEFAULT_BY_MODE: dict[Mode, str] = {
    Mode.txt2img: "qwen-image",
    Mode.img2img: "qwen-image",
    Mode.inpaint: "lustify-inpaint",
    Mode.edit: "qwen-edit",
    Mode.controlnet: "pony-v6",
    Mode.reference: "qwen-edit",
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

UPSCALE_MODEL = "RealESRGAN_x4.pth"
PONY_SCORE_PREFIX = "score_9, score_8_up, score_7_up, "


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
