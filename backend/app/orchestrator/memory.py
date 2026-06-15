"""Memory orchestrator for the 24GB unified-memory ceiling.

Enforces "one big model at a time": frees ComfyUI's resident model when the family changes,
unloads the chat LLM before a heavy generation if they wouldn't co-fit, and downshifts to a
lighter equivalent model when even a single model would exceed budget.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.comfy.client import ComfyUIClient
from app.config import get_settings
from app.llm.ollama_client import OllamaClient
from app.models_catalog.registry import LIGHTER_EQUIVALENT, MODELS, ModelDef

log = logging.getLogger("imggen.memory")


@dataclass
class Ledger:
    llm_loaded: bool = True
    comfy_family: str | None = None


class MemoryOrchestrator:
    def __init__(self, comfy: ComfyUIClient, ollama: OllamaClient):
        self.comfy = comfy
        self.ollama = ollama
        s = get_settings()
        self.budget = s.vram_budget_gb
        self.llm_gb = s.llm_resident_gb
        self.ledger = Ledger()

    def downshift(self, model: ModelDef) -> ModelDef:
        """If a model alone exceeds budget, swap to a lighter equivalent when one exists."""
        if model.vram_gb <= self.budget:
            return model
        alt = LIGHTER_EQUIVALENT.get(model.id)
        if alt and MODELS[alt].vram_gb <= self.budget:
            log.warning("downshift %s -> %s (%.0fGB > %.0fGB budget)", model.id, alt, model.vram_gb, self.budget)
            return MODELS[alt]
        return model

    async def ensure_ready_for(self, model: ModelDef) -> ModelDef:
        model = self.downshift(model)

        # 1) Different big model resident in ComfyUI? free it.
        if self.ledger.comfy_family not in (None, model.family):
            log.info("freeing ComfyUI (family %s -> %s)", self.ledger.comfy_family, model.family)
            await self.comfy.free(unload_models=True, free_memory=True)
            self.ledger.comfy_family = None

        # 2) model + LLM over budget? unload the LLM.
        if self.ledger.llm_loaded and (model.vram_gb + self.llm_gb) > self.budget:
            log.info("unloading LLM (%.0f + %.0f > %.0f)", model.vram_gb, self.llm_gb, self.budget)
            await self.ollama.unload()
            self.ledger.llm_loaded = False

        # 3) ComfyUI lazy-loads the unet on /prompt; just record intended family.
        self.ledger.comfy_family = model.family
        return model

    async def after_job(self, next_family: str | None = None) -> None:
        """Free ComfyUI between heavy jobs of different families; re-warm LLM when it fits."""
        if next_family is not None and next_family != self.ledger.comfy_family:
            await self.comfy.free(unload_models=True)
            self.ledger.comfy_family = None
        # Re-warm the LLM when nothing huge is resident.
        resident = MODELS_resident_gb(self.ledger.comfy_family)
        if not self.ledger.llm_loaded and (resident + self.llm_gb) <= self.budget:
            await self.ollama.warm()
            self.ledger.llm_loaded = True


def MODELS_resident_gb(family: str | None) -> float:
    if family is None:
        return 0.0
    sizes = [m.vram_gb for m in MODELS.values() if m.family == family]
    return max(sizes) if sizes else 0.0
