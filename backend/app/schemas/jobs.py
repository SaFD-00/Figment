"""Job DTOs and progress events."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from .genspec import GenSpec

JobStatus = Literal["queued", "running", "done", "error", "canceled"]


class JobCreate(BaseModel):
    project_id: str
    genspec: GenSpec


class JobOut(BaseModel):
    id: str
    project_id: str
    mode: str
    status: JobStatus
    progress: float = 0.0
    result_asset: Optional[str] = None
    error: Optional[str] = None
    created_at: float
    updated_at: float


class ProgressEvent(BaseModel):
    """Streamed to the browser over SSE."""
    type: Literal["queued", "progress", "preview", "done", "error", "log"]
    job_id: str
    progress: float = 0.0           # 0..1
    step: Optional[int] = None
    total: Optional[int] = None
    node: Optional[str] = None      # human label of the executing node
    preview_b64: Optional[str] = None
    result_asset: Optional[str] = None
    message: Optional[str] = None
