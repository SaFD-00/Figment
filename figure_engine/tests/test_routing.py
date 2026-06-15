"""Phase C — 이미지-우선/구조적 하이브리드 라우팅 + 분류 오버라이드 (오프라인/mock)."""

from __future__ import annotations

import asyncio

from figgen.pipeline.planner import Planner
from figgen.pipeline.routing import is_image_first, route
from figgen.providers import MockLLMClient
from figgen.schema.requests import GenerationRequest


def _classify(desc: str, ftype=None, paper_text=None) -> str:
    planner = Planner(MockLLMClient())
    req = GenerationRequest(description=desc, figure_type=ftype, paper_text=paper_text)
    return asyncio.run(planner.classify(req))


def test_route_mapping():
    assert is_image_first("scientific_illustration")
    assert is_image_first("graphical_abstract")
    assert not is_image_first("method_diagram")
    assert not is_image_first("chart")
    assert route("scientific_illustration") == "image_first"
    assert route("graphical_abstract") == "image_first"
    assert route("method_diagram") == "structured"
    assert route("chart") == "structured"
    assert route("concept") == "structured"


def test_mock_classify_routes_representative_prompts():
    assert _classify("bar chart of accuracy across datasets") == "chart"
    assert _classify("encoder-decoder transformer architecture pipeline") == "method_diagram"
    assert _classify("graphical abstract of our drug discovery method") == "graphical_abstract"
    # 그림으로 그릴 장면 → 이미지-우선 기본값
    assert _classify("a macrophage engulfing bacteria in inflamed tissue") == "scientific_illustration"


def test_figure_type_override_always_wins():
    # 명시적 figure_type은 분류기를 건너뛴다(데이터 키워드가 있어도)
    assert _classify("bar chart of accuracy", ftype="scientific_illustration") == \
        "scientific_illustration"
    assert _classify("a cell membrane", ftype="method_diagram") == "method_diagram"


def test_classify_uses_paper_text():
    # 짧은 description + 차트성 paper_text → chart로 라우팅(분류에 paper_text 반영)
    assert _classify("Figure 3", paper_text="A bar chart comparing accuracy and F1 "
                     "across three datasets with error bars.") == "chart"
