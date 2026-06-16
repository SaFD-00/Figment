"""Ollama message adaptation — OpenAI-style multimodal parts → native `images` array.

Provider-agnostic builders emit a parts-list `content`; Ollama's `/api/chat` wants a string
`content` plus a per-message `images` list of raw base64. `_to_ollama_messages` bridges the two
so local vision prompt-enhance works (no network here — just the pure transform)."""
from app.llm.ollama_client import _to_ollama_messages


def test_passes_through_plain_string_messages():
    msgs = [{"role": "system", "content": "rules"}, {"role": "user", "content": "hi"}]
    assert _to_ollama_messages(msgs) == msgs


def test_converts_multimodal_to_content_and_images():
    msgs = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "describe this"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}},
        ],
    }]
    out = _to_ollama_messages(msgs)
    assert out[0]["role"] == "user"
    assert out[0]["content"] == "describe this"        # text parts joined into a string
    assert out[0]["images"] == ["QUJD"]                # data: prefix stripped → raw base64


def test_keeps_raw_base64_without_data_prefix():
    msgs = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "QUJD"}}]}]
    out = _to_ollama_messages(msgs)
    assert out[0]["images"] == ["QUJD"]
    assert out[0]["content"] == ""                     # no text parts → empty content


def test_no_images_key_when_text_only_parts_list():
    msgs = [{"role": "user", "content": [{"type": "text", "text": "just text"}]}]
    out = _to_ollama_messages(msgs)
    assert out[0]["content"] == "just text"
    assert "images" not in out[0]                      # absent, not empty, when no images
