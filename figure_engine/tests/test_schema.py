"""스키마 검증기·순회·패치 테스트."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from figgen.schema import FigureSpec, PatchOp, SpecPatch, apply_patch, validate_patch_scope


def _spec(**over):
    base = {
        "figure_type": "method_diagram",
        "root": {
            "type": "row",
            "id": "root",
            "children": [
                {"type": "box", "id": "a", "label": "A", "role": "process"},
                {"type": "box", "id": "b", "label": "B", "role": "process"},
            ],
        },
        "connectors": [{"id": "c1", "source": "a", "target": "b"}],
    }
    base.update(over)
    return FigureSpec.model_validate(base)


def test_valid_spec_iter_and_find():
    spec = _spec()
    assert spec.element_ids() == ["root", "a", "b"]
    assert spec.find("a").label == "A"
    assert spec.find("nope") is None
    assert spec.max_depth() == 2


def test_duplicate_element_id_rejected():
    with pytest.raises(ValidationError, match="중복 element id"):
        FigureSpec.model_validate(
            {
                "figure_type": "concept",
                "root": {"type": "row", "id": "r", "children": [
                    {"type": "box", "id": "x"}, {"type": "box", "id": "x"}]},
            }
        )


def test_missing_connector_endpoint_rejected():
    with pytest.raises(ValidationError, match="target"):
        FigureSpec.model_validate(
            {
                "figure_type": "concept",
                "root": {"type": "box", "id": "a"},
                "connectors": [{"id": "c", "source": "a", "target": "ghost"}],
            }
        )


def test_depth_limit_rejected():
    # 깊이 7 중첩 → 거부 (최대 6)
    node = {"type": "box", "id": "leaf"}
    for i in range(7):
        node = {"type": "column", "id": f"c{i}", "children": [node]}
    with pytest.raises(ValidationError, match="깊이"):
        FigureSpec.model_validate({"figure_type": "concept", "root": node})


def test_bad_element_id_pattern_rejected():
    with pytest.raises(ValidationError):
        FigureSpec.model_validate(
            {"figure_type": "concept", "root": {"type": "box", "id": "Bad-ID"}}
        )


def test_extra_field_forbidden():
    with pytest.raises(ValidationError):
        FigureSpec.model_validate(
            {"figure_type": "concept", "root": {"type": "box", "id": "a", "bogus": 1}}
        )


# ── 패치 ──────────────────────────────────────────────────────────────────────
def test_patch_set_label():
    spec = _spec()
    patched, errs = apply_patch(
        spec, SpecPatch(ops=[PatchOp(op="set", target_id="a", path="label", value="A2")])
    )
    assert not errs
    assert patched.find("a").label == "A2"
    assert spec.find("a").label == "A"  # 원본 불변


def test_patch_set_nested_path():
    spec = _spec()
    patched, errs = apply_patch(
        spec,
        SpecPatch(ops=[PatchOp(op="set", target_id="a", path="size_hint.width_mm", value=40.0)]),
    )
    assert not errs
    assert patched.find("a").size_hint.width_mm == 40.0


def test_patch_scope_blocks_out_of_scope():
    spec = _spec()
    patch = SpecPatch(ops=[PatchOp(op="set", target_id="b", path="label", value="z")])
    assert validate_patch_scope(patch, {"a"}) == patch.ops  # b는 스코프 밖
    patched, errs = apply_patch(spec, patch, allowed_ids={"a"})
    assert errs and "스코프 밖" in errs[0].message
    assert patched.find("b").label == "B"  # 변경 안 됨


def test_patch_remove_and_revalidate():
    # b 제거 시 c1 커넥터의 target이 사라져 재검증 실패 → op 스킵
    spec = _spec()
    patched, errs = apply_patch(spec, SpecPatch(ops=[PatchOp(op="remove", target_id="b")]))
    assert errs  # 커넥터 무결성 위반으로 거부
    assert patched.find("b") is not None


def test_patch_insert_child():
    spec = _spec()
    new_box = {"type": "box", "id": "cc", "label": "C", "role": "process"}
    patched, errs = apply_patch(
        spec, SpecPatch(ops=[PatchOp(op="insert_child", target_id="cc", parent_id="root", value=new_box)])
    )
    assert not errs
    assert "cc" in patched.element_ids()
