"""Memory orchestrator decisions on the H100 80GB budget (no real ComfyUI/Ollama).

Co-residency: at the 78GB budget the photoreal stack co-fits, so a family switch does NOT free
ComfyUI; freeing/unloading only kicks in under (artificially lowered) budget pressure.
"""
from app.models_catalog.registry import MODELS
from app.orchestrator.memory import MemoryOrchestrator


class FakeComfy:
    def __init__(self): self.freed = 0
    async def free(self, **kw): self.freed += 1


class FakeOllama:
    def __init__(self): self.unloaded = self.warmed = 0
    async def unload(self, *a, **k): self.unloaded += 1
    async def warm(self, *a, **k): self.warmed += 1


def make():
    return MemoryOrchestrator(FakeComfy(), FakeOllama())


async def test_unloads_llm_for_heavy_model():
    orch = make()
    orch.budget = 32.0
    orch.llm_gb = 5.0
    # qwen-edit-aio is 29GB; 29 + 5 = 34 > 32 → unload the LLM
    await orch.ensure_ready_for(MODELS["qwen-edit-aio"])
    assert orch.ollama.unloaded == 1
    assert orch.ledger.llm_loaded is False


async def test_keeps_llm_for_light_model():
    orch = make()
    orch.budget = 19.0
    orch.llm_gb = 5.0
    await orch.ensure_ready_for(MODELS["lustify"])     # 8 + 5 = 13 <= 19 → keep
    assert orch.ollama.unloaded == 0
    assert orch.ledger.llm_loaded is True


async def test_coresident_no_free_on_family_switch():
    orch = make()
    orch.budget = 78.0
    orch.ledger.comfy_family = "sdxl"
    await orch.ensure_ready_for(MODELS["chroma-hd"])   # 8 + 15 + 6.5 << 78 → co-resident, no free
    assert orch.comfy.freed == 0
    assert orch.ledger.comfy_family == "chroma"


async def test_frees_comfy_under_budget_pressure():
    orch = make()
    orch.budget = 16.0                                 # artificially tiny → forces a free
    orch.ledger.llm_loaded = False
    orch.ledger.comfy_family = "sdxl"                  # resident ~8GB
    await orch.ensure_ready_for(MODELS["chroma-hd"])   # 8 + 15 > 16 → free the old family
    assert orch.comfy.freed == 1
    assert orch.ledger.comfy_family == "chroma"


async def test_no_downshift_without_equivalent():
    orch = make()
    orch.budget = 8.0                                  # below chroma's 15GB
    # LIGHTER_EQUIVALENT is empty on H100 → model returned unchanged (no downshift)
    chosen = await orch.ensure_ready_for(MODELS["chroma-hd"])
    assert chosen.id == "chroma-hd"
