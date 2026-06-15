"""method_diagram 견고화 — LLM이 재귀 트리를 빈약하게 낼 때 flat ContentPlan으로 재조립.

라이브 회귀(gpt-5.4가 root를 단일 box로 반환)를 mock/stub로 오프라인 재현·검증한다.
"""

from __future__ import annotations

import asyncio

from figgen.pipeline.planner import (
    Planner,
    _assemble_method_diagram,
    _is_degenerate_diagram,
)
from figgen.schema.content_plan import ContentPlan, Entity, Relation
from figgen.schema.figure_spec import FigureSpec
from figgen.schema.requests import GenerationRequest


def _run(c):
    return asyncio.run(c)


_DEGENERATE = FigureSpec.model_validate({
    "figure_type": "method_diagram",
    "root": {"type": "box", "id": "root", "label": "Input Image", "role": "input"},
})


def _diffusion_plan() -> ContentPlan:
    return ContentPlan(
        entities=[
            Entity(name="input image", kind="data"),
            Entity(name="encoder", kind="module"),
            Entity(name="latent code", kind="data"),
            Entity(name="diffusion u-net", kind="module"),
            Entity(name="decoder", kind="module"),
            Entity(name="output image", kind="data"),
            Entity(name="autoencoder", kind="module"),  # contains-부모(흐름에 없음)
        ],
        relations=[
            Relation(source="input image", target="encoder", kind="flow", label="encoded"),
            Relation(source="encoder", target="latent code", kind="flow", label="produces"),
            Relation(source="latent code", target="diffusion u-net", kind="flow"),
            Relation(source="diffusion u-net", target="decoder", kind="flow",
                     label="reverse denoise to"),  # 14자 초과 → 라벨 드롭
            Relation(source="decoder", target="output image", kind="flow", label="produces"),
            Relation(source="autoencoder", target="encoder", kind="contains"),
            Relation(source="autoencoder", target="decoder", kind="contains"),
        ],
    )


def test_is_degenerate_detects_single_box_root():
    assert _is_degenerate_diagram(_DEGENERATE) is True
    # 정상 row(박스 ≥2)는 degenerate 아님
    healthy = FigureSpec.model_validate({
        "figure_type": "method_diagram",
        "root": {"type": "row", "id": "root", "children": [
            {"type": "box", "id": "a", "label": "A", "role": "input"},
            {"type": "box", "id": "b", "label": "B", "role": "output"},
        ]},
    })
    assert _is_degenerate_diagram(healthy) is False


def test_assemble_builds_pipeline_row_with_connectors():
    spec = _assemble_method_diagram(_diffusion_plan(), title="Latent Diffusion")
    assert spec is not None
    assert spec.root.type == "row"  # 6개(≤_PER_ROW) → 단일 행
    boxes = [n for n, _ in spec.iter_elements() if getattr(n, "type", None) == "box"]
    labels = [b.label for b in boxes]
    # autoencoder(흐름에 없는 contains-부모)는 제외, 흐름 순서대로 6개
    assert labels == ["input image", "encoder", "latent code",
                      "diffusion u-net", "decoder", "output image"]
    assert boxes[0].role == "input" and boxes[-1].role == "output"
    # connectors: flow 5개, 라벨은 생략(좁은 행에서 잘려 가독성 해침 — 박스 시퀀스로 충분)
    assert len(spec.connectors) == 5
    assert all(c.label is None for c in spec.connectors)
    # FigureSpec 검증 통과 = connector가 실재 box id 참조(무결성)
    assert not _is_degenerate_diagram(spec)


def test_assemble_wraps_long_pipeline_into_snake():
    """7단계 이상이면 한 줄로 늘이지 않고 Column(여러 Row) 뱀 배치로 줄바꿈."""
    names = [f"stage {i}" for i in range(9)]
    ents = [Entity(name=n, kind="operation") for n in names]
    rels = [Relation(source=names[i], target=names[i + 1], kind="flow") for i in range(8)]
    spec = _assemble_method_diagram(ContentPlan(entities=ents, relations=rels), title="long")
    assert spec is not None and spec.root.type == "column"
    rows = [c for c in spec.root.children if c.type == "row"]
    assert len(rows) >= 2  # 줄바꿈됨
    boxes = [n for n, _ in spec.iter_elements() if getattr(n, "type", None) == "box"]
    assert len(boxes) == 9 and len(spec.connectors) == 8


def test_assemble_returns_none_for_sparse_flow():
    cp = ContentPlan(entities=[Entity(name="x", kind="module")],
                     relations=[Relation(source="x", target="x", kind="contains")])
    assert _assemble_method_diagram(cp, title="t") is None


class _DegenerateLLM:
    """FigureSpec엔 빈약한 단일 box, ContentPlan엔 풍부한 flow를 내는 stub(gpt-5.4 회귀 모사)."""

    name = "fake"

    async def complete_structured(self, messages, schema, *, system="", images=None, max_repair=2):
        if schema.__name__ == "FigureSpec":
            return _DEGENERATE
        if schema.__name__ == "ContentPlan":
            return _diffusion_plan()
        raise AssertionError(f"예상치 못한 스키마: {schema.__name__}")


def test_plan_recovers_degenerate_method_diagram():
    """planner.plan이 빈약한 FigureSpec을 감지하면 ContentPlan으로 재조립해야 한다(배선 검증)."""
    planner = Planner(_DegenerateLLM())
    req = GenerationRequest(description="latent diffusion pipeline", figure_type="method_diagram")
    spec = _run(planner.plan(req, "method_diagram"))
    assert spec.figure_type == "method_diagram"
    assert spec.root.type == "row"  # 단일 box가 아니라 재조립된 row
    boxes = [n for n, _ in spec.iter_elements() if getattr(n, "type", None) == "box"]
    assert len(boxes) == 6 and len(spec.connectors) == 5
    assert spec.stylesheet is None  # Planner는 스타일 미지정(Stylist가 주입)
