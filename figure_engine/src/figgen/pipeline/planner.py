"""사용자 입력 → FigureSpec 생성 (분류 → (장문: ContentPlan) → 플래닝).

Planner는 시맨틱 role만 태깅하고 스타일은 일절 지정하지 않는다(stylesheet=None 강제).
"""

from __future__ import annotations

import re
from functools import lru_cache
from importlib import resources
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..fullimage.composer import LabelProposal
from ..jobs.models import JobTask
from ..providers.base import ImageInput, LLMClient, user
from ..schema.content_plan import ContentPlan
from ..schema.figure_spec import (
    CONTAINER_TYPES,
    BoxElement,
    Canvas,
    Column,
    Connector,
    FigureSpec,
    FigureType,
    Row,
)
from ..schema.requests import GenerationRequest

_LONG_TEXT_THRESHOLD = 1500


class ClassifyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    figure_type: FigureType
    confidence: float = Field(ge=0, le=1, default=0.8)
    reason: str = ""


class SceneBrief(BaseModel):
    """scientific_illustration 계획 결과: 텍스트 없는 단일 장면 프롬프트 + 편집가능 라벨."""

    model_config = ConfigDict(extra="forbid")
    scene_prompt: str  # 하나의 응집된 장면(여러 주체가 공간/해부적 관계), 이미지 안엔 글자 없음
    title: str | None = None
    aspect: Literal["wide", "square", "tall"] = "wide"
    labels: list[LabelProposal] = Field(default_factory=list)


class RefStyleReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    palette_hex: list[str] = Field(default_factory=list)
    density: Literal["sparse", "medium", "dense"] = "medium"
    layout_pattern: str = ""
    font_feel: str = ""


class EnhancePromptResponse(BaseModel):
    """AI 프롬프트 강화 결과 — 구체적·자기완결적 영문 생성 프롬프트."""

    model_config = ConfigDict(extra="forbid")
    prompt: str


# ── 대화형 계획 확정(M6) ─────────────────────────────────────────────────────
class ChatMessage(BaseModel):
    """단일 대화 턴 (프론트가 히스토리를 보유, 매 턴 전체를 전송 — stateless)."""

    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"] = "user"
    content: str


class PlanBrief(BaseModel):
    """대화로 확정된 figure 생성 계획 — 그대로 JobRequest로 흘려보낸다.

    task로 generate/sketch/refine/vectorize 분기, reference_role로 첨부 이미지 용도를 명시.
    """

    model_config = ConfigDict(extra="forbid")
    task: JobTask = "generate"
    figure_type: FigureType = "scientific_illustration"
    title: str | None = None
    description: str  # 생성에 쓸 보강된 프롬프트(영문 권장)
    summary: str = ""  # 사용자에게 보일 한국어 계획 요약
    style_preset: str | None = None
    refine_modes: list[Literal["upscale", "white_bg", "denoise", "color_correct"]] = Field(
        default_factory=list
    )
    reference_role: Literal["style", "sketch", "refine", "none"] = "none"


class PlanTurn(BaseModel):
    """converse() 1턴 결과 — 어시스턴트 메시지 + (확정 시) 계획."""

    model_config = ConfigDict(extra="forbid")
    reply: str  # 어시스턴트의 한국어 메시지(질문 또는 확정 안내)
    ready: bool = False  # 충분히 합의됨 → plan 채워짐, '생성' 버튼 노출
    plan: PlanBrief | None = None


def _with_research(content: str, research_ctx: str) -> str:
    """웹검색 그라운딩 컨텍스트를 플래너 입력에 정확도 보강용으로 덧붙인다."""
    if not research_ctx:
        return content
    return (
        f"{content}\n\nResearched scientific context (use for accuracy; do not copy verbatim):\n"
        f"{research_ctx}"
    )


def _style_guidance(report: RefStyleReport | None) -> str:
    """참조 스타일 리포트 → 생성 프롬프트에 덧붙일 한 줄 가이드(없으면 빈 문자열)."""
    if report is None:
        return ""
    parts: list[str] = []
    if report.palette_hex:
        parts.append("palette " + ", ".join(report.palette_hex[:6]))
    if report.density:
        parts.append(f"{report.density} visual density")
    if report.layout_pattern:
        parts.append(f"{report.layout_pattern} layout")
    if report.font_feel:
        parts.append(f"{report.font_feel} typography")
    return "; ".join(parts)


