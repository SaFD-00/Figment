"""대화형 계획 확정 — POST /api/projects/{pid}/plan (동기, 잡 아님).

프론트가 대화 히스토리를 보유하고 매 턴 전체를 보낸다(stateless). 충분히 합의되면
PlanTurn.ready=true + PlanBrief를 반환하고, 프론트는 그 계획으로 기존 /jobs를 호출한다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ...config import get_settings
from ...jobs.models import ModelPrefs
from ...pipeline.orchestrator import research_context
from ...pipeline.planner import ChatMessage, Planner, PlanTurn
from ...providers.registry import get_llm
from ...schema.figure_spec import FigureType

router = APIRouter(prefix="/api")


class PlanChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    messages: list[ChatMessage] = Field(default_factory=list)
    data_file_ids: list[str] = Field(default_factory=list)
    reference_image_ids: list[str] = Field(default_factory=list)
    paper_text: str | None = None  # 논문 method 원문(ContentPlan 분해 트리거)
    style_preset: str = "nature_minimal"
    research: bool = False
    model_prefs: ModelPrefs = Field(default_factory=ModelPrefs)


class EnhancePromptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str
    figure_type: FigureType | None = None
    model_prefs: ModelPrefs = Field(default_factory=ModelPrefs)


class EnhancePromptResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str


def _store(request: Request):
    return request.app.state.store


@router.post("/projects/{pid}/plan", response_model=PlanTurn)
async def plan_chat(pid: str, body: PlanChatRequest, request: Request) -> PlanTurn:
    store = _store(request)
    if store.load_project(pid) is None:
        raise HTTPException(404, "프로젝트 없음")
    if not body.messages:
        raise HTTPException(400, "메시지가 필요합니다")

    settings = get_settings()
    provider = body.model_prefs.provider
    planner = Planner(
        get_llm("planner", settings, provider_override=provider),
        get_llm("classifier", settings, provider_override=provider))
    note = _attachments_note(store, body)
    research_ctx = ""
    if body.research:
        last_user = next((m.content for m in reversed(body.messages) if m.role == "user"), "")
        research_ctx = await research_context(last_user, provider, settings)
    return await planner.converse(
        body.messages, attachments_note=note,
        research_ctx=research_ctx, paper_text=body.paper_text)


@router.post("/projects/{pid}/enhance-prompt", response_model=EnhancePromptResponse)
async def enhance_prompt(
    pid: str, body: EnhancePromptRequest, request: Request
) -> EnhancePromptResponse:
    store = _store(request)
    if store.load_project(pid) is None:
        raise HTTPException(404, "프로젝트 없음")
    if not body.prompt.strip():
        raise HTTPException(400, "프롬프트가 필요합니다")
    settings = get_settings()
    provider = body.model_prefs.provider
    planner = Planner(get_llm("planner", settings, provider_override=provider))
    enhanced = await planner.enhance_prompt(body.prompt, body.figure_type)
    return EnhancePromptResponse(prompt=enhanced)


def _attachments_note(store, body: PlanChatRequest) -> str:
    """첨부 파일명/이미지 유무를 대화 컨텍스트에 명시(용도 분기 유도)."""
    parts: list[str] = []
    names = []
    for fid in body.data_file_ids:
        p = store.resolve_input(fid)
        if p:
            names.append(p.name)
    if names:
        parts.append(f"데이터 파일(CSV/JSON, 차트용) {len(names)}개: {', '.join(names[:5])}")
    if body.reference_image_ids:
        parts.append(
            f"이미지 {len(body.reference_image_ids)}개 첨부됨 — 용도 확인 필요"
            "(스타일 참조 / 손스케치 / 기존 figure 정제·벡터화 중 무엇인지).")
    return "\n".join(parts)
