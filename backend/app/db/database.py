"""aiosqlite connection management (single-file local DB in WAL mode)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import aiosqlite

from app.config import get_settings

_db: Optional[aiosqlite.Connection] = None


async def init_db() -> aiosqlite.Connection:
    global _db
    if _db is not None:
        return _db
    s = get_settings()
    s.ensure_dirs()
    _db = await aiosqlite.connect(s.db_path)
    _db.row_factory = aiosqlite.Row
    schema = (Path(__file__).parent / "schema.sql").read_text()
    await _db.executescript(schema)
    await _db.commit()
    return _db


def db() -> aiosqlite.Connection:
    if _db is None:
        raise RuntimeError("DB not initialized; call init_db() at startup")
    return _db


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None
