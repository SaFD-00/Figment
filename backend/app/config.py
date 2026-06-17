"""Central settings.

All runtime artifacts (models, ComfyUI, SQLite DB, logs, generated outputs) live under
AISTUDIO_HOME, which defaults to the repo's own `AIStudio/` folder so everything is
self-contained in the project. Override via AISTUDIO_HOME in .env.

NOTE: this repo lives inside Google Drive; keeping AIStudio/ here means Drive will sync the
model weights and DB. That is the user's chosen layout — see .gitignore (AIStudio/ is ignored
from git) and the README note about excluding it from Drive sync if churn becomes an issue.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = .../ImgGen  (this file is backend/app/config.py)
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Read the repo-root .env (same file the scripts use), regardless of process cwd.
    model_config = SettingsConfigDict(env_file=str(REPO_ROOT / ".env"), extra="ignore")

    # Single runtime home for everything. Defaults to <repo>/AIStudio.
    aistudio_home: Path = REPO_ROOT / "AIStudio"
    comfy_url: str = "http://127.0.0.1:8188"
    ollama_url: str = "http://127.0.0.1:11434"
    backend_port: int = 8000

    ollama_llm: str = "huihui_ai/gemma-4-abliterated:e4b"

    # Memory budget for the 24GB M4 Pro (usable unified memory for ML after OS overhead)
    vram_budget_gb: float = 19.0
    llm_resident_gb: float = 5.0

    @property
    def outputs_dir(self) -> Path:
        return self.aistudio_home / "outputs"

    @property
    def logs_dir(self) -> Path:
        return self.aistudio_home / "logs"

    @property
    def models_dir(self) -> Path:
        return self.aistudio_home / "models"

    @property
    def db_path(self) -> Path:
        return self.aistudio_home / "db.sqlite"

    def ensure_dirs(self) -> None:
        for d in (self.aistudio_home, self.outputs_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
