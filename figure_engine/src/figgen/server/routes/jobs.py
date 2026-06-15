"""job 제출/조회/취소 + SSE 진행 스트림 (신규 생성·부분 재생성 통합)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from ...jobs.models import JobRequest, JobStatus
from ..schemas import job_detail

router = APIRouter(prefix="/api")

_TERMINAL = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}


def _mgr(request: Request):
    return request.app.state.job_manager


def _store(request: Request):
    return request.app.state.store


@router.post("/projects/{pid}/jobs", status_code=202)
async def submit_job(pid: str, body: JobRequest, request: Request) -> JSONResponse:
    store = _store(request)
    if store.load_project(pid) is None:
        raise HTTPException(404, "프로젝트 없음")
    rec = await _mgr(request).submit(pid, body)
    return JSONResponse({"job_id": rec.job_id}, status_code=202)


@router.get("/jobs/{jid}")
async def get_job(jid: str, request: Request):
    rec = _store(request).load_job(jid)
    if rec is None:
        raise HTTPException(404, "job 없음")
    return job_detail(rec)


@router.post("/jobs/{jid}/cancel")
async def cancel_job(jid: str, request: Request) -> dict:
    return {"cancelled": await _mgr(request).cancel(jid)}


@router.get("/jobs/{jid}/spec")
async def get_spec(jid: str, request: Request) -> Response:
    store = _store(request)
    rec = store.load_job(jid)
    if rec is None:
        raise HTTPException(404, "job 없음")
    p = store.job_dir(rec.project_id, jid) / "spec.json"
    if not p.exists():
        raise HTTPException(404, "spec 없음")
    return Response(p.read_text("utf-8"), media_type="application/json")


@router.get("/jobs/{jid}/events")
async def events(jid: str, request: Request):
    store = _store(request)
    mgr = _mgr(request)
    rec = store.load_job(jid)
    if rec is None:
        raise HTTPException(404, "job 없음")
    after = 0
    leid = request.headers.get("Last-Event-ID")
    if leid and leid.isdigit():
        after = int(leid)

    async def gen():
        seen: set[int] = set()
        for ev in store.load_events(jid, after):
            seen.add(ev.seq)
            yield ServerSentEvent(id=str(ev.seq), event=ev.type, data=ev.model_dump_json())
        cur = store.load_job(jid)
        if cur and (cur.status not in _TERMINAL or mgr.is_active(jid)):
            async for ev in mgr.subscribe(jid):
                if ev.seq in seen:
                    continue
                yield ServerSentEvent(id=str(ev.seq), event=ev.type, data=ev.model_dump_json())

    return EventSourceResponse(gen())
