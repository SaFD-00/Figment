"""OpenRouter provider — multimodal (vision-capable) LLM + image generation.

OpenRouter는 OpenAI 호환(`https://openrouter.ai/api/v1`)이므로 LLM은 OpenAIClient에
base_url만 지정해 재사용한다. 이미지 생성은 OpenAI Images API가 아니라
`POST /chat/completions` + ``modalities:["image","text"]`` 방식으로, 응답
``choices[0].message.images[0].image_url.url``(data URL)에서 base64를 디코드한다.

검증: https://openrouter.ai/docs/quickstart ,
https://openrouter.ai/docs/guides/overview/multimodal/image-generation
- 종횡비/해상도: ``image_config.aspect_ratio``("16:9"/"1:1"/"9:16") · ``image_config.image_size``
  ("0.5K"/"1K"/"2K"/"4K"). image-to-image는 입력 이미지 첨부 + ``image_config.strength``(0~1).
- 이 이미지 생성 경로(`/chat/completions` modalities)는 투명 PNG·mask 인페인트를 보장하지 않는다
  → has_alpha=False, mask는 무시하고 전체-이미지 편집으로 degrade(Region Redraw 품질 저하 가능).
"""

from __future__ import annotations

import base64

from .base import AssetResult
from .openai_client import OpenAIClient

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_HEADERS = {"HTTP-Referer": "https://figgen.local", "X-Title": "FigGen"}


class OpenRouterClient(OpenAIClient):
    """OpenRouter LLM (멀티모달 VL) — OpenAI 호환 chat-completions 재사용."""

    def __init__(
        self,
        api_key: str,
        model: str = "google/gemini-2.5-flash",
        *,
        base_url: str = OPENROUTER_BASE_URL,
    ):
        super().__init__(
            api_key,
            model,
            base_url=base_url,
            extra_headers=dict(_HEADERS),
            omit_temp=False,  # OpenRouter LLM은 temperature 지원
            name=f"openrouter:{model}",
        )

    async def web_research(self, query: str, *, max_chars: int = 4000) -> str:
        """OpenRouter 웹검색 그라운딩 — 모델에 ``:online`` 접미사를 붙여 chat으로 수집.

        OpenAI Responses API(web_search 도구)는 OpenRouter 미지원이므로 online 변종을 쓴다.
        실패해도 절대 예외를 올리지 않고 빈 문자열을 반환(베스트-에포트).
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
            resp = await client.chat.completions.create(
                model=f"{self.model}:online",
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.choices[0].message.content or ""
        except Exception:  # noqa: BLE001
            return ""
        return text[:max_chars]


class OpenRouterImageClient:
    """GPT Image / Gemini Image 등 OpenRouter 이미지 모델 — chat-completions + modalities(httpx)."""

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-5.4-image-2",   # VERIFY slug
        *,
        base_url: str = OPENROUTER_BASE_URL,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.name = f"openrouter-image:{model}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **_HEADERS,
        }

    @staticmethod
    def _aspect(width_px: int, height_px: int) -> str:
        if width_px > height_px * 1.2:
            return "16:9"
        if height_px > width_px * 1.2:
            return "9:16"
        return "1:1"

    @staticmethod
    def _image_size(width_px: int, height_px: int) -> str:
        long_edge = max(width_px, height_px)
        if long_edge >= 3072:
            return "4K"
        if long_edge >= 1280:
            return "2K"
        return "1K"

    @staticmethod
    def _decode(result: dict) -> tuple[bytes, str]:
        """``choices[0].message.images[0].image_url.url``(data URL) → (bytes, mime)."""
        choices = result.get("choices") or []
        if not choices:
            raise ValueError(f"OpenRouter 이미지 응답에 choices 없음: {str(result)[:200]}")
        images = (choices[0].get("message") or {}).get("images") or []
        if not images:
            raise ValueError(f"OpenRouter 이미지 응답에 images 없음: {str(result)[:200]}")
        url = images[0]["image_url"]["url"]
        mime = "image/png"
        if url.startswith("data:") and ";" in url:
            mime = url[5:].split(";", 1)[0] or mime
        b64 = url.split(",", 1)[1] if "," in url else url
        return base64.b64decode(b64), mime

    @staticmethod
    def _to_png(data: bytes, mime: str) -> bytes:
        """파이프라인은 PNG를 가정하므로 JPEG 등은 PNG로 정규화한다."""
        if mime == "image/png":
            return data
        import io

        from PIL import Image

        buf = io.BytesIO()
        Image.open(io.BytesIO(data)).convert("RGB").save(buf, format="PNG")
        return buf.getvalue()

    async def _post(self, payload: dict) -> bytes:
        import httpx

        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions", headers=self._headers(), json=payload
            )
            resp.raise_for_status()
            data, mime = self._decode(resp.json())
        return self._to_png(data, mime)

    async def generate(
        self,
        prompt: str,
        *,
        width_px: int = 1024,
        height_px: int = 1024,
        transparent: bool = True,
        style_hint: str | None = None,
    ) -> AssetResult:
        full = f"{prompt}. {style_hint}" if style_hint else prompt
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": full}],
            "modalities": ["image"],  # 이미지 전용 출력
            "image_config": {
                "aspect_ratio": self._aspect(width_px, height_px),
                "image_size": self._image_size(width_px, height_px),
            },
        }
        data = await self._post(payload)
        return AssetResult(data=data, mime="image/png", has_alpha=False, provider=self.name)

    async def edit(
        self,
        image: bytes,
        prompt: str,
        *,
        mask: bytes | None = None,
        strength: float | None = None,
        size: str | None = None,
        background: str = "auto",
        input_fidelity: str = "high",
        transparent: bool = False,
    ) -> AssetResult:
        """image-to-image 편집. mask는 이 경로 미지원 → 무시(전체-이미지 편집).

        ``strength``(0~1)은 입력 충실도 다이얼 — 낮을수록 입력에 가깝게(보수적 편집).
        미지정 시 0.55(편집 기본)."""
        b64 = base64.b64encode(image).decode("ascii")
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "modalities": ["image"],
            # strength↓ = 입력에 가깝게(편집), upscale/white_bg은 보존 우선.
            "image_config": {"strength": strength if strength is not None else 0.55},
        }
        data = await self._post(payload)
        return AssetResult(data=data, mime="image/png", has_alpha=False, provider=self.name)
