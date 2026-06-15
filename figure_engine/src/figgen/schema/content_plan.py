"""2단계 플래닝용 중간 표현 — 장문(논문 메서드 등)에서 엔티티+관계만 먼저 추출.

장문→복잡 스키마 직행은 누락·환각이 잦아, 내용 추출과 레이아웃 결정을 분리한다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Entity(_Base):
    name: str
    kind: Literal["module", "data", "operation", "loss"]
    description: str = ""


class Relation(_Base):
    source: str  # Entity.name
    target: str
    kind: Literal["flow", "feedback", "contains"]
    label: str | None = None


class ContentPlan(_Base):
    entities: list[Entity]
    relations: list[Relation]
    narrative: str = ""
