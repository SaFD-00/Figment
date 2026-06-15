"""Projects CRUD + per-project messages/assets listing."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import repo

router = APIRouter(prefix="/projects", tags=["projects"])


class CreateProject(BaseModel):
    title: str = "Untitled"


class RenameProject(BaseModel):
    title: str


@router.post("")
async def create(req: CreateProject) -> dict:
    return await repo.create_project(req.title)


@router.get("")
async def list_all() -> list[dict]:
    return await repo.list_projects()


@router.get("/{pid}")
async def get(pid: str) -> dict:
    p = await repo.get_project(pid)
    if not p:
        raise HTTPException(404, "not found")
    return p


@router.patch("/{pid}")
async def rename(pid: str, req: RenameProject) -> dict:
    await repo.rename_project(pid, req.title)
    return await repo.get_project(pid)  # type: ignore[return-value]


@router.delete("/{pid}")
async def delete(pid: str) -> dict:
    await repo.delete_project(pid)
    return {"ok": True}


@router.get("/{pid}/messages")
async def messages(pid: str) -> list[dict]:
    return await repo.list_messages(pid)


@router.get("/{pid}/assets")
async def assets(pid: str) -> list[dict]:
    return await repo.list_assets(pid)
