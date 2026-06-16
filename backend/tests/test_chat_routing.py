"""Chat LLM provider routing — the picker's llm_model id selects the chat backend.

Key presence is monkeypatched so the test is independent of whether the dev `.env` has an
OpenRouter key: cloud LLMs route to OpenRouter when a key exists and degrade to the local
Ollama default when it doesn't; local LLMs map to their Ollama tag; unknown/None → default.
"""
import app.llm.routing as routing
from app.llm.routing import resolve_chat as _resolve_chat


class _FakeSettings:
    def __init__(self, has: bool):
        self._has = has

    def has_key(self, provider: str) -> bool:
        return self._has


def _patch_key(monkeypatch, present: bool):
    monkeypatch.setattr(routing, "figure_settings", lambda: _FakeSettings(present))


def test_local_llm_maps_to_ollama_tag(monkeypatch):
    _patch_key(monkeypatch, True)  # key state irrelevant for local
    provider, model = _resolve_chat("qwen-9b-local")
    assert provider == "ollama"
    assert model == "hf.co/HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive:Q4_K_M"


def test_cloud_llm_with_key_routes_to_openrouter(monkeypatch):
    _patch_key(monkeypatch, True)
    assert _resolve_chat("qwen3-plus") == ("openrouter", "qwen/qwen3.7-plus")


def test_cloud_llm_without_key_falls_back_to_default_ollama(monkeypatch):
    _patch_key(monkeypatch, False)
    assert _resolve_chat("qwen3-plus") == ("ollama", None)


def test_none_uses_default_ollama(monkeypatch):
    _patch_key(monkeypatch, True)
    assert _resolve_chat(None) == ("ollama", None)


def test_unknown_id_uses_default_ollama(monkeypatch):
    _patch_key(monkeypatch, True)
    assert _resolve_chat("does-not-exist") == ("ollama", None)
