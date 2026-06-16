"""job 도메인 모델 / 이벤트 정의 (웹 API 경계와 공유하는 전송 계층 포함)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..schema.figure_spec import FigureType
from ..schema.requests import EditDirective


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Stage(StrEnum):
    PLANNING = "planning"
    STYLING = "styling"
    ASSETS = "assets"
    RENDERING = "rendering"
    CRITIC = "critic"
    FINALIZING = "finalizing"


STAGE_ORDER = [
    Stage.PLANNING, Stage.STYLING, Stage.ASSETS, Stage.RENDERING, Stage.CRITIC, Stage.FINALIZING
]


class ModelPrefs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["mock", "openrouter", "auto"] = "auto"
    planner: str | None = None
    imager: str | None = None
    critic: str | None = None
    max_critic_rounds: int = 2


# figurelabs surface별 job 종류. generate=텍스트→figure(기본), edit=부분 재생성,
# sketch=스케치→정제 figure, refine=업스케일/색보정/노이즈제거, vectorize=PNG→SVG.
JobTask = Literal["generate", "edit", "sketch", "refine", "vectorize"]


class CanvasOp(BaseModel):
    """figurelabs 인-캔버스 편집 도구 (task='edit'와 함께, parent_job_id 필요).

    - region_redraw: 선택 이미지 요소의 영역(region: [x,y,w,h] 0..1)을 마스크 인페인트로 재생성.
    - text_edit: 라벨/텍스트를 결정론적으로 교체(LLM 없음).
    - white_bg: 배경을 흰색으로 정리.
    - upscale: 선택 이미지 요소를 고해상도/선명화.
    """

    model_config = ConfigDict(extra="forbid")
    kind: Literal["region_redraw", "text_edit", "white_bg", "upscale"]
    target_element_id: str
    instruction: str = ""  # region_redraw 프롬프트
    text: str | None = None  # text_edit 새 텍스트
    region: list[float] | None = None  # region_redraw 마스크 [x, y, w, h] (0..1)


class JobRequest(BaseModel):
    """전송 계층 생성/수정 요청 (신규 생성과 부분 재생성·신규 surface 통합)."""

    model_config = ConfigDict(extra="forbid")
    task: JobTask = "generate"
    figure_type: FigureType | None = None
    prompt: str = ""
    paper_text: str | None = None
    style_preset: str = "nature_minimal"
    palette: list[str] = Field(default_factory=list)  # 수동 색 팔레트(비면 프리셋)
    aspect: Literal["wide", "square", "tall"] | None = None  # 이미지-우선 종횡비
    research: bool = False  # 웹검색 그라운딩 토글
    model_prefs: ModelPrefs = Field(default_factory=ModelPrefs)
    data_file_ids: list[str] = Field(default_factory=list)
    reference_image_ids: list[str] = Field(default_factory=list)
    parent_job_id: str | None = None
    edit: EditDirective | None = None
    canvas_op: CanvasOp | None = None  # 인-캔버스 도구(task='edit')
    refine_modes: list[Literal["upscale", "white_bg", "denoise", "color_correct"]] = Field(
        default_factory=list
    )  # task='refine' 전용


class StageEvent(BaseModel):
    seq: int = 0
    job_id: str = ""
    type: Literal["stage", "log", "preview", "done", "error"] = "log"
    stage: Stage | None = None
    status: Literal["started", "progress", "completed"] | None = None
    message: str = ""
    progress: float | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    ts: float = 0.0


class JobRecord(BaseModel):
    job_id: str
    project_id: str
    status: JobStatus = JobStatus.QUEUED
    request: JobRequest
    parent_job_id: str | None = None
    created_at: float = 0.0
    finished_at: float | None = None
    stages: list[StageEvent] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)
    error: str | None = None
