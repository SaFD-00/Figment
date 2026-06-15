"""헬스체크 + 정적 메타(figure-types/styles/models)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ... import __version__
from ...config import get_settings
from ...styles.presets import list_presets
from ..schemas import FigureTypeInfo, ModelInfo, StyleInfo

router = APIRouter(prefix="/api")

_FIGURE_TYPES = [
    FigureTypeInfo(id="scientific_illustration", label="과학 일러스트",
                   description="세포·조직·생물 등 풍부한 단일 장면 (이미지-우선)"),
    FigureTypeInfo(id="method_diagram", label="방법론 다이어그램",
                   description="파이프라인·아키텍처 (박스+화살표)"),
    FigureTypeInfo(id="concept", label="개념도/일러스트", description="아이콘·일러스트 중심 개념도"),
    FigureTypeInfo(id="chart", label="데이터 차트", description="CSV/JSON 데이터 플롯", needs_data=True),
    FigureTypeInfo(id="graphical_abstract", label="Graphical Abstract",
                   description="문제→방법→결과 한 장 요약 (이미지-우선)"),
]


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": __version__}


@router.get("/meta/figure-types", response_model=list[FigureTypeInfo])
async def figure_types() -> list[FigureTypeInfo]:
    return _FIGURE_TYPES


@router.get("/meta/styles", response_model=list[StyleInfo])
async def styles() -> list[StyleInfo]:
    return [StyleInfo(**p) for p in list_presets()]


@router.get("/meta/models", response_model=list[ModelInfo])
async def models(request: Request) -> list[ModelInfo]:
    s = get_settings()
    avail = s.available_providers()
    out: list[ModelInfo] = [ModelInfo(id="mock", label="Mock (오프라인)", role="all", disabled=False)]
    specs = [
        ("planner", "openrouter", s.planner_model),
        ("classifier", "openrouter", s.classifier_model),
        ("critic", "openrouter", s.vision_model),
        ("imager", "openrouter", s.image_model),
    ]
    for role, prov, model in specs:
        out.append(ModelInfo(id=f"{prov}:{model}", label=f"{model}", role=role,
                             disabled=prov not in avail))
    return out
