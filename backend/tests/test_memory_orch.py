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
    await orch.ensure_ready_for(MODELS["pony-v6"])     # 7 + 5 = 12 <= 19 → keep
    assert orch.ollama.unloaded == 0
    assert orch.ledger.llm_loaded is True


async def test_frees_comfy_on_family_switch():
    orch = make()
    orch.ledger.comfy_family = "qwen-image"
    await orch.ensure_ready_for(MODELS["pony-v6"])     # sdxl family differs from qwen-image
    assert orch.comfy.freed == 1
    assert orch.ledger.comfy_family == "sdxl"


async def test_no_downshift_without_equivalent():
    # LIGHTER_EQUIVALENT is empty in the trimmed lineup, so an over-budget model has no
    # lighter stand-in → downshift() returns the original model unchanged.
    orch = make()
    orch.budget = 4.0                                  # tiny budget (pony-v6 is 7GB)
    chosen = await orch.ensure_ready_for(MODELS["pony-v6"])
    assert chosen.id == "pony-v6"
