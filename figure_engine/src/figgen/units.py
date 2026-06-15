"""단위 변환 단일 진실 소스.

내부 좌표는 전부 **mm float**, 폰트 크기만 **pt**를 사용한다(고정 계약 #1).
EMU/px/inch 변환은 이 모듈만 경유한다 — 렌더러·엔진 내 인라인 곱셈 금지.

기준값:
- 1 inch = 25.4 mm = 72 pt
- 1 mm = 36000 EMU  (python-pptx Emu 기준)
- 1 pt = 12700 EMU
"""

from __future__ import annotations

EMU_PER_MM: int = 36000
EMU_PER_PT: int = 12700
MM_PER_INCH: float = 25.4
PT_PER_INCH: float = 72.0

# icon_asset이 있는 박스의 상단 아이콘 영역 높이(mm) — measure/렌더 공유 상수.
BOX_ICON_MM: float = 12.0


# ── mm 기준 변환 ────────────────────────────────────────────────────────────
def mm_to_emu(mm: float) -> int:
    """mm → EMU(정수). PPTX 좌표/크기용."""
    return int(round(mm * EMU_PER_MM))


def mm_to_px(mm: float, dpi: float = 150.0) -> float:
    """mm → 픽셀. SVG 래스터화·미리보기용."""
    return mm / MM_PER_INCH * dpi


def mm_to_pt(mm: float) -> float:
    """mm → pt."""
    return mm / MM_PER_INCH * PT_PER_INCH


def mm_to_inch(mm: float) -> float:
    """mm → inch. matplotlib figsize용."""
    return mm / MM_PER_INCH


# ── pt 기준 변환 (폰트·선굵기) ──────────────────────────────────────────────
def pt_to_mm(pt: float) -> float:
    """pt → mm."""
    return pt / PT_PER_INCH * MM_PER_INCH


def pt_to_emu(pt: float) -> int:
    """pt → EMU(정수). 선 굵기 등."""
    return int(round(pt * EMU_PER_PT))


def pt_to_px(pt: float, dpi: float = 150.0) -> float:
    """pt → 픽셀."""
    return pt / PT_PER_INCH * dpi


# ── 기타 ────────────────────────────────────────────────────────────────────
def inch_to_mm(inch: float) -> float:
    return inch * MM_PER_INCH


def frac_to_mm(frac: float, total_mm: float) -> float:
    """0~1 비율 좌표 → mm. Free 노드 환산용."""
    return frac * total_mm


def px_to_mm(px: float, dpi: float = 150.0) -> float:
    return px / dpi * MM_PER_INCH
