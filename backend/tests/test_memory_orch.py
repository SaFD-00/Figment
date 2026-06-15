"""Memory orchestrator downshift + unload decisions (no real ComfyUI/Ollama)."""
import pytest

from app.models_catalog.registry import MODELS
from app.orchestrator.memory import MemoryOrchestrator


class FakeComfy:
    def __init__(self): self.freed = 0
    async def free(self, **kw): self.freed += 1


class FakeOllama:
    def __init__(self): self.unloaded = 0; self.warmed = 0
    async def unload(self, *a, **k): self.unloaded += 1
    async def warm(self, *a, **k): self.warmed += 1


def make():
    return MemoryOrchestrator(FakeComfy(), FakeOllama())


async def test_unloads_llm_for_heavy_model():
    orch = make()
    orch.budget = 19.0
    orch.llm_gb = 5.0
    # qwen-edit is 13GB; 13 + 5 = 18 <= 19 → actually fits; use a heavier scenario
    orch.budget = 16.0
    await orch.ensure_ready_for(MODELS["qwen-edit"])   # 13 + 5 = 18 > 16 → unload
    assert orch.ollama.unloaded == 1
    assert orch.ledger.llm_loaded is False


async def test_keeps_llm_for_light_model():
    orch = make()
    orch.budget = 19.0
    orch.llm_gb = 5.0
    await orch.ensure_ready_for(MODELS["z-image"])     # 4 + 5 = 9 <= 19 → keep
    assert orch.ollama.unloaded == 0
    assert orch.ledger.llm_loaded is True


async def test_frees_comfy_on_family_switch():
    orch = make()
    orch.ledger.comfy_family = "sdxl"
    await orch.ensure_ready_for(MODELS["chroma-hd"])   # chroma family differs from sdxl
    assert orch.comfy.freed == 1
    assert orch.ledger.comfy_family == "chroma"


async def test_downshift_when_over_budget():
    orch = make()
    orch.budget = 8.0                                  # tiny budget
    chosen = await orch.ensure_ready_for(MODELS["chroma-hd"])  # 10GB > 8 → downshift to z-image (4GB)
    assert chosen.id == "z-image"
