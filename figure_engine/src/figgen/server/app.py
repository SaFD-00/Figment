"""FastAPI 앱 팩토리 + lifespan + 정적 파일 마운트."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ..config import get_settings
from ..jobs.manager import JobManager
from ..jobs.store import FileStore
from ..pipeline.orchestrator import Orchestrator
from .routes import files, jobs, meta, plan, projects


def _frontend_dir() -> Path:
    env = os.environ.get("FIGGEN_FRONTEND")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "frontend"


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings = get_settings()
        store = FileStore(settings.resolved_outputs_dir())
        recovered = store.recover_interrupted_jobs()
        if recovered:
            print(f"· 중단된 job {recovered}건을 failed로 복구")
        orch = Orchestrator(settings, store, critic_enabled=settings.critic_enabled)
        app.state.store = store
        app.state.job_manager = JobManager(store, orch,
                                            max_concurrent=settings.max_concurrent_jobs)
        # 기본 프로젝트 보장
        if not store.list_projects():
            store.create_project("My Figures")
        yield
        await app.state.job_manager.shutdown()

    app = FastAPI(title="FigGen", lifespan=lifespan)

    @app.middleware("http")
    async def _no_cache_frontend(request, call_next):
        # 로컬 개발 도구 — 프론트 정적 파일(JS/CSS/HTML)을 브라우저가 캐시해
        # 구버전을 띄우지 않도록 항상 재검증. (/api 응답은 영향 없음)
        resp = await call_next(request)
        if not request.url.path.startswith("/api"):
            resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp

    for r in (meta.router, projects.router, jobs.router, files.router, plan.router):
        app.include_router(r)

    fe = _frontend_dir()
    if fe.exists():
        app.mount("/", StaticFiles(directory=str(fe), html=True), name="frontend")
    return app
