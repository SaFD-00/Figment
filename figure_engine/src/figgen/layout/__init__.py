"""레이아웃 — FigureSpec을 절대 mm 좌표(ResolvedLayout)로 변환."""

from .connectors import route_connectors
from .diagnostics import check_text_fit, detect_overlaps, nudge_free_items
from .engine import LayoutEngine
from .text_metrics import FontProvider, Size, TextMetrics
from .types import ConnectorPath, LayoutWarning, Rect, ResolvedLayout

__all__ = [
    "LayoutEngine",
    "FontProvider",
    "Size",
    "TextMetrics",
    "Rect",
    "ResolvedLayout",
    "ConnectorPath",
    "LayoutWarning",
    "route_connectors",
    "detect_overlaps",
    "check_text_fit",
    "nudge_free_items",
]