def _with_style(content: str, report: RefStyleReport | None) -> str:
    """참조 이미지 스타일 가이드를 플래너 입력에 덧붙인다(reference_role='style')."""
    guidance = _style_guidance(report)
    if not guidance:
        return content
    return f"{content}\n\nReference style guidance (match this visual style): {guidance}"


@lru_cache(maxsize=8)
def _load_prompt(name: str) -> str:
    try:
        return resources.files("figgen.pipeline.prompts").joinpath(f"{name}.md").read_text("utf-8")
    except Exception:  # noqa: BLE001
        return ""


# ── method_diagram 견고화: flat ContentPlan → 결정론적 트리 조립 ──────────────────
# gpt-5.x가 재귀 FigureSpec을 빈약하게(단일 box 루트 등) 내는 경우의 폴백. flat 스키마인
# ContentPlan(entities+relations)은 안정적으로 풍부하게 나오므로, 그 flow 관계로 좌→우
# 파이프라인 row + connectors를 직접 만든다(LLM 트리 채우기에 의존하지 않음).
_KIND_ROLE = {"module": "model", "data": "data", "operation": "process", "loss": "loss"}
_PER_ROW = 6  # 한 행 최대 박스 수 — 초과 시 뱀(boustrophedon)으로 줄바꿈


def _slugify(name: str, idx: int, used: set[str]) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    s = re.sub(r"_+", "_", s)[:40]
    if not s or not s[0].isalpha():
        s = f"stage_{idx}"
    base, k = s, 1
    while s in used:
        s = f"{base[:38]}_{k}"
        k += 1
    used.add(s)
    return s


def _topo_order(names: list[str], flow: list) -> list[str]:
    """flow 엣지로 위상정렬(좌→우). 사이클/누락은 최초 등장 순서로 보존."""
    from collections import deque

    indeg = {nm: 0 for nm in names}
    succ: dict[str, list[str]] = {nm: [] for nm in names}
    edges: set[tuple[str, str]] = set()
    for r in flow:
        if (r.source in indeg and r.target in indeg and r.source != r.target
                and (r.source, r.target) not in edges):
            edges.add((r.source, r.target))
            succ[r.source].append(r.target)
            indeg[r.target] += 1
    q = deque([nm for nm in names if indeg[nm] == 0])
    order, seen = [], set()
    while q:
        nm = q.popleft()
        if nm in seen:
            continue
        seen.add(nm)
        order.append(nm)
        for v in succ[nm]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    for nm in names:  # 사이클로 남은 노드
        if nm not in seen:
            order.append(nm)
            seen.add(nm)
    return order


def _is_degenerate_diagram(spec: FigureSpec) -> bool:
    """method_diagram이 빈약한가 — 루트가 컨테이너가 아니거나 box leaf가 2개 미만."""
    boxes = [n for n, _ in spec.iter_elements() if getattr(n, "type", None) == "box"]
    return spec.root.type not in CONTAINER_TYPES or len(boxes) < 2


