"""Graph builder produces well-formed ComfyUI graphs for each mode.

The local lineup is a single SDXL checkpoint (juggernaut-xl): txt2img/img2img/inpaint/edit run on
the checkpoint, reference uses IP-Adapter Plus, controlnet uses a ControlNet adapter.
"""
from app.comfy import builder as B
from app.models_catalog.registry import MODELS
from app.schemas.genspec import GenSpec, Mode

LOCAL = "juggernaut-xl"


def _ctx(model_id, **kw):
    m = MODELS[model_id]
    return B.BuildContext(model=m, width=kw.get("width", 1024), height=kw.get("height", 1024),
                          comfy_source=kw.get("src"), comfy_mask=kw.get("mask"),
                          comfy_refs=kw.get("refs", []))


def _types(res: B.BuildResult):
    return [n["class_type"] for n in res.graph.values()]


def _assert_graph(result: B.BuildResult):
    g = result.graph
    assert isinstance(g, dict) and g
    # every node has class_type + inputs; links point to existing nodes
    for nid, node in g.items():
        assert "class_type" in node and "inputs" in node
        for v in node["inputs"].values():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                assert v[0] in g, f"node {nid} links to missing node {v[0]}"
    assert result.save_node in g
    assert g[result.save_node]["class_type"] == "SaveImage"


def test_txt2img_sdxl():
    spec = GenSpec(mode=Mode.txt2img, model=LOCAL, prompt="a fox")
    res = B.build(spec, _ctx(LOCAL))
    _assert_graph(res)
    assert "CheckpointLoaderSimple" in _types(res)


def test_img2img_sdxl():
    spec = GenSpec(mode=Mode.img2img, model=LOCAL, prompt="a fox", source_asset="s")
    res = B.build(spec, _ctx(LOCAL, src="imggen/src.png"))
    _assert_graph(res)
    assert "VAEEncode" in _types(res)


def test_inpaint_sets_latent_noise_mask():
    # Standard 4-ch SDXL checkpoint → inpaint must re-assert the mask via SetLatentNoiseMask.
    spec = GenSpec(mode=Mode.inpaint, model=LOCAL, prompt="brick wall",
                   source_asset="s", mask_asset="m")
    res = B.build(spec, _ctx(LOCAL, src="imggen/src.png", mask="imggen/mask.png"))
    _assert_graph(res)
    types = _types(res)
    assert "VAEEncodeForInpaint" in types
    assert "SetLatentNoiseMask" in types


def test_edit_with_mask_routes_to_inpaint():
    spec = GenSpec(mode=Mode.edit, model=LOCAL, prompt="make the sky red",
                   source_asset="s", mask_asset="m")
    res = B.build(spec, _ctx(LOCAL, src="imggen/src.png", mask="imggen/mask.png"))
    _assert_graph(res)
    assert "SetLatentNoiseMask" in _types(res)


def test_edit_without_mask_routes_to_img2img():
    spec = GenSpec(mode=Mode.edit, model=LOCAL, prompt="brighten it", source_asset="s")
    res = B.build(spec, _ctx(LOCAL, src="imggen/src.png"))
    _assert_graph(res)
    types = _types(res)
    assert "VAEEncode" in types
    assert "SetLatentNoiseMask" not in types


def test_reference_routes_to_ipadapter():
    # Reference → IP-Adapter Plus, single reference image.
    spec = GenSpec(mode=Mode.reference, model=LOCAL, prompt="in this style",
                   reference_images=[{"asset": "r", "strength": 0.7}])
    res = B.build(spec, _ctx(LOCAL, refs=["imggen/ref.png"]))
    _assert_graph(res)
    types = _types(res)
    assert "IPAdapterModelLoader" in types
    assert "IPAdapterAdvanced" in types
    assert "CLIPVisionLoader" in types
    assert types.count("LoadImage") == 1


def test_controlnet_sdxl():
    spec = GenSpec(mode=Mode.controlnet, model=LOCAL, prompt="city", controlnet_type="canny")
    res = B.build(spec, _ctx(LOCAL, refs=["imggen/ref.png"]))
    _assert_graph(res)
    assert "ControlNetApplyAdvanced" in _types(res)


def test_lora_chain():
    spec = GenSpec(mode=Mode.txt2img, model=LOCAL, prompt="x",
                   loras=[{"name": "a.safetensors", "weight": 0.7}])
    res = B.build(spec, _ctx(LOCAL))
    assert "LoraLoader" in _types(res)


def test_upscale_graph():
    res = B.build_upscale("imggen/x.png")
    _assert_graph(res)
    assert "ImageUpscaleWithModel" in _types(res)
