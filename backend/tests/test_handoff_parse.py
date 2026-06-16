"""GENSPEC extraction + 'chatting vs ready' logic."""
from app.llm.handoff import GenSpecExtractor


def _feed_all(text: str, chunk: int = 7):
    ex = GenSpecExtractor()
    visible = ""
    for i in range(0, len(text), chunk):
        visible += ex.feed(text[i:i + chunk])
    return ex, visible


def test_pure_chat_no_block():
    ex, visible = _feed_all("어떤 스타일을 원하세요? 사진풍 또는 일러스트?")
    spec, raw, err = ex.finish()
    assert spec is None and err is None
    visible += ex.trailing_visible()
    assert "스타일" in visible


def test_ready_with_valid_block():
    text = (
        "사진풍 고양이를 생성할게요.\n"
        '<GENSPEC>{"version":1,"mode":"txt2img","model":"qwen-image",'
        '"prompt":"a ginger cat on a windowsill","seed":42}</GENSPEC>'
    )
    ex, visible = _feed_all(text)
    spec, raw, err = ex.finish()
    assert err is None
    assert spec is not None
    assert spec.prompt == "a ginger cat on a windowsill"
    assert spec.model == "qwen-image"
    assert spec.seed == 42
    # the GENSPEC block must NOT leak into visible text
    assert "GENSPEC" not in visible
    assert "사진풍 고양이" in visible


def test_invalid_json_reports_error():
    text = "ok\n<GENSPEC>{not json}</GENSPEC>"
    ex, _ = _feed_all(text)
    spec, raw, err = ex.finish()
    assert spec is None
    assert err is not None and "JSON" in err
