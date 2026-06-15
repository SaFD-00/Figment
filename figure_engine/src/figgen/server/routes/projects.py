"""프로젝트 CRUD + 입력 파일 업로드."""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile

from ..schemas import (
    CreateProjectBody,
    JobSummary,
    ProjectDetail,
    ProjectSummary,
    RenameProjectBody,
    job_summary,
    project_detail,
)

router = APIRouter(prefix="/api/projects")


def _store(request: Request):
    return request.app.state.store


@router.get("", response_model=list[ProjectSummary])
async def list_projects(request: Request) -> list[ProjectSummary]:
    store = _store(request)
    out = []
    for m in store.list_projects():
        out.append(ProjectSummary(project_id=m.project_id, name=m.name, created_at=m.created_at,
                                  version_count=len(store.list_jobs(m.project_id))))
    return out


@router.post("", response_model=ProjectDetail)
async def create_project(body: CreateProjectBody, request: Request) -> ProjectDetail:
    meta = _store(request).create_project(body.name)
    return project_detail(meta, [])


@router.get("/{pid}", response_model=ProjectDetail)
async def get_project(pid: str, request: Request) -> ProjectDetail:
    store = _store(request)
    meta = store.load_project(pid)
    if meta is None:
        raise HTTPException(404, "프로젝트 없음")
    return project_detail(meta, store.list_jobs(pid))


@router.patch("/{pid}", response_model=ProjectDetail)
async def rename_project(pid: str, body: RenameProjectBody, request: Request) -> ProjectDetail:
    store = _store(request)
    meta = store.rename_project(pid, body.name)
    if meta is None:
        raise HTTPException(404, "프로젝트 없음")
    return project_detail(meta, store.list_jobs(pid))


@router.delete("/{pid}")
async def delete_project(pid: str, request: Request) -> dict:
    return {"deleted": _store(request).delete_project(pid)}


@router.get("/{pid}/versions", response_model=list[JobSummary])
async def versions(pid: str, request: Request) -> list[JobSummary]:
    return [job_summary(j) for j in _store(request).list_jobs(pid)]


@router.post("/{pid}/uploads")
async def upload(pid: str, request: Request, file: UploadFile,
                 kind: str = Form("data")) -> dict:
    store = _store(request)
    if store.load_project(pid) is None:
        raise HTTPException(404, "프로젝트 없음")
    data = await file.read()
    res = store.save_upload(pid, file.filename or "upload.bin", data, kind)
    return res.model_dump()
