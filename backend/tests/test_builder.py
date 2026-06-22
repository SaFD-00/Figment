"""Graph builder produces well-formed ComfyUI graphs for each mode.

Shared helpers (build_ctx / assert_graph / assert_video_graph) live in conftest.py.
The exhaustive "every local model × supported mode" sweep lives in test_registry.py;
this file keeps the targeted, behaviour-specific assertions.
"""
from app.comfy import builder as B
from app.schemas.genspec import GenSpec, Mode


def _types(res: B.BuildResult) -> set[str]:
    return {n["class_type"] for n in res.graph.values()}


# ── txt2img / img2img ────────────────────────────────────────────────────────
def test_txt2img_sdxl(build_ctx, assert_graph):
    spec = GenSpec(mode=Mode.txt2img, model="lustify", prompt="a fox")
    assert_graph(B.build(spec, build_ctx("lustify")))


def test_txt2img_chroma_native(build_ctx, assert_graph):
    spec = GenSpec(mode=Mode.txt2img, model="chroma-hd", prompt="a fox")
    res = B.build(spec, build_ctx("chroma-hd"))
    assert_graph(res)
    # chroma-hd ships native fp8 safetensors → native UNETLoader, not the GGUF loader
    assert "UNETLoader" in _types(res)
    assert "UnetLoaderGGUF" not in _types(res)
    assert "FluxGuidance" in _types(res)


def test_img2img_chroma_native(build_ctx, assert_graph):
    spec = GenSpec(mode=Mode.img2img, model="chroma-hd", prompt="a fox",
                   source_asset="s", denoise=0.6)
    res = B.build(spec, build_ctx("chroma-hd", src="imggen/s.png"))
    assert_graph(res)
    assert "UNETLoader" in _types(res) and "VAEEncode" in _types(res)


def test_no_score_prefix_for_lustify(build_ctx, assert_graph):
    spec = GenSpec(mode=Mode.txt2img, model="lustify", prompt="a fox")
    res = B.build(spec, build_ctx("lustify"))
    texts = [n["inputs"].get("text", "") for n in res.graph.values() if n["class_type"] == "CLIPTextEncode"]
    assert all("score_9" not in t for t in texts)


# ── inpaint ──────────────────────────────────────────────────────────────────
def test_inpaint_flux_fill_stays_gguf(build_ctx, assert_graph):
    spec = GenSpec(mode=Mode.inpaint, model="flux-fill", prompt="brick wall",
                   source_asset="s", mask_asset="m")
    res = B.build(spec, build_ctx("flux-fill", src="imggen/src.png", mask="imggen/mask.png"))
    assert_graph(res)
    assert "InpaintModelConditioning" in _types(res)
    assert "UnetLoaderGGUF" in _types(res)  # flux-fill keeps GGUF weights


def test_inpaint_sdxl_lustify(build_ctx, assert_graph):
    spec = GenSpec(mode=Mode.inpaint, model="sdxl-inpaint", prompt="skin",
                   source_asset="s", mask_asset="m")
    res = B.build(spec, build_ctx("sdxl-inpaint", src="imggen/src.png", mask="imggen/mask.png"))
    assert_graph(res)
    assert "VAEEncodeForInpaint" in _types(res)


# ── edit ─────────────────────────────────────────────────────────────────────
def test_edit_qwen_aio(build_ctx, assert_graph):
    spec = GenSpec(mode=Mode.edit, model="qwen-edit-aio", prompt="remove the hat", source_asset="s")
    res = B.build(spec, build_ctx("qwen-edit-aio", src="imggen/src.png"))
    assert_graph(res)
    # AIO loads from one fused checkpoint, not the separate-file Qwen loaders
    assert "CheckpointLoaderSimple" in _types(res)
    assert "TextEncodeQwenImageEdit" in _types(res)
    assert "UnetLoaderGGUF" not in _types(res)


def test_edit_kontext_multiref(build_ctx, assert_graph):
    spec = GenSpec(mode=Mode.edit, model="kontext", prompt="same outfit")
    res = B.build(spec, build_ctx("kontext", refs=["imggen/a.png", "imggen/b.png"]))
    assert_graph(res)
    # one chained ReferenceLatent per reference image
    assert sum(1 for n in res.graph.values() if n["class_type"] == "ReferenceLatent") == 2


# ── reference / style ────────────────────────────────────────────────────────
def test_reference_redux_native(build_ctx, assert_graph):
    spec = GenSpec(mode=Mode.reference, model="redux", prompt="this style")
    res = B.build(spec, build_ctx("redux", refs=["imggen/r.png"]))
    assert_graph(res)
    assert "StyleModelApply" in _types(res)
    # redux rides the Chroma fp8 base → native loader, not GGUF
    assert "UNETLoader" in _types(res) and "UnetLoaderGGUF" not in _types(res)


# ── identity / face (consent-gated) ──────────────────────────────────────────
def test_identity_instantid(build_ctx, assert_graph):
    spec = GenSpec(mode=Mode.reference, model="instantid", prompt="portrait")
    res = B.build(spec, build_ctx("instantid", refs=["imggen/face.png"]))
    assert_graph(res)
    assert "ApplyInstantID" in _types(res)


