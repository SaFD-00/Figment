"""파이프라인 입출력 DTO (웹앱 API 경계와 공유하는 코어 모델)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ._types import ElementId
from .figure_spec import FigureSpec, FigureType


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str
    paper_text: str | None = None  # 메서드 섹션 원문 (2단계 플래닝 트리거)
    figure_type: FigureType | None = None  # None이면 자동 분류
    style_preset: str = "nature_minimal"
    palette: list[str] = Field(default_factory=list)  # 수동 색 팔레트(비면 프리셋 사용)
    aspect: Literal["wide", "square", "tall"] | None = None  # 이미지-우선 종횡비 오버라이드
    provider: Literal["mock", "openrouter", "auto"] = "auto"
    max_critic_iters: int = 2
    research: bool = False  # 생성 전 웹검색 그라운딩(OpenRouter ':online') on/off
    data_refs: dict[str, str] = Field(default_factory=dict)  # data_ref → 파일 경로(차트용)
    reference_image_path: str | None = None


class EditDirective(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["element", "global"] = "element"
    instruction: str
    target_element_ids: list[ElementId] = Field(default_factory=list)


class GenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spec: FigureSpec
    svg: str
    pptx_path: str | None = None
    png_path: str | None = None
    warnings: list[str] = Field(default_factory=list)
    critic_notes: list[str] = Field(default_factory=list)
