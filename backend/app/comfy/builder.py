"""GenSpec -> ComfyUI API graph.

Graphs are constructed programmatically (not JSON+placeholder) so LoRA chains, reference
images, and mode branching stay type-safe and easy to correct against a live /object_info.

Node `class_type`s used:
  Core:    CheckpointLoaderSimple, CLIPTextEncode, EmptyLatentImage, EmptySD3LatentImage,
           KSampler, KSamplerAdvanced, VAEDecode, VAEEncode, VAEEncodeForInpaint, LoadImage, SaveImage,
           LoraLoader, LoraLoaderModelOnly, ControlNetLoader, ControlNetApplyAdvanced, ImageUpscaleWithModel,
           UpscaleModelLoader, StyleModelLoader, CLIPVisionLoader, CLIPVisionEncode,
           StyleModelApply, FluxGuidance, InpaintModelConditioning, ReferenceLatent,
           UNETLoader, CLIPLoader, DualCLIPLoader, VAELoader, TextEncodeQwenImageEdit
  GGUF (ComfyUI-GGUF):  UnetLoaderGGUF, DualCLIPLoaderGGUF, CLIPLoaderGGUF
  Pose (controlnet_aux): DWPreprocessor
  Upscale (USDU):       UltimateSDUpscale
  Video (Wan 2.2):      Wan22ImageToVideoLatent, SaveAnimatedWEBP

TARGET = single NVIDIA H100 80GB (CUDA): native fp8/bf16 safetensors are first-class. The loader
node is chosen by file extension — `.gguf` → ComfyUI-GGUF loaders (flux-fill), otherwise native
UNETLoader/CLIPLoader (chroma/redux). Custom-node class_types for pose/video/upscale are
best-effort and validated at startup against /object_info (see templates.validate_required_nodes);
correct here if a name drifts.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from app.models_catalog.registry import (
    CONTROLNET_FILES,
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
    is_video: bool = False                 # save_node yields a video (webp) instead of a PNG


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
    loras = [(name, w) for name, w in m.builtin_loras] + [(lo.name, lo.weight) for lo in spec.loras]
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
    pos = g.add("CLIPTextEncode", {"text": spec.prompt, "clip": clip_link})
    neg = g.add("CLIPTextEncode", {"text": spec.negative_prompt, "clip": clip_link})
    return model_link, vae_link, [pos, 0], [neg, 0]


# ── FLUX/Chroma family (native fp8 safetensors OR GGUF, by file extension) ───────
def _flux_base(g: _G, m: ModelDef, spec: GenSpec, *, flux_guidance: float | None = None):
    """Chroma/FLUX loaders. `.gguf` files → ComfyUI-GGUF loaders; otherwise native CUDA loaders."""
    is_gguf = m.files["unet"].endswith(".gguf")
    if is_gguf:
        unet = g.add("UnetLoaderGGUF", {"unet_name": m.files["unet"]})
    else:
        unet = g.add("UNETLoader", {"unet_name": m.files["unet"], "weight_dtype": "fp8_e4m3fn"})
    model_link = [unet, 0]
    # Chroma-family bases (chroma-hd, redux) ride a SINGLE T5 encoder (type="chroma");
    # only true dual-CLIP FLUX weights (flux-fill) carry a second CLIP ("clip2").
    single_t5 = "clip2" not in m.files
    if single_t5:
        if is_gguf:
            clip = g.add("CLIPLoaderGGUF", {"clip_name": m.files["clip"], "type": "chroma"})
        else:
            clip = g.add("CLIPLoader", {"clip_name": m.files["clip"], "type": "chroma"})
    else:
        if is_gguf:
            clip = g.add("DualCLIPLoaderGGUF", {
                "clip_name1": m.files["clip"], "clip_name2": m.files["clip2"], "type": "flux",
            })
        else:
            clip = g.add("DualCLIPLoader", {
                "clip_name1": m.files["clip"], "clip_name2": m.files["clip2"], "type": "flux",
            })
    clip_link = [clip, 0]
    vae = g.add("VAELoader", {"vae_name": m.files["vae"]})
    vae_link = [vae, 0]
    model_link, clip_link = _apply_loras(g, model_link, clip_link, m, spec)
    pos = g.add("CLIPTextEncode", {"text": spec.prompt, "clip": clip_link})
    if flux_guidance is not None:
        pos = g.add("FluxGuidance", {"guidance": flux_guidance, "conditioning": [pos, 0]})
        pos_link = [pos, 0]
    else:
        pos_link = [pos, 0]
    neg = g.add("CLIPTextEncode", {"text": "", "clip": clip_link})
    return model_link, clip_link, vae_link, pos_link, [neg, 0]


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


def build_txt2img_flux(spec: GenSpec, ctx: BuildContext) -> BuildResult:
    g = _G()
    m, d = ctx.model, _defaults(spec, ctx.model)
    model_link, _clip, vae_link, pos, neg = _flux_base(g, m, spec, flux_guidance=float(d["cfg"]))
    latent = g.add("EmptySD3LatentImage", {"width": ctx.width, "height": ctx.height, "batch_size": spec.batch})
    # FLUX uses cfg=1 in the sampler; guidance is carried by FluxGuidance on the conditioning.
    ks = _ksampler(g, model=model_link, positive=pos, negative=neg, latent=[latent, 0], spec=spec,
                   d={**d, "cfg": 1.0})
    dec = g.add("VAEDecode", {"samples": [ks, 0], "vae": vae_link})
    save = g.add("SaveImage", {"filename_prefix": "imggen", "images": [dec, 0]})
    return BuildResult(g.nodes, save, "imggen")


def build_img2img(spec: GenSpec, ctx: BuildContext) -> BuildResult:
    g = _G()
    m, d = ctx.model, _defaults(spec, ctx.model)
    load = g.add("LoadImage", {"image": ctx.comfy_source})
    if m.family == "chroma":   # Chroma/FLUX base → flux path; SDXL (lustify) falls through below
        model_link, _clip, vae_link, pos, neg = _flux_base(g, m, spec, flux_guidance=float(d["cfg"]))
        d = {**d, "cfg": 1.0}
    else:
        model_link, vae_link, pos, neg = _sdxl_base(g, m, spec)
    enc = g.add("VAEEncode", {"pixels": [load, 0], "vae": vae_link})
    ks = _ksampler(g, model=model_link, positive=pos, negative=neg, latent=[enc, 0], spec=spec, d=d,
                   denoise=spec.denoise)
    dec = g.add("VAEDecode", {"samples": [ks, 0], "vae": vae_link})
    save = g.add("SaveImage", {"filename_prefix": "imggen", "images": [dec, 0]})
    return BuildResult(g.nodes, save, "imggen")


def build_inpaint_flux_fill(spec: GenSpec, ctx: BuildContext) -> BuildResult:
    g = _G()
    m, d = ctx.model, _defaults(spec, ctx.model)
    model_link, clip_link, vae_link, pos, neg = _flux_base(g, m, spec, flux_guidance=float(d["cfg"]))
    img = g.add("LoadImage", {"image": ctx.comfy_source})
    mask = g.add("LoadImage", {"image": ctx.comfy_mask})
    to_mask = g.add("ImageToMask", {"image": [mask, 0], "channel": "red"})
    cond = g.add("InpaintModelConditioning", {
        "positive": pos, "negative": neg, "vae": vae_link,
        "pixels": [img, 0], "mask": [to_mask, 0], "noise_mask": True,
    })
    ks = _ksampler(g, model=model_link, positive=[cond, 0], negative=[cond, 1], latent=[cond, 2],
                   spec=spec, d={**d, "cfg": 1.0}, denoise=1.0)
    dec = g.add("VAEDecode", {"samples": [ks, 0], "vae": vae_link})
    save = g.add("SaveImage", {"filename_prefix": "imggen", "images": [dec, 0]})
    return BuildResult(g.nodes, save, "imggen")


def build_edit_qwen_aio(spec: GenSpec, ctx: BuildContext) -> BuildResult:
    """Qwen-Image-Edit Rapid AIO: a single fused checkpoint (transformer + Qwen2.5-VL + VAE).

    Loaded via CheckpointLoaderSimple (not the separate-file Qwen loaders); the instruction +
    source image are encoded by TextEncodeQwenImageEdit (validated at startup).
    """
    g = _G()
    m, d = ctx.model, _defaults(spec, ctx.model)
    ck = g.add("CheckpointLoaderSimple", {"ckpt_name": m.files["checkpoint"]})
    model_link, clip_link, vae_link = [ck, 0], [ck, 1], [ck, 2]
    model_link, clip_link = _apply_loras(g, model_link, clip_link, m, spec)
    src = g.add("LoadImage", {"image": ctx.comfy_source or (ctx.comfy_refs[0] if ctx.comfy_refs else "")})
    pos = g.add("TextEncodeQwenImageEdit", {"clip": clip_link, "prompt": spec.prompt, "image": [src, 0], "vae": vae_link})
    neg = g.add("TextEncodeQwenImageEdit", {"clip": clip_link, "prompt": spec.negative_prompt, "image": [src, 0], "vae": vae_link})
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
    # xinsir ControlNet-Union ProMax is a single file for every type; pose uses the DWPose preprocessor.
    pre_node = {
        "canny": ("CannyEdgePreprocessor", {"image": [ref, 0]}),
        "depth": ("DepthAnythingV2Preprocessor", {"image": [ref, 0]}),
        "scribble": ("ScribblePreprocessor", {"image": [ref, 0]}),
        "lineart": ("LineArtPreprocessor", {"image": [ref, 0]}),
        "pose": ("DWPreprocessor", {"image": [ref, 0], "detect_body": "enable",
                                    "detect_hand": "enable", "detect_face": "enable"}),
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


def build_redux_flux(spec: GenSpec, ctx: BuildContext) -> BuildResult:
    g = _G()
    m, d = ctx.model, _defaults(spec, ctx.model)
    model_link, clip_link, vae_link, pos, neg = _flux_base(g, m, spec, flux_guidance=float(d["cfg"]))
    style = g.add("StyleModelLoader", {"style_model_name": m.files["style_model"]})
    cvis = g.add("CLIPVisionLoader", {"clip_name": m.files["clip_vision"]})
    refs = ctx.comfy_refs or ([ctx.comfy_source] if ctx.comfy_source else [])
    # Blend every style reference: chain one StyleModelApply per ref (single ref → identical to before).
    cond_link = pos
    for i, ref in enumerate(refs):
        load = g.add("LoadImage", {"image": ref})
        venc = g.add("CLIPVisionEncode", {"clip_vision": [cvis, 0], "image": [load, 0], "crop": "center"})
        strength = spec.reference_images[i].strength if i < len(spec.reference_images) else 0.8
        applied = g.add("StyleModelApply", {
            "conditioning": cond_link, "style_model": [style, 0], "clip_vision_output": [venc, 0],
            "strength": strength, "strength_type": "multiply",
        })
        cond_link = [applied, 0]
    latent = g.add("EmptySD3LatentImage", {"width": ctx.width, "height": ctx.height, "batch_size": 1})
    ks = _ksampler(g, model=model_link, positive=cond_link, negative=neg, latent=[latent, 0],
                   spec=spec, d={**d, "cfg": 1.0}, denoise=1.0)
    dec = g.add("VAEDecode", {"samples": [ks, 0], "vae": vae_link})
    save = g.add("SaveImage", {"filename_prefix": "imggen", "images": [dec, 0]})
    return BuildResult(g.nodes, save, "imggen")


# ── NSFW video (Wan 2.2). Best-effort graph; node names validated at startup. ────
def build_video_wan(spec: GenSpec, ctx: BuildContext) -> BuildResult:
    """Wan 2.2 TI2V-5B text/image→video — single dense expert on the new wan2.2 VAE.

    One UNET + one KSampler. The 5B-specific Wan22ImageToVideoLatent node takes an optional
    start_image, so the same graph covers both text→video and image→video."""
    g = _G()
    m, d = ctx.model, _defaults(spec, ctx.model)
    clip = g.add("CLIPLoader", {"clip_name": m.files["clip"], "type": "wan"})
    vae = g.add("VAELoader", {"vae_name": m.files["vae"]})
    clip_link, vae_link = [clip, 0], [vae, 0]

    unet_hi = g.add("UNETLoader", {"unet_name": m.files["unet"], "weight_dtype": "fp8_e4m3fn"})
    hi_link, clip_link = _apply_loras(g, [unet_hi, 0], clip_link, m, spec)

    pos = g.add("CLIPTextEncode", {"text": spec.prompt, "clip": clip_link})
    neg = g.add("CLIPTextEncode", {"text": spec.negative_prompt, "clip": clip_link})

    lat_inputs = {"vae": vae_link, "width": ctx.width, "height": ctx.height,
                  "length": spec.video_frames, "batch_size": 1}
    if ctx.comfy_source:
        lat_inputs["start_image"] = [g.add("LoadImage", {"image": ctx.comfy_source}), 0]
    latent_node = g.add("Wan22ImageToVideoLatent", lat_inputs)

    ks = _ksampler(g, model=hi_link, positive=[pos, 0], negative=[neg, 0],
                   latent=[latent_node, 0], spec=spec, d=d)

    dec = g.add("VAEDecode", {"samples": [ks, 0], "vae": vae_link})
    save = g.add("SaveAnimatedWEBP", {
        "filename_prefix": "imggen", "images": [dec, 0], "fps": spec.video_fps,
        "lossless": False, "quality": 90, "method": "default",
    })
    return BuildResult(g.nodes, save, "imggen", is_video=True)


def build_upscale(comfy_source: str) -> BuildResult:
    """Real-ESRGAN upscale of an already-uploaded image. Standalone (no model family)."""
    g = _G()
    load = g.add("LoadImage", {"image": comfy_source})
    um = g.add("UpscaleModelLoader", {"model_name": UPSCALE_MODEL})
    up = g.add("ImageUpscaleWithModel", {"upscale_model": [um, 0], "image": [load, 0]})
    save = g.add("SaveImage", {"filename_prefix": "imggen", "images": [up, 0]})
    return BuildResult(g.nodes, save, "imggen")


def build_ultimate_upscale(spec: GenSpec, ctx: BuildContext, comfy_source: str) -> BuildResult:
    """Tiled diffusion upscale (Ultimate SD Upscale) that reuses an SDXL NSFW base — so the detail
    pass inherits the base's explicit capability. Best-effort node names (validated at startup)."""
    g = _G()
    m, d = ctx.model, _defaults(spec, ctx.model)
    model_link, vae_link, pos, neg = _sdxl_base(g, m, spec)
    img = g.add("LoadImage", {"image": comfy_source})
    um = g.add("UpscaleModelLoader", {"model_name": UPSCALE_MODEL})
    usdu = g.add("UltimateSDUpscale", {
        "image": [img, 0], "model": model_link, "positive": pos, "negative": neg, "vae": vae_link,
        "upscale_model": [um, 0], "upscale_by": 2.0, "seed": _seed(spec), "steps": int(d["steps"]),
        "cfg": float(d["cfg"]), "sampler_name": d["sampler"], "scheduler": d["scheduler"],
        "denoise": 0.2, "mode_type": "Linear", "tile_width": 1024, "tile_height": 1024,
        "mask_blur": 8, "tile_padding": 32,
    })
    save = g.add("SaveImage", {"filename_prefix": "imggen", "images": [usdu, 0]})
    return BuildResult(g.nodes, save, "imggen")


_TEMPLATE_DISPATCH = {
    "txt2img_chroma": build_txt2img_flux,
    "txt2img_sdxl_lora": build_txt2img_sdxl,
    "inpaint_flux_fill": build_inpaint_flux_fill,
    "edit_qwen_aio": build_edit_qwen_aio,
    "redux_flux": build_redux_flux,
    "video_wan": build_video_wan,
}


def build(spec: GenSpec, ctx: BuildContext) -> BuildResult:
    """Dispatch to the right builder by mode + model template."""
    if spec.mode == Mode.controlnet:
        return build_controlnet_sdxl(spec, ctx)
    if spec.mode == Mode.img2img:
        return build_img2img(spec, ctx)
    template = ctx.model.template or "txt2img_sdxl_lora"
    fn = _TEMPLATE_DISPATCH.get(template, build_txt2img_sdxl)
    return fn(spec, ctx)
