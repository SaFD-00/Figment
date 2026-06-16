"""GenSpec -> ComfyUI API graph.

Graphs are constructed programmatically (not JSON+placeholder) so LoRA chains, reference
images, and mode branching stay type-safe and easy to correct against a live /object_info.

Node `class_type`s used:
  Core:    CheckpointLoaderSimple, CLIPTextEncode, EmptyLatentImage, EmptySD3LatentImage,
           KSampler, VAEDecode, VAEEncode, VAEEncodeForInpaint, ImageToMask, LoadImage,
           SaveImage, LoraLoader, VAELoader, ControlNetLoader, ControlNetApplyAdvanced,
           ImageUpscaleWithModel, UpscaleModelLoader
  GGUF (ComfyUI-GGUF):  UnetLoaderGGUF, CLIPLoaderGGUF, TextEncodeQwenImageEdit

GGUF/Metal note: only GGUF/bf16/fp16 weights are referenced — never fp8 (corrupts on MPS).
Node names for the Qwen GGUF paths are best-effort and validated at startup against
/object_info (see templates.validate_required_nodes); correct here if a name drifts.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from app.models_catalog.registry import (
    CONTROLNET_FILES,
    PONY_SCORE_PREFIX,
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


# ── SDXL family (verified, rock-solid path) ─────────────────────────────────────
def _sdxl_base(g: _G, m: ModelDef, spec: GenSpec):
    ck = g.add("CheckpointLoaderSimple", {"ckpt_name": m.files["checkpoint"]})
    model_link, clip_link, vae_link = [ck, 0], [ck, 1], [ck, 2]
    model_link, clip_link = _apply_loras(g, model_link, clip_link, m, spec)
    pos_text = (PONY_SCORE_PREFIX + spec.prompt) if m.id == "pony-v6" else spec.prompt
    pos = g.add("CLIPTextEncode", {"text": pos_text, "clip": clip_link})
    neg = g.add("CLIPTextEncode", {"text": spec.negative_prompt, "clip": clip_link})
    return model_link, vae_link, [pos, 0], [neg, 0]


# ── Qwen-Image family (GGUF + Qwen text/vision encoder) ─────────────────────────
def _qwen_base(g: _G, m: ModelDef, spec: GenSpec):
    """Qwen-Image loaders (UNET GGUF + Qwen2.5-VL CLIP + Qwen VAE), LoRA-chained.

    Returns (model, clip, vae, pos, neg) so txt2img/img2img can share it.
    """
    unet = g.add("UnetLoaderGGUF", {"unet_name": m.files["unet"]})
    model_link = [unet, 0]
    clip = g.add("CLIPLoaderGGUF", {
        "clip_name": m.files.get("clip", "qwen_2.5_vl_7b.safetensors"), "type": "qwen_image",
    })
    clip_link = [clip, 0]
    vae = g.add("VAELoader", {"vae_name": m.files.get("vae", "qwen_image_vae.safetensors")})
    vae_link = [vae, 0]
    model_link, clip_link = _apply_loras(g, model_link, clip_link, m, spec)
    pos = g.add("CLIPTextEncode", {"text": spec.prompt, "clip": clip_link})
    neg = g.add("CLIPTextEncode", {"text": "", "clip": clip_link})
    return model_link, clip_link, vae_link, [pos, 0], [neg, 0]


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


def build_txt2img_qwen(spec: GenSpec, ctx: BuildContext) -> BuildResult:
    # Qwen-Image 2512 base (+ optional Lightning LoRA via builtin_loras). Latent space is SD3-style.
    g = _G()
    m, d = ctx.model, _defaults(spec, ctx.model)
    model_link, _clip, vae_link, pos, neg = _qwen_base(g, m, spec)
    latent = g.add("EmptySD3LatentImage", {"width": ctx.width, "height": ctx.height, "batch_size": spec.batch})
    ks = _ksampler(g, model=model_link, positive=pos, negative=neg, latent=[latent, 0], spec=spec, d=d)
    dec = g.add("VAEDecode", {"samples": [ks, 0], "vae": vae_link})
    save = g.add("SaveImage", {"filename_prefix": "imggen", "images": [dec, 0]})
    return BuildResult(g.nodes, save, "imggen")


def build_img2img(spec: GenSpec, ctx: BuildContext) -> BuildResult:
    g = _G()
    m, d = ctx.model, _defaults(spec, ctx.model)
    load = g.add("LoadImage", {"image": ctx.comfy_source})
    if m.family == "qwen-image":
        model_link, _clip, vae_link, pos, neg = _qwen_base(g, m, spec)
    else:
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
    ks = _ksampler(g, model=model_link, positive=pos, negative=neg, latent=[enc, 0], spec=spec, d=d,
                   denoise=max(spec.denoise, 0.85))
    dec = g.add("VAEDecode", {"samples": [ks, 0], "vae": vae_link})
    save = g.add("SaveImage", {"filename_prefix": "imggen", "images": [dec, 0]})
    return BuildResult(g.nodes, save, "imggen")


def build_edit_qwen(spec: GenSpec, ctx: BuildContext) -> BuildResult:
    # Qwen-Image-Edit 2511 (+ Lightning LoRA via builtin_loras). Uses a Qwen text/vision encoder.
    g = _G()
    m, d = ctx.model, _defaults(spec, ctx.model)
    unet = g.add("UnetLoaderGGUF", {"unet_name": m.files["unet"]})
    model_link = [unet, 0]
    # Qwen edit uses its own CLIP loader; fall back generic name validated at startup.
    clip = g.add("CLIPLoaderGGUF", {"clip_name": m.files.get("clip", "qwen_2.5_vl_7b.safetensors"), "type": "qwen_image"})
    clip_link = [clip, 0]
    vae = g.add("VAELoader", {"vae_name": m.files.get("vae", "qwen_image_vae.safetensors")})
    vae_link = [vae, 0]
    model_link, clip_link = _apply_loras(g, model_link, clip_link, m, spec)
    # Single-input model: uses source, else the first reference; extra refs are ignored (see docs/WORKFLOWS.md).
    src = g.add("LoadImage", {"image": ctx.comfy_source or (ctx.comfy_refs[0] if ctx.comfy_refs else "")})
    # Text-instruction edit conditioning (TextEncodeQwenImageEdit name validated at startup).
    pos = g.add("TextEncodeQwenImageEdit", {"clip": clip_link, "prompt": spec.prompt, "image": [src, 0], "vae": vae_link})
    neg = g.add("TextEncodeQwenImageEdit", {"clip": clip_link, "prompt": "", "image": [src, 0], "vae": vae_link})
    enc = g.add("VAEEncode", {"pixels": [src, 0], "vae": vae_link})
    ks = _ksampler(g, model=model_link, positive=[pos, 0], negative=[neg, 0], latent=[enc, 0],
                   spec=spec, d=d, denoise=1.0)
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
    "txt2img_qwen": build_txt2img_qwen,
    "txt2img_sdxl_lora": build_txt2img_sdxl,
    "inpaint_sdxl": build_inpaint_sdxl,
    "edit_qwen_lightning": build_edit_qwen,
}


def build(spec: GenSpec, ctx: BuildContext) -> BuildResult:
    """Dispatch to the right builder by mode + model template."""
    if spec.mode == Mode.controlnet:
        return build_controlnet_sdxl(spec, ctx)
    if spec.mode == Mode.img2img:
        return build_img2img(spec, ctx)
    if spec.mode == Mode.reference:
        # Reference is handled by Qwen-Image-Edit (uses the first reference image).
        return build_edit_qwen(spec, ctx)
    template = ctx.model.template or "txt2img_sdxl_lora"
    fn = _TEMPLATE_DISPATCH.get(template, build_txt2img_sdxl)
    return fn(spec, ctx)
