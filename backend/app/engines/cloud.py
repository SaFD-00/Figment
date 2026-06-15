"""Cloud engine glue — binds the vendored FigGen (`figgen`) settings to Figment's repo .env
so the cloud LLM/image providers (OpenRouter / OpenAI) share one configuration surface.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from figgen.config import Settings as FigureSettings

# backend/app/engines/cloud.py -> Figment repo root
REPO_ROOT = Path(__file__).resolve().parents[3]


@lru_cache
def figure_settings() -> FigureSettings:
    """A figgen Settings singleton reading the Figment repo-root .env (regardless of cwd)."""
    env = REPO_ROOT / ".env"
    if env.exists():
        return FigureSettings(_env_file=str(env))  # type: ignore[call-arg]
    return FigureSettings()


def cloud_key_present(provider: str) -> bool:
    """True if the API key for an OpenRouter/OpenAI provider is configured."""
    return figure_settings().has_key(provider)
