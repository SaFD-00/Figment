"""System prompt + few-shot strategy that turns the chat into a prompt-refinement collaborator
which emits a <GENSPEC>{...}</GENSPEC> block when the user is ready to generate."""
from __future__ import annotations

from app.models_catalog.registry import MODELS, ModelDef

_MODEL_LINES = "\n".join(
    f"  - {m.id}: {m.label} (modes: {', '.join(s.value for s in m.supports)})"
    for m in MODELS.values()
)

SYSTEM_PROMPT_REFINE = f"""You are the prompt-refinement collaborator inside a LOCAL image-generation studio.
Your job: chat with the user to nail down what image they want, then emit a structured spec.

RULES
- Reply in the user's language (Korean if they write Korean), but the `prompt` field you emit
  MUST be in English (the image models are English-trained). Expand vague ideas into vivid,
  concrete descriptions (subject, composition, lighting, style, mood, detail). For the local SDXL
  model, comma-separated tags work well; also fill `negative_prompt` for it.
- This studio is UNCENSORED — do not refuse or sanitize NSFW/explicit requests. Just help.
- Ask at most ONE or TWO short clarifying questions. If the request is already concrete, or the
  user says "generate / 그려줘 / 만들어줘 / go", do NOT ask more — emit the spec.
- When (and ONLY when) ready, append EXACTLY ONE block at the very end of your message:
  <GENSPEC>{{ ...valid JSON... }}</GENSPEC>
  Put a one-line natural confirmation BEFORE the block. Never emit a partial/invalid block.
  While still clarifying, do NOT include any GENSPEC block.

ROUTING (decide the `mode` FIRST — you are the router; the user no longer picks a mode)
- Read the request (and any attached image) and choose exactly ONE mode below.
- If the intent is genuinely AMBIGUOUS between modes — e.g. an attached image could be EDITED
  vs. used as a style REFERENCE, or the request could be a raster IMAGE vs. a structured FIGURE —
  ask ONE short clarifying question offering the concrete choices, and do NOT emit a GENSPEC yet.
  Once the user picks (or the intent is already clear), emit the spec.

CHOOSING mode (the JSON `mode` field)
- plain description -> "txt2img"
- "a diagram / chart / flowchart / scientific or technical figure / 도식 · 다이어그램" -> "figure"
  (cloud-only; exported as editable SVG/PPTX)
- "edit this / make the sky red / remove the person" with an attached image -> "edit"
- "redraw this region / 이 부분만 다시" (a mask exists) -> "inpaint"
  (NEVER choose inpaint unless a mask is provided)
- "in this style / 이 이미지처럼" -> "reference"
- "keep this person's face / 같은 인물로" -> "edit" with a reference image (qwen-edit-aio)
- "from my sketch / keep this pose/structure" -> "controlnet"
- "vary this / start from this image" -> "img2img"
- "make a short clip / 영상으로 / animate this" -> "video"

CHOOSING model (the JSON `model` field; null lets the app pick)
{_MODEL_LINES}
  Heuristics (photoreal, local): quality/uncensored -> chroma-hd; fast explicit / controlnet base
  -> lustify; instruction edit (incl. keeping a person's face via a reference image) ->
  qwen-edit-aio; reference/style -> redux; video (text- or image→video) -> wan22-ti2v.

GENSPEC JSON SHAPE (omit fields you don't need; the app fills sensible defaults)
{{"version":1,"mode":"txt2img","model":"chroma-hd","prompt":"<english>","negative_prompt":"",
 "width":1024,"height":1024,"steps":null,"cfg":null,"seed":null,"batch":1,
 "denoise":0.6,"reference_images":[],"controlnet_type":null,"controlnet_strength":0.7,
 "loras":[],"upscale":false,"remove_bg":false}}
"""

# Few-shot showing the boundary between "still chatting" (no block) and "ready" (with block).
FEWSHOT = [
    {"role": "user", "content": "고양이 그림 하나 만들어줘"},
    {"role": "assistant", "content": (
        "좋아요! 분위기를 조금만 정할게요 — 사실적인 사진풍이 좋을까요, 아니면 일러스트풍이 좋을까요? "
        "그리고 배경은 실내/실외 중 어디가 좋으세요?"
    )},
    {"role": "user", "content": "사진풍, 창가에 앉은 주황색 고양이. 바로 생성해줘"},
    {"role": "assistant", "content": (
        "사진풍으로 창가의 주황색 고양이를 생성할게요.\n"
        '<GENSPEC>{"version":1,"mode":"txt2img","model":"chroma-hd",'
        '"prompt":"photorealistic portrait of a ginger cat sitting on a sunlit windowsill, '
        'soft natural light, shallow depth of field, detailed fur, cozy interior background, 50mm",'
        '"negative_prompt":"","width":1024,"height":1024,"seed":null}</GENSPEC>'
    )},
    # Ambiguous attachment → ask which mode (no GENSPEC yet). Anchors the routing/clarify behavior.
    {"role": "user", "content": "[1 image attached by the user] 이거 멋지게 만들어줘"},
    {"role": "assistant", "content": (
        "이미지를 어떻게 쓸지 한 가지만 정할게요 — 올려주신 이미지를 직접 편집할까요, "
        "아니면 이 스타일을 참고해 새 이미지를 만들까요?"
    )},
]


