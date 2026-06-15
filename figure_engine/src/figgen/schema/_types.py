"""schema 공통 스칼라 타입 — style/figure_spec 순환 import 방지용 단일 소스."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

# 내부 좌표는 전부 mm float (고정 계약 #1)
MM = float

# 요소 식별자 — 사람이 읽을 수 있는 slug. 3중 키(spec/SVG/PPTX)의 근간.
ElementId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,40}$")]

# #RRGGBB 6자리 hex
HexColor = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]
