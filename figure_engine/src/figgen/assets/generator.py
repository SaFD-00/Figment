"""아이콘/일러스트 생성 오케스트레이터: 모델 라우팅 + 캐시 + 후처리 파이프.

투명 필요 → gpt-image-1.5 강제(registry). 콘텐츠 주소 캐시로 critic 반복 중 재호출 차단.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ..config import Settings
from ..providers.registry import get_image_client
from .cache import AssetCache
from .postprocess import resize_for_placement, trim_transparent
from .prompts import PRESET_VERSION, build_icon_prompt
from .store import AssetStore


class AssetRequest(BaseModel):
    description: str
    kind: Literal["icon", "illustration", "photo"] = "icon"
    style_preset: str = "nature_minimal"
    transparency_required: bool = True
    target_size_pt: tuple[float, float] = (48.0, 48.0)
    quality: Literal["fast", "high"] = "fast"


class GenResult(BaseModel):
    asset_id: str
    cached: bool
    model: str


class AssetGenerator:
    def __init__(
        self,
        settings: Settings,
        store: AssetStore,
        cache: AssetCache | None = None,
        *,
        provider_override: str | None = None,
    ):
        self.settings = settings
        self.store = store
        self.cache = cache or AssetCache()
        self.provider_override = provider_override

    async def generate(self, req: AssetRequest) -> GenResult:
        client = get_image_client(
            self.settings,
            transparent=req.transparency_required,
            provider_override=self.provider_override,
        )
        prompt = build_icon_prompt(req.description, req.style_preset, req.transparency_required)
        px = 1024
        size_str = f"{px}x{px}"
        key = self.cache.key(client.name, prompt, size_str, req.transparency_required, PRESET_VERSION)

        cached_png = self.cache.get(key)
        if cached_png is not None:
            asset_id = self.store.put(cached_png, "image/png",
                                      kind="illustration" if req.kind == "illustration" else "icon")
            return GenResult(asset_id=asset_id, cached=True, model=client.name)

        result = await client.generate(
            prompt, width_px=px, height_px=px, transparent=req.transparency_required,
            style_hint=None)
        png = result.data
        if result.has_alpha or req.transparency_required:
            png = trim_transparent(png)
        png = resize_for_placement(png, req.target_size_pt, oversample=2.0)

        self.cache.put(key, png, meta={"model": client.name, "prompt": prompt})
        asset_id = self.store.put(png, "image/png",
                                  kind="illustration" if req.kind == "illustration" else "icon")
        return GenResult(asset_id=asset_id, cached=False, model=client.name)

    async def regenerate(self, asset_id: str, feedback: str, req: AssetRequest) -> GenResult:
        """부분 재생성 — feedback을 프롬프트에 병합, 캐시 우회(nonce), 버전 체인 연결."""
        client = get_image_client(
            self.settings, transparent=req.transparency_required,
            provider_override=self.provider_override)
        prompt = build_icon_prompt(f"{req.description}. {feedback}", req.style_preset,
                                   req.transparency_required)
        result = await client.generate(prompt, width_px=1024, height_px=1024,
                                       transparent=req.transparency_required)
        png = result.data
        if result.has_alpha or req.transparency_required:
            png = trim_transparent(png)
        png = resize_for_placement(png, req.target_size_pt, oversample=2.0)
        new_id = self.store.put(png, "image/png", kind="icon", parent_id=asset_id)
        return GenResult(asset_id=new_id, cached=False, model=client.name)
