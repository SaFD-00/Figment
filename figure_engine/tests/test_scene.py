"""M4.1/M4.2 — scientific_illustration 장면 모드 + 공격적 분류 라우팅."""

from __future__ import annotations

import asyncio

from figgen.assets.prompts import build_icon_prompt, build_scene_prompt
from figgen.assets.store import AssetStore
from figgen.config import get_settings
from figgen.layout import LayoutEngine
from figgen.pipeline.planner import Planner, SceneBrief
from figgen.pipeline.scene import generate_scene_spec
from figgen.providers import MockLLMClient
from figgen.render.pptx_renderer import PptxRenderer
from figgen.render.resolver import resolve
from figgen.render.svg_renderer import SvgRenderer
from figgen.schema.figure_spec import FigureSpec
from figgen.schema.requests import GenerationRequest
from figgen.styles.presets import get_preset


def _run(c):
    return asyncio.run(c)


def _classify(desc: str, **kw) -> str:
    p = Planner(MockLLMClient(), MockLLMClient())
    return _run(p.classify(GenerationRequest(description=desc, **kw)))


def test_classify_routes_scene_by_default():
    # 생물/해부/장면 → scientific_illustration (공격적 기본값)
    assert _classify("the Krebs cycle inside a mitochondrion") == "scientific_illustration"
    assert _classify("wound healing in mouse skin with immune cells") == "scientific_illustration"
    # 아키텍처/파이프라인 → method_diagram (회귀 가드)
    assert _classify("encoder-decoder transformer architecture pipeline") == "method_diagram"
    # 데이터 플롯 → chart
    assert _classify("bar chart of accuracy across datasets") == "chart"
    # 명시적 --type override 우선
    assert _classify("anything at all", figure_type="method_diagram") == "method_diagram"


def test_plan_scene_returns_brief():
    brief = _run(Planner(MockLLMClient()).plan_scene(
        GenerationRequest(description="wound healing in mouse skin")))
    assert isinstance(brief, SceneBrief)
    assert brief.scene_prompt
    assert brief.labels


def test_scene_spec_renders_image_plus_vector_labels(tmp_path):
    store = AssetStore(tmp_path / "assets")
    req = GenerationRequest(
        description="wound healing across damage to repair in mouse skin", provider="mock")
    spec = _run(generate_scene_spec(Planner(MockLLMClient()), req, store, get_settings(), "mock"))

    assert spec.figure_type == "scientific_illustration"
    assert spec.root.type == "free"
    base = spec.find("base_image")
    assert base is not None and base.asset_id  # 래스터 PNG 바인딩됨
    assert base.svg_asset_id  # 벡터화 변형도 바인딩됨(M4.4)

    spec2 = spec.model_copy(update={"stylesheet": get_preset("nature_minimal")})
    fig = resolve(spec2, LayoutEngine().layout(spec2), spec2.stylesheet)

    svg = SvgRenderer(store, embed_images=True).render(fig)
    assert 'data-fg-id="base_image"' in svg
    assert "<path" in svg   # 장면 아트가 편집 가능 벡터 path로 인라인(M4.4)
    assert "<text" in svg   # 편집 가능 벡터 라벨

    pptx = PptxRenderer(store).render(fig)  # 라벨=텍스트박스, 이미지=picture(래스터 폴백)
    assert isinstance(pptx, bytes) and len(pptx) > 1000


def test_vectorize_png_produces_paths():
    # mock 이미지 PNG → vtracer 벡터 SVG(<path>)
    import io as _io

    from PIL import Image

    from figgen.fullimage.vectorize import vectorize_png

    img = Image.new("RGB", (64, 64), (240, 240, 240))
    for x in range(16, 48):
        for y in range(16, 48):
            img.putpixel((x, y), (200, 60, 60))
    buf = _io.BytesIO()
    img.save(buf, format="PNG")
    svg = vectorize_png(buf.getvalue())
    assert "<svg" in svg and "<path" in svg


def test_box_icons_opt_in_render(tmp_path):
    from figgen.pipeline.diagram_icons import generate_box_icons

    spec = FigureSpec.model_validate({
        "figure_type": "method_diagram",
        "root": {"type": "row", "id": "root", "children": [
            {"type": "box", "id": "a", "label": "Encoder", "role": "model"},
            {"type": "box", "id": "b", "label": "Decoder", "role": "model"},
            {"type": "box", "id": "n", "label": "side note", "role": "note"},
        ]},
    })
    store = AssetStore(tmp_path / "assets")
    req = GenerationRequest(description="x", provider="mock")
    out = _run(generate_box_icons(spec, req, store, get_settings(), "mock"))

    assert out.find("a").icon_asset and out.find("b").icon_asset  # 박스마다 아이콘
    assert out.find("n").icon_asset is None  # note role은 제외

    out2 = out.model_copy(update={"stylesheet": get_preset("nature_minimal")})
    fig = resolve(out2, LayoutEngine().layout(out2), out2.stylesheet)
    svg = SvgRenderer(store, embed_images=True).render(fig)
    assert svg.count("<image") >= 2  # 박스 아이콘이 이미지로 들어감


def test_build_scene_prompt_drops_isolated_subject_suffix():
    sp = build_scene_prompt("mouse skin cross-section across healing stages", "nature_minimal")
    assert "single isolated subject" not in sp  # 장면은 고립 객체가 아니다
    assert "no text" in sp
    # 아이콘 프롬프트는 여전히 고립 접미사 유지
    assert "single isolated subject" in build_icon_prompt("a neuron", "nature_minimal", True)
