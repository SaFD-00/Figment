"""Unified model registry — the single source of truth for every model the user can pick,
spanning the LOCAL engine (ComfyUI diffusion + Ollama LLM) and the CLOUD engine
(OpenRouter for both image generation and LLM).

Two catalogs:
  • MODELS      — image/video-generation models (local ComfyUI + cloud OpenRouter), keyed by id.
  • LLM_MODELS  — chat/planner LLMs (local Ollama + cloud OpenRouter), keyed by id.

LOCAL TARGET: a single NVIDIA H100 80GB (CUDA). bf16/fp16/fp8 safetensors are all first-class
(the old "never fp8 — corrupts on Metal" rule is gone). The whole photoreal feature set is sized to
CO-RESIDE at once (~70GB), so the orchestrator no longer serialises one-big-model-at-a-time.

Local ComfyUI `files` names must match what scripts/20_download_models.sh places under
<repo>/AIStudio/models/<dir>. Cloud models carry a `cloud_model_id` (the provider slug) and
`provider` instead of files. Slugs/filenames marked `# VERIFY` are best-guess — confirm on the repo.
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
    family: str                      # chroma|sdxl|flux|flux-fill|qwen-edit|kontext|identity|video|cloud|ollama
    label: str
    vram_gb: float                   # bf16/fp8 CUDA footprint on H100 (incl. shared encoders)
    supports: tuple[Mode, ...]
    files: dict[str, str] = field(default_factory=dict)  # role -> filename (local only)
    uses_negative: bool = False
    nsfw: bool = False
    defaults: dict = field(default_factory=dict)   # steps,cfg,sampler,scheduler
    template: Optional[str] = None   # ComfyUI builder path key; defaults to family if None
    builtin_loras: tuple[tuple[str, float], ...] = ()       # high-noise expert (or sole model) LoRAs
    builtin_loras_low: tuple[tuple[str, float], ...] = ()   # low-noise expert LoRAs (A14B MoE video only)
    # engine routing
    engine: str = ENGINE_LOCAL_COMFY
    kind: str = "image"              # "image" | "video" | "llm"
    provider: Optional[str] = None   # cloud: "openrouter"|"openai"; local llm: "ollama"
    cloud_model_id: Optional[str] = None  # provider slug for cloud / ollama tag for local llm
    vision: bool = False             # llm: accepts image input (multimodal) — gates image-enhance


# Shared FLUX/Chroma encoders + VAE (native safetensors on CUDA). Chroma uses a SINGLE T5.
_T5 = "t5xxl_fp8_e4m3fn.safetensors"       # VERIFY: comfyanonymous/flux_text_encoders
_CLIP_L = "clip_l.safetensors"
_FLUX_VAE = "ae.safetensors"
_CHROMA_UNET = "Chroma1-HD-fp8.safetensors"  # VERIFY: lodestones/Chroma1-HD (native fp8 single-file)
_LUSTIFY = "lustifySDXLNSFW_v40.safetensors"  # VERIFY: TheImposterImposters/LUSTIFY-v4.0 / civitai 573152

# ── Image/Video-generation models ──────────────────────────────────────────
MODELS: dict[str, ModelDef] = {
    # ── Local txt2img/img2img bases (photoreal) ─────────────────────────────
    "chroma-hd": ModelDef(
        id="chroma-hd", family="chroma", label="Chroma 1-HD (local · uncensored photoreal, quality)",
        vram_gb=15.0, supports=(Mode.txt2img, Mode.img2img),
        files={"unet": _CHROMA_UNET, "clip": _T5, "vae": _FLUX_VAE},  # native fp8 (single T5, FLUX VAE)
        uses_negative=False, nsfw=True,
        defaults={"steps": 28, "cfg": 4.0, "sampler": "euler", "scheduler": "simple"},
        template="txt2img_chroma",
    ),
    "lustify": ModelDef(
        id="lustify", family="sdxl", label="LUSTIFY! SDXL v4 (local · fast explicit photoreal)",
        vram_gb=8.0, supports=(Mode.txt2img, Mode.img2img, Mode.controlnet),
        files={"checkpoint": _LUSTIFY},
        uses_negative=True, nsfw=True,
        defaults={"steps": 28, "cfg": 6.0, "sampler": "dpmpp_2m_sde", "scheduler": "karras"},
        template="txt2img_sdxl_lora",  # SDXL CheckpointLoaderSimple path; also the adapter base
    ),
    # ── Local inpaint (masked region redraw) ────────────────────────────────
    "flux-fill": ModelDef(
        id="flux-fill", family="flux-fill", label="FLUX.1 Fill (local · inpaint, prompt-faithful)",
        vram_gb=12.0, supports=(Mode.inpaint,),
        files={"unet": "FLUX.1-Fill-dev-Q5_K_M.gguf", "clip": "t5-v1_1-xxl-encoder-Q5_K_M.gguf",
               "clip2": _CLIP_L, "vae": _FLUX_VAE},  # GGUF kept (non-default; needs NSFW LoRA)
        defaults={"steps": 24, "cfg": 30.0, "sampler": "euler", "scheduler": "normal"},
        template="inpaint_flux_fill",
    ),
    "sdxl-inpaint": ModelDef(
        id="sdxl-inpaint", family="sdxl", label="LUSTIFY SDXL Inpainting (local · explicit, fast)",
        vram_gb=8.0, supports=(Mode.inpaint,),
        files={"checkpoint": "lustifySDXL_inpainting.safetensors"},  # VERIFY: andro-flock/LUSTIFY-SDXL-NSFW-checkpoint-v2-0-INPAINTING
        uses_negative=True, nsfw=True,
        defaults={"steps": 24, "cfg": 7.0, "sampler": "dpmpp_2m", "scheduler": "karras"},
        template="inpaint_sdxl",
    ),
    # ── Local instruction / reference edit ──────────────────────────────────
    "qwen-edit-aio": ModelDef(
        id="qwen-edit-aio", family="qwen-edit", label="Qwen-Image-Edit Rapid AIO (local · NSFW instruction edit)",
        vram_gb=29.0, supports=(Mode.edit,),
        files={"checkpoint": "Qwen-Image-Edit-Rapid-AIO.safetensors"},  # VERIFY: Phr00t/Qwen-Image-Edit-Rapid-AIO (fp8 all-in-one)
        nsfw=True,
        defaults={"steps": 4, "cfg": 1.0, "sampler": "euler", "scheduler": "simple"},
        template="edit_qwen_aio",
    ),
    "kontext": ModelDef(
        id="kontext", family="kontext", label="FLUX.1 Kontext (local · reference edit, multi-ref)",
        vram_gb=12.0, supports=(Mode.edit, Mode.reference),
        files={"unet": "flux1-kontext-dev-Q4_K_M.gguf", "clip": "t5-v1_1-xxl-encoder-Q5_K_M.gguf",
               "clip2": _CLIP_L, "vae": _FLUX_VAE},  # GGUF kept (needs NSFW Kontext LoRA)
        defaults={"steps": 20, "cfg": 2.5, "sampler": "euler", "scheduler": "simple"},
        template="edit_kontext",
    ),
    # ── Local style reference (Redux rides the Chroma fp8 base — shared weights) ──
    "redux": ModelDef(
        id="redux", family="chroma", label="FLUX Redux (local · style reference, multi-ref)",
        vram_gb=15.0, supports=(Mode.reference,),
        files={"unet": _CHROMA_UNET, "clip": _T5, "vae": _FLUX_VAE,
               "style_model": "flux1-redux-dev.safetensors",
               "clip_vision": "sigclip_vision_patch14_384.safetensors"},
        defaults={"steps": 24, "cfg": 3.5, "sampler": "euler", "scheduler": "simple"},
        template="redux_flux",
    ),
    # ── Local identity / face (consent-gated: consenting adults / synthetic faces only) ──
    "instantid": ModelDef(
        id="instantid", family="identity", label="InstantID (local · face identity over SDXL) · consent-gated",
        vram_gb=12.0, supports=(Mode.reference,),
        files={"checkpoint": _LUSTIFY,
               "instantid": "ip-adapter.bin",                 # VERIFY: InstantX/InstantID
               "controlnet": "instantid-diffusion_pytorch_model.safetensors"},
        uses_negative=True, nsfw=True,
        defaults={"steps": 28, "cfg": 5.0, "sampler": "dpmpp_2m_sde", "scheduler": "karras"},
        template="identity_instantid",
    ),
    "ip-adapter": ModelDef(
        id="ip-adapter", family="identity", label="IP-Adapter FaceID (local · identity/style over SDXL) · consent-gated",
        vram_gb=9.0, supports=(Mode.reference,),
        files={"checkpoint": _LUSTIFY,
               "ipadapter": "ip-adapter-faceid-plusv2_sdxl.bin",  # VERIFY: h94/IP-Adapter-FaceID
               "clip_vision": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"},
        uses_negative=True, nsfw=True,
        defaults={"steps": 28, "cfg": 6.0, "sampler": "dpmpp_2m_sde", "scheduler": "karras"},
        template="identity_ipadapter",
    ),
    "pulid-flux": ModelDef(
        id="pulid-flux", family="identity", label="PuLID-FLUX (local · face identity over Chroma/FLUX) · consent-gated",
        vram_gb=20.0, supports=(Mode.reference,),
        files={"unet": _CHROMA_UNET, "clip": _T5, "vae": _FLUX_VAE,
               "pulid": "pulid_flux_v0.9.1.safetensors"},        # VERIFY: guozinan/PuLID
        nsfw=True,
        defaults={"steps": 20, "cfg": 3.5, "sampler": "euler", "scheduler": "simple"},
        template="identity_pulid",
    ),
    # ── Local NSFW video (Wan 2.2) — swap-in (does NOT co-reside with the full image stack) ──
    "wan22-ti2v": ModelDef(
        id="wan22-ti2v", family="video", label="Wan 2.2 TI2V-5B (local · text+image→video, light)",
        vram_gb=16.0, supports=(Mode.video,), kind="video",
        files={"unet": "wan2.2_ti2v_5B_fp16.safetensors", "clip": "umt5_xxl_fp8_e4m3fn.safetensors",
               "vae": "wan2.2_vae.safetensors"},  # VERIFY: Wan-AI/Wan2.2-TI2V-5B (Comfy-Org repackaged)
        nsfw=True,
        defaults={"steps": 20, "cfg": 5.0, "sampler": "euler", "scheduler": "simple"},
        template="video_wan",
    ),
    "wan22-t2v": ModelDef(
        id="wan22-t2v", family="video", label="Wan 2.2 T2V-A14B (local · text→video, MoE quality)",
        vram_gb=34.0, supports=(Mode.video,), kind="video",
        files={"unet": "wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors",
               "unet2": "wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors",
               "clip": "umt5_xxl_fp8_e4m3fn.safetensors", "vae": "wan_2.1_vae.safetensors"},  # A14B reuses the Wan2.1 VAE (only the 5B uses wan2.2_vae)
        nsfw=True,
        # lightx2v 4-step distill is built in (both experts) → run at cfg 1.0, 4 total steps (high+low split).
        defaults={"steps": 4, "cfg": 1.0, "sampler": "euler", "scheduler": "simple"},
        template="video_wan",
        builtin_loras=(("wan2.2_t2v_lightx2v_4step.safetensors", 1.0),),          # → high-noise expert
        builtin_loras_low=(("wan2.2_t2v_lightx2v_4step_low.safetensors", 1.0),),  # → low-noise expert
    ),
    "wan22-i2v": ModelDef(
        id="wan22-i2v", family="video", label="Wan 2.2 I2V-A14B (local · image→video, MoE quality)",
        vram_gb=34.0, supports=(Mode.video,), kind="video",
        files={"unet": "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
               "unet2": "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
               "clip": "umt5_xxl_fp8_e4m3fn.safetensors", "vae": "wan_2.1_vae.safetensors"},  # A14B reuses the Wan2.1 VAE (only the 5B uses wan2.2_vae)
        nsfw=True,
        # lightx2v 4-step distill is built in (both experts) → run at cfg 1.0, 4 total steps (high+low split).
        defaults={"steps": 4, "cfg": 1.0, "sampler": "euler", "scheduler": "simple"},
        template="video_wan",
        builtin_loras=(("wan2.2_i2v_lightx2v_4step.safetensors", 1.0),),          # → high-noise expert
        builtin_loras_low=(("wan2.2_i2v_lightx2v_4step_low.safetensors", 1.0),),  # → low-noise expert
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
}

# ── Chat / planner LLM models ───────────────────────────────────────────────
# Vision-capable only: every chat/planner LLM here is multimodal (`vision=True`), so prompt-enhance
# can always ground the rewrite in an uploaded edit/reference image. The Ollama client converts
# OpenAI-style multimodal messages into Ollama's native per-message `images` array; cloud forwards
# as-is. (Text-only LLMs were deliberately dropped — do not re-add; the role stays a multimodal LLM.)
LLM_MODELS: dict[str, ModelDef] = {
    # Local multimodal LLM — uncensored "thinking" model so local prompt-enhance / mask judgement
    # can read images too.
    "qwen3-vl-local": ModelDef(
        id="qwen3-vl-local", family="ollama",
        label="Huihui Qwen3-VL 8B abliterated (local · Ollama, multimodal)",
        vram_gb=5.0, supports=(), engine=ENGINE_LOCAL_OLLAMA, kind="llm", provider="ollama",
        cloud_model_id="huihui_ai/qwen3-vl-abliterated:8b", vision=True,  # VERIFY Ollama tag
    ),
    # Cloud multimodal LLMs (OpenRouter) — any one serves chat + planner + vision-enhance.
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


# Default IMAGE/VIDEO model chosen per mode when GenSpec.model is null (local-first; photoreal).
DEFAULT_BY_MODE: dict[Mode, str] = {
    Mode.txt2img: "chroma-hd",
    Mode.img2img: "chroma-hd",
    Mode.inpaint: "flux-fill",
    Mode.edit: "qwen-edit-aio",
    Mode.controlnet: "lustify",
    Mode.reference: "redux",
    Mode.video: "wan22-ti2v",
}

# H100 80GB: the photoreal stack co-resides (~70GB), so no memory-pressure downshift is needed.
# Kept (empty) for the orchestrator import + future low-budget machines.
LIGHTER_EQUIVALENT: dict[str, str] = {}

# SDXL ControlNet — a single xinsir ControlNet-Union ProMax file covers every control type
# (incl. pose). Pose preprocessing is DWPose (see builder.build_controlnet_sdxl).
_CONTROLNET_UNION = "controlnet-union-sdxl-promax.safetensors"  # VERIFY: xinsir/controlnet-union-sdxl-1.0 (ProMax)
CONTROLNET_FILES: dict[str, str] = {
    "canny": _CONTROLNET_UNION,
    "depth": _CONTROLNET_UNION,
    "scribble": _CONTROLNET_UNION,
    "lineart": _CONTROLNET_UNION,
    "pose": _CONTROLNET_UNION,
}

UPSCALE_MODEL = "RealESRGAN_x4plus.pth"


def resolve(model_id: Optional[str], mode: Mode) -> ModelDef:
    """Resolve an image/video-generation model id (falling back to the per-mode default)."""
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
