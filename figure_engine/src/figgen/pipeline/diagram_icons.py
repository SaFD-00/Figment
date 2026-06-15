"""M4.3 — method_diagram 박스별 과학 일러스트(icon_asset) 생성(opt-in).

각 박스 라벨을 주제로 작은 투명 아이콘을 생성해 box.icon_asset에 바인딩한다. 박스당 이미지
1콜이 들어 비용이 크므로 settings.diagram_box_icons로 게이트하고 박스 수를 상한한다.
content-addressed AssetCache(AssetGenerator 내부)로 동일 아이콘 재요청은 무료.
"""

from __future__ import annotations

import asyncio

from ..assets.generator import AssetGenerator, AssetRequest
from ..assets.store import AssetStore
from ..config import Settings
from ..schema.figure_spec import CONTAINER_TYPES, FigureSpec
from ..schema.requests import GenerationRequest

# 그림으로 표현하기 애매한 role은 제외(추상 노드).
_SKIP_ROLES = {"decision", "loss", "note"}
_MAX_ICONS = 12


async def generate_box_icons(
    spec: FigureSpec,
    req: GenerationRequest,
    asset_store: AssetStore,
    settings: Settings,
    provider: str | None,
) -> FigureSpec:
    if spec.figure_type != "method_diagram":
        return spec
    boxes = [
        n for n, _ in spec.iter_elements()
        if getattr(n, "type", None) == "box"
        and getattr(n, "label", None)
        and not getattr(n, "icon_asset", None)
        and getattr(n, "role", None) not in _SKIP_ROLES
    ][:_MAX_ICONS]
    if not boxes:
        return spec

    gen = AssetGenerator(settings, asset_store, provider_override=provider)

    async def _one(box):
        r = await gen.generate(AssetRequest(
            description=box.label, kind="icon", style_preset=req.style_preset,
            transparency_required=True))
        return box.id, r.asset_id

    results = await asyncio.gather(*[_one(b) for b in boxes])
    mapping = {bid: aid for bid, aid in results}
    data = spec.model_dump()
    _apply_box_icon_ids(data["root"], mapping)
    return FigureSpec.model_validate(data)


def _apply_box_icon_ids(node: dict, mapping: dict[str, str]) -> None:
    if node.get("type") == "box" and node.get("id") in mapping:
        node["icon_asset"] = mapping[node["id"]]
    if node.get("type") in CONTAINER_TYPES:
        for c in node.get("children", []):
            _apply_box_icon_ids(c, mapping)
    elif node.get("type") == "free":
        for it in node.get("items", []):
            _apply_box_icon_ids(it["node"], mapping)
