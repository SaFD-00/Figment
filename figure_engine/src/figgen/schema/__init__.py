"""FigGen 스키마 — FigureSpec(단일 진실 소스) 및 스타일/패치/요청 모델."""

from ._types import MM, ElementId, HexColor
from .content_plan import ContentPlan, Entity, Relation
from .figure_spec import (
    BoxElement,
    Canvas,
    ChartElement,
    Column,
    Connector,
    FigureSpec,
    FigureType,
    Free,
    FreeItem,
    Grid,
    Group,
    ImageElement,
    Row,
    SizeHint,
    TextElement,
)
from .patch import PatchError, PatchOp, SpecPatch, apply_patch, validate_patch_scope
from .requests import EditDirective, GenerationRequest, GenerationResult
from .style import Font, ResolvedStyle, Stroke, StyleOverride, StyleSheet, resolve_style

__all__ = [
    "MM",
    "ElementId",
    "HexColor",
    "FigureSpec",
    "FigureType",
    "Canvas",
    "Connector",
    "Row",
    "Column",
    "Grid",
    "Group",
    "Free",
    "FreeItem",
    "SizeHint",
    "BoxElement",
    "TextElement",
    "ImageElement",
    "ChartElement",
    "ContentPlan",
    "Entity",
    "Relation",
    "Stroke",
    "Font",
    "StyleOverride",
    "StyleSheet",
    "ResolvedStyle",
    "resolve_style",
    "PatchOp",
    "SpecPatch",
    "PatchError",
    "apply_patch",
    "validate_patch_scope",
    "GenerationRequest",
    "EditDirective",
    "GenerationResult",
]
