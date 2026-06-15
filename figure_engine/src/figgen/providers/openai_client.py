"""OpenAI provider — gpt-5.4 구조적 출력 + gpt-image-1.5(투명 네이티브).

complete_structured: to_openai_strict 성공 시 response_format=json_schema(strict=True),
실패 시 JSON-mode 폴백 → 두 경로 모두 Pydantic 검증 + repair 재시도.
gpt-image-2는 투명 미지원이므로 사용 금지(모델 핀 고정).
"""

from __future__ import annotations

import base64
from typing import Any

from pydantic import BaseModel, ValidationError

from .base import AssetResult, ImageInput, Message, StructuredOutputError
from .schema_transform import build_json_mode_prompt, to_openai_strict

_SIZES = {(1, 1): "1024x1024", (3, 2): "1536x1024", (2, 3): "1024x1536"}


def _omit_temperature(model: str) -> bool:
    """추론 모델(gpt-5.x base·o-시리즈)은 temperature 기본값(1)만 허용 → 파라미터 생략.

    chat-latest 변종과 gpt-4o/4.1 등은 커스텀 temperature 지원.
    """
    m = model.lower()
    if m.startswith(("o1", "o3", "o4")):
        return True
    if m.startswith("gpt-5") and "chat" not in m:
        return True
    return False


def _pick_size(w: int, h: int) -> str:
    if w > h * 1.2:
        return "1536x1024"
    if h > w * 1.2:
        return "1024x1536"
    return "1024x1024"


class OpenAIClient:
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5.4",
        *,
        base_url: str | None = None,
        extra_headers: dict[str, str] | None = None,
        omit_temp: bool | None = None,
        name: str | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.name = name or f"openai:{model}"
        self.base_url = base_url
        self.extra_headers = extra_headers
        self._omit_temp = omit_temp if omit_temp is not None else _omit_temperature(model)

    def _client(self):
        from openai import AsyncOpenAI

        kwargs: dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        if self.extra_headers:
            kwargs["default_headers"] = self.extra_headers
        return AsyncOpenAI(**kwargs)

    def _messages(self, system: str, messages: list[Message]) -> list[dict]:
        out: list[dict] = []
        if system:
            out.append({"role": "system", "content": system})
        for m in messages:
            if m.images:
                parts: list[dict] = [{"type": "text", "text": m.content}]
                for img in m.images:
                    b64 = base64.b64encode(img.data).decode("ascii")
                    parts.append({"type": "image_url",
                                  "image_url": {"url": f"data:{img.mime};base64,{b64}"}})
                out.append({"role": m.role, "content": parts})
            else:
                out.append({"role": m.role, "content": m.content})
        return out

    async def web_research(self, query: str, *, max_chars: int = 4000) -> str:
        """OpenAI Responses API web_search로 과학적 맥락을 수집(베스트-에포트).

        figure 정확도 그라운딩 전용 — 실패해도 절대 예외를 올리지 않고 빈 문자열을 반환한다.
        """
        prompt = (
            "Gather accurate scientific facts to help draw an accurate, publication-quality "
            f"figure of: {query}\n\n"
            "Report: key entities/structures, pathways or mechanisms (step order), correct "
            "terminology and labels, relevant quantities, and spatial/temporal relationships. "
            "Be concise and factual. Plain text, no preamble, no markdown headings."
        )
        try:
            client = self._client()
            resp = await client.responses.create(
                model=self.model, input=prompt, tools=[{"type": "web_search"}])
            text = getattr(resp, "output_text", "") or ""
        except Exception:  # noqa: BLE001
            return ""
        return text[:max_chars]

    async def complete(self, messages: list[Message], *, system: str = "",
                       temperature: float = 0.3) -> str:
        client = self._client()
        kwargs: dict[str, Any] = {
            "model": self.model, "messages": self._messages(system, messages)}
        if not self._omit_temp:
            kwargs["temperature"] = temperature
        resp = await client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    async def complete_structured(
        self,
        messages: list[Message],
        schema: type[BaseModel],
        *,
        system: str = "",
        images: list[ImageInput] | None = None,
        max_repair: int = 2,
    ) -> Any:
        client = self._client()
        if images and messages:
            messages = [*messages[:-1], messages[-1].model_copy(update={"images": images})]
        try:
            strict_schema = to_openai_strict(schema)
        except Exception:  # noqa: BLE001
            strict_schema = None

        msgs = self._messages(system, messages)
        text = ""
        last_err = ""
        for attempt in range(max_repair + 1):
            try:
                if strict_schema is not None:
                    kwargs: dict[str, Any] = {
                        "model": self.model, "messages": msgs,
                        "response_format": {"type": "json_schema", "json_schema": {
                            "name": schema.__name__, "schema": strict_schema, "strict": True}}}
                else:
                    kwargs = {
                        "model": self.model,
                        "messages": [{"role": "system", "content": build_json_mode_prompt(schema)},
                                     *msgs],
                        "response_format": {"type": "json_object"}}
                if not self._omit_temp:
                    kwargs["temperature"] = 0.2
                resp = await client.chat.completions.create(**kwargs)
                text = resp.choices[0].message.content or ""
                return schema.model_validate_json(text)
            except ValidationError as e:
                last_err = str(e)
                msgs = [*msgs, {"role": "assistant", "content": text},
                        {"role": "user",
                         "content": f"검증 실패: {last_err[:400]}. 스키마를 정확히 따르는 JSON만 다시 출력."}]
            except Exception as e:  # noqa: BLE001
                if strict_schema is not None and attempt == 0:
                    strict_schema = None  # JSON-mode 폴백
                    continue
                raise StructuredOutputError(f"OpenAI 호출 실패: {e}", raw_text=text) from e
        raise StructuredOutputError("repair 초과", raw_text=text, validation_errors=last_err)