def test_identity_ipadapter(build_ctx, assert_graph):
    spec = GenSpec(mode=Mode.reference, model="ip-adapter", prompt="same face")
    res = B.build(spec, build_ctx("ip-adapter", refs=["imggen/face.png"]))
    assert_graph(res)
    assert "IPAdapterFaceID" in _types(res)


def test_identity_pulid_native(build_ctx, assert_graph):
    spec = GenSpec(mode=Mode.reference, model="pulid-flux", prompt="same face")
    res = B.build(spec, build_ctx("pulid-flux", refs=["imggen/face.png"]))
    assert_graph(res)
    assert "ApplyPulidFlux" in _types(res)
    assert "UNETLoader" in _types(res)


# ── controlnet + pose ────────────────────────────────────────────────────────
def test_controlnet_sdxl_pose(build_ctx, assert_graph):
    spec = GenSpec(mode=Mode.controlnet, model="lustify", prompt="city", controlnet_type="pose")
    res = B.build(spec, build_ctx("lustify", refs=["imggen/ref.png"]))
    assert_graph(res)
    assert "ControlNetApplyAdvanced" in _types(res)
    assert "DWPreprocessor" in _types(res)  # pose preprocessor


def test_controlnet_sdxl_canny(build_ctx, assert_graph):
    spec = GenSpec(mode=Mode.controlnet, model="lustify", prompt="city", controlnet_type="canny")
    res = B.build(spec, build_ctx("lustify", refs=["imggen/ref.png"]))
    assert_graph(res)
    assert "CannyEdgePreprocessor" in _types(res)


# ── video (Wan 2.2) ──────────────────────────────────────────────────────────
def test_video_wan_5b_ti2v(build_ctx, assert_video_graph):
    """The 5B TI2V (default video model) uses the new wan2.2 VAE → the 5B-specific latent node,
    NOT EmptyHunyuanLatentVideo (which is the 14B Hunyuan-shaped latent). Single dense sampler."""
    spec = GenSpec(mode=Mode.video, model="wan22-ti2v", prompt="a waterfall")
    res = B.build(spec, build_ctx("wan22-ti2v"))
    assert_video_graph(res)
    assert "SaveAnimatedWEBP" in _types(res)
    assert "Wan22ImageToVideoLatent" in _types(res)       # 5B latent node
    assert "EmptyHunyuanLatentVideo" not in _types(res)   # not the 14B latent
    assert "KSampler" in _types(res)                      # single dense sampler (no MoE split)


def test_video_wan_i2v(build_ctx, assert_video_graph):
    spec = GenSpec(mode=Mode.video, model="wan22-i2v", prompt="pan the camera", source_asset="s")
    res = B.build(spec, build_ctx("wan22-i2v", src="imggen/src.png"))
    assert_video_graph(res)
    assert "WanImageToVideo" in _types(res)  # image→video branch


def test_video_wan_a14b_moe(build_ctx, assert_video_graph):
    """A14B (t2v) is a MoE: both noise experts load, each with its own lightx2v LoRA, and
    sampling splits across two KSamplerAdvanced stages (high-noise → low-noise)."""
    spec = GenSpec(mode=Mode.video, model="wan22-t2v", prompt="a city at night")
    res = B.build(spec, build_ctx("wan22-t2v"))
    assert_video_graph(res)
    nodes = list(res.graph.values())
    assert "EmptyHunyuanLatentVideo" in _types(res)  # 14B t2v uses the Hunyuan-shaped latent
    # two UNET experts + two-stage advanced sampling
    assert sum(n["class_type"] == "UNETLoader" for n in nodes) == 2
    assert sum(n["class_type"] == "KSamplerAdvanced" for n in nodes) == 2
    # high-noise expert LoRA (CLIP-side LoraLoader) + low-noise expert LoRA (LoraLoaderModelOnly)
    lora_names = {n["inputs"].get("lora_name") for n in nodes if "lora" in n["class_type"].lower()}
    assert "wan2.2_t2v_lightx2v_4step.safetensors" in lora_names
    assert "wan2.2_t2v_lightx2v_4step_low.safetensors" in lora_names
    assert any(n["class_type"] == "LoraLoaderModelOnly" for n in nodes)
    # high stage seeds noise & hands leftover-noise latent to the low stage that finishes it
    adv = [n for n in nodes if n["class_type"] == "KSamplerAdvanced"]
    assert {n["inputs"]["add_noise"] for n in adv} == {"enable", "disable"}


# ── LoRA chain + standalone upscalers ────────────────────────────────────────
def test_lora_chain(build_ctx):
    spec = GenSpec(mode=Mode.txt2img, model="lustify", prompt="x",
                   loras=[{"name": "a.safetensors", "weight": 0.7}])
    res = B.build(spec, build_ctx("lustify"))
    assert "LoraLoader" in _types(res)


def test_upscale_realesrgan(assert_graph):
    res = B.build_upscale("imggen/x.png")
    assert_graph(res)
    assert "ImageUpscaleWithModel" in _types(res)


def test_ultimate_sd_upscale(build_ctx, assert_graph):
    spec = GenSpec(mode=Mode.txt2img, model="lustify", prompt="more detail")
    res = B.build_ultimate_upscale(spec, build_ctx("lustify"), "imggen/x.png")
    assert_graph(res)
    assert "UltimateSDUpscale" in _types(res)
