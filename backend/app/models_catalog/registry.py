"""Unified model registry — the single source of truth for every model the user can pick,
spanning the LOCAL engine (ComfyUI diffusion + Ollama LLM) and the CLOUD engine
(OpenRouter / OpenAI for both image generation and LLM).

Two catalogs:
  • MODELS      — image-generation models (local ComfyUI + cloud APIs), keyed by id.
  • LLM_MODELS  — chat/planner LLMs (local Ollama + cloud APIs), keyed by id.

Local ComfyUI `files` names must match what scripts/20_download_models.sh places under
~/AIStudio/models/<dir>. FP8 files are never listed — they corrupt on Metal.
Cloud models carry a `cloud_model_id` (the provider slug) and `provider` instead of files.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.schemas.genspec import Mode

# engine values
ENGINE_LOCAL_COMFY = "local-comfy"
ENGINE_LOCAL_OLLAMA = "local-ollama"
ENGINE_CLOUD_OPENROUTER = "cloud-openrouter"
ENGINE_CLOUD_OPENAI = "cloud-openai"


@dataclass(frozen=True)
class ModelDef:
    id: str
    family: str                      # chroma|flux|sdxl|z-image|flux-fill|qwen-edit|kontext|cloud|ollama
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
    # ── Local ComfyUI bases ────────────────────────────────────────────────
    "chroma-hd": ModelDef(
        id="chroma-hd", family="chroma", label="Chroma 1-HD (local · uncensored, quality)",
        vram_gb=10.0, supports=(Mode.txt2img, Mode.img2img),
        files={"unet": "Chroma1-HD-Q5_K_M.gguf", "clip": "t5-v1_1-xxl-encoder-Q5_K_M.gguf",
               "clip2": "clip_l.safetensors", "vae": "ae.safetensors"},
        uses_negative=False, nsfw=True,
        defaults={"steps": 28, "cfg": 4.0, "sampler": "euler", "scheduler": "simple"},
        template="txt2img_chroma",
    ),
    "z-image": ModelDef(
        id="z-image", family="z-image", label="Z-Image Turbo (local · fast, light)",
        vram_gb=4.0, supports=(Mode.txt2img, Mode.img2img),
        files={"checkpoint": "z-image-turbo.safetensors"},
        uses_negative=False, nsfw=True,
        defaults={"steps": 8, "cfg": 1.0, "sampler": "euler", "scheduler": "simple"},
        template="txt2img_zimage",
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
    "flux-fill": ModelDef(
        id="flux-fill", family="flux-fill", label="FLUX.1 Fill (local · inpaint)",
        vram_gb=8.0, supports=(Mode.inpaint,),
        files={"unet": "FLUX.1-Fill-dev-Q5_K_M.gguf", "clip": "t5-v1_1-xxl-encoder-Q5_K_M.gguf",
               "clip2": "clip_l.safetensors", "vae": "ae.safetensors"},
        defaults={"steps": 24, "cfg": 30.0, "sampler": "euler", "scheduler": "normal"},
        template="inpaint_flux_fill",
    ),
    "sdxl-inpaint": ModelDef(
        id="sdxl-inpaint", family="sdxl", label="SDXL Inpainting (local · fast)",
        vram_gb=7.0, supports=(Mode.inpaint,),
        files={"checkpoint": "sd_xl_inpainting_0.1.safetensors"},
        uses_negative=True,
        defaults={"steps": 24, "cfg": 7.0, "sampler": "dpmpp_2m", "scheduler": "karras"},
        template="inpaint_sdxl",
    ),
    # ── Local instruction / reference edit ──────────────────────────────────
    "qwen-edit": ModelDef(
        id="qwen-edit", family="qwen-edit", label="Qwen-Image-Edit 2511 (local · instruction edit)",
        vram_gb=13.0, supports=(Mode.edit,),
        files={"unet": "Qwen-Image-Edit-2511-Q4_K_M.gguf"},
        defaults={"steps": 4, "cfg": 1.0, "sampler": "euler", "scheduler": "simple"},
        template="edit_qwen_lightning",
        builtin_loras=(("Qwen-Image-Edit-2511-Lightning.safetensors", 1.0),),
    ),
    "kontext": ModelDef(
        id="kontext", family="kontext", label="FLUX.1 Kontext (local · reference edit)",
        vram_gb=7.0, supports=(Mode.edit, Mode.reference),
        files={"unet": "flux1-kontext-dev-Q4_K_M.gguf", "clip": "t5-v1_1-xxl-encoder-Q5_K_M.gguf",
               "clip2": "clip_l.safetensors", "vae": "ae.safetensors"},
        defaults={"steps": 20, "cfg": 2.5, "sampler": "euler", "scheduler": "simple"},
        template="edit_kontext",
    ),
    # ── Local style reference ───────────────────────────────────────────────
    "redux": ModelDef(
        id="redux", family="flux", label="FLUX Redux (local · style reference)",
        vram_gb=10.0, supports=(Mode.reference,),
        files={"unet": "Chroma1-HD-Q5_K_M.gguf", "clip": "t5-v1_1-xxl-encoder-Q5_K_M.gguf",
               "clip2": "clip_l.safetensors", "vae": "ae.safetensors",
               "style_model": "flux1-redux-dev.safetensors", "clip_vision": "sigclip_vision_patch14_384.safetensors"},
        defaults={"steps": 24, "cfg": 3.5, "sampler": "euler", "scheduler": "simple"},
        template="redux_flux",
    ),
    # ── Cloud image models (OpenRouter / OpenAI) ────────────────────────────
    "seedream-4.5": ModelDef(
        id="seedream-4.5", family="cloud", label="SeeDream 4.5 (cloud · BioRender-grade)",
        vram_gb=0.0, supports=(Mode.txt2img, Mode.img2img, Mode.edit, Mode.reference),
        engine=ENGINE_CLOUD_OPENROUTER, kind="image", provider="openrouter",
        cloud_model_id="bytedance-seed/seedream-4.5",
        defaults={"aspect_ratio": "1:1", "image_size": "2K"},
    ),
    "gpt-image-1.5": ModelDef(
        id="gpt-image-1.5", family="cloud", label="GPT-Image 1.5 (cloud · transparent PNG)",
        vram_gb=0.0, supports=(Mode.txt2img, Mode.img2img, Mode.edit, Mode.inpaint),
        engine=ENGINE_CLOUD_OPENAI, kind="image", provider="openai",
        cloud_model_id="gpt-image-1.5",
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
    "minimax-m3": ModelDef(
        id="minimax-m3", family="cloud", label="MiniMax M3 (cloud · OpenRouter)",
        vram_gb=0.0, supports=(), engine=ENGINE_CLOUD_OPENROUTER, kind="llm", provider="openrouter",
        cloud_model_id="minimax/minimax-m3",
    ),
    "claude-opus-4.8": ModelDef(
        id="claude-opus-4.8", family="cloud", label="Claude Opus 4.8 (cloud · OpenRouter)",
        vram_gb=0.0, supports=(), engine=ENGINE_CLOUD_OPENROUTER, kind="llm", provider="openrouter",
        cloud_model_id="anthropic/claude-opus-4.8",
    ),
    "gpt-5.4": ModelDef(
        id="gpt-5.4", family="cloud", label="GPT-5.4 (cloud · OpenAI)",
        vram_gb=0.0, supports=(), engine=ENGINE_CLOUD_OPENAI, kind="llm", provider="openai",
        cloud_model_id="gpt-5.4",
    ),
}


# Default IMAGE model chosen per mode when GenSpec.model is null (local-first; cloud fallback).
DEFAULT_BY_MODE: dict[Mode, str] = {
    Mode.txt2img: "chroma-hd",
    Mode.img2img: "chroma-hd",
    Mode.inpaint: "flux-fill",
    Mode.edit: "qwen-edit",
    Mode.controlnet: "pony-v6",
    Mode.reference: "redux",
}

# Lighter equivalents the orchestrator can downshift to under memory pressure.
LIGHTER_EQUIVALENT: dict[str, str] = {
    "chroma-hd": "z-image",
    "qwen-edit": "kontext",
    "flux-fill": "sdxl-inpaint",
}

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
    return m.engine in (ENGINE_CLOUD_OPENROUTER, ENGINE_CLOUD_OPENAI)
