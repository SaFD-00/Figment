"""Shared DTOs for projects, assets, chat messages."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Project(BaseModel):
    id: str
    title: str
    cover_asset: Optional[str] = None
    created_at: float
    updated_at: float


class Asset(BaseModel):
    id: str
    project_id: str
    kind: str            # source|reference|mask|output|upscaled|nobg
    path: str
    width: Optional[int] = None
    height: Optional[int] = None
    parent_id: Optional[str] = None
    meta: dict = {}
    created_at: float


class ChatMessage(BaseModel):
    id: str
    project_id: str
    role: str            # system|user|assistant
    content: str
    genspec: Optional[dict] = None
    created_at: float