def _assemble_method_diagram(plan: ContentPlan, *, title: str | None) -> FigureSpec | None:
    """flat ContentPlan → 좌→우 row(박스) + connectors. flow가 빈약하면 None(폴백 포기)."""
    flow = [r for r in plan.relations if r.kind == "flow"]
    names, seen = [], set()
    for r in flow:
        for nm in (r.source, r.target):
            if nm not in seen:
                seen.add(nm)
                names.append(nm)
    if len(names) < 2:
        return None

    order = _topo_order(names, flow)
    ent_by_name = {e.name: e for e in plan.entities}
    used: set[str] = set()
    slug_of: dict[str, str] = {}
    boxes = []
    n = len(order)
    for i, nm in enumerate(order):
        slug = _slugify(nm, i, used)
        slug_of[nm] = slug
        ent = ent_by_name.get(nm)
        role = _KIND_ROLE.get(ent.kind if ent else "operation", "process")
        if i == 0:
            role = "input"
        elif i == n - 1:
            role = "output"
        shape = "ellipse" if role in ("input", "output") else "rounded"
        boxes.append(BoxElement(id=slug, label=nm[:40], role=role, shape=shape))

    # 다단계는 한 줄로 늘이면 과도하게 가늘어진다 → 행당 ≤_PER_ROW로 끊고 뱀(boustrophedon)
    # 배치: 짝수 행은 좌→우, 홀수 행은 우→좌 순서로 담아 행간 연결이 짧은 수직 점프가 되게.
    rows_count = (n + _PER_ROW - 1) // _PER_ROW  # ceil(n/_PER_ROW)
    per_row = (n + rows_count - 1) // rows_count  # 행 수 고정 후 균등 분배
    rows: list[list[BoxElement]] = [boxes[i:i + per_row] for i in range(0, n, per_row)]
    row_nodes = []
    for ri, rb in enumerate(rows):
        ordered = rb if ri % 2 == 0 else list(reversed(rb))
        row_nodes.append(Row(id=f"mdrow_{ri}", gap_mm=10.0, children=ordered))
    root: Row | Column
    if len(row_nodes) == 1:
        root = Row(id="root", gap_mm=10.0, padding_mm=8.0, children=row_nodes[0].children)
    else:
        root = Column(id="root", gap_mm=14.0, padding_mm=8.0, children=row_nodes)

    # connectors: flow 순서대로(라벨은 생략 — 좁은 행에서 잘리고 박스 시퀀스가 흐름을 이미 표현)
    connectors, cused = [], set()
    for j, r in enumerate(flow):
        s, t = slug_of.get(r.source), slug_of.get(r.target)
        if not s or not t or s == t:
            continue
        cid = f"c{j}"
        while cid in cused:
            cid += "_x"
        cused.add(cid)
        connectors.append(Connector(id=cid, source=s, target=t))

    width = max(180.0, 38.0 * min(n, per_row))
    return FigureSpec(
        figure_type="method_diagram", title=title or None,
        canvas=Canvas(width_mm=width), root=root, connectors=connectors, stylesheet=None)