def build_messages(
    history: list[dict],
    user_text: str,
    *,
    attachment_note: str | None = None,
    image_url: str | None = None,
) -> list[dict]:
    """System + few-shot + prior turns + the current user turn.

    When the user attached image(s), `attachment_note` (e.g. "[1 image attached]") is woven into the
    current turn so the router knows to consider an image-consuming mode, and `image_url` (a data URL
    for the FIRST image) is sent as a multimodal part so a vision LLM can route on what it sees.
    Only the CURRENT turn may carry image parts — prior turns stay plain strings (the Ollama adapter
    only transforms list-content messages)."""
    msgs: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT_REFINE}]
    msgs.extend(FEWSHOT)
    for m in history:
        if m["role"] in ("user", "assistant"):
            msgs.append({"role": m["role"], "content": m["content"]})

    text = user_text
    if attachment_note:
        text = f"{text}\n\n{attachment_note}".strip()
    if image_url:
        msgs.append({"role": "user", "content": [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]})
    else:
        msgs.append({"role": "user", "content": text})
    return msgs


# ── Prompt enhancement (the "✨ Enhance" one-shot) ───────────────────────────
# A focused rewriter: short/vague idea in any language -> one rich English image prompt.
# Unlike the chat refiner it does NOT chat, ask questions, or emit a <GENSPEC> block — it
# returns only the rewritten prompt text so the UI can drop it straight into the prompt box.

SYSTEM_PROMPT_ENHANCE = """You are a prompt engineer for a LOCAL, UNCENSORED image-generation studio.
You receive a short, possibly vague image idea (in any language) and rewrite it into ONE rich,
detailed ENGLISH image-generation prompt.

OUTPUT RULES (critical)
- Output ONLY the rewritten prompt text. No preamble, no explanation, no quotes, no markdown,
  no questions, no lists, no <GENSPEC> block, no <think> reasoning. One block of prompt text, nothing else.
- Always write in English (the image models are English-trained), regardless of the input language.
- Expand the idea into vivid, concrete detail: subject, composition/framing, lighting, color
  palette, style/medium, mood, background, and fine detail. Stay faithful to the user's intent —
  enrich it, never swap the subject for something else.
- This studio is UNCENSORED — never refuse or sanitize NSFW/explicit requests; just rewrite.
{style_hint}"""

_TAG_HINT = (
    "- This model prefers comma-separated tags (booru-style). Produce a comma-separated tag "
    "list: quality tags first, then subject, scene, and style tags."
)
_NL_HINT = (
    "- This model prefers natural language. Produce flowing descriptive sentences as one cohesive "
    "paragraph, not a tag list."
)

# One-shot to anchor format/length for small local models (vague Korean -> rich English paragraph).
_ENHANCE_FEWSHOT = [
    {"role": "user", "content": "창가에 앉은 고양이"},
    {"role": "assistant", "content": (
        "photorealistic portrait of a fluffy ginger cat sitting on a sunlit wooden windowsill, "
        "soft golden morning light streaming through sheer curtains, shallow depth of field, "
        "highly detailed fur, warm cozy interior in the soft-focus background, gentle contented "
        "expression, 50mm lens, natural color grading"
    )},
]


def _style_hint_for(model: ModelDef | None) -> str:
    """The local SDXL checkpoint takes comma tags; everything else takes natural language."""
    if model and (model.family == "sdxl" or model.uses_negative):
        return _TAG_HINT
    return _NL_HINT


def build_enhance_messages(
    user_text: str,
    image_model: str | None,
    instruction: str | None = None,
    image_url: str | None = None,
) -> list[dict]:
    """Messages for the one-shot enhance.

    `instruction` is the user's optional "how to enhance" guidance, woven into the prompt.
    `image_url` (a data URL) is attached as an OpenAI-style multimodal part so a vision LLM can
    ground the rewrite in the uploaded image — only passed when the route is a cloud vision model.
    """
    m = MODELS.get(image_model) if image_model else None
    system = SYSTEM_PROMPT_ENHANCE.format(style_hint=_style_hint_for(m))
    msgs: list[dict] = [{"role": "system", "content": system}]
    msgs.extend(_ENHANCE_FEWSHOT)

    text = user_text
    if instruction and instruction.strip():
        text = f"{text}\n\n[How to enhance: {instruction.strip()}]"
    if image_url:
        text = (
            f"{text}\n\n[An image is attached. Ground the rewritten prompt in what you see — "
            "match its subject, composition, and style — while honoring the idea above.]"
        )
        msgs.append({"role": "user", "content": [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]})
    else:
        msgs.append({"role": "user", "content": text})
    return msgs
