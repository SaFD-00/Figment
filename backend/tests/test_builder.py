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


def _assert_video_graph(result: B.BuildResult):
    """Like _assert_graph but the save node is a video writer, not SaveImage."""
    g = result.graph
    assert isinstance(g, dict) and g
    for nid, node in g.items():
        assert "class_type" in node and "inputs" in node
        for v in node["inputs"].values():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                assert v[0] in g, f"node {nid} links to missing node {v[0]}"
    assert result.save_node in g
    assert result.is_video


def test_txt2img_sdxl():
    spec = GenSpec(mode=Mode.txt2img, model="lustify", prompt="a fox")
    _assert_graph(B.build(spec, _ctx("lustify")))


def test_txt2img_chroma_native():
    spec = GenSpec(mode=Mode.txt2img, model="chroma-hd", prompt="a fox")
    res = B.build(spec, _ctx("chroma-hd"))
    _assert_graph(res)
    # chroma-hd ships native fp8 safetensors → native UNETLoader, not the GGUF loader
    assert any(n["class_type"] == "UNETLoader" for n in res.graph.values())
    assert not any(n["class_type"] == "UnetLoaderGGUF" for n in res.graph.values())
    assert any(n["class_type"] == "FluxGuidance" for n in res.graph.values())


def test_inpaint_flux_fill_stays_gguf():
    spec = GenSpec(mode=Mode.inpaint, model="flux-fill", prompt="brick wall",
                   source_asset="s", mask_asset="m")
    res = B.build(spec, _ctx("flux-fill", src="imggen/src.png", mask="imggen/mask.png"))
    _assert_graph(res)
    assert any(n["class_type"] == "InpaintModelConditioning" for n in res.graph.values())
    # flux-fill keeps GGUF weights → GGUF loader
    assert any(n["class_type"] == "UnetLoaderGGUF" for n in res.graph.values())


def test_controlnet_sdxl_pose():
    spec = GenSpec(mode=Mode.controlnet, model="lustify", prompt="city", controlnet_type="pose")
    res = B.build(spec, _ctx("lustify", refs=["imggen/ref.png"]))
    _assert_graph(res)
    assert any(n["class_type"] == "ControlNetApplyAdvanced" for n in res.graph.values())
    assert any(n["class_type"] == "DWPreprocessor" for n in res.graph.values())


def test_no_score_prefix_for_lustify():
    spec = GenSpec(mode=Mode.txt2img, model="lustify", prompt="a fox")
    res = B.build(spec, _ctx("lustify"))
    texts = [n["inputs"].get("text", "") for n in res.graph.values() if n["class_type"] == "CLIPTextEncode"]
    assert all("score_9" not in t for t in texts)


def test_edit_qwen_aio():
    spec = GenSpec(mode=Mode.edit, model="qwen-edit-aio", prompt="remove the hat", source_asset="s")
    res = B.build(spec, _ctx("qwen-edit-aio", src="imggen/src.png"))
    _assert_graph(res)
    assert any(n["class_type"] == "TextEncodeQwenImageEdit" for n in res.graph.values())
    assert any(n["class_type"] == "CheckpointLoaderSimple" for n in res.graph.values())


def test_identity_instantid():
    spec = GenSpec(mode=Mode.reference, model="instantid", prompt="portrait")
    res = B.build(spec, _ctx("instantid", refs=["imggen/face.png"]))
    _assert_graph(res)
    assert any(n["class_type"] == "ApplyInstantID" for n in res.graph.values())


def test_video_wan_t2v():
    spec = GenSpec(mode=Mode.video, model="wan22-ti2v", prompt="a waterfall")
    res = B.build(spec, _ctx("wan22-ti2v"))
    _assert_video_graph(res)
    assert any(n["class_type"] == "SaveAnimatedWEBP" for n in res.graph.values())


def test_video_wan_i2v():
    spec = GenSpec(mode=Mode.video, model="wan22-i2v", prompt="pan the camera", source_asset="s")
    res = B.build(spec, _ctx("wan22-i2v", src="imggen/src.png"))
    _assert_video_graph(res)
    assert any(n["class_type"] == "WanImageToVideo" for n in res.graph.values())


def test_lora_chain():
    spec = GenSpec(mode=Mode.txt2img, model="lustify", prompt="x",
                   loras=[{"name": "a.safetensors", "weight": 0.7}])
    res = B.build(spec, _ctx("lustify"))
    assert any(n["class_type"] == "LoraLoader" for n in res.graph.values())


def test_upscale_graph():
    res = B.build_upscale("imggen/x.png")
    _assert_graph(res)
    assert any(n["class_type"] == "ImageUpscaleWithModel" for n in res.graph.values())
