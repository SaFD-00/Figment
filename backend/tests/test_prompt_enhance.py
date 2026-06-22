"""Prompt-enhance endpoint + message builder.

The endpoint reuses the shared LLM routing (covered by test_chat_routing). Here we check the
tag-vs-natural-language hint selection, the output cleaner, and the endpoint's accumulate/clean
behaviour with a fake token stream (no network)."""
import base64
import io

import pytest
from fastapi import HTTPException
from PIL import Image

import app.routers.prompt as promptmod
from app.llm.prompts import build_enhance_messages
from app.routers.prompt import EnhanceRequest, _clean, enhance


def _system(msgs: list[dict]) -> str:
    return next(m["content"] for m in msgs if m["role"] == "system")


def _png_data_url() -> str:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 20, 30)).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


# ── message builder ──────────────────────────────────────────────────────────

def test_build_enhance_messages_tag_vs_nl():
    # Local SDXL (tag-trained) → comma tag hint
    assert "comma-separated tags" in _system(build_enhance_messages("a cat", "lustify"))
    # cloud / unknown / None → natural-language hint
    assert "natural language" in _system(build_enhance_messages("a cat", "gpt-image-2"))
    assert "natural language" in _system(build_enhance_messages("a cat", "gemini-pro-image"))
    assert "natural language" in _system(build_enhance_messages("a cat", None))


def test_enhance_system_prompt_is_output_only():
    # The enhance prompt (not the chat refiner): instructs output-only, forbids the GENSPEC block.
    sys = _system(build_enhance_messages("a cat", "lustify"))
    assert "Output ONLY the rewritten prompt text" in sys
    assert "GENSPEC JSON SHAPE" not in sys  # the refiner's section header — must NOT appear here
    assert "rewrite" in sys.lower()


def test_build_enhance_messages_weaves_instruction():
    msgs = build_enhance_messages("a cat", "lustify", instruction="more cinematic")
    user = msgs[-1]["content"]
    assert isinstance(user, str)  # no image → plain string content
    assert "How to enhance: more cinematic" in user


def test_build_enhance_messages_attaches_image_as_multimodal():
    url = "data:image/png;base64,AAAA"
    msgs = build_enhance_messages("a cat", "lustify", image_url=url)
    content = msgs[-1]["content"]
    assert isinstance(content, list)  # OpenAI-style multimodal parts
    assert content[0]["type"] == "text"
    assert content[1] == {"type": "image_url", "image_url": {"url": url}}


# ── output cleaner ───────────────────────────────────────────────────────────

def test_clean_strips_think_block():
    assert _clean("<think>let me reason</think>a ginger cat") == "a ginger cat"


def test_clean_strips_wrapping_quotes_and_label():
    assert _clean('"a ginger cat"') == "a ginger cat"
    assert _clean("`a ginger cat`") == "a ginger cat"
    assert _clean("Enhanced prompt: a ginger cat") == "a ginger cat"
    assert _clean("Prompt: a ginger cat") == "a ginger cat"


# ── endpoint ─────────────────────────────────────────────────────────────────

def _recording_stream(tokens: list[str], captured: dict):
    async def gen(messages, llm_model):
        captured["messages"] = messages
        captured["llm_model"] = llm_model
        for t in tokens:
            yield t
    return gen


async def test_enhance_returns_joined_prompt(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        promptmod, "chat_stream",
        _recording_stream(["a photorealistic ", "ginger cat on a ", "sunlit windowsill"], captured),
    )
    res = await enhance(EnhanceRequest(prompt="고양이", image_model="lustify", llm_model="qwen3-vl-local"))
    assert res.prompt == "a photorealistic ginger cat on a sunlit windowsill"
    # routed via the enhance system prompt (not the chat refiner) and forwarded the picker LLM id
    assert "Output ONLY the rewritten prompt text" in _system(captured["messages"])
    assert captured["llm_model"] == "qwen3-vl-local"


async def test_enhance_cleans_stream(monkeypatch):
    monkeypatch.setattr(
        promptmod, "chat_stream",
        _recording_stream(["<think>plan</think>", '"a tidy cat"'], {}),
    )
    res = await enhance(EnhanceRequest(prompt="cat"))
    assert res.prompt == "a tidy cat"


async def test_enhance_empty_prompt_raises_400():
    with pytest.raises(HTTPException) as ei:
        await enhance(EnhanceRequest(prompt="   "))
    assert ei.value.status_code == 400


async def test_enhance_empty_result_raises_502(monkeypatch):
    monkeypatch.setattr(
        promptmod, "chat_stream",
        _recording_stream(["<think>only thinking, no answer</think>"], {}),
    )
    with pytest.raises(HTTPException) as ei:
        await enhance(EnhanceRequest(prompt="cat"))
    assert ei.value.status_code == 502


async def test_enhance_attaches_image_for_vision_cloud_llm(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(promptmod, "chat_stream", _recording_stream(["x"], captured))
    # gemini-2.5-flash is a cloud vision model → image is normalized and attached
    await enhance(EnhanceRequest(prompt="cat", llm_model="gemini-2.5-flash", image=_png_data_url()))
    assert isinstance(captured["messages"][-1]["content"], list)  # multimodal attached


async def test_enhance_attaches_image_for_vision_local_llm(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(promptmod, "chat_stream", _recording_stream(["x"], captured))
    # qwen3-vl-local is a LOCAL vision model → image attached too (gated on vision, not provider)
    await enhance(EnhanceRequest(prompt="cat", llm_model="qwen3-vl-local", image=_png_data_url()))
    assert isinstance(captured["messages"][-1]["content"], list)  # multimodal attached


async def test_enhance_ignores_image_for_non_vision_model(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(promptmod, "chat_stream", _recording_stream(["x"], captured))
    # unknown/non-vision pick → resolve_llm None → image dropped, text-only enhance
    await enhance(EnhanceRequest(prompt="cat", llm_model="does-not-exist", image=_png_data_url()))
    assert isinstance(captured["messages"][-1]["content"], str)  # image ignored
