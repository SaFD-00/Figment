"""Typed query helpers (raw SQL, no ORM)."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Optional

from app.db.database import db


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def now() -> float:
    return time.time()


# ── projects ──────────────────────────────────────────────────────────────────
async def create_project(title: str) -> dict:
    pid = _id("p")
    t = now()
    await db().execute(
        "INSERT INTO projects(id,title,cover_asset,created_at,updated_at) VALUES(?,?,?,?,?)",
        (pid, title, None, t, t),
    )
    await db().commit()
    return {"id": pid, "title": title, "cover_asset": None, "created_at": t, "updated_at": t}


async def list_projects() -> list[dict]:
    cur = await db().execute("SELECT * FROM projects ORDER BY updated_at DESC")
    return [dict(r) for r in await cur.fetchall()]


async def get_project(pid: str) -> Optional[dict]:
    cur = await db().execute("SELECT * FROM projects WHERE id=?", (pid,))
    r = await cur.fetchone()
    return dict(r) if r else None


async def touch_project(pid: str, cover_asset: Optional[str] = None) -> None:
    if cover_asset:
        await db().execute(
            "UPDATE projects SET updated_at=?, cover_asset=COALESCE(cover_asset,?) WHERE id=?",
            (now(), cover_asset, pid),
        )
    else:
        await db().execute("UPDATE projects SET updated_at=? WHERE id=?", (now(), pid))
    await db().commit()


async def rename_project(pid: str, title: str) -> None:
    await db().execute("UPDATE projects SET title=?, updated_at=? WHERE id=?", (title, now(), pid))
    await db().commit()


async def delete_project(pid: str) -> None:
    await db().execute("DELETE FROM projects WHERE id=?", (pid,))
    await db().commit()


# ── assets ────────────────────────────────────────────────────────────────────
async def create_asset(project_id: str, kind: str, path: str, width: int | None = None,
                       height: int | None = None, parent_id: str | None = None,
                       meta: dict | None = None) -> dict:
    aid = _id("ast")
    t = now()
    await db().execute(
        "INSERT INTO assets(id,project_id,kind,path,width,height,parent_id,meta,created_at)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (aid, project_id, kind, path, width, height, parent_id, json.dumps(meta or {}), t),
    )
    await db().commit()
    return {"id": aid, "project_id": project_id, "kind": kind, "path": path,
            "width": width, "height": height, "parent_id": parent_id, "meta": meta or {}, "created_at": t}


async def get_asset(aid: str) -> Optional[dict]:
    cur = await db().execute("SELECT * FROM assets WHERE id=?", (aid,))
    r = await cur.fetchone()
    if not r:
        return None
    d = dict(r)
    d["meta"] = json.loads(d.get("meta") or "{}")
    return d


async def list_assets(project_id: str) -> list[dict]:
    cur = await db().execute("SELECT * FROM assets WHERE project_id=? ORDER BY created_at", (project_id,))
    out = []
    for r in await cur.fetchall():
        d = dict(r)
        d["meta"] = json.loads(d.get("meta") or "{}")
        out.append(d)
    return out


# ── messages ──────────────────────────────────────────────────────────────────
async def add_message(project_id: str, role: str, content: str, genspec: dict | None = None) -> dict:
    mid = _id("m")
    t = now()
    await db().execute(
        "INSERT INTO messages(id,project_id,role,content,genspec,created_at) VALUES(?,?,?,?,?,?)",
        (mid, project_id, role, content, json.dumps(genspec) if genspec else None, t),
    )
    await db().commit()
    return {"id": mid, "project_id": project_id, "role": role, "content": content,
            "genspec": genspec, "created_at": t}


async def list_messages(project_id: str) -> list[dict]:
    cur = await db().execute("SELECT * FROM messages WHERE project_id=? ORDER BY created_at", (project_id,))
    out = []
    for r in await cur.fetchall():
        d = dict(r)
        d["genspec"] = json.loads(d["genspec"]) if d.get("genspec") else None
        out.append(d)
    return out


# ── jobs ──────────────────────────────────────────────────────────────────────
async def create_job(project_id: str, mode: str, genspec: dict) -> dict:
    jid = _id("job")
    t = now()
    await db().execute(
        "INSERT INTO jobs(id,project_id,mode,genspec,status,progress,created_at,updated_at)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (jid, project_id, mode, json.dumps(genspec), "queued", 0.0, t, t),
    )
    await db().commit()
    return await get_job(jid)  # type: ignore[return-value]


async def get_job(jid: str) -> Optional[dict]:
    cur = await db().execute("SELECT * FROM jobs WHERE id=?", (jid,))
    r = await cur.fetchone()
    if not r:
        return None
    d = dict(r)
    d["genspec"] = json.loads(d["genspec"])
    return d


async def update_job(jid: str, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = now()
    cols = ", ".join(f"{k}=?" for k in fields)
    await db().execute(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), jid))
    await db().commit()


# ── model cache ───────────────────────────────────────────────────────────────
async def set_model_ready(model_id: str, file: str, size_bytes: int, ready: bool) -> None:
    await db().execute(
        "INSERT INTO model_cache(model_id,file,size_bytes,ready,updated_at) VALUES(?,?,?,?,?)"
        " ON CONFLICT(model_id) DO UPDATE SET file=excluded.file, size_bytes=excluded.size_bytes,"
        " ready=excluded.ready, updated_at=excluded.updated_at",
        (model_id, file, size_bytes, 1 if ready else 0, now()),
    )
    await db().commit()
