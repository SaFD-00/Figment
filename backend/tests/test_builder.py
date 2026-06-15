"""Graph builder produces well-formed ComfyUI graphs for each mode."""
import pytest

from app.comfy import builder as B
from app.models_catalog.registry import MODELS, resolve
from app.schemas.genspec import GenSpec, Mode


def _ctx(model_id, **kw):
    m = MODELS[model_id]
    return B.BuildContext(model=m, width=kw.get("width", 1024), height=kw.get("height", 1024),
                          comfy_source=kw.get("src"), comfy_mask=kw.get("mask"),
                          comfy_refs=kw.get("refs", []))


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
    spec = GenSpec(mode=Mode.txt2img, model="pony-v6", prompt="a fox")
    _assert_graph(B.build(spec, _ctx("pony-v6")))


def test_txt2img_chroma_flux():
    spec = GenSpec(mode=Mode.txt2img, model="chroma-hd", prompt="a fox")
    res = B.build(spec, _ctx("chroma-hd"))
    _assert_graph(res)
    assert any(n["class_type"] == "UnetLoaderGGUF" for n in res.graph.values())
    assert any(n["class_type"] == "FluxGuidance" for n in res.graph.values())


def test_inpaint_flux_fill():
    spec = GenSpec(mode=Mode.inpaint, model="flux-fill", prompt="brick wall",
                   source_asset="s", mask_asset="m")
    res = B.build(spec, _ctx("flux-fill", src="imggen/src.png", mask="imggen/mask.png"))
    _assert_graph(res)
    assert any(n["class_type"] == "InpaintModelConditioning" for n in res.graph.values())


def test_controlnet_sdxl():
    spec = GenSpec(mode=Mode.controlnet, model="pony-v6", prompt="city", controlnet_type="canny")
    res = B.build(spec, _ctx("pony-v6", refs=["imggen/ref.png"]))
    _assert_graph(res)
    assert any(n["class_type"] == "ControlNetApplyAdvanced" for n in res.graph.values())


def test_pony_score_prefix_injected():
    spec = GenSpec(mode=Mode.txt2img, model="pony-v6", prompt="a fox")
    res = B.build(spec, _ctx("pony-v6"))
    texts = [n["inputs"].get("text", "") for n in res.graph.values() if n["class_type"] == "CLIPTextEncode"]
    assert any("score_9" in t for t in texts)


def test_lora_chain():
    spec = GenSpec(mode=Mode.txt2img, model="pony-v6", prompt="x",
                   loras=[{"name": "a.safetensors", "weight": 0.7}])
    res = B.build(spec, _ctx("pony-v6"))
    assert any(n["class_type"] == "LoraLoader" for n in res.graph.values())


def test_upscale_graph():
    res = B.build_upscale("imggen/x.png")
    _assert_graph(res)
    assert any(n["class_type"] == "ImageUpscaleWithModel" for n in res.graph.values())
