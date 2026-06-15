"""에셋 — 이미지 생성 라우팅/캐시/후처리 + 버전 체인 저장소."""

from .cache import AssetCache
from .generator import AssetGenerator, AssetRequest, GenResult
from .postprocess import chroma_key, resize_for_placement, trim_transparent
from .store import Asset, AssetStore

__all__ = [
    "AssetCache",
    "AssetStore",
    "Asset",
    "AssetGenerator",
    "AssetRequest",
    "GenResult",
    "chroma_key",
    "trim_transparent",
    "resize_for_placement",
]
