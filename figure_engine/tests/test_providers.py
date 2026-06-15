"""Phase 2 — mock provider + planner/stylist 파이프라인(오프라인) + registry 라우팅."""

from __future__ import annotations

import asyncio

from figgen.config import Settings
from figgen.layout import LayoutEngine
from figgen.pipeline.planner import Planner
from figgen.pipeline.stylist import Stylist
from figgen.providers import MockLLMClient, get_image_client, get_llm
from figgen.providers.mock_client import MockImageClient
from figgen.render.resolver import resolve
from figgen.schema.figure_spec import FigureSpec
from figgen.schema.requests import GenerationRequest

TYPES = ["method_diagram", "concept", "chart", "graphical_abstract"]


def _run(coro):
    return asyncio.run(coro)


async def _pipeline(desc, ftype):
    planner = Planner(MockLLMClient())
    stylist = Stylist()
    req = GenerationRequest(description=desc, figure_type=ftype, style_preset="nature_minimal")
    t = await planner.classify(req)
    spec = await planner.plan(req, t)
    spec = stylist.apply(spec, "nature_minimal")
    return spec


def test_mock_pipeline_all_types_valid_and_render():
    for ftype in TYPES:
        spec = _run(_pipeline("A pipeline encodes input then decodes output", ftype))
        assert isinstance(spec, FigureSpec)
        assert spec.figure_type == ftype
        assert spec.stylesheet is not None  # Stylist가 주입
        # 렌더까지 통과
        layout = LayoutEngine().layout(spec)
        fig = resolve(spec, layout, spec.stylesheet)
        assert fig.elements


def test_planner_clears_stylesheet_before_stylist():
    planner = Planner(MockLLMClient())
    req = GenerationRequest(description="x->y->z", figure_type="method_diagram")
    spec = _run(planner.plan(req, "method_diagram"))
    assert spec.stylesheet is None  # Planner는 스타일 미지정


def test_mock_classify_detects_chart():
    planner = Planner(MockLLMClient())
    req = GenerationRequest(description="bar chart of accuracy across datasets")
    assert _run(planner.classify(req)) == "chart"


def test_stylist_injects_palette_for_roleless_box():
    planner = Planner(MockLLMClient())
    spec = _run(planner.plan(
        GenerationRequest(description="alpha, beta, gamma", figure_type="method_diagram"),
        "method_diagram"))
    styled = Stylist().apply(spec, "nature_minimal")
    assert styled.stylesheet.name == "nature_minimal"


def test_registry_falls_back_to_mock_without_keys():
    s = Settings(_env_file=None)  # 키 없음
    assert isinstance(get_llm("planner", s), MockLLMClient)
    assert isinstance(get_image_client(s, transparent=True), MockImageClient)


def test_mock_image_client_alpha():
    res = _run(MockImageClient().generate("brain icon", transparent=True))
    assert res.has_alpha and res.data[:4] == b"\x89PNG"
    from io import BytesIO

    from PIL import Image

    assert Image.open(BytesIO(res.data)).mode == "RGBA"


# ── OpenRouter provider (네트워크 없이 구성·파싱·라우팅만 검증) ──────────────


def test_openrouter_llm_config():
    from figgen.providers.openrouter_client import OpenRouterClient

    c = OpenRouterClient("sk-or-xxx", "minimax/minimax-m3")
    assert c.base_url == "https://openrouter.ai/api/v1"
    assert c.name == "openrouter:minimax/minimax-m3"
    assert c._omit_temp is False  # minimax는 temperature 지원
    assert c.extra_headers.get("X-Title") == "FigGen"


def test_openrouter_image_aspect_and_size():
    from figgen.providers.openrouter_client import OpenRouterImageClient

    c = OpenRouterImageClient("sk-or-xxx", "bytedance-seed/seedream-4.5")
    assert c._aspect(1536, 1024) == "16:9"
    assert c._aspect(1024, 1536) == "9:16"
    assert c._aspect(1024, 1024) == "1:1"
    assert c._image_size(1024, 1024) == "1K"
    assert c._image_size(1536, 1024) == "2K"
    assert c._image_size(4096, 2048) == "4K"


def test_openrouter_image_decode_data_url():
    import base64

    from figgen.providers.openrouter_client import OpenRouterImageClient

    raw = b"\x89PNG\r\n\x1a\nmock-bytes"
    url = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
    result = {"choices": [{"message": {"images": [{"image_url": {"url": url}}]}}]}
    data, mime = OpenRouterImageClient._decode(result)
    assert data == raw and mime == "image/png"
    # JPEG data URL의 mime도 파싱
    jurl = "data:image/jpeg;base64," + base64.b64encode(b"jpegbytes").decode("ascii")
    _d, jmime = OpenRouterImageClient._decode(
        {"choices": [{"message": {"images": [{"image_url": {"url": jurl}}]}}]})
    assert jmime == "image/jpeg"


def test_stylist_from_report_applies_palette_font_density():
    """Bug E: RefStyleReport(palette/font_feel/density)가 실제 StyleSheet에 반영."""
    from figgen.pipeline.planner import Planner, RefStyleReport
    from figgen.schema.requests import GenerationRequest
    from figgen.styles.presets import get_preset

    spec = _run(Planner(MockLLMClient()).plan(
        GenerationRequest(description="a,b,c", figure_type="method_diagram"), "method_diagram"))
    rep = RefStyleReport(palette_hex=["#101010", "#202020", "#303030"], density="sparse",
                         font_feel="serif")
    styled = Stylist().from_report(spec, rep, base_preset="nature_minimal")
    assert [c.lower() for c in styled.stylesheet.palette[:3]] == ["#101010", "#202020", "#303030"]
    assert styled.stylesheet.font_family == "Times New Roman"  # serif
    # sparse → 선을 더 두껍게
    assert styled.stylesheet.stroke_width_pt > get_preset("nature_minimal").stroke_width_pt


def test_registry_routes_to_openrouter_with_key():
    from figgen.providers.openrouter_client import OpenRouterClient, OpenRouterImageClient

    s = Settings(_env_file=None, OPENROUTER_API_KEY="sk-or-xxx", FIGGEN_PROVIDER="openrouter")
    assert "openrouter" in s.available_providers()
    assert isinstance(get_llm("planner", s), OpenRouterClient)
    assert isinstance(get_image_client(s), OpenRouterImageClient)