class OpenAIImageClient:
    def __init__(self, api_key: str, model: str = "gpt-image-1.5"):
        self.api_key = api_key
        self.model = model
        self.name = f"openai-image:{model}"

    async def generate(self, prompt: str, *, width_px: int = 1024, height_px: int = 1024,
                       transparent: bool = True, style_hint: str | None = None) -> AssetResult:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key)
        full = f"{prompt}. {style_hint}" if style_hint else prompt
        resp = await client.images.generate(
            model=self.model, prompt=full, size=_pick_size(width_px, height_px),
            background="transparent" if transparent else "auto", output_format="png")
        data = base64.b64decode(resp.data[0].b64_json)
        return AssetResult(data=data, mime="image/png", has_alpha=transparent,
                           provider=self.name, revised_prompt=getattr(resp.data[0], "revised_prompt", None))

    async def edit(self, image: bytes, prompt: str, *, mask: bytes | None = None,
                   size: str | None = None, background: str = "auto",
                   input_fidelity: str = "high", transparent: bool = False) -> AssetResult:
        """gpt-image edit — mask 인페인트(투명영역 재생성)/배경교체/업스케일.

        Region Redraw·White BG·Upscale·Figure Refiner의 공통 백본.
        """
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key)
        kwargs: dict[str, Any] = {
            "model": self.model, "prompt": prompt,
            "image": ("image.png", image, "image/png"),
            "background": "transparent" if transparent else background,
            "input_fidelity": input_fidelity, "output_format": "png",
        }
        if mask is not None:
            kwargs["mask"] = ("mask.png", mask, "image/png")
        if size:
            kwargs["size"] = size
        resp = await client.images.edit(**kwargs)
        data = base64.b64decode(resp.data[0].b64_json)
        return AssetResult(data=data, mime="image/png", has_alpha=transparent, provider=self.name,
                           revised_prompt=getattr(resp.data[0], "revised_prompt", None))