class Planner:
    def __init__(self, llm: LLMClient, classifier_llm: LLMClient | None = None):
        self.llm = llm
        self.classifier_llm = classifier_llm or llm

    async def classify(self, req: GenerationRequest) -> FigureType:
        if req.figure_type:
            return req.figure_type  # 명시적 override 우선
        system = _load_prompt("classify")
        content = req.description
        if req.paper_text:
            content = f"{req.description}\n\n{req.paper_text[:_LONG_TEXT_THRESHOLD]}"
        res = await self.classifier_llm.complete_structured(
            [user(content)], ClassifyResult, system=system)
        return res.figure_type

    async def plan_scene(
        self,
        req: GenerationRequest,
        *,
        research_ctx: str = "",
        style_ref: RefStyleReport | None = None,
        figure_type: str = "scientific_illustration",
    ) -> SceneBrief:
        """이미지-우선 장면(단일 장면 프롬프트 + 라벨 세트)을 1콜로 생성.

        figure_type='graphical_abstract'면 problem→method→result 전용 장면 프롬프트를 쓴다.
        """
        prompt_name = (
            "graphical_abstract_scene"
            if figure_type == "graphical_abstract"
            else "scientific_illustration"
        )
        system = _load_prompt(prompt_name) or _load_prompt("scientific_illustration")
        content = req.description
        if req.paper_text:
            content = f"{req.description}\n\n{req.paper_text[:_LONG_TEXT_THRESHOLD]}"
        content = _with_research(content, research_ctx)
        content = _with_style(content, style_ref)
        return await self.llm.complete_structured([user(content)], SceneBrief, system=system)

    async def extract_content_plan(self, paper_text: str) -> ContentPlan:
        system = (
            "Extract entities and relations from this method description as a ContentPlan JSON. "
            "entities: {name, kind∈(module,data,operation,loss), description}; "
            "relations: {source, target, kind∈(flow,feedback,contains), label}."
        )
        return await self.llm.complete_structured([user(paper_text)], ContentPlan, system=system)

    async def plan(
        self,
        req: GenerationRequest,
        figure_type: FigureType,
        *,
        research_ctx: str = "",
        style_ref: RefStyleReport | None = None,
    ) -> FigureSpec:
        system = f"[[figure_type:{figure_type}]]\n{_load_prompt(figure_type)}"
        content = req.description
        content_plan: ContentPlan | None = None
        if (
            figure_type == "method_diagram"
            and req.paper_text
            and len(req.paper_text) > _LONG_TEXT_THRESHOLD
        ):
            content_plan = await self.extract_content_plan(req.paper_text)
            content = (
                f"{req.description}\n\nEntities: "
                + ", ".join(f"{e.name}({e.kind})" for e in content_plan.entities)
                + "\nRelations: "
                + ", ".join(f"{r.source}->{r.target}" for r in content_plan.relations)
            )
        elif req.paper_text:
            content = f"{req.description}\n\n{req.paper_text[:_LONG_TEXT_THRESHOLD]}"

        if req.data_refs:
            content += "\n\nAvailable data_ref keys: " + ", ".join(req.data_refs.keys())

        content = _with_research(content, research_ctx)
        content = _with_style(content, style_ref)
        spec = await self.llm.complete_structured([user(content)], FigureSpec, system=system)
        # 타입 강제 + 스타일 제거 (Planner는 스타일을 지정하지 않음)
        spec = spec.model_copy(update={"figure_type": figure_type, "stylesheet": None})

        # 견고화: LLM이 재귀 트리를 빈약하게 냈으면(단일 box 루트 등) flat ContentPlan으로
        # 좌→우 파이프라인을 재조립. 정상 spec엔 영향 없음(mock 포함).
        if figure_type == "method_diagram" and _is_degenerate_diagram(spec):
            if content_plan is None:
                try:
                    content_plan = await self.extract_content_plan(req.description)
                except Exception:  # noqa: BLE001
                    content_plan = None
            if content_plan is not None:
                assembled = _assemble_method_diagram(
                    content_plan, title=spec.title or req.description[:40])
                if assembled is not None:
                    spec = assembled
        return spec

    async def _paper_digest(self, paper_text: str) -> str:
        """긴 method 원문 → ContentPlan 엔티티/관계 다이제스트(짧으면 원문 절단)."""
        if len(paper_text) > _LONG_TEXT_THRESHOLD:
            try:
                cp = await self.extract_content_plan(paper_text)
                return (
                    "[논문 method 분해] Entities: "
                    + ", ".join(f"{e.name}({e.kind})" for e in cp.entities)
                    + " | Relations: "
                    + ", ".join(f"{r.source}->{r.target}" for r in cp.relations)
                )
            except Exception:  # noqa: BLE001
                pass
        return f"[논문 method 원문]\n{paper_text[:_LONG_TEXT_THRESHOLD]}"

    async def converse(
        self,
        messages: list[ChatMessage],
        *,
        attachments_note: str = "",
        research_ctx: str = "",
        paper_text: str | None = None,
    ) -> PlanTurn:
        """대화로 계획을 좁혀 PlanTurn 반환. 정보 부족 시 질문, 충분하면 ready=true + PlanBrief.

        대화 전체를 트랜스크립트 1블록으로 평탄화해 1콜로 처리(상태 비저장).
        paper_text(논문 method)가 있으면 ContentPlan으로 분해해 트랜스크립트에 덧붙인다.
        """
        system = _load_prompt("plan_chat")
        lines = []
        for m in messages:
            who = "User" if m.role == "user" else "Assistant"
            lines.append(f"{who}: {m.content.strip()[:2000]}")
        transcript = "\n".join(lines)
        if paper_text:
            transcript += "\n\n" + await self._paper_digest(paper_text)
        if attachments_note:
            transcript += f"\n\n[첨부 정보]\n{attachments_note}"
        transcript = _with_research(transcript, research_ctx)
        return await self.llm.complete_structured([user(transcript)], PlanTurn, system=system)

    async def enhance_prompt(self, text: str, figure_type: str | None = None) -> str:
        """사용자의 짧은 figure 아이디어 → 구체적·자기완결적 영문 생성 프롬프트(AI 강화)."""
        system = _load_prompt("enhance")
        hint = f"\n\n(figure_type hint: {figure_type})" if figure_type else ""
        try:
            res = await self.llm.complete_structured(
                [user(f"{text}{hint}")], EnhancePromptResponse, system=system)
        except Exception:  # noqa: BLE001
            return text
        return (res.prompt or text).strip()

    async def describe_reference(self, image: bytes, mime: str = "image/png") -> RefStyleReport:
        system = (
            "Analyze this reference figure's visual style. Return RefStyleReport JSON: "
            "palette_hex (3-6 dominant hex colors), density, layout_pattern, font_feel."
        )
        return await self.llm.complete_structured(
            [user("Describe the style.", images=[ImageInput(mime=mime, data=image)])],
            RefStyleReport, system=system)
