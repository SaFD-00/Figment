"""Phase 4 — critic best-snapshot, 부분 재생성 스코프, 풀이미지, 차트, 프리셋."""

from __future__ import annotations

import asyncio

from figgen.fullimage.composer import LabelProposal, build_overlay_spec
from figgen.layout import LayoutEngine
from figgen.pipeline.critic import Critic, CritiqueResult
from figgen.pipeline.partial_edit import PartialEditor
from figgen.providers import MockLLMClient
from figgen.render.resolver import resolve
from figgen.render.svg_renderer import SvgRenderer
from figgen.schema.figure_spec import FigureSpec
from figgen.schema.patch import PatchOp, SpecPatch
from figgen.schema.requests import EditDirective
from figgen.styles.presets import get_preset, list_presets


def _run(c):
    return asyncio.run(c)


def _spec():
    return FigureSpec.model_validate({
        "figure_type": "method_diagram",
        "stylesheet": get_preset("nature_minimal").model_dump(),
        "root": {"type": "row", "id": "root", "children": [
            {"type": "box", "id": "a", "label": "A", "role": "process"},
            {"type": "box", "id": "b", "label": "B", "role": "process"},
        ]},
    })


# ── critic ────────────────────────────────────────────────────────────────────
def test_critic_mock_accepts_and_keeps_spec():
    spec = _spec()
    critic = Critic(MockLLMClient(), max_iters=2)
    out, history = _run(critic.run(spec, intent="diagram"))
    assert history and history[0].verdict == "accept"
    assert out.model_dump() == spec.model_dump()  # 수정 없음


def test_critic_best_snapshot_picks_highest():
    # 점수 5 → 8로 개선되는 stub VLM
    class StubVLM:
        name = "stub"
        def __init__(self):
            self.calls = 0
        async def complete(self, *a, **k):
            return ""
        async def complete_structured(self, messages, schema, **k):
            if schema.__name__ == "CritiqueResult":
                self.calls += 1
                if self.calls == 1:
                    return CritiqueResult(issues=[{"severity": "major", "category": "overlap",
                                                   "element_ids": ["a"], "description": "x"}],
                                          overall_score=5, verdict="revise")
                return CritiqueResult(issues=[], overall_score=8, verdict="accept")
            return SpecPatch(ops=[PatchOp(op="set", target_id="a", path="label", value="A2")],
                             reason="fix")
    spec = _spec()
    out, history = _run(Critic(StubVLM(), max_iters=3).run(spec, intent="x"))
    assert len(history) == 2
    assert max(c.overall_score for c in history) == 8
    assert out.find("a").label == "A2"  # 패치 반영된 스냅샷 채택


# ── 부분 재생성 스코프 ──────────────────────────────────────────────────────────
def test_partial_edit_scope_rejects_out_of_target():
    class StubLLM:
        name = "stub"
        async def complete(self, *a, **k):
            return ""
        async def complete_structured(self, messages, schema, **k):
            # 타깃 a + 스코프 밖 b 를 모두 건드리는 패치
            return SpecPatch(ops=[
                PatchOp(op="set", target_id="a", path="label", value="A2"),
                PatchOp(op="set", target_id="b", path="label", value="HACKED"),
            ], reason="x")
    spec = _spec()
    editor = PartialEditor(StubLLM())
    out = _run(editor.edit(spec, EditDirective(mode="element", instruction="bigger",
                                               target_element_ids=["a"])))
    assert out.find("a").label == "A2"      # 타깃은 수정
    assert out.find("b").label == "B"       # 스코프 밖은 불변


# ── 풀이미지 ──────────────────────────────────────────────────────────────────
def test_fullimage_overlay_spec_renders():
    spec = build_overlay_spec("ast_dummy", [
        LabelProposal(text="Problem", nx=0.2, ny=0.5),
        LabelProposal(text="Result", nx=0.8, ny=0.5),
    ], title="Overview")
    spec = spec.model_copy(update={"stylesheet": get_preset("nature_minimal")})
    layout = LayoutEngine().layout(spec)
    fig = resolve(spec, layout, spec.stylesheet)
    svg = SvgRenderer().render(fig)
    # 베이스 이미지 요소 + 편집 가능 텍스트 라벨
    assert 'data-fg-id="base_image"' in svg
    assert "Problem" in svg and "Result" in svg and "Overview" in svg


# ── 프리셋 ────────────────────────────────────────────────────────────────────
def test_all_presets_apply_and_render():
    ids = [p["id"] for p in list_presets()]
    assert len(ids) == 6
    assert "flat" in ids  # figurelabs 'Flat' 프리셋
    for pid in ids:
        spec = _spec().model_copy(update={"stylesheet": get_preset(pid)})
        fig = resolve(spec, LayoutEngine().layout(spec), spec.stylesheet)
        assert SvgRenderer().render(fig).startswith("<?xml")
