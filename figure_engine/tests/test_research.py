"""Phase B — 웹검색 그라운딩(research) 토글 배선 (오프라인/mock)."""

from __future__ import annotations

import asyncio

from figgen.config import Settings
from figgen.pipeline.orchestrator import Orchestrator
from figgen.pipeline.planner import Planner, _with_research
from figgen.providers import MockLLMClient
from figgen.schema.figure_spec import FigureSpec
from figgen.schema.requests import GenerationRequest


def _run(coro):
    return asyncio.run(coro)


def test_mock_web_research_returns_empty():
    # 오프라인 — 네트워크 호출 없이 빈 문자열
    assert _run(MockLLMClient().web_research("citric acid cycle")) == ""


def test_with_research_appends_and_passthrough():
    out = _with_research("base prompt", "ATP is produced in the mitochondria")
    assert "Researched scientific context" in out and "base prompt" in out
    assert _with_research("base prompt", "") == "base prompt"  # 빈 컨텍스트는 그대로


def test_planner_plan_accepts_research_ctx():
    planner = Planner(MockLLMClient())
    req = GenerationRequest(description="a -> b -> c", figure_type="method_diagram")
    spec = _run(planner.plan(req, "method_diagram", research_ctx="key facts about a,b,c"))
    assert isinstance(spec, FigureSpec) and spec.figure_type == "method_diagram"


def test_planner_plan_scene_accepts_research_ctx():
    planner = Planner(MockLLMClient())
    req = GenerationRequest(description="macrophage engulfing bacteria")
    brief = _run(planner.plan_scene(req, research_ctx="phagocytosis steps"))
    assert brief.scene_prompt


def test_orchestrator_research_skips_for_mock():
    # provider=mock이면 research 토글이 켜져도 네트워크 없이 빈 컨텍스트
    orch = Orchestrator(Settings(_env_file=None), store=None)
    req = GenerationRequest(description="the citric acid cycle", research=True)
    ctx = _run(orch._research(req, "mock", lambda *a, **k: None))
    assert ctx == ""


def test_orchestrator_research_off_by_default():
    orch = Orchestrator(Settings(_env_file=None), store=None)
    req = GenerationRequest(description="x")  # research 기본 False
    ctx = _run(orch._research(req, "openai", lambda *a, **k: None))
    assert ctx == ""
