"""Central settings.

All runtime artifacts (models, ComfyUI, SQLite DB, logs, generated outputs) live under
AISTUDIO_HOME, which defaults to the repo's own `AIStudio/` folder so everything is
self-contained in the project. Override via AISTUDIO_HOME in .env.

NOTE: per AGENTS.md, <repo>/AIStudio is normally a SYMLINK to /data/<user>/Figment/AIStudio so
the multi-GB weights/DB land on the big /data volume, not the (small) root volume. Code paths are
unchanged by the symlink. See .gitignore (AIStudio is ignored) and scripts/00_bootstrap_dirs.sh.
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

    # Fallback chat/planner LLM when nothing is selected (mirrors .env OLLAMA_LLM and what
    # scripts/21_pull_ollama_models.sh pulls). The UI picker overrides this per turn. The chat/
    # planner LLM lineup is vision-capable only, so the local default is the multimodal qwen3-vl.
    ollama_llm: str = "huihui_ai/qwen3-vl-abliterated:8b"

    # Memory budget for a single NVIDIA H100 80GB (usable VRAM after CUDA/driver overhead).
    # The photoreal stack co-resides (~70GB), so this rarely triggers a free/unload.
    vram_budget_gb: float = 78.0
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
