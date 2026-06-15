"""Critic과 부분 재생성이 공유하는 제한된 spec 수정 연산.

전체 재작성을 막아 회귀를 차단한다. 매 op마다 FigureSpec 재검증, 실패 op는 건너뛰고
PatchError 수집(전체 롤백 아님 — 부분 성공 허용). ``allowed_ids`` 지정 시 스코프 밖 op 거부.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ._types import ElementId
from .figure_spec import CONTAINER_TYPES, FigureSpec

PatchOpKind = Literal["set", "remove", "insert_child", "move_child", "replace_element"]
_FREE_ITEM_FIELDS = {"x_frac", "y_frac", "w_frac", "h_frac", "anchor"}


class PatchOp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: PatchOpKind
    target_id: ElementId
    path: str | None = None  # 요소 내부 점 표기 필드 경로 (set 전용), 예 'size_hint.width_mm'
    value: Any | None = None  # JSON 값 또는 Node dict
    parent_id: ElementId | None = None  # insert/move용
    index: int | None = None


class SpecPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ops: list[PatchOp] = Field(default_factory=list)
    reason: str = ""


class PatchError(BaseModel):
    op: PatchOp
    message: str


def validate_patch_scope(patch: SpecPatch, allowed_ids: set[str]) -> list[PatchOp]:
    """스코프(allowed_ids) 밖을 건드리는 op 목록을 반환(거부 대상)."""
    bad: list[PatchOp] = []
    for op in patch.ops:
        ids = {op.target_id}
        if op.parent_id:
            ids.add(op.parent_id)
        if not ids <= allowed_ids:
            bad.append(op)
    return bad


def apply_patch(
    spec: FigureSpec, patch: SpecPatch, *, allowed_ids: set[str] | None = None
) -> tuple[FigureSpec, list[PatchError]]:
    """패치를 적용해 (새 FigureSpec, 오류목록) 반환. 실패 op는 스킵."""
    data = spec.model_dump()
    errors: list[PatchError] = []
    current = spec

    for op in patch.ops:
        if allowed_ids is not None:
            scope = {op.target_id} | ({op.parent_id} if op.parent_id else set())
            if not scope <= allowed_ids:
                errors.append(PatchError(op=op, message=f"스코프 밖: {scope - allowed_ids}"))
                continue
        trial = _deepcopy(data)
        try:
            _apply_op(trial, op)
            current = FigureSpec.model_validate(trial)  # 매 op 재검증
            data = trial  # 성공분만 누적
        except Exception as e:  # noqa: BLE001
            errors.append(PatchError(op=op, message=f"{type(e).__name__}: {str(e)[:160]}"))

    return current, errors


# ── 내부: dict 트리 조작 ──────────────────────────────────────────────────────
def _deepcopy(d: Any) -> Any:
    import copy

    return copy.deepcopy(d)


def _container_list(node: dict) -> list | None:
    if node.get("type") in CONTAINER_TYPES:
        return node.get("children")
    return None


def _find_node(node: dict, target: str) -> dict | None:
    if node.get("id") == target:
        return node
    for child in _iter_child_nodes(node):
        found = _find_node(child, target)
        if found is not None:
            return found
    return None


def _iter_child_nodes(node: dict) -> list[dict]:
    if node.get("type") in CONTAINER_TYPES:
        return list(node.get("children", []))
    if node.get("type") == "free":
        return [it["node"] for it in node.get("items", [])]
    return []


def _find_parent(root: dict, target: str) -> tuple[dict, str, int] | None:
    """(parent_dict, list_key, index) — list_key는 'children' 또는 'items'."""
    if root.get("type") in CONTAINER_TYPES:
        for i, c in enumerate(root.get("children", [])):
            if c.get("id") == target:
                return root, "children", i
    if root.get("type") == "free":
        for i, it in enumerate(root.get("items", [])):
            if it["node"].get("id") == target:
                return root, "items", i
    for child in _iter_child_nodes(root):
        res = _find_parent(child, target)
        if res is not None:
            return res
    return None


def _find_free_item(root: dict, target: str) -> dict | None:
    if root.get("type") == "free":
        for it in root.get("items", []):
            if it["node"].get("id") == target:
                return it
    for child in _iter_child_nodes(root):
        res = _find_free_item(child, target)
        if res is not None:
            return res
    return None


def _apply_op(root: dict, op: PatchOp) -> None:
    if op.op == "set":
        _op_set(root, op)
    elif op.op == "remove":
        _op_remove(root, op)
    elif op.op == "insert_child":
        _op_insert(root, op)
    elif op.op == "move_child":
        _op_move(root, op)
    elif op.op == "replace_element":
        _op_replace(root, op)
    else:  # pragma: no cover
        raise ValueError(f"알 수 없는 op: {op.op}")


def _op_set(root: dict, op: PatchOp) -> None:
    if not op.path:
        raise ValueError("set 은 path 필수")
    parts = op.path.split(".")
    # Free 비율 좌표는 wrapping FreeItem에 위치
    if parts[0] in _FREE_ITEM_FIELDS:
        item = _find_free_item(root["root"], op.target_id)
        if item is None:
            raise ValueError(f"{op.target_id} 는 Free 자식이 아님")
        item[parts[0]] = op.value
        return
    node = _find_node(root["root"], op.target_id)
    if node is None:
        raise ValueError(f"target_id 미존재: {op.target_id}")
    cur = node
    for p in parts[:-1]:
        if cur.get(p) is None:
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = op.value


def _op_remove(root: dict, op: PatchOp) -> None:
    res = _find_parent(root["root"], op.target_id)
    if res is None:
        raise ValueError(f"제거 대상 부모 없음: {op.target_id}")
    parent, key, idx = res
    parent[key].pop(idx)


def _op_insert(root: dict, op: PatchOp) -> None:
    if op.parent_id is None or op.value is None:
        raise ValueError("insert_child 는 parent_id, value 필수")
    parent = _find_node(root["root"], op.parent_id)
    if parent is None or parent.get("type") not in CONTAINER_TYPES:
        raise ValueError(f"insert 대상이 컨테이너가 아님: {op.parent_id}")
    idx = op.index if op.index is not None else len(parent["children"])
    parent.setdefault("children", []).insert(idx, op.value)


def _op_move(root: dict, op: PatchOp) -> None:
    res = _find_parent(root["root"], op.target_id)
    if res is None or op.parent_id is None:
        raise ValueError("move_child 는 기존 부모/대상 parent_id 필요")
    src_parent, key, idx = res
    node = src_parent[key].pop(idx)
    if key == "items":
        node = node  # FreeItem 통째 이동
    dst = _find_node(root["root"], op.parent_id)
    if dst is None or dst.get("type") not in CONTAINER_TYPES:
        raise ValueError(f"move 대상이 컨테이너가 아님: {op.parent_id}")
    target_idx = op.index if op.index is not None else len(dst.get("children", []))
    dst.setdefault("children", []).insert(target_idx, node["node"] if key == "items" else node)


def _op_replace(root: dict, op: PatchOp) -> None:
    if op.value is None:
        raise ValueError("replace_element 는 value(Node) 필수")
    res = _find_parent(root["root"], op.target_id)
    if res is None:
        # 루트 교체
        if root["root"].get("id") == op.target_id:
            root["root"] = op.value
            return
        raise ValueError(f"교체 대상 없음: {op.target_id}")
    parent, key, idx = res
    if key == "items":
        parent["items"][idx]["node"] = op.value
    else:
        parent["children"][idx] = op.value
