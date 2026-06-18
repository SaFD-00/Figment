"""GenSpec -> ComfyUI API graph.

Graphs are constructed programmatically (not JSON+placeholder) so LoRA chains, reference
images, and mode branching stay type-safe and easy to correct against a live /object_info.

The local lineup is a single SDXL checkpoint (juggernaut-xl). Every mode builds on the verified
SDXL path:
  txt2img/img2img → checkpoint + KSampler
  inpaint         → VAEEncodeForInpaint + SetLatentNoiseMask (standard 4-ch checkpoint)
  edit            → mask present → inpaint; else high-denoise img2img
  reference       → IP-Adapter Plus (single image) patches the model
  controlnet      → ControlNet adapter on the same checkpoint

Node `class_type`s used:
  Core:    CheckpointLoaderSimple, CLIPTextEncode, EmptyLatentImage, KSampler, VAEDecode,
           VAEEncode, VAEEncodeForInpaint, SetLatentNoiseMask, ImageToMask, LoadImage,
           SaveImage, LoraLoader, ControlNetLoader, ControlNetApplyAdvanced,
           ImageUpscaleWithModel, UpscaleModelLoader
  IP-Adapter (ComfyUI_IPAdapter_plus):  IPAdapterModelLoader, CLIPVisionLoader, IPAdapterAdvanced

GGUF/Metal note: only safetensors/bf16/fp16 weights are referenced — never fp8 (corrupts on MPS).
IP-Adapter node names/enums are best-effort and validated at startup against /object_info
(see templates.validate_required_nodes); correct here if a name drifts.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from app.models_catalog.registry import (
    CONTROLNET_FILES,
    IPADAPTER_FILES,
    UPSCALE_MODEL,
    ModelDef,
)
from app.schemas.genspec import GenSpec, Mode


@dataclass
class BuildContext:
    model: ModelDef
    width: int
    height: int
    comfy_source: Optional[str] = None     # server-side ref for source image
    comfy_mask: Optional[str] = None       # server-side ref for mask
    comfy_refs: list[str] = field(default_factory=list)  # reference image refs


@dataclass
class BuildResult:
    graph: dict
    save_node: str
    filename_prefix: str


class _G:
    """Tiny graph builder. add() returns a node id; link with [id, out_index]."""
    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self._n = 0

    def add(self, class_type: str, inputs: dict, title: str | None = None) -> str:
        self._n += 1
        nid = str(self._n)
        node = {"class_type": class_type, "inputs": inputs}
        if title:
            node["_meta"] = {"title": title}
        self.nodes[nid] = node
        return nid


def _seed(spec: GenSpec) -> int:
    return spec.seed if spec.seed is not None else random.randint(0, 2**31 - 1)


def _defaults(spec: GenSpec, m: ModelDef) -> dict:
    d = dict(m.defaults)
    if spec.steps is not None:
        d["steps"] = spec.steps
    if spec.cfg is not None:
        d["cfg"] = spec.cfg
    if spec.sampler:
        d["sampler"] = spec.sampler
    if spec.scheduler:
        d["scheduler"] = spec.scheduler
    return d


def _apply_loras(g: _G, model_link, clip_link, m: ModelDef, spec: GenSpec):
    """Chain builtin + user LoRAs; returns (model_link, clip_link)."""
    loras = [(name, w) for name, w in m.builtin_loras] + [(l.name, l.weight) for l in spec.loras]
    for name, weight in loras:
        nid = g.add("LoraLoader", {
            "lora_name": name, "strength_model": weight, "strength_clip": weight,
            "model": model_link, "clip": clip_link,
        })
        model_link, clip_link = [nid, 0], [nid, 1]
    return model_link, clip_link


def _ksampler(g: _G, *, model, positive, negative, latent, spec: GenSpec, d: dict, denoise: float = 1.0) -> str:
    return g.add("KSampler", {
        "seed": _seed(spec), "steps": int(d["steps"]), "cfg": float(d["cfg"]),
        "sampler_name": d["sampler"], "scheduler": d["scheduler"], "denoise": denoise,
        "model": model, "positive": positive, "negative": negative, "latent_image": latent,
    })


# ── SDXL base (the single local checkpoint path) ────────────────────────────────
def _sdxl_base(g: _G, m: ModelDef, spec: GenSpec):
    ck = g.add("CheckpointLoaderSimple", {"ckpt_name": m.files["checkpoint"]})
    model_link, clip_link, vae_link = [ck, 0], [ck, 1], [ck, 2]
    model_link, clip_link = _apply_loras(g, model_link, clip_link, m, spec)
    pos = g.add("CLIPTextEncode", {"text": spec.prompt, "clip": clip_link})
    neg = g.add("CLIPTextEncode", {"text": spec.negative_prompt, "clip": clip_link})
    return model_link, vae_link, [pos, 0], [neg, 0]


# ── builders per mode ───────────────────────────────────────────────────────────
def build_txt2img_sdxl(spec: GenSpec, ctx: BuildContext) -> BuildResult:
    g = _G()
    m, d = ctx.model, _defaults(spec, ctx.model)
    model_link, vae_link, pos, neg = _sdxl_base(g, m, spec)
    latent = g.add("EmptyLatentImage", {"width": ctx.width, "height": ctx.height, "batch_size": spec.batch})
    ks = _ksampler(g, model=model_link, positive=pos, negative=neg, latent=[latent, 0], spec=spec, d=d)
    dec = g.add("VAEDecode", {"samples": [ks, 0], "vae": vae_link})
    save = g.add("SaveImage", {"filename_prefix": "imggen", "images": [dec, 0]})
    return BuildResult(g.nodes, save, "imggen")


def build_img2img(spec: GenSpec, ctx: BuildContext) -> BuildResult:
    g = _G()
    m, d = ctx.model, _defaults(spec, ctx.model)
    load = g.add("LoadImage", {"image": ctx.comfy_source})
    model_link, vae_link, pos, neg = _sdxl_base(g, m, spec)
    enc = g.add("VAEEncode", {"pixels": [load, 0], "vae": vae_link})
    ks = _ksampler(g, model=model_link, positive=pos, negative=neg, latent=[enc, 0], spec=spec, d=d,
                   denoise=spec.denoise)
    dec = g.add("VAEDecode", {"samples": [ks, 0], "vae": vae_link})
    save = g.add("SaveImage", {"filename_prefix": "imggen", "images": [dec, 0]})
    return BuildResult(g.nodes, save, "imggen")


def build_inpaint_sdxl(spec: GenSpec, ctx: BuildContext) -> BuildResult:
    g = _G()
    m, d = ctx.model, _defaults(spec, ctx.model)
    model_link, vae_link, pos, neg = _sdxl_base(g, m, spec)
    img = g.add("LoadImage", {"image": ctx.comfy_source})
    mask = g.add("LoadImage", {"image": ctx.comfy_mask})  # mask in alpha/red channel
    to_mask = g.add("ImageToMask", {"image": [mask, 0], "channel": "red"})
    enc = g.add("VAEEncodeForInpaint", {"pixels": [img, 0], "vae": vae_link, "mask": [to_mask, 0], "grow_mask_by": 6})
    # Juggernaut XL is a standard 4-ch SDXL checkpoint (not a 9-ch inpaint UNet), so re-assert the
    # mask on the latent — KSampler then only denoises the masked region.
    masked = g.add("SetLatentNoiseMask", {"samples": [enc, 0], "mask": [to_mask, 0]})
    ks = _ksampler(g, model=model_link, positive=pos, negative=neg, latent=[masked, 0], spec=spec, d=d,
                   denoise=max(spec.denoise, 0.9))
    dec = g.add("VAEDecode", {"samples": [ks, 0], "vae": vae_link})
    save = g.add("SaveImage", {"filename_prefix": "imggen", "images": [dec, 0]})
    return BuildResult(g.nodes, save, "imggen")


def build_edit_juggernaut(spec: GenSpec, ctx: BuildContext) -> BuildResult:
    """Edit mode on a standard SDXL checkpoint: if the planner supplied a mask, treat the edit
    instruction as an inpaint prompt over the masked region; otherwise run high-denoise img2img on
    the source image. The LLM/GENSPEC planner decides whether a mask is present — we do NOT generate
    masks here."""
    if ctx.comfy_mask:
        return build_inpaint_sdxl(spec, ctx)
    # No mask → whole-image instruction edit via high-denoise img2img. Floor the denoise so a low
    # img2img default still yields a visible edit.
    edited = spec.model_copy(update={"denoise": max(spec.denoise, 0.75)})
    return build_img2img(edited, ctx)


def build_reference_ipadapter(spec: GenSpec, ctx: BuildContext) -> BuildResult:
    """Reference-to-image via IP-Adapter Plus (single reference) on the SDXL checkpoint.

    IPAdapterModelLoader + CLIPVisionLoader feed IPAdapterAdvanced, which patches the MODEL with the
    reference's style/subject; the patched model then drives a normal txt2img KSampler.
    """
    g = _G()
    m, d = ctx.model, _defaults(spec, ctx.model)
    model_link, vae_link, pos, neg = _sdxl_base(g, m, spec)
    # Single reference image; fall back to the source if no explicit reference was uploaded.
    ref_name = ctx.comfy_refs[0] if ctx.comfy_refs else ctx.comfy_source
    ref = g.add("LoadImage", {"image": ref_name})
    ipa = g.add("IPAdapterModelLoader", {"ipadapter_file": IPADAPTER_FILES["ipadapter"]})
    vis = g.add("CLIPVisionLoader", {"clip_name": IPADAPTER_FILES["clip_vision"]})
    # Strength from the first reference (clamped to the guide's 0.6–0.8 window), default 0.7.
    strength = spec.reference_images[0].strength if spec.reference_images else 0.7
    strength = min(max(strength, 0.6), 0.8)
    apply = g.add("IPAdapterAdvanced", {
        "model": model_link, "ipadapter": [ipa, 0], "clip_vision": [vis, 0],
        "image": [ref, 0], "weight": strength, "weight_type": "linear",
        "combine_embeds": "concat", "start_at": 0.0, "end_at": 1.0, "embeds_scaling": "V only",
    })
    model_link = [apply, 0]   # IPAdapterAdvanced returns the patched MODEL
    latent = g.add("EmptyLatentImage", {"width": ctx.width, "height": ctx.height, "batch_size": spec.batch})
    ks = _ksampler(g, model=model_link, positive=pos, negative=neg, latent=[latent, 0], spec=spec, d=d)
    dec = g.add("VAEDecode", {"samples": [ks, 0], "vae": vae_link})
    save = g.add("SaveImage", {"filename_prefix": "imggen", "images": [dec, 0]})
    return BuildResult(g.nodes, save, "imggen")


def build_controlnet_sdxl(spec: GenSpec, ctx: BuildContext) -> BuildResult:
    g = _G()
    m, d = ctx.model, _defaults(spec, ctx.model)
    model_link, vae_link, pos, neg = _sdxl_base(g, m, spec)
    # Single-input ControlNet: uses the first reference (extra refs ignored; see docs/WORKFLOWS.md).
    ref = g.add("LoadImage", {"image": ctx.comfy_refs[0] if ctx.comfy_refs else ctx.comfy_source})
    ctype = spec.controlnet_type or "canny"
    pre_node = {
        "canny": ("CannyEdgePreprocessor", {"image": [ref, 0]}),
        "depth": ("DepthAnythingV2Preprocessor", {"image": [ref, 0]}),
        "scribble": ("ScribblePreprocessor", {"image": [ref, 0]}),
        "lineart": ("LineArtPreprocessor", {"image": [ref, 0]}),
    }[ctype]
    pre = g.add(pre_node[0], pre_node[1])
    cn = g.add("ControlNetLoader", {"control_net_name": CONTROLNET_FILES[ctype]})
    apply = g.add("ControlNetApplyAdvanced", {
        "positive": pos, "negative": neg, "control_net": [cn, 0], "image": [pre, 0],
        "strength": spec.controlnet_strength, "start_percent": 0.0, "end_percent": 1.0, "vae": vae_link,
    })
    latent = g.add("EmptyLatentImage", {"width": ctx.width, "height": ctx.height, "batch_size": spec.batch})
    ks = _ksampler(g, model=model_link, positive=[apply, 0], negative=[apply, 1], latent=[latent, 0], spec=spec, d=d)
    dec = g.add("VAEDecode", {"samples": [ks, 0], "vae": vae_link})
    save = g.add("SaveImage", {"filename_prefix": "imggen", "images": [dec, 0]})
    return BuildResult(g.nodes, save, "imggen")


def build_upscale(comfy_source: str) -> BuildResult:
    """Real-ESRGAN upscale of an already-uploaded image. Standalone (no model family)."""
    g = _G()
    load = g.add("LoadImage", {"image": comfy_source})
    um = g.add("UpscaleModelLoader", {"model_name": UPSCALE_MODEL})
    up = g.add("ImageUpscaleWithModel", {"upscale_model": [um, 0], "image": [load, 0]})
    save = g.add("SaveImage", {"filename_prefix": "imggen", "images": [up, 0]})
    return BuildResult(g.nodes, save, "imggen")


_TEMPLATE_DISPATCH = {
    "txt2img_sdxl_lora": build_txt2img_sdxl,
    "inpaint_sdxl": build_inpaint_sdxl,
}


def build(spec: GenSpec, ctx: BuildContext) -> BuildResult:
    """Dispatch to the right builder by mode (all local modes are SDXL now)."""
    if spec.mode == Mode.controlnet:
        return build_controlnet_sdxl(spec, ctx)
    if spec.mode == Mode.reference:
        return build_reference_ipadapter(spec, ctx)   # IP-Adapter Plus, single reference
    if spec.mode == Mode.edit:
        return build_edit_juggernaut(spec, ctx)        # mask→inpaint, else high-denoise img2img
    if spec.mode == Mode.inpaint:
        return build_inpaint_sdxl(spec, ctx)
    if spec.mode == Mode.img2img:
        return build_img2img(spec, ctx)
    # txt2img
    template = ctx.model.template or "txt2img_sdxl_lora"
    fn = _TEMPLATE_DISPATCH.get(template, build_txt2img_sdxl)
    return fn(spec, ctx)
