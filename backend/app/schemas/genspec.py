"""GenSpec — the structured contract the chat LLM emits and the generator consumes."""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class Mode(str, Enum):
    txt2img = "txt2img"
    img2img = "img2img"
    inpaint = "inpaint"
    edit = "edit"          # instruction edit (mask→inpaint, else high-denoise img2img)
    controlnet = "controlnet"
    reference = "reference"  # style/look reference (Redux) + identity (InstantID/PuLID/IP-Adapter)
    video = "video"          # NSFW text/image→video (Wan 2.2)


RefRole = Literal["style", "structure", "edit", "identity"]
ControlType = Literal["canny", "depth", "scribble", "lineart", "pose"]

# Max reference images per request. Mirror in frontend/lib/constants.ts — keep in sync.
MAX_REFERENCE_IMAGES = 6

# Local reference cap: on H100 the multi-ref local builders (Redux style, Kontext edit) consume
# every reference, so local matches the global cap; single-ref builders (identity, ControlNet) use
# the first. Mirror in frontend/lib/constants.ts (LOCAL_MAX_REFERENCE_IMAGES).
LOCAL_MAX_REFS = MAX_REFERENCE_IMAGES

# Local (edit/reference) working-size cap, longest side in px. SDXL is 1024-native and the
# reference encoders resize internally, so source + reference uploads are downscaled to this before
# they reach ComfyUI (see orchestrator.queue._prepare_inputs) — a sane working-resolution default,
# not a memory necessity on the 80GB H100.
LOCAL_MAX_SIDE = 1024


class ReferenceImage(BaseModel):
    asset: str                       # asset id of an uploaded reference image
    role: RefRole = "edit"
    strength: float = Field(0.85, ge=0.0, le=1.0)


class LoRA(BaseModel):
    name: str                        # filename in models/loras
    weight: float = Field(0.8, ge=-2.0, le=2.0)


class GenSpec(BaseModel):
    """One generation/edit request. `model` may be null → backend picks by mode + free RAM."""
    version: int = 1
    mode: Mode = Mode.txt2img
    model: Optional[str] = None      # image registry id, e.g. "chroma-hd" / "gpt-image-2"
    llm_model: Optional[str] = None  # chat/planner LLM id, e.g. "qwen3-vl-local" / "gemini-2.5-flash"

    prompt: str = ""
    negative_prompt: str = ""        # used by the local SDXL checkpoint; ignored by cloud models

    width: int = 1024
    height: int = 1024
    steps: Optional[int] = None      # None → registry default per model
    cfg: Optional[float] = None
    sampler: Optional[str] = None
    scheduler: Optional[str] = None
    seed: Optional[int] = None       # None → random
    batch: int = Field(1, ge=1, le=4)

    # conditioning on existing imagery
    denoise: float = Field(0.6, ge=0.0, le=1.0)   # img2img / reference fidelity dial
    source_asset: Optional[str] = None            # base image (img2img/inpaint/edit)
    mask_asset: Optional[str] = None              # inpaint mask: white=regen, black=keep
    reference_images: list[ReferenceImage] = Field(default_factory=list)

    # structure control
    controlnet_type: Optional[ControlType] = None
    controlnet_strength: float = Field(0.7, ge=0.0, le=2.0)

    # LoRAs (NSFW finetunes etc.)
    loras: list[LoRA] = Field(default_factory=list)

    # video (Wan 2.2): clip length in frames + fps; ignored by image modes
    video_frames: int = Field(81, ge=9, le=241)
    video_fps: int = Field(16, ge=8, le=30)

    # chained post-steps
    upscale: bool = False
    remove_bg: bool = False

    @field_validator("width", "height")
    @classmethod
    def _bounds(cls, v: int) -> int:
        if not (256 <= v <= 2048):
            raise ValueError("width/height must be in [256, 2048]")
        return v

    @field_validator("reference_images")
    @classmethod
    def _max_refs(cls, v: list[ReferenceImage]) -> list[ReferenceImage]:
        if len(v) > MAX_REFERENCE_IMAGES:
            raise ValueError(f"at most {MAX_REFERENCE_IMAGES} reference images")
        return v

    @model_validator(mode="after")
    def _consistency(self) -> "GenSpec":
        if self.mask_asset and not self.source_asset:
            raise ValueError("mask_asset requires source_asset")
        if self.mode in (Mode.img2img, Mode.inpaint) and not self.source_asset:
            raise ValueError(f"mode={self.mode} requires source_asset")
        if self.mode == Mode.inpaint and not self.mask_asset:
            raise ValueError("mode=inpaint requires mask_asset")
        if self.mode == Mode.controlnet and not self.controlnet_type:
            self.controlnet_type = "canny"
        return self
