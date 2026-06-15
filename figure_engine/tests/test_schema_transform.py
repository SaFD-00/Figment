"""M0 스파이크: 재귀 discriminated-union의 provider별 스키마 변환 검증 (오프라인).

라이브 API 호출 없이 *생성된 스키마 자체의 유효성*을 확인한다. 라이브 성공률 측정은
``scripts/smoke_structured.py``로 분리된다.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from figgen.providers import schema_transform as st


# ── 미니 재귀 FigureSpec (Node가 자기참조 union) ────────────────────────────────
class Leaf(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["leaf"] = "leaf"
    label: str = Field(pattern=r"^[a-z]+$")
    size: float | None = None


class Box(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["box"] = "box"
    children: list[Node]
    gap: float = 4.0


Node = Annotated[Leaf | Box, Field(discriminator="type")]


class MiniSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root: Node
    title: str | None = None


MiniSpec.model_rebuild()
Box.model_rebuild()


# ── 헬퍼: 스키마 트리 전체 순회 ────────────────────────────────────────────────
def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


_SCHEMA_INDICATORS = {"type", "$ref", "anyOf", "oneOf", "enum", "const", "items", "properties"}


def _is_schema_node(d: dict) -> bool:
    """스키마 노드(필드값) 여부 — properties/$defs 컨테이너 dict는 제외."""
    return isinstance(d, dict) and bool(_SCHEMA_INDICATORS & d.keys())


def _schema_nodes(schema):
    return [n for n in _walk(schema) if _is_schema_node(n)]


# ── OpenAI strict ─────────────────────────────────────────────────────────────
def test_openai_strict_all_objects_closed_and_required():
    schema = st.to_openai_strict(MiniSpec)
    objects = [n for n in _walk(schema) if n.get("type") == "object"]
    assert objects, "객체 노드가 있어야 함"
    for obj in objects:
        # 모든 객체는 닫혀 있어야(additionalProperties false)
        assert obj.get("additionalProperties") is False
        # 모든 property가 required에 포함
        props = set(obj.get("properties", {}).keys())
        assert set(obj.get("required", [])) == props


def test_openai_strict_recursion_preserved_via_defs():
    schema = st.to_openai_strict(MiniSpec)
    assert "$defs" in schema, "재귀는 $defs/$ref로 보존되어야 함"
    # Box.children.items는 Node union을 $ref로 참조 → 재귀 유지
    refs = [n["$ref"] for n in _walk(schema) if "$ref" in n]
    assert any("Box" in r or "Leaf" in r for r in refs)


def test_openai_strict_drops_unsupported_keywords():
    schema = st.to_openai_strict(MiniSpec)
    # 스키마 노드(필드값)에서만 검사 — properties 키로 등장하는 동명 필드는 제외
    for node in _schema_nodes(schema):
        for banned in ("pattern", "default", "title", "discriminator", "minItems"):
            assert banned not in node, f"{banned} 가 제거되지 않음: {node}"


def test_openai_strict_const_to_enum():
    schema = st.to_openai_strict(MiniSpec)
    # Literal["leaf"] 등은 enum으로 변환
    assert not any("const" in n for n in _walk(schema))


def test_openai_strict_json_serializable():
    import json

    json.dumps(st.to_openai_strict(MiniSpec))


# ── 공통 ──────────────────────────────────────────────────────────────────────
def test_supports_native_schema():
    # GPT-only: openai만 네이티브 스키마 지원
    assert st.supports_native_schema("openai", MiniSpec) is True
    assert st.supports_native_schema("mock", MiniSpec) is False


def test_json_mode_prompt_mentions_fields():
    prompt = st.build_json_mode_prompt(MiniSpec)
    assert "root" in prompt and "JSON" in prompt
