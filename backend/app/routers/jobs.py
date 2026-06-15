"""Jobs: submit a GenSpec, poll status, stream progress (SSE), cancel."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app import deps
from app.db import repo
from app.schemas.jobs import JobCreate

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("")
async def create_job(req: JobCreate) -> dict:
    if not await repo.get_project(req.project_id):
        raise HTTPException(404, "project not found")
    job = await repo.create_job(req.project_id, req.genspec.mode.value, req.genspec.model_dump(mode="json"))
    await deps.worker().submit(job["id"])
    return job


@router.get("/{job_id}")
async def get_job(job_id: str) -> dict:
    job = await repo.get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict:
    deps.worker().cancel(job_id)
    return {"ok": True}


@router.get("/{job_id}/events")
async def job_events(job_id: str):
    async def gen():
        async for ev in deps.worker().events(job_id):
            yield {"event": ev.type, "data": ev.model_dump_json()}
    return EventSourceResponse(gen())
