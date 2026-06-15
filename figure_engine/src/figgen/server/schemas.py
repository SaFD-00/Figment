"""API 전송 계층 DTO (FigureSpec과 별개). 요청은 jobs.JobRequest 재사용."""

from __future__ import annotations

from pydantic import BaseModel

from ..jobs.models import JobRecord, JobRequest, StageEvent
from ..jobs.store import ProjectMeta


class FigureTypeInfo(BaseModel):
    id: str
    label: str
    description: str
    needs_data: bool = False


class StyleInfo(BaseModel):
    id: str
    name: str
    palette: list[str]


class ModelInfo(BaseModel):
    id: str
    label: str
    role: str
    disabled: bool = False


class JobSummary(BaseModel):
    job_id: str
    status: str
    created_at: float
    parent_job_id: str | None = None
    task: str = "generate"
    prompt: str = ""
    edit_summary: str | None = None
    error: str | None = None
    thumb_url: str | None = None
    preview_url: str | None = None


class JobDetail(JobSummary):
    project_id: str
    stages: list[StageEvent] = []
    artifacts: dict[str, str] = {}
    request: JobRequest | None = None


class ProjectSummary(BaseModel):
    project_id: str
    name: str
    created_at: float
    version_count: int = 0


class ProjectDetail(ProjectSummary):
    versions: list[JobSummary] = []


class CreateProjectBody(BaseModel):
    name: str = "Untitled"


class RenameProjectBody(BaseModel):
    name: str


def job_summary(rec: JobRecord) -> JobSummary:
    edit = rec.request.edit
    artifacts = rec.artifacts or {}
    has_preview = "preview.png" in artifacts
    return JobSummary(
        job_id=rec.job_id,
        status=rec.status.value,
        created_at=rec.created_at,
        parent_job_id=rec.parent_job_id,
        task=rec.request.task,
        prompt=rec.request.prompt,
        edit_summary=(edit.instruction if edit else None),
        error=rec.error,
        thumb_url=f"/api/jobs/{rec.job_id}/files/preview.png" if has_preview else None,
        preview_url=f"/api/jobs/{rec.job_id}/preview.svg" if has_preview else None,
    )


def job_detail(rec: JobRecord) -> JobDetail:
    base = job_summary(rec)
    artifacts = {name: f"/api/jobs/{rec.job_id}/files/{name}" for name in (rec.artifacts or {})}
    return JobDetail(
        **base.model_dump(), project_id=rec.project_id, stages=rec.stages,
        artifacts=artifacts, request=rec.request)


def project_detail(meta: ProjectMeta, jobs: list[JobRecord]) -> ProjectDetail:
    return ProjectDetail(
        project_id=meta.project_id, name=meta.name, created_at=meta.created_at,
        version_count=len(jobs), versions=[job_summary(j) for j in jobs])
