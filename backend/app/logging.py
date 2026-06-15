"""Logging setup — console + a rolling file under ~/AIStudio/logs."""
from __future__ import annotations

import logging

from app.config import get_settings


def setup_logging() -> None:
    s = get_settings()
    s.ensure_dirs()
    fmt = "%(asctime)s %(levelname)s %(name)s — %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        handlers.append(logging.FileHandler(s.logs_dir / "backend.log"))
    except Exception:
        pass
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
