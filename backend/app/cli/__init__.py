"""Figment in-process terminal CLI — drive the whole studio from the shell, no server needed.

Entry point: `python -m app.cli ...` (wrapper: `scripts/figment`). See app.build_parser for the
subcommands (generate, enhance, upscale/removebg/whitebg, export, chat, models, projects, doctor,
verify). Each reuses the backend's worker/pipeline/registry/DB in-process.
"""
from app.cli.app import __version__, main

__all__ = ["main", "__version__"]
