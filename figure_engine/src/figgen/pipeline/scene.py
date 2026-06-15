"""scientific_illustration 장면 모드 — FigureLabs식 '풍부한 단일 장면 + 편집 라벨'.

흐름: LLM 장면 브리프(plan_scene) → 텍스트 없는 베이스 이미지(generate_base_image) →
AssetStore 저장 → 편집 가능 라벨 오버레이 Free-root FigureSpec(build_overlay_spec).
결과 spec은 connectors=[]인 Free 루트라 표준 STYLING→RENDERING→CRITIC 꼬리를 그대로 통과한다.
cli_gen(오프라인/CLI)과 orchestrator(웹) 양쪽이 공유한다.
"""

from __future__ import annotations

from ..assets.cache import AssetCache
from ..assets.prompts import PRESET_VERSION, build_scene_prompt
from ..assets.store import AssetStore
from ..config import Settings
from ..fullimage.composer import build_overlay_spec, generate_base_image
from ..providers.registry import get_image_client
from ..schema.figure_spec import FigureSpec
from ..schema.requests import GenerationRequest
from .planner import Planner, RefStyleReport

# aspect → (이미지 px, 캔버스 mm). gpt-image-1.5 지원 사이즈에 맞춤.
_ASPECT = {
    "wide": (1536, 1024, (170.0, 113.0)),
    "square": (1024, 1024, (150.0, 150.0)),
    "tall": (1024, 1536, (120.0, 170.0)),
}


async def generate_scene_spec(
    planner: Planner,
    req: GenerationRequest,
    asset_store: AssetStore,
    settings: Settings,
    provider: str | None,
    *,
    research_ctx: str = "",
    figure_type: str = "scientific_illustration",
    style_ref: RefStyleReport | None = None,
    aspect: str | None = None,
) -> FigureSpec:
    brief = await planner.plan_scene(
        req, research_ctx=research_ctx, style_ref=style_ref, figure_type=figure_type)
    chosen = (aspect or brief.aspect) if (aspect or brief.aspect) in _ASPECT else "wide"
    w_px, h_px, canvas_mm = _ASPECT[chosen]
    palette = style_ref.palette_hex if style_ref else None
    scene_prompt = build_scene_prompt(brief.scene_prompt, req.style_preset, palette=palette)

    client = get_image_client(settings, transparent=False, provider_override=provider)

    # 콘텐츠 주소 캐시(동일 프롬프트 재요청 시 재과금 방지). 실패해도 진행.
    data: bytes | None = None
    cache: AssetCache | None = None
    try:
        cache = AssetCache(settings.resolved_asset_cache_dir())
        ckey = cache.key(client.name, scene_prompt, f"{w_px}x{h_px}", False, PRESET_VERSION)
        data = cache.get(ckey)
    except Exception:  # noqa: BLE001
        cache, ckey = None, ""
    if data is None:
        data = await generate_base_image(scene_prompt, client, width_px=w_px, height_px=h_px)
        if cache is not None:
            try:
                cache.put(ckey, data, meta={"model": client.name, "prompt": scene_prompt})
            except Exception:  # noqa: BLE001
                pass

    base_id = asset_store.put(data, "image/png", kind="illustration")

    # 장면 아트를 벡터화해 SVG에서 편집 가능하게(선택). 실패해도 래스터로 정상 동작.
    svg_id: str | None = None
    if getattr(settings, "scene_vectorize", True):
        try:
            from ..fullimage.vectorize import vectorize_png

            svg = vectorize_png(data)
            svg_id = asset_store.put(svg, "image/svg+xml", kind="illustration_svg")
        except Exception:  # noqa: BLE001
            svg_id = None

    return build_overlay_spec(
        base_id, brief.labels, canvas_mm=canvas_mm, title=brief.title,
        figure_type=figure_type, base_svg_asset_id=svg_id,
    )
