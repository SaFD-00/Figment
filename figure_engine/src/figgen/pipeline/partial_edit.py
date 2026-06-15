"""요소 단위 부분 재생성 (figurelabs Region Redraw 대응).

대상 요소 서브트리 + 부모/형제 요약 + 자연어 지시를 LLM에 주고 제한된 SpecPatch를 받아,
``allowed_ids`` 스코프(타깃 ∪ 자손)로 강제 적용한다. '한 요소 고치랬더니 전체가 바뀜' 차단.
"""

from __future__ import annotations

import json

from ..providers.base import LLMClient, user
from ..schema.figure_spec import CONTAINER_TYPES, FigureSpec
from ..schema.patch import SpecPatch, apply_patch
from ..schema.requests import EditDirective

_SYSTEM = (
    "You edit a FigureSpec by returning a MINIMAL SpecPatch. Allowed ops: "
    "set/remove/insert_child/move_child/replace_element. Touch ONLY the elements you are asked to. "
    "For 'bigger/smaller/wider' use set on path 'size_hint.width_mm'/'size_hint.height_mm' or 'weight'. "
    "For text changes use set on 'label'/'text'. For color use set on 'style.fill'. "
    "Every op needs a target_id and a reason. Return SpecPatch JSON."
)


class PartialEditor:
    def __init__(self, llm: LLMClient, assets=None):
        self.llm = llm
        self.assets = assets

    async def edit(self, spec: FigureSpec, directive: EditDirective) -> FigureSpec:
        if directive.mode == "global" or not directive.target_element_ids:
            patch = await self._ask_patch(spec, directive, allowed=None)
            new_spec, _ = apply_patch(spec, patch)
            return new_spec

        allowed: set[str] = set()
        for eid in directive.target_element_ids:
            allowed.add(eid)
            node = spec.find(eid)
            if node is not None:
                allowed |= _descendant_ids(node)
        patch = await self._ask_patch(spec, directive, allowed=allowed)
        new_spec, _ = apply_patch(spec, patch, allowed_ids=allowed)
        return new_spec

    async def _ask_patch(self, spec, directive, allowed) -> SpecPatch:
        ctx = {
            "instruction": directive.instruction,
            "targets": directive.target_element_ids,
            "allowed_ids": sorted(allowed) if allowed else "all",
            "spec": spec.model_dump(mode="json", exclude_none=True),
        }
        content = json.dumps(ctx, ensure_ascii=False)[:6000]
        return await self.llm.complete_structured([user(content)], SpecPatch, system=_SYSTEM)

    def get_element_context(self, spec: FigureSpec, element_id: str) -> dict:
        """웹앱 편집 패널용 — 클릭한 요소 정보."""
        node = spec.find(element_id)
        if node is None:
            return {}
        return {"id": element_id, "type": getattr(node, "type", None),
                "label": getattr(node, "label", None) or getattr(node, "text", None)}


def _descendant_ids(node) -> set[str]:
    out: set[str] = set()
    t = getattr(node, "type", None)
    if t in CONTAINER_TYPES:
        for c in node.children:
            out.add(c.id)
            out |= _descendant_ids(c)
    elif t == "free":
        for it in node.items:
            out.add(it.node.id)
            out |= _descendant_ids(it.node)
    return out
