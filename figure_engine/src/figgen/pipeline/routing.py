"""figure_type → 생성 엔진 라우팅 (이미지-우선 vs 구조적).

figurelabs식 하이브리드: 그림으로 그릴 장면(세포·조직·생물·메커니즘 단일 장면, 문제→방법→
결과 한 장 요약)은 **이미지-우선**(베이스 래스터 1장 + 편집 라벨 + 벡터화), 라벨된 구조
(박스+화살표 아키텍처, 정량 플롯, 아이콘 개념도)는 **구조적**(FigureSpec) 경로로 보낸다.
분류 결과(figure_type)와 무관하게 단일 진실원천으로 두 경로를 가른다.
"""

from __future__ import annotations

from typing import Literal

# 베이스 이미지 1장 + 편집 가능 벡터 라벨 오버레이로 만드는 타입
IMAGE_FIRST_TYPES: frozenset[str] = frozenset({"scientific_illustration", "graphical_abstract"})

Route = Literal["image_first", "structured"]


def is_image_first(figure_type: str) -> bool:
    return figure_type in IMAGE_FIRST_TYPES


def route(figure_type: str) -> Route:
    return "image_first" if is_image_first(figure_type) else "structured"
